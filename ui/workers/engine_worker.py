# ui/workers/engine_worker.py
import os, json, time, threading, random, logging, queue, unicodedata
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple, List
from PySide6.QtCore import QThread, Signal, QTimer
import cv2
import numpy as np

from src.autobet.autobet_engine import AutoBetEngine
from src.autobet.chip_profile_manager import ChipProfileManager
from src.autobet.detectors import BeadPlateResultDetector
from src.autobet.phase_detector import PhaseDetector
from src.autobet.lines import (
    LineOrchestrator,
    TablePhase,
    BetDecision,
    load_strategy_definitions,
)

# 桌號映射: canonical_id -> display_name (僅供 UI 顯示)
TABLE_DISPLAY_MAP = {
    "WG7": "BG_131",
    "WG8": "BG_132",
    "WG9": "BG_133",
    "WG10": "BG_135",
    "WG11": "BG_136",
    "WG12": "BG_137",
    "WG13": "BG_138",
    "WG14": "BG_139",
    "WG15": "BG_140",
}

# 反向映射: display_name -> canonical_id (用於標準化)
DISPLAY_TO_CANONICAL_MAP = {v: k for k, v in TABLE_DISPLAY_MAP.items()}

logger = logging.getLogger(__name__)

# --- 簡易事件來源 ---

class DemoFeeder:
    def __init__(self, interval_sec: int, on_event: Callable, seed: Optional[int] = None):
        self.interval = max(2, int(interval_sec))
        self.on_event = on_event
        self._running = False
        self._thread = None
        self._rng = random.Random(seed)

    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        idx = 0
        winners = ["B", "P", "T"]
        while self._running:
            idx += 1
            evt = {
                "type": "RESULT",
                "round_id": f"demo-{int(time.time())}-{idx:03d}",
                "winner": self._rng.choice(winners),
                "ts": int(time.time() * 1000),
            }
            try:
                self.on_event(evt)
            except Exception as e:
                logger.exception("DemoFeeder on_event error: %s", e)
            time.sleep(self.interval)

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running


class NDJSONPlayer:
    def __init__(self, file_path: str, on_event: Callable, interval: float = 1.0):
        self.file_path = file_path
        self.on_event = on_event
        self.interval = interval
        self._running = False
        self._thread = None

    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not self._running:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    evt = json.loads(line)
                    try:
                        self.on_event(evt)
                    except Exception as e:
                        logger.exception("NDJSON on_event error: %s", e)
                    time.sleep(self.interval)
        except Exception as e:
            logger.exception("NDJSONPlayer _run error: %s", e)

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running


# --- 引擎工作執行緒 ---

class EngineWorker(QThread):
    # 重要: 這些 signals 對應 Dashboard 期待的接口
    state_changed = Signal(str)
    session_stats = Signal(dict)
    risk_alert = Signal(str, str)
    log_message = Signal(str, str, str)
    engine_status = Signal(dict)
    next_bet_info = Signal(dict)  # 即時下注詳情更新

    def __init__(self):
        super().__init__()
        self.engine = None
        self.event_feeder = None
        self._enabled = False
        self._dry_run = True
        self._tick_running = False
        self._round_count = 0
        self._net_profit = 0
        self._last_winner = None
        self._incoming_events: "queue.Queue[Dict]" = queue.Queue()

        # BeadPlateResultDetector 相關狀態
        self._result_detector: Optional[BeadPlateResultDetector] = None
        self._detection_timer: Optional[QTimer] = None
        self._detection_enabled = False

        # PhaseDetector 相關狀態
        self._phase_detector: Optional[PhaseDetector] = None

        self._latest_results: Dict[str, Dict[str, Any]] = {}
        self._line_orchestrator: Optional[LineOrchestrator] = None
        self._line_order_queue: "queue.Queue[BetDecision]" = queue.Queue()
        self._line_summary: Dict[str, Any] = {}
        self._selected_table: Optional[str] = None  # 使用者選擇的桌號
        base_dir = Path("data/sessions")
        base_dir.mkdir(parents=True, exist_ok=True)
        self._line_state_path = base_dir / "line_state.json"
        self._line_orders_path = base_dir / "line_orders.ndjson"

        # ChipProfile 管理器
        self._chip_profile_manager = ChipProfileManager()

    def initialize_engine(self, dry_run: bool = True) -> bool:
        """初始化引擎並載入配置"""
        try:
            # 載入 ChipProfile
            chip_profile = None
            try:
                chip_profile = self._chip_profile_manager.load_profile("default")
                self._emit_log("INFO", "Engine", f"✅ ChipProfile 載入成功: {chip_profile.profile_name}")
            except Exception as e:
                self._emit_log("WARNING", "Engine", f"⚠️ ChipProfile 載入失敗: {e}，將使用舊系統")

            # 初始化引擎，傳入 ChipProfile
            self.engine = AutoBetEngine(dry_run=dry_run, chip_profile=chip_profile)
            self.engine.set_log_callback(self._emit_log)  # 設置日誌回調
            self._dry_run = dry_run
            self._emit_log("INFO", "Engine", "引擎已初始化")

            # 立即載入配置，讓檢測器可以工作
            if self._load_real_configs():
                self._emit_log("INFO", "Engine", "✅ 配置載入成功，檢測器已準備就緒")
                # 配置載入成功，但保持待機狀態 (不自動啟用檢測)
                # self._enabled 保持 False，等待用戶手動啟動
            else:
                self._emit_log("WARNING", "Engine", "⚠️ 配置載入失敗，檢測器未就緒")

            # 開始狀態輪詢
            self._tick_running = True
            self._init_line_orchestrator()

            # 初始化 PhaseDetector（階段檢測器）
            self._setup_phase_detector()

            # 初始化 ResultDetector（但不啟動檢測）
            self._setup_result_detector()

            # 發送初始狀態
            self.state_changed.emit("idle")

            return True

        except Exception as e:
            self._emit_log("ERROR", "Engine", f"初始化失敗: {e}")
            return False

    def run(self):
        """QThread.run() - 狀態監控迴圈"""
        self._emit_log("INFO", "Thread", f"EngineWorker.run() 開始執行，_tick_running={getattr(self, '_tick_running', None)}")

        # 等待初始化完成（等待 _tick_running 變為 True）
        while not getattr(self, '_tick_running', False):
            self.msleep(50)

        self._emit_log("INFO", "Thread", f"EngineWorker 初始化完成，開始主迴圈")

        while self._tick_running:
            try:
                # 處理外部結果事件
                self._drain_incoming_events()

                # 始終發送狀態更新，不管引擎是否啟用
                current_state = "running" if self._enabled else "idle"
                self.state_changed.emit(current_state)

                # 狀態日誌 (僅在啟動時顯示一次)
                if not hasattr(self, '_initial_status_logged'):
                    self._emit_log("INFO", "Status", f"EngineWorker狀態: enabled={self._enabled}, engine={bool(self.engine)}")
                    self._initial_status_logged = True

                # 模擬統計數據
                self.session_stats.emit({
                    "rounds": getattr(self, '_round_count', 0),
                    "net": getattr(self, '_net_profit', 0),
                    "last_winner": getattr(self, '_last_winner', None),
                    "enabled": self._enabled,
                    "dry_run": self._dry_run,
                })

                # 檢測邏輯已移至 Dashboard，EngineWorker 只負責引擎狀態管理
                # 不再在此處執行檢測，避免與 Dashboard 重複檢測

                # 發送引擎狀態
                status = {
                    "current_state": current_state,
                    "enabled": self._enabled,
                    "dry_run": self._dry_run,
                    "rounds": getattr(self, '_round_count', 0),
                    "net": getattr(self, '_net_profit', 0),
                    "last_winner": getattr(self, '_last_winner', None),
                    "detection_enabled": self._detection_enabled,
                    "latest_results": self._latest_results_snapshot(),
                    "line_summary": self._line_summary,
                }
                self.engine_status.emit(status)

            except Exception as e:
                self._emit_log("ERROR", "Status", f"狀態檢查錯誤: {e}")

            # 固定頻率，簡化邏輯
            self.msleep(1000)  # 1秒，只需定期發送狀態更新

    def get_all_history_results(self) -> list:
        """獲取所有歷史開獎結果（從 SignalTracker）"""
        results = []
        if not self._line_orchestrator:
            return results

        try:
            # 從所有 SignalTracker 收集歷史
            for strategy_key, tracker in self._line_orchestrator.signal_trackers.items():
                for table_id, history_deque in tracker.history.items():
                    for winner, timestamp in history_deque:
                        results.append({
                            "winner": winner,
                            "timestamp": timestamp,
                            "round_id": f"{table_id}-{int(timestamp)}",
                            "table_id": table_id
                        })

            # 按時間排序
            results.sort(key=lambda x: x["timestamp"])

        except Exception as e:
            self._emit_log("ERROR", "Engine", f"獲取歷史結果失敗: {e}")

        return results

    def start_engine(self, mode: str = "simulation", **kwargs) -> bool:
        """啟動引擎
        Args:
            mode: "simulation" (模擬模式) 或 "real" (實戰模式)
        """
        if not self.engine:
            self._emit_log("ERROR", "Engine", "引擎未初始化")
            return False

        try:
            # 檢查是否需要重新載入配置（如果已經載入過就跳過）
            if not hasattr(self.engine, 'overlay') or not self.engine.overlay:
                if not self._load_real_configs():
                    return False
            else:
                self._emit_log("INFO", "Engine", "配置已載入，跳過重複載入")

            # 設定模式
            self._is_simulation = (mode == "simulation")
            self.set_dry_run(self._is_simulation)

            # 啟動引擎讓它檢測 overlay
            if self.engine:
                try:
                    self.engine.set_enabled(True)
                except AttributeError:
                    pass

            self._enabled = True

            # 啟動結果檢測
            if self._result_detector:
                self._start_result_detection()
                self._emit_log("INFO", "Engine", "✅ 結果檢測已啟動")
            else:
                self._emit_log("WARNING", "Engine", "⚠️ ResultDetector 未初始化")

            mode_text = "模擬" if self._is_simulation else "實戰"
            self._emit_log("INFO", "Engine", f"{mode_text}模式已啟動 - 開始檢測遊戲畫面")

            # 立即發送狀態更新
            self.state_changed.emit("running")

            return True

        except Exception as e:
            self._emit_log("ERROR", "Engine", f"啟動失敗: {e}")
            return False

    def _load_real_configs(self) -> bool:
        """載入真實的配置檔案"""
        try:
            # 載入 UI 配置 (空字典，使用預設值)
            self.engine.load_ui_config({})
            self._emit_log("INFO", "Config", "✅ UI 配置載入完成（使用預設值）")

            # 載入 positions.json
            if os.path.exists("configs/positions.json"):
                success = self.engine.load_positions("configs/positions.json")
                if not success:
                    self._emit_log("ERROR", "Config", "載入 positions.json 失敗")
                    return False
                self._emit_log("INFO", "Config", "✅ positions.json 載入成功")
            else:
                self._emit_log("ERROR", "Config", "未找到 configs/positions.json")
                return False

            # 載入線路策略 (新系統)
            strategy_dir = "configs/line_strategies"
            if os.path.exists(strategy_dir):
                strategy_files = [f for f in os.listdir(strategy_dir) if f.endswith('.json')]
                if strategy_files:
                    self._emit_log("INFO", "Config", f"✅ 找到 {len(strategy_files)} 個線路策略")
                else:
                    self._emit_log("ERROR", "Config", "未找到任何線路策略，請先在「策略設定」頁面創建策略")
                    return False
            else:
                self._emit_log("ERROR", "Config", "未找到 configs/line_strategies 目錄")
                return False

            # 初始化引擎組件 (detector, actuator 等)
            success = self.engine.initialize_components()
            if not success:
                self._emit_log("ERROR", "Engine", "引擎組件初始化失敗")
                return False

            self._emit_log("INFO", "Engine", "✅ 引擎組件初始化成功")

            # 檢查 overlay 是否正確初始化
            if hasattr(self.engine, 'overlay') and self.engine.overlay:
                self._emit_log("INFO", "Config", "✅ Overlay 檢測器已初始化")
            else:
                self._emit_log("WARNING", "Config", "⚠️ Overlay 檢測器初始化失敗")

            return True

        except Exception as e:
            self._emit_log("ERROR", "Config", f"載入配置失敗: {e}")
            return False

    def stop_engine(self):
        self._enabled = False
        # 停止結果檢測
        if self._detection_timer:
            self._detection_timer.stop()
            self._detection_enabled = False
            self._emit_log("INFO", "Engine", "結果檢測已停止")

        if self.engine:
            try:
                self.engine.set_enabled(False)
            except AttributeError:
                pass  # 引擎可能沒有 set_enabled 方法
        if self.event_feeder:
            try:
                self.event_feeder.stop()
            except Exception:
                pass
            self.event_feeder = None

        self._emit_log("INFO", "Engine", "引擎已停止")

        # 立即發送狀態更新
        self.state_changed.emit("idle")

    def set_dry_run(self, dry: bool):
        self._dry_run = dry
        if self.engine:
            try:
                # 嘗試設定乾跑模式，但不強制要求引擎有這個方法
                if hasattr(self.engine, 'set_dry_run'):
                    self.engine.set_dry_run(dry)
                elif hasattr(self.engine, 'dry'):
                    self.engine.dry = dry
            except Exception:
                pass
        self._emit_log("INFO", "Engine", f"切換模式 → {'乾跑' if dry else '實戰'}")

    def _handle_event(self, event):
        """處理事件並更新統計"""
        try:
            event_type = event.get("type", "UNKNOWN")
            winner = event.get("winner", "N/A")
            table_id = event.get("table_id")
            round_id = event.get("round_id")

            # 調試：記錄每個事件的類型
            self._emit_log(
                "DEBUG",
                "Engine",
                f"_handle_event 收到事件: type={event_type}, table={table_id}, round={round_id}, winner={winner}"
            )

            if event_type == "RESULT":
                # 只處理選定桌號的事件（使用 mapping）
                if not self._is_selected_table(table_id):
                    return  # 靜默忽略非選定桌號

                self._emit_log("DEBUG", "Engine", f"🎲 處理 RESULT: table={table_id} round={round_id} winner={winner}")

                # 🔍 診斷：檢查 Line orchestrator 條件
                has_orchestrator = self._line_orchestrator is not None
                has_table = table_id is not None
                has_round = round_id is not None
                self._emit_log("INFO", "Engine", f"🔍 Line 條件檢查: orchestrator={has_orchestrator}, table={has_table} ({table_id}), round={has_round} ({round_id}), winner={winner}")

                if self._line_orchestrator and table_id and round_id:
                    ts_raw = event.get("received_at")
                    if isinstance(ts_raw, (int, float)):
                        ts_sec = float(ts_raw) / 1000.0 if ts_raw > 1e6 else float(ts_raw)
                    else:
                        ts_sec = time.time()

                    self._emit_log("DEBUG", "Engine", f"📞 調用 handle_result: table={table_id} winner={winner}")
                    self._line_orchestrator.handle_result(table_id, round_id, winner, ts_sec)
                    self._line_summary = self._line_orchestrator.snapshot()
                    self._save_line_state()
                    self._flush_line_events()

                    # 階段檢測現在由 PhaseDetector 自動處理
                    # PhaseDetector 會在 SETTLING → BETTABLE → LOCKED 的適當時機
                    # 通過 phase_changed 信號觸發 _on_phase_changed()
                else:
                    self._emit_log("WARNING", "Engine", f"⚠️ 跳過 Line 處理: orchestrator={has_orchestrator}, table={has_table}, round={has_round}")

                self._round_count += 1
                self._last_winner = winner
                self._store_latest_result(event)

                # 模擬投注結果（這裡只是示例）
                if winner in ["B", "P"]:
                    # 模擬盈虧（隨機）
                    import random
                    profit = random.randint(-100, 150)
                    self._net_profit += profit

                result_text_map = {"B": "莊", "P": "閒", "T": "和"}
                result_text = result_text_map.get(winner, winner)
                details = []
                if round_id:
                    details.append(f"round={round_id}")
                details_str = f" ({', '.join(details)})" if details else ""
                message = f"結果：{result_text}{details_str}"

                # 調試：在發送 Events 日誌前後加標記
                self._emit_log("DEBUG", "Engine", f"📤 準備發送 Events 日誌: table={table_id} round={round_id} winner={winner}")
                self._emit_table_log("INFO", table_id, message, module="Events")
                self._emit_log("DEBUG", "Engine", f"✅ Events 日誌已發送")

                # 如果有真正的引擎，也發送給它
                if self.engine:
                    try:
                        self.engine.on_event(event)
                    except Exception as e:
                        self._emit_log("WARNING", "Engine", f"引擎處理事件錯誤: {e}")

        except Exception as e:
            import traceback
            self._emit_log("ERROR", "Events", f"事件處理錯誤: {e}")
            self._emit_log("ERROR", "Events", f"堆棧追蹤: {traceback.format_exc()}")



    def _store_latest_result(self, event: Dict[str, Any]) -> None:
        """儲存最新結果（內部統一使用 canonical ID）"""
        table_id = event.get("table_id")
        if not table_id:
            return

        # 使用 canonical ID 作為唯一 key
        canonical_id = self._normalize_table_id(table_id)
        if not canonical_id:
            return
        round_id = event.get("round_id")
        round_str = str(round_id) if round_id is not None else None

        info: Dict[str, Any] = {
            "table_id": canonical_id,  # 統一使用 canonical ID
            "display_table_id": self._map_table_display(canonical_id),
            "round_id": round_str,
            "winner": event.get("winner"),
            "received_at": event.get("received_at") or int(time.time() * 1000),
        }

        raw = event.get("raw")
        if isinstance(raw, dict):
            game_result = raw.get("gameResult")
            if isinstance(game_result, dict):
                info["result_code"] = game_result.get("result")
                if game_result.get("win_lose_result"):
                    info["win_lose_result"] = game_result.get("win_lose_result")
            elif game_result:
                info["game_result"] = game_result
            if raw.get("win_lose_result"):
                info["win_lose_result"] = raw.get("win_lose_result")

        # 將最新資料移到字典尾端維持近序（只用 canonical ID）
        self._latest_results.pop(canonical_id, None)
        self._latest_results[canonical_id] = info

        # 限制最多保留 20 個桌號
        max_tables = 20
        while len(self._latest_results) > max_tables:
            first_key = next(iter(self._latest_results))
            if first_key == canonical_id and len(self._latest_results) == 1:
                break
            self._latest_results.pop(first_key, None)

    def _latest_results_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {k: v.copy() for k, v in self._latest_results.items()}

    def _push_status_immediately(self):
        """立即推送狀態到UI（不等200ms迴圈）"""
        current_state = "running" if self._enabled else "idle"
        status = {
            "current_state": current_state,
            "enabled": self._enabled,
            "dry_run": self._dry_run,
            "rounds": getattr(self, '_round_count', 0),
            "net": getattr(self, '_net_profit', 0),
            "last_winner": getattr(self, '_last_winner', None),
            "detection_enabled": self._detection_enabled,
            "latest_results": self._latest_results_snapshot(),
        }
        self.engine_status.emit(status)

    def _emit_log(self, level: str, module: str, msg: str):
        # 調試：對 Result 和 Events 模組的日誌加上堆棧追蹤
        if module in ["Result", "Events"] and "結果：" in msg:
            import traceback
            stack_lines = traceback.format_stack()
            # 取最後5層調用，跳過當前函數
            relevant_stack = stack_lines[-6:-1]
            caller_summary = " -> ".join([
                line.split(",")[0].split('"')[-2].split("/")[-1].split("\\")[-1] + ":" + line.split(",")[1].strip().split()[1]
                for line in relevant_stack if "File" in line
            ])
            self.log_message.emit("DEBUG", "StackFull", f"📞 {module} 完整調用鏈: {caller_summary}")

        self.log_message.emit(level, module, msg)

    # _trigger_engine_execution 方法已移除
    # 觸發邏輯現在由 Dashboard 直接處理

    # ------------------------------------------------------------------
    def _normalize_table_id(self, table_id: Optional[str]) -> Optional[str]:
        """將桌號標準化為 canonical ID

        Args:
            table_id: 可能是 display name (BG_131) 或 canonical ID (WG7)

        Returns:
            canonical ID (標準化的桌號)
        """
        if table_id is None:
            return None

        table_id_str = str(table_id).strip()
        if not table_id_str:
            return None

        # 如果是 display name (BG_131-140)，轉換為 canonical ID
        canonical = DISPLAY_TO_CANONICAL_MAP.get(table_id_str)
        if canonical:
            return canonical

        # 已經是 canonical ID (BG125-130, WG7-15) 或未知格式，直接返回
        return table_id_str

    def _map_table_display(self, table_id: Optional[str]) -> Optional[str]:
        """將 canonical ID 映射為 display name（僅供 UI 顯示）"""
        if not table_id:
            return None
        table_str = str(table_id).strip()
        if not table_str:
            return None
        return TABLE_DISPLAY_MAP.get(table_str, table_str)

    def _is_selected_table(self, table_id: Optional[str]) -> bool:
        """檢查桌號是否為選定桌號（內部統一使用 canonical ID）

        注意：
        - _selected_table 已在 set_selected_table() 中標準化為 canonical ID
        - table_id 是事件中的桌號（已是 canonical ID）
        - 因此只需直接比對即可
        """
        if not self._selected_table:
            return True  # 未選擇桌號時，接受所有事件

        if not table_id:
            return False

        # 直接比對 canonical ID
        normalized = self._normalize_table_id(table_id)
        if not normalized:
            return False
        return str(normalized).strip() == str(self._selected_table).strip()

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_text(value: Optional[Any]) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8", errors="replace")
            except Exception:
                value = value.decode(errors="ignore")
        text = str(value).strip()
        if not text:
            return ""
        try:
            return unicodedata.normalize("NFKC", text)
        except Exception:
            return text

    # ------------------------------------------------------------------
    def _emit_table_log(self, level: str, table_id: Optional[str], message: str, module: str = "Result") -> None:
        # 只處理選定桌號的日誌（使用 mapping）
        canonical_id = self._normalize_table_id(table_id) if table_id else None
        if not self._is_selected_table(canonical_id):
            return

        # 過濾不必要的狀態訊息（停止下注、投注中等）
        skip_messages = ["狀態：停止下注", "狀態：投注中", "狀態：派彩中", "狀態：局已結束", "狀態：开奖中"]
        if any(skip in message for skip in skip_messages):
            return

        # 調試：記錄堆棧追蹤（僅針對 Result 和 Events 模組）
        if module in ["Result", "Events"] and "結果：" in message:
            import traceback
            stack = traceback.format_stack()
            # 只取最後3層調用
            caller_info = " <- ".join([
                line.strip().split("\n")[0].replace("  File ", "")
                for line in stack[-4:-1]
            ])
            self._emit_log("DEBUG", "Stack", f"📞 {module} 日誌調用路徑: {caller_info}")

        prefix = ""
        if canonical_id:
            display = self._map_table_display(canonical_id)
            prefix_parts = [f"[table={canonical_id}]"]
            if display and display != canonical_id:
                prefix_parts.append(f"[display={display}]")
            prefix = "".join(prefix_parts) + " "
        self._emit_log(level, module, f"{prefix}{message}")

    def force_test_sequence(self):
        """強制測試點擊順序"""
        if not self.engine:
            self._emit_log("ERROR", "Test", "引擎未初始化")
            return

        def _run():
            try:
                self.engine.force_execute_sequence()
                self._emit_log("INFO", "Test", "強制執行點擊順序完成")
            except Exception as e:
                self._emit_log("ERROR", "Test", f"強制執行失敗: {e}")

        threading.Thread(target=_run, name="ForceTestSequence", daemon=True).start()

    def trigger_click_sequence_async(self):
        """在背景執行點擊序列，避免阻塞 UI 線程"""
        if not self.engine:
            self._emit_log("ERROR", "Engine", "引擎未初始化")
            return

        def _run():
            self._emit_log("INFO", "Engine", "✅ 開始執行點擊序列")
            try:
                triggered = self.engine.trigger_if_open()
                if not triggered:
                    self._emit_log("WARNING", "Engine", "⚠️ 點擊序列執行失敗")
            except Exception as e:
                self._emit_log("ERROR", "Engine", f"觸發點擊序列錯誤: {e}")

        threading.Thread(target=_run, name="TriggerClickSequence", daemon=True).start()

    def set_selected_table(self, table_id: str):
        """
        設定選定的桌號（單桌模式）

        注意：系統運行於單桌模式，所有事件固定分配到 table_id = "main"
        此方法保留接口以便未來擴展，但當前強制設為 "main"

        Args:
            table_id: 桌號（當前忽略，固定使用 "main"）
        """
        # 單桌模式：固定為 "main"，忽略傳入的 table_id
        _ = table_id  # 保留參數以便未來擴展
        self._selected_table = "main"
        self._emit_log("INFO", "Strategy", f"🎯 單桌模式：追蹤桌號 main")

    def quit(self):
        self._tick_running = False
        self.stop_engine()
        super().quit()

    # ------------------------------------------------------------------
    def _init_line_orchestrator(self) -> None:
        """
        初始化 Line 策略系統（單桌模式）

        環境變數配置：
        - LINE_STRATEGY_DIR: 策略目錄 (預設: configs/line_strategies)

        注意：
        - 系統只追蹤 PnL 和止盈止損，不做資金檢查
        - 止盈止損配置在各策略的 risk.levels 中設定
        - table_id 固定為 "main"（單桌模式）
        """
        strategy_dir_env = os.getenv("LINE_STRATEGY_DIR", "configs/line_strategies")
        strategy_dir = Path(strategy_dir_env)

        try:
            # ✅ 不再需要 bankroll 相關參數
            self._line_orchestrator = LineOrchestrator()

            if strategy_dir.exists():
                definitions = load_strategy_definitions(strategy_dir)
                for definition in definitions.values():
                    self._line_orchestrator.register_strategy(definition)
                self._emit_log("INFO", "Strategy", f"✅ 載入 {len(definitions)} 條策略")
            else:
                self._emit_log(
                    "WARNING",
                    "Line",
                    f"找不到 Line 策略目錄: {strategy_dir}",
                )

            self._load_line_state()
            if self._line_orchestrator:
                self._line_summary = self._line_orchestrator.snapshot()
                self._save_line_state()
            else:
                self._line_summary = {}
        except Exception as exc:
            self._line_orchestrator = None
            self._emit_log("ERROR", "Strategy", f"❌ 策略系統初始化失敗: {exc}")

    # ------------------------------------------------------------------
    def _load_line_state(self) -> None:
        if not self._line_orchestrator or not self._line_state_path.exists():
            return
        try:
            data = json.loads(self._line_state_path.read_text(encoding="utf-8"))
            self._line_orchestrator.restore_state(data)
            self._line_summary = self._line_orchestrator.snapshot()
        except Exception as exc:
            self._emit_log("ERROR", "Strategy", f"❌ 恢復策略狀態失敗: {exc}")

    def _save_line_state(self) -> None:
        if not self._line_orchestrator:
            return
        try:
            payload = self._line_orchestrator.snapshot()
            payload["saved_at"] = int(time.time())
            self._line_state_path.parent.mkdir(parents=True, exist_ok=True)
            self._line_state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            self._emit_log("ERROR", "Line", f"寫入 Line 狀態失敗: {exc}")

    # ------------------------------------------------------------------
    # PhaseDetector 相關方法
    # ------------------------------------------------------------------

    def _setup_phase_detector(self) -> None:
        """初始化 PhaseDetector（階段檢測器）"""
        try:
            # 創建 PhaseDetector 實例
            self._phase_detector = PhaseDetector(parent=self)

            # 連接階段變化信號到處理函數
            self._phase_detector.phase_changed.connect(self._on_phase_changed)

            self._emit_log("INFO", "PhaseDetector", "✅ 階段檢測器初始化完成")

        except Exception as e:
            self._emit_log("ERROR", "PhaseDetector", f"初始化失敗: {e}")
            self._phase_detector = None

    def _on_phase_changed(self, table_id: str, round_id: str, phase: str, timestamp: float) -> None:
        """
        處理 PhaseDetector 發送的階段變化事件

        Args:
            table_id: 桌號
            round_id: 局號
            phase: 階段名稱 (bettable/locked)
            timestamp: 時間戳
        """
        try:
            if not self._line_orchestrator:
                return

            # 轉換為 TablePhase 枚舉
            try:
                table_phase = TablePhase(phase)
            except ValueError:
                self._emit_log("WARNING", "PhaseDetector", f"未知的階段: {phase}")
                return

            self._emit_log("DEBUG", "PhaseDetector",
                          f"階段變化: table={table_id} round={round_id} phase={phase}")

            # 通知 LineOrchestrator 階段變化，並接收決策
            decisions = self._line_orchestrator.update_table_phase(
                table_id, round_id, table_phase, timestamp
            )

            # 如果有決策產生，執行下注
            if decisions:
                self._emit_log("INFO", "PhaseDetector",
                              f"✅ 階段 {phase} 觸發 {len(decisions)} 個下注決策")
                self._handle_line_decisions(decisions)

            # 更新狀態
            self._line_summary = self._line_orchestrator.snapshot()
            self._save_line_state()
            self._flush_line_events()

        except Exception as e:
            self._emit_log("ERROR", "PhaseDetector", f"處理階段變化錯誤: {e}")
            import traceback
            self._emit_log("ERROR", "PhaseDetector", traceback.format_exc())

    # ------------------------------------------------------------------
    # ResultDetector 相關方法
    # ------------------------------------------------------------------

    def _setup_result_detector(self) -> None:
        """初始化 BeadPlateResultDetector (珠盤檢測器)"""
        try:
            # 從配置檔載入設定
            config_path = Path("configs/bead_plate_detection.json")
            if not config_path.exists():
                self._emit_log("WARNING", "BeadPlate", "未找到 bead_plate_detection.json，使用預設配置")
                config = {}
            else:
                with open(config_path, 'r', encoding='utf-8') as f:
                    full_config = json.load(f)
                    config = full_config.get("detection_config", {})

            # 建立 BeadPlateResultDetector
            self._result_detector = BeadPlateResultDetector(config)

            # 載入 ROI
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    full_config = json.load(f)

                # 設定珠盤 ROI
                roi_config = full_config.get("bead_plate_roi", {})
                if roi_config and all(k in roi_config for k in ["x", "y", "w", "h"]):
                    self._result_detector.set_bead_plate_roi(
                        x=roi_config["x"],
                        y=roi_config["y"],
                        w=roi_config["w"],
                        h=roi_config["h"]
                    )
                    self._emit_log("INFO", "BeadPlate", "✅ 珠盤 ROI 配置載入成功")
                else:
                    self._emit_log("WARNING", "BeadPlate", "未配置珠盤 ROI")

                # 健康檢查
                ok, msg = self._result_detector.health_check()
                if ok:
                    self._emit_log("INFO", "BeadPlate", f"✅ 健康檢查通過: {msg}")
                else:
                    self._emit_log("WARNING", "BeadPlate", f"⚠️ 健康檢查失敗: {msg}")
            else:
                self._emit_log("WARNING", "BeadPlate", "未配置珠盤 ROI，請先進行配置")

        except Exception as e:
            self._emit_log("ERROR", "BeadPlate", f"初始化失敗: {e}")
            self._result_detector = None

    def _load_initial_beads(self) -> None:
        """載入珠盤上已有的歷史珠子"""
        if not self._result_detector:
            self._emit_log("ERROR", "InitialBeads", "檢測器未初始化")
            return

        try:
            self._emit_log("INFO", "InitialBeads", "開始檢測珠盤上已有的珠子...")

            # 截取當前螢幕
            import mss
            import numpy as np
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                img = np.array(screenshot)

                self._emit_log("DEBUG", "InitialBeads", f"截圖尺寸: {img.shape}")

                # 轉換為 BGR (OpenCV 格式)
                if img.shape[2] == 4:  # BGRA
                    img = img[:, :, :3]  # 去掉 alpha 通道
                img = img[:, :, ::-1]  # RGB -> BGR

                # 檢查 ROI 配置
                if self._result_detector.roi:
                    roi = self._result_detector.roi
                    self._emit_log("DEBUG", "InitialBeads",
                                 f"珠盤 ROI: x={roi['x']}, y={roi['y']}, w={roi['w']}, h={roi['h']}")
                else:
                    self._emit_log("WARNING", "InitialBeads", "珠盤 ROI 未設置")

                # 呼叫檢測器的 detect_initial_beads 方法
                initial_beads = self._result_detector.detect_initial_beads(img)

                if initial_beads:
                    self._emit_log("INFO", "InitialBeads", f"檢測到 {len(initial_beads)} 顆歷史珠子")

                    # 將每個珠子作為檢測結果發送給策略追蹤器
                    for i, bead in enumerate(initial_beads):
                        winner = bead["winner"]
                        timestamp = bead["timestamp"]

                        # 生成唯一的 round_id (使用序號確保每個珠子有不同的 ID)
                        round_id = f"initial-{int(timestamp * 1000)}-{i}"

                        # 發送給 SignalTracker
                        if self._line_orchestrator:
                            for _, tracker in self._line_orchestrator.signal_trackers.items():
                                tracker.record("main", winner, timestamp)

                        # 發送狀態更新 (讓 Dashboard 顯示)
                        result_info = {
                            "winner": winner,
                            "received_at": timestamp,
                            "round_id": round_id,
                            "table_id": "main",
                            "source": "initial_bead"
                        }

                        self.status_updated.emit({
                            "main": result_info,
                            "lines": self._get_line_status(),
                            "timestamp": time.time()
                        })

                        winner_map = {"B": "莊", "P": "閒", "T": "和"}
                        self._emit_log("DEBUG", "InitialBeads",
                                     f"載入珠子 #{i+1}: {winner_map.get(winner, winner)}")

                    self._emit_log("INFO", "InitialBeads",
                                 f"✅ 成功載入 {len(initial_beads)} 顆歷史珠子到策略追蹤器")
                else:
                    self._emit_log("INFO", "InitialBeads", "珠盤上沒有檢測到歷史珠子（可能是空盤）")

        except Exception as e:
            self._emit_log("ERROR", "InitialBeads", f"載入歷史珠子失敗: {e}")
            import traceback
            self._emit_log("ERROR", "InitialBeads", traceback.format_exc())

    def _start_result_detection(self) -> None:
        """啟動結果檢測循環"""
        if not self._result_detector:
            self._emit_log("ERROR", "ResultDetector", "檢測器未初始化")
            return

        # 注意：初始珠子檢測功能已暫時停用
        # 原因：珠盤格子（垂直長條）與開獎結果珠子（圓形）形狀差異太大
        # 無法用同一套參數同時檢測兩者
        # self._load_initial_beads()

        # 建立 QTimer（必須在 QThread 內部建立）
        self._detection_timer = QTimer()
        self._detection_timer.timeout.connect(self._on_detection_tick)
        self._detection_timer.start(200)  # 每 200ms 檢測一次
        self._detection_enabled = True
        self._emit_log("INFO", "ResultDetector", "檢測循環已啟動 (200ms)")
        self._emit_log("INFO", "ResultDetector", "💡 啟動後將從新結果開始記錄")

    def _on_detection_tick(self) -> None:
        """檢測循環回調"""
        if not self._detection_enabled or not self._result_detector:
            return

        try:
            # 截取螢幕
            import mss
            with mss.mss() as sct:
                # 截取主螢幕
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                # 轉換為 numpy array
                img = np.array(screenshot)
                # 轉換顏色 BGRA -> BGR
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

            # 執行檢測
            result = self._result_detector.process_frame(img)

            # 如果檢測到結果（只在 state=detected 時才發送事件）
            if result.winner and result.state == "detected":
                winner_map = {"B": "莊", "P": "閒", "T": "和"}
                winner_text = winner_map.get(result.winner, result.winner)

                # 使用檢測時間的毫秒級時間戳作為 round_id（確保唯一性）
                round_id = f"detect-{int(result.detected_at * 1000)}"

                # 產生事件
                event = {
                    "type": "RESULT",
                    "winner": result.winner,
                    "source": "image_detection",
                    "confidence": result.confidence,
                    "received_at": int(result.detected_at * 1000),
                    "table_id": self._selected_table or "main",  # 單桌模式
                    "round_id": round_id
                }

                self._incoming_events.put(event)
                self._emit_log(
                    "INFO",
                    "ResultDetector",
                    f"✅ 檢測到結果: {winner_text} (信心: {result.confidence:.3f})"
                )

                # 通知 PhaseDetector 開始階段轉換循環
                if self._phase_detector:
                    table_id = self._selected_table or "main"
                    self._phase_detector.on_result_detected(table_id, round_id, result.winner)
                    self._emit_log("DEBUG", "PhaseDetector",
                                  f"已通知 PhaseDetector 開始階段循環: {round_id}")
                else:
                    self._emit_log("WARNING", "PhaseDetector", "PhaseDetector 未初始化")

        except Exception as e:
            self._emit_log("ERROR", "ResultDetector", f"檢測錯誤: {e}")

    # ------------------------------------------------------------------
    def _drain_incoming_events(self) -> None:
        processed = 0
        while True:
            try:
                evt = self._incoming_events.get_nowait()
            except queue.Empty:
                break
            else:
                processed += 1
                self._handle_event(evt)
        self._drain_line_orders_queue()

    # ------------------------------------------------------------------
    def _process_line_state(self, info: Dict[str, Any]) -> None:
        if not self._line_orchestrator:
            self._emit_log("ERROR", "Line", "❌ _line_orchestrator 是 None，無法處理 Line 狀態！")
            return
        table_id = info.get("table_id")
        if not table_id:
            return

        # 只處理選定桌號的階段事件（使用 mapping）
        if not self._is_selected_table(table_id):
            return  # 靜默忽略非選定桌號

        stage = info.get("stage")
        phase = self._map_stage_to_phase(stage)
        round_id = info.get("round_id")
        ts_raw = info.get("received_at")
        if isinstance(ts_raw, (int, float)):
            timestamp = float(ts_raw) / 1000.0 if ts_raw > 1e6 else float(ts_raw)
        else:
            timestamp = time.time()

        if phase:
            decisions = self._line_orchestrator.update_table_phase(table_id, round_id, phase, timestamp)
            if decisions:
                self._handle_line_decisions(decisions)
        if self._line_orchestrator:
            self._line_summary = self._line_orchestrator.snapshot()
            self._save_line_state()
        self._flush_line_events()

    # ------------------------------------------------------------------
    def _map_stage_to_phase(self, stage: Optional[str]) -> Optional[TablePhase]:
        if not stage:
            return None
        mapping = {
            "idle": TablePhase.IDLE,
            "open": TablePhase.OPEN,
            "betting": TablePhase.BETTABLE,
            "closing": TablePhase.LOCKED,
            "dealing": TablePhase.RESULTING,
            "payout": TablePhase.RESULTING,
            "result": TablePhase.RESULTING,
            "finished": TablePhase.SETTLED,
            "cancelled": TablePhase.SETTLED,
        }
        return mapping.get(stage)

    # ------------------------------------------------------------------
    def _handle_line_decisions(self, decisions: List[BetDecision]) -> None:
        for decision in decisions:
            self._line_order_queue.put(decision)
            self._emit_log(
                "INFO",
                "Line",
                f"Line {decision.strategy_key} -> table {decision.table_id} round={decision.round_id} direction={decision.direction.value} amount={decision.amount} layer={decision.layer_index}",
            )
            self._persist_line_order(decision)

    # ------------------------------------------------------------------
    def _flush_line_events(self) -> None:
        if not self._line_orchestrator:
            return
        for event in self._line_orchestrator.drain_events():
            meta = " ".join(f"{k}={v}" for k, v in event.metadata.items()) if event.metadata else ""
            msg = f"{event.message} {meta}".strip()
            self._emit_log(event.level, "Line", msg)

    # ------------------------------------------------------------------
    def _persist_line_order(self, decision: BetDecision) -> None:
        try:
            record = {
                "ts": int(time.time()),
                "created_at": int(decision.created_at),
                "table": decision.table_id,
                "round": decision.round_id,
                "strategy": decision.strategy_key,
                "direction": decision.direction.value,
                "amount": decision.amount,
                "layer": decision.layer_index,
                "reason": decision.reason,
            }
            self._line_orders_path.parent.mkdir(parents=True, exist_ok=True)
            with self._line_orders_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            self._emit_log("ERROR", "Line", f"記錄 Line 訂單失敗: {exc}")

    # ------------------------------------------------------------------
    def _drain_line_orders_queue(self) -> None:
        pending: List[BetDecision] = []
        while True:
            try:
                decision = self._line_order_queue.get_nowait()
            except queue.Empty:
                break
            else:
                pending.append(decision)

        for decision in pending:
            self._dispatch_line_order(decision)

    # ------------------------------------------------------------------
    def _dispatch_line_order(self, decision: BetDecision) -> None:
        """執行 Line 策略產生的下注決策"""
        self._emit_log(
            "INFO",
            "Line",
            f"📋 執行 Line 訂單: {decision.strategy_key} -> table {decision.table_id} {decision.direction.value} ${decision.amount}",
        )

        if not self.engine:
            self._emit_log("ERROR", "Line", "引擎未初始化，無法執行訂單")
            return

        # 將 BetDecision 轉換成 AutobetEngine 可以執行的格式
        try:
            # 轉換方向：BetDirection -> target string
            direction_map = {
                "BANKER": "banker",
                "PLAYER": "player",
                "TIE": "tie"
            }
            target = direction_map.get(decision.direction.value, decision.direction.value.lower())

            # 檢查下注期是否開放
            if self._line_orchestrator:
                # 獲取該桌的當前階段
                current_phase = self._line_orchestrator.table_phases.get(decision.table_id)

                # 檢查是否在 BETTABLE 階段
                if current_phase and current_phase != TablePhase.BETTABLE:
                    self._emit_log(
                        "WARNING",
                        "Line",
                        f"⚠️ 下注期未開放 (當前階段: {current_phase.name})，跳過訂單"
                    )
                    return

            # 構建下注計畫
            from src.autobet.chip_planner import SmartChipPlanner

            if self.engine.smart_planner:
                # 使用 SmartChipPlanner 規劃籌碼組合
                bet_plan = self.engine.smart_planner.plan_bet(
                    target_amount=decision.amount,
                    max_clicks=self.engine.chip_profile.constraints.get("max_clicks_per_hand", 8) if self.engine.chip_profile else 8
                )

                if not bet_plan.success:
                    self._emit_log("ERROR", "Line", f"❌ 籌碼規劃失敗: {bet_plan.reason}")
                    return

                # 獲取當前層數資訊
                current_layer_info = "N/A"
                total_layers = "N/A"
                if self._line_orchestrator:
                    for line_state in self._line_orchestrator.line_states.values():
                        if line_state.strategy_key == decision.strategy_key:
                            current_layer_info = decision.layer_index + 1
                            if line_state.progression and line_state.progression.sequence:
                                total_layers = len(line_state.progression.sequence)
                            break

                # 發送即時更新到 NextBetCard
                self.next_bet_info.emit({
                    'table_id': decision.table_id,
                    'strategy': decision.strategy_key,
                    'layer': f"{current_layer_info}/{total_layers}",
                    'direction': target,
                    'amount': decision.amount,
                    'recipe': bet_plan.description
                })

                self._emit_log(
                    "INFO",
                    "Line",
                    f"✅ 籌碼配方: {bet_plan.recipe} (總點擊{bet_plan.clicks}次)"
                )

                # 執行下注序列（帶詳細日誌和回滾）
                if self.engine.act:
                    execution_log = []  # 記錄執行步驟，用於錯誤追蹤

                    try:
                        total_steps = len(bet_plan.chips)
                        self._emit_log("INFO", "Line", f"🚀 開始執行下注序列 (共 {total_steps} 個籌碼)")

                        # 依序執行每個籌碼的放置
                        for idx, chip in enumerate(bet_plan.chips, 1):
                            step_info = f"步驟 {idx}/{total_steps}"

                            # 點擊籌碼
                            chip_desc = f"點擊籌碼 {chip.value}"
                            self._emit_log("DEBUG", "Line", f"  [{step_info}] {chip_desc}")
                            execution_log.append(("chip", chip.value))

                            if not self.engine.act.click_chip_value(chip.value):
                                raise Exception(f"{step_info} 失敗: {chip_desc}")

                            # 點擊下注區
                            bet_desc = f"點擊下注區 {target}"
                            self._emit_log("DEBUG", "Line", f"  [{step_info}] {bet_desc}")
                            execution_log.append(("bet", target))

                            if not self.engine.act.click_bet(target):
                                raise Exception(f"{step_info} 失敗: {bet_desc}")

                        # 所有步驟成功，確認下注
                        self._emit_log("DEBUG", "Line", "  最後步驟: 確認下注")
                        self.engine.act.confirm()
                        self._emit_log("INFO", "Line", f"✅ 訂單執行完成: {decision.strategy_key}")

                    except Exception as e:
                        # 執行失敗，記錄詳細錯誤和已執行步驟
                        self._emit_log("ERROR", "Line", f"❌ 執行下注失敗: {e}")

                        # 記錄已執行的步驟
                        if execution_log:
                            executed_steps = " → ".join([f"{action}:{value}" for action, value in execution_log])
                            self._emit_log("DEBUG", "Line", f"已執行步驟: {executed_steps}")

                        # 嘗試回滾（取消不完整的下注）
                        self._emit_log("WARNING", "Line", "🔄 嘗試回滾不完整的下注...")
                        try:
                            if self.engine.act.cancel():
                                self._emit_log("INFO", "Line", "✅ 已成功取消不完整的下注")
                            else:
                                self._emit_log("WARNING", "Line", "⚠️ 取消操作未確認成功，請手動檢查遊戲畫面")
                        except Exception as cancel_error:
                            self._emit_log("ERROR", "Line", f"❌ 回滾失敗: {cancel_error}，請立即手動檢查遊戲畫面！")

                        # 重新拋出異常，讓外層處理
                        raise
                else:
                    self._emit_log("ERROR", "Line", "Actuator 未初始化")
            else:
                self._emit_log("ERROR", "Line", "SmartChipPlanner 未初始化，無法執行訂單")

        except Exception as e:
            self._emit_log("ERROR", "Line", f"處理 Line 訂單錯誤: {e}")

