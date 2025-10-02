# ui/workers/engine_worker.py
import os, json, time, threading, random, logging
from typing import Optional, Callable, Dict
from PySide6.QtCore import QThread, Signal

from src.autobet.autobet_engine import AutoBetEngine

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
                    "last_winner": getattr(self, '_last_winner', None)
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

            if event_type == "RESULT":
                self._round_count += 1
                self._last_winner = winner

                # 模擬投注結果（這裡只是示例）
                if winner in ["B", "P"]:
                    # 模擬盈虧（隨機）
                    import random
                    profit = random.randint(-100, 150)
                    self._net_profit += profit

                self._emit_log("INFO", "Events", f"第 {self._round_count} 局結果: {winner}")

                # 如果有真正的引擎，也發送給它
                if self.engine:
                    try:
                        self.engine.on_event(event)
                    except Exception as e:
                        self._emit_log("WARNING", "Engine", f"引擎處理事件錯誤: {e}")

        except Exception as e:
            self._emit_log("ERROR", "Events", f"事件處理錯誤: {e}")



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
            "detection_error": getattr(self, '_last_detection_error', None)
        }
        self.engine_status.emit(status)

    def _emit_log(self, level: str, module: str, msg: str):
        self.log_message.emit(level, module, msg)

    # _trigger_engine_execution 方法已移除
    # 觸發邏輯現在由 Dashboard 直接處理

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
