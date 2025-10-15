# ui/workers/engine_worker.py
import os, json, time, threading, random, logging, queue, unicodedata
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple, List
from PySide6.QtCore import QThread, Signal

from src.autobet.autobet_engine import AutoBetEngine
from ipc.t9_stream import T9StreamClient
from src.autobet.lines import (
    LineOrchestrator,
    TablePhase,
    BetDecision,
    load_strategy_definitions,
)

TABLE_DISPLAY_MAP = {
    "WG7": "BG_131",
    "WG8": "BG_132",
    "WG9": "BG_133",
    "WG10": "BG_135",
    "WG11": "BG_136",
    "WG12": "BG_137",
    "WG13": "BG_138",
}

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
        self._t9_client: Optional[T9StreamClient] = None
        self._t9_status = "stopped"
        self._t9_enabled = os.getenv("T9_STREAM_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self._latest_results: Dict[str, Dict[str, Any]] = {}
        self._line_orchestrator: Optional[LineOrchestrator] = None
        self._line_order_queue: "queue.Queue[BetDecision]" = queue.Queue()
        self._line_summary: Dict[str, Any] = {}
        base_dir = Path("data/sessions")
        base_dir.mkdir(parents=True, exist_ok=True)
        self._line_state_path = base_dir / "line_state.json"
        self._line_orders_path = base_dir / "line_orders.ndjson"
        # 移除檢測相關狀態，檢測邏輯由 Dashboard 處理

    def initialize_engine(self, dry_run: bool = True) -> bool:
        """初始化引擎並載入配置"""
        try:
            self.engine = AutoBetEngine(dry_run=dry_run)
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

            # 啟動結果流監聽（若配置允許）
            self._setup_result_stream()

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

                # 發送引擎狀態（移除檢測相關狀態）
                status = {
                    "current_state": current_state,
                    "enabled": self._enabled,
                    "dry_run": self._dry_run,
                    "rounds": getattr(self, '_round_count', 0),
                    "net": getattr(self, '_net_profit', 0),
                    "last_winner": getattr(self, '_last_winner', None),
                    "t9_stream_status": getattr(self, '_t9_status', None),
                    "latest_results": self._latest_results_snapshot(),
                    "line_summary": self._line_summary,
                }
                self.engine_status.emit(status)

            except Exception as e:
                self._emit_log("ERROR", "Status", f"狀態檢查錯誤: {e}")

            # 固定頻率，簡化邏輯
            self.msleep(1000)  # 1秒，只需定期發送狀態更新

    def start_engine(self, mode: str = "simulation", **kwargs) -> bool:
        """啟動引擎
        Args:
            mode: "simulation" (模擬模式) 或 "real" (實戰模式)
        """
        if not self.engine:
            self._emit_log("ERROR", "Engine", "引擎未初始化")
            return False

        try:
            # 確保結果流已啟動
            self._setup_result_stream()

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

            # 載入 strategy.json
            if os.path.exists("configs/strategy.json"):
                success = self.engine.load_strategy("configs/strategy.json")
                if not success:
                    self._emit_log("ERROR", "Config", "載入 strategy.json 失敗")
                    return False
                self._emit_log("INFO", "Config", "✅ strategy.json 載入成功")
            else:
                self._emit_log("ERROR", "Config", "未找到 configs/strategy.json")
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
        # 檢測狀態由 Dashboard 管理，此處不再重置
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
        if self._t9_client:
            try:
                self._t9_client.stop()
            except Exception:
                pass
            self._t9_client = None
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

            if event_type == "RESULT":
                if self._line_orchestrator and table_id and round_id:
                    ts_raw = event.get("received_at")
                    if isinstance(ts_raw, (int, float)):
                        ts_sec = float(ts_raw) / 1000.0 if ts_raw > 1e6 else float(ts_raw)
                    else:
                        ts_sec = time.time()
                    self._line_orchestrator.handle_result(table_id, round_id, winner, ts_sec)
                    self._line_summary = self._line_orchestrator.snapshot()
                    self._save_line_state()
                    self._flush_line_events()

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
                self._emit_table_log("INFO", table_id, message, module="Events")

                # 如果有真正的引擎，也發送給它
                if self.engine:
                    try:
                        self.engine.on_event(event)
                    except Exception as e:
                        self._emit_log("WARNING", "Engine", f"引擎處理事件錯誤: {e}")

        except Exception as e:
            self._emit_log("ERROR", "Events", f"事件處理錯誤: {e}")



    def _store_latest_result(self, event: Dict[str, Any]) -> None:
        table_id = event.get("table_id")
        if not table_id:
            return

        table_key = str(table_id)
        round_id = event.get("round_id")
        round_str = str(round_id) if round_id is not None else None

        info: Dict[str, Any] = {
            "table_id": table_key,
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

        # 將最新資料移到字典尾端維持近序
        self._latest_results.pop(table_key, None)
        self._latest_results[table_key] = info

        max_tables = 20
        while len(self._latest_results) > max_tables:
            first_key = next(iter(self._latest_results))
            if first_key == table_key and len(self._latest_results) == 1:
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
            "detection_state": self._detection_state,
            "detection_error": getattr(self, '_last_detection_error', None),
            "t9_stream_status": getattr(self, '_t9_status', None),
            "latest_results": self._latest_results_snapshot(),
        }
        self.engine_status.emit(status)

    def _emit_log(self, level: str, module: str, msg: str):
        self.log_message.emit(level, module, msg)

    # _trigger_engine_execution 方法已移除
    # 觸發邏輯現在由 Dashboard 直接處理

    # ------------------------------------------------------------------
    def _map_table_display(self, table_id: Optional[str]) -> Optional[str]:
        if not table_id:
            return None
        return TABLE_DISPLAY_MAP.get(str(table_id), None)

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
        prefix = ""
        if table_id:
            table_id_str = str(table_id)
            display = self._map_table_display(table_id_str)
            prefix_parts = [f"[table={table_id_str}]"]
            if display and display != table_id_str:
                prefix_parts.append(f"[display={display}]")
            prefix = "".join(prefix_parts) + " "
        self._emit_log(level, module, f"{prefix}{message}")

    # ------------------------------------------------------------------
    def _classify_t9_state(self, record: Dict[str, Any]) -> Dict[str, Any]:
        table_id = record.get("table_id") or record.get("tableId") or record.get("table")
        table_id = str(table_id) if table_id is not None else None

        round_raw = record.get("round_id") or record.get("roundId") or record.get("merchant_round_id")
        round_id = str(round_raw) if round_raw is not None else None

        winner, reason = self._extract_t9_winner(record)
        game_result_raw = record.get("gameResult")
        game_result = game_result_raw if isinstance(game_result_raw, dict) else {}
        player_point = game_result.get("player_point")
        banker_point = game_result.get("banker_point")

        status_candidates = [
            record.get("game_payment_status_name"),
            record.get("game_status"),
            record.get("status"),
            record.get("state"),
            record.get("settle_status"),
            game_result.get("win_lose_result") if isinstance(game_result, dict) else None,
            record.get("win_lose_result"),
            record.get("message"),
        ]
        status_text = ""
        for candidate in status_candidates:
            text = self._normalize_text(candidate)
            if text:
                status_text = text
                break

        summary = ""
        stage = "unknown"
        level = "INFO"

        if winner:
            stage = "result"
            text_map = {"B": "莊勝", "P": "閒勝", "T": "和局"}
            summary = f"結果：{text_map.get(winner, winner)}"
        elif reason == "cancelled":
            stage = "cancelled"
            summary = "結果：取消/無效"
            level = "WARNING"
        else:
            lowered = status_text.lower()

            def _match(keywords):
                return any(kw in lowered for kw in keywords)

            if lowered:
                if _match(["投注", "下注", "bet", "wager"]):
                    stage = "betting"
                    summary = "狀態：投注中"
                elif _match(["停止", "關閉", "封盤", "封牌", "stop", "close"]):
                    stage = "closing"
                    summary = "狀態：停止下注"
                elif _match(["開獎", "開牌", "進行", "running", "progress", "deal", "發牌"]):
                    stage = "dealing"
                    summary = "狀態：開獎中"
                elif _match(["派彩", "結算", "settle", "payout"]):
                    stage = "payout"
                    summary = "狀態：派彩中"
                elif _match(["完成", "結束", "finish", "done"]):
                    stage = "finished"
                    summary = "狀態：局已結束"

            if not summary:
                if status_text:
                    summary = f"狀態：{status_text}"
                else:
                    summary = "狀態：未知"

        return {
            "table_id": table_id,
            "round_id": round_id,
            "winner": winner,
            "reason": reason,
            "status_text": status_text,
            "stage": stage,
            "summary": summary,
            "level": level,
            "player_point": player_point,
            "banker_point": banker_point,
            "raw_record": record,
        }

    # ------------------------------------------------------------------
    def _format_t9_log_message(self, info: Dict[str, Any]) -> str:
        summary = info.get("summary") or "狀態：未知"
        round_id = info.get("round_id")
        status_text = info.get("status_text")
        reason = info.get("reason")
        winner = info.get("winner")
        details = []

        if round_id:
            details.append(f"round={round_id}")

        if winner:
            player_point = self._normalize_text(info.get("player_point"))
            banker_point = self._normalize_text(info.get("banker_point"))
            if player_point or banker_point:
                points = []
                if player_point:
                    points.append(f"閒 {player_point}")
                if banker_point:
                    points.append(f"莊 {banker_point}")
                if points:
                    details.append(" / ".join(points))

        if status_text and summary != f"狀態：{status_text}" and summary != f"結果：{status_text}":
            details.append(f"狀態={status_text}")

        if reason and not winner and reason != "cancelled":
            details.append(f"原因={reason}")

        if details:
            return f"{summary} ({', '.join(details)})"
        return summary

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

    def quit(self):
        self._tick_running = False
        self.stop_engine()
        super().quit()

    # ------------------------------------------------------------------
    def _init_line_orchestrator(self) -> None:
        bankroll = float(os.getenv("LINE_BANKROLL", "10000") or 10000)
        per_hand_pct = float(os.getenv("LINE_PER_HAND_PCT", "0.05") or 0.05)
        per_table_pct = float(os.getenv("LINE_PER_TABLE_PCT", "0.1") or 0.1)
        per_hand_cap_env = os.getenv("LINE_PER_HAND_CAP")
        per_hand_cap = float(per_hand_cap_env) if per_hand_cap_env else None
        max_tables = int(os.getenv("LINE_MAX_CONCURRENT_TABLES", "3") or 3)
        min_unit = float(os.getenv("LINE_MIN_BET_UNIT", "1") or 1.0)
        strategy_dir_env = os.getenv("LINE_STRATEGY_DIR", "configs/line_strategies")
        strategy_dir = Path(strategy_dir_env)

        try:
            self._line_orchestrator = LineOrchestrator(
                bankroll=bankroll,
                per_hand_risk_pct=per_hand_pct,
                per_table_risk_pct=per_table_pct,
                per_hand_cap=per_hand_cap,
                max_concurrent_tables=max_tables,
                min_unit=min_unit,
            )
            if strategy_dir.exists():
                definitions = load_strategy_definitions(strategy_dir)
                for definition in definitions.values():
                    self._line_orchestrator.register_strategy(definition)
                self._emit_log("INFO", "Line", f"載入 {len(definitions)} 條 Line 策略")
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
            self._emit_log("ERROR", "Line", f"策略系統初始化失敗: {exc}")

    # ------------------------------------------------------------------
    def _load_line_state(self) -> None:
        if not self._line_orchestrator or not self._line_state_path.exists():
            return
        try:
            data = json.loads(self._line_state_path.read_text(encoding="utf-8"))
            self._line_orchestrator.restore_state(data)
            self._line_summary = self._line_orchestrator.snapshot()
            self._emit_log("INFO", "Line", "Line 狀態已恢復")
        except Exception as exc:
            self._emit_log("ERROR", "Line", f"恢復 Line 狀態失敗: {exc}")

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

    def _setup_result_stream(self) -> None:
        if not self._t9_enabled:
            self._emit_log("INFO", "Result", "T9 結果流已停用 (T9_STREAM_ENABLED=false)")
            return

        if self._t9_client:
            return

        base_url = os.getenv("T9_STREAM_URL", "http://127.0.0.1:8000/api/stream").strip()
        if not base_url:
            self._emit_log("WARNING", "Result", "T9_STREAM_URL 未設定，結果流未啟動")
            return

        event_types = os.getenv("T9_STREAM_EVENT_TYPES", "result")

        retry_env = os.getenv("T9_STREAM_RETRY_SEC", "5")
        try:
            retry_delay = float(retry_env)
        except ValueError:
            retry_delay = 5.0

        timeout_env = os.getenv("T9_STREAM_TIMEOUT_SEC", "65")
        try:
            request_timeout = float(timeout_env)
        except ValueError:
            request_timeout = 65.0

        headers = {"Accept": "text/event-stream"}
        ingest_key = os.getenv("T9_STREAM_INGEST_KEY")
        if ingest_key:
            headers["x-ingest-key"] = ingest_key

        self._t9_client = T9StreamClient(
            base_url,
            event_types=event_types,
            headers=headers,
            retry_delay=retry_delay,
            request_timeout=request_timeout,
            on_event=self._on_t9_raw_event,
            on_status=self._on_t9_status,
        )

        self._emit_log("INFO", "Result", f"嘗試連線 T9 結果流: {base_url}")
        self._t9_client.start()

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
        if processed:
            self._emit_log("DEBUG", "Result", f"處理 {processed} 筆結果事件")
        self._drain_line_orders_queue()

    # ------------------------------------------------------------------
    def _on_t9_status(self, status: str, detail: Optional[str]) -> None:
        if status == self._t9_status and status not in {"error"}:
            return
        self._t9_status = status

        if status == "connecting":
            self._emit_log("INFO", "Result", f"連線 T9 流... {detail or ''}")
        elif status == "connected":
            self._emit_log("INFO", "Result", "✅ T9 結果流已連線")
        elif status == "error":
            self._emit_log("WARNING", "Result", f"T9 結果流錯誤: {detail}")
        elif status == "disconnected":
            self._emit_log("INFO", "Result", "T9 結果流已斷線，準備重新連線")
        elif status == "stopped":
            self._emit_log("INFO", "Result", "T9 結果流已停止")

    # ------------------------------------------------------------------
    def _on_t9_raw_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        event_type = (payload.get("event_type") or event_name or "").lower()
        if event_type != "result":
            # 忽略 heartbeat / 其他事件
            return

        record: Optional[Dict[str, Any]] = None
        if isinstance(payload.get("payload"), dict):
            record = payload["payload"].get("record")
        if record is None:
            record = payload.get("record")

        if not isinstance(record, dict):
            self._emit_log("DEBUG", "Result", "skip unknown T9 record format")
            return

        event, info = self._convert_t9_record_to_event(record)
        if info:
            message = self._format_t9_log_message(info)
            self._emit_table_log(info.get("level", "INFO"), info.get("table_id"), message)
            self._process_line_state(info)

        if event:
            self._incoming_events.put(event)
    # ------------------------------------------------------------------
    def _process_line_state(self, info: Dict[str, Any]) -> None:
        if not self._line_orchestrator:
            return
        table_id = info.get("table_id")
        if not table_id:
            return
        phase = self._map_stage_to_phase(info.get("stage"))
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
        # TODO: Integrate with AutoBetEngine for automated execution
        self._emit_log(
            "INFO",
            "Line",
            f"待執行 Line 訂單: {decision.strategy_key} -> {decision.table_id} amount={decision.amount}",
        )

    # ------------------------------------------------------------------
    def _convert_t9_record_to_event(self, record: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        info = self._classify_t9_state(record)
        winner = info.get("winner")
        table_id = info.get("table_id")
        round_id = info.get("round_id")

        event: Optional[Dict[str, Any]] = None
        if winner:
            event = {
                "type": "RESULT",
                "winner": winner,
                "source": "t9_stream",
                "received_at": int(time.time() * 1000),
                "raw": record,
            }
            if table_id:
                event["table_id"] = str(table_id)
            if round_id is not None:
                event["round_id"] = str(round_id)

        return event, info

    # ------------------------------------------------------------------
    def _extract_t9_winner(self, record: Dict[str, Any]) -> (Optional[str], Optional[str]):
        game_result = record.get("gameResult")
        cancel_detected = False

        if isinstance(game_result, dict):
            result_code = game_result.get("result")
            mapped = self._map_t9_result_code(result_code)
            if mapped:
                return mapped, None
            if result_code == 3:
                cancel_detected = True

            text_winner = self._map_t9_text(game_result.get("win_lose_result"))
            if text_winner:
                return text_winner, None

        # 其他欄位
        candidates = [
            record.get("win_lose_result"),
            record.get("result"),
            record.get("game_result"),
            record.get("gameResult") if isinstance(game_result, str) else None,
        ]
        for item in candidates:
            mapped = self._map_t9_text(item)
            if mapped:
                return mapped, None

        if cancel_detected:
            return None, "cancelled"

        return None, None

    # ------------------------------------------------------------------
    @staticmethod
    def _map_t9_result_code(code: Optional[int]) -> Optional[str]:
        if code is None:
            return None
        mapping = {0: "B", 1: "P", 2: "T"}
        return mapping.get(code)

    # ------------------------------------------------------------------
    @staticmethod
    def _map_t9_text(value: Optional[Any]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None

        lowered = text.lower()
        if any(keyword in lowered for keyword in ["cancel", "無效", "取消", "invalid", "void"]):
            return None

        upper = text.upper()
        direct_map = {
            "BANKER": "B",
            "B": "B",
            "PLAYER": "P",
            "P": "P",
            "TIE": "T",
            "T": "T",
        }
        if upper in direct_map:
            return direct_map[upper]

        normalized = text.replace("\u3000", "").replace(" ", "")
        if any(ch in normalized for ch in ["莊", "庄"]):
            return "B"
        if any(ch in normalized for ch in ["閒", "闲", "閑"]):
            return "P"
        if any(ch in normalized for ch in ["和", "平"]):
            return "T"

        return None
