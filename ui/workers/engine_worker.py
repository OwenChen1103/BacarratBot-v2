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
    plan_ready = Signal(dict)
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

    def initialize_engine(self, dry_run: bool = True) -> bool:
        """初始化引擎（最小可行版）"""
        try:
            self.engine = AutoBetEngine(dry_run=dry_run)
            self._dry_run = dry_run
            self._emit_log("INFO", "Engine", "引擎已初始化")

            # 嘗試載入必要檔案，但不強制存在
            ok = True
            ok = ok and self.engine.load_positions("configs/positions.sample.json", dpi_scale=1.0)
            ok = ok and self.engine.load_strategy("configs/strategy.default.json")
            # ui.yaml 可選
            ui_cfg = {}
            try:
                import yaml
                with open("configs/ui.yaml", "r", encoding="utf-8") as f:
                    ui_cfg = yaml.safe_load(f)
            except Exception:
                pass
            self.engine.load_ui_config(ui_cfg)

            init_ok = self.engine.initialize_components()
            if init_ok:
                self._emit_log("INFO", "Engine", "元件初始化成功")
            else:
                self._emit_log("WARNING", "Engine", "元件初始化部分失敗（可能缺少配置檔案）")

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
        while self._tick_running:
            try:
                # 始終發送狀態更新，不管引擎是否啟用
                current_state = "running" if self._enabled else "idle"
                self.state_changed.emit(current_state)

                # 模擬統計數據
                self.session_stats.emit({
                    "rounds": getattr(self, '_round_count', 0),
                    "net": getattr(self, '_net_profit', 0),
                    "last_winner": getattr(self, '_last_winner', None),
                    "enabled": self._enabled,
                    "dry_run": self._dry_run,
                })

                # 發送引擎狀態
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

            self.msleep(200)

    def start_engine(self, source: str, **kwargs) -> bool:
        """啟動引擎與事件來源"""
        if not self.engine:
            self._emit_log("ERROR", "Engine", "引擎未初始化")
            return False

        # 創建事件來源
        if source == "demo":
            interval = int(kwargs.get("interval", 15))
            seed = kwargs.get("seed", 42)
            self.event_feeder = DemoFeeder(interval, self._handle_event, seed)
        elif source == "ndjson":
            file_path = kwargs.get("file_path", "data/sessions/events.sample.ndjson")
            if not os.path.exists(file_path):
                self._emit_log("ERROR", "Events", f"檔案不存在: {file_path}")
                return False
            interval = float(kwargs.get("interval", 1.0))
            self.event_feeder = NDJSONPlayer(file_path, self._handle_event, interval)
        else:
            self._emit_log("ERROR", "Events", f"未知事件來源: {source}")
            return False

        if self.engine:
            try:
                self.engine.set_enabled(True)
            except AttributeError:
                pass  # 引擎可能沒有 set_enabled 方法
        self._enabled = True
        self.event_feeder.start()
        self._emit_log("INFO", "Events", f"事件來源啟動: {source}")

        # 立即發送狀態更新
        self.state_changed.emit("running")

        return True

    def stop_engine(self):
        self._enabled = False
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

    def _emit_log(self, level: str, module: str, msg: str):
        self.log_message.emit(level, module, msg)

    def quit(self):
        self._tick_running = False
        self.stop_engine()
        super().quit()