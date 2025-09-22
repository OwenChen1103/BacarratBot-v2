# ui/workers/engine_worker.py
import os
import json
import logging
from typing import Dict, Optional
from PySide6.QtCore import QThread, Signal, QTimer
from src.autobet import AutoBetEngine
from src.autobet.io_events import NDJSONPlayer, DemoFeeder

logger = logging.getLogger(__name__)

class EngineWorker(QThread):
    """引擎工作執行緒 - 處理 AutoBetEngine 相關操作"""

    # 訊號定義
    state_changed = Signal(str)  # 狀態改變 (idle, betting_open, etc.)
    plan_ready = Signal(dict)    # 下注計畫準備就緒
    session_stats = Signal(dict) # 會話統計更新
    risk_alert = Signal(str, str) # 風控警示 (level, message)
    log_message = Signal(str, str, str) # 日誌訊息 (level, module, message)
    engine_status = Signal(dict) # 引擎狀態更新

    def __init__(self):
        super().__init__()
        self.engine: Optional[AutoBetEngine] = None
        self.event_feeder = None
        self.is_running = False

        # 狀態監控定時器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_engine_status)
        self.status_timer.moveToThread(self)

    def initialize_engine(self, dry_run: bool = True):
        """初始化引擎"""
        try:
            self.engine = AutoBetEngine(dry_run=dry_run)

            # 載入配置檔案
            self.load_configurations()

            # 初始化元件
            if self.engine.initialize_components():
                self.log_message.emit("INFO", "Engine", "引擎初始化成功")
                return True
            else:
                self.log_message.emit("ERROR", "Engine", "引擎元件初始化失敗")
                return False

        except Exception as e:
            self.log_message.emit("ERROR", "Engine", f"引擎初始化錯誤：{e}")
            return False

    def load_configurations(self):
        """載入配置檔案"""
        if not self.engine:
            return

        # 載入位置配置
        if os.path.exists("configs/positions.json"):
            success = self.engine.load_positions("configs/positions.json")
            if success:
                self.log_message.emit("INFO", "Config", "位置配置載入成功")
            else:
                self.log_message.emit("WARNING", "Config", "位置配置載入失敗")

        # 載入策略配置
        if os.path.exists("configs/strategy.json"):
            success = self.engine.load_strategy("configs/strategy.json")
            if success:
                self.log_message.emit("INFO", "Config", "策略配置載入成功")
            else:
                self.log_message.emit("WARNING", "Config", "策略配置載入失敗")

        # 載入 UI 配置
        if os.path.exists("configs/ui.yaml"):
            try:
                import yaml
                with open("configs/ui.yaml", 'r', encoding='utf-8') as f:
                    ui_config = yaml.safe_load(f)
                self.engine.load_ui_config(ui_config)
                self.log_message.emit("INFO", "Config", "UI 配置載入成功")
            except Exception as e:
                self.log_message.emit("WARNING", "Config", f"UI 配置載入失敗：{e}")

    def start_engine(self, event_source: str = "demo", **kwargs):
        """啟動引擎與事件來源"""
        if not self.engine:
            self.log_message.emit("ERROR", "Engine", "引擎未初始化")
            return False

        try:
            # 啟動事件來源
            self.start_event_source(event_source, **kwargs)

            # 啟動引擎
            self.engine.set_enabled(True)

            # 啟動狀態監控
            self.status_timer.start(200)  # 每 200ms 檢查一次

            self.is_running = True
            self.log_message.emit("INFO", "Engine", f"引擎已啟動 - 事件來源：{event_source}")
            return True

        except Exception as e:
            self.log_message.emit("ERROR", "Engine", f"啟動引擎失敗：{e}")
            return False

    def stop_engine(self):
        """停止引擎"""
        if self.engine:
            self.engine.set_enabled(False)

        if self.event_feeder:
            self.event_feeder.stop()
            self.event_feeder = None

        self.status_timer.stop()
        self.is_running = False
        self.log_message.emit("INFO", "Engine", "引擎已停止")

    def start_event_source(self, source_type: str, **kwargs):
        """啟動事件來源"""
        if self.event_feeder:
            self.event_feeder.stop()

        if source_type == "demo":
            interval = kwargs.get("interval", 15)
            self.event_feeder = DemoFeeder(
                callback=self.on_event,
                interval_sec=interval,
                random_seed=kwargs.get("seed", 42)
            )
        elif source_type == "ndjson":
            file_path = kwargs.get("file_path", "data/sessions/events.sample.ndjson")
            interval = kwargs.get("interval", 1.2)
            self.event_feeder = NDJSONPlayer(
                path=file_path,
                callback=self.on_event,
                interval=interval
            )
        else:
            raise ValueError(f"不支援的事件來源：{source_type}")

        self.event_feeder.start()
        self.log_message.emit("INFO", "Events", f"事件來源已啟動：{source_type}")

    def on_event(self, event: Dict):
        """處理事件"""
        if self.engine:
            self.engine.on_event(event)

        # 發送事件到 UI
        self.log_message.emit("DEBUG", "Events", f"收到事件：{event.get('type')} - {event.get('winner', 'N/A')}")

    def check_engine_status(self):
        """檢查引擎狀態並發送更新"""
        if not self.engine:
            return

        try:
            status = self.engine.get_status()

            # 檢查狀態變化
            current_state = status.get("current_state", "unknown")
            self.state_changed.emit(current_state)

            # 發送完整狀態
            self.engine_status.emit(status)

            # 發送統計資料
            stats = {
                "rounds": status.get("rounds", 0),
                "net": status.get("net", 0),
                "last_winner": status.get("last_winner"),
                "enabled": status.get("enabled", False),
                "dry_run": status.get("dry_run", True)
            }
            self.session_stats.emit(stats)

        except Exception as e:
            self.log_message.emit("ERROR", "Status", f"狀態檢查錯誤：{e}")

    def set_dry_run(self, dry_run: bool):
        """設定乾跑模式"""
        if self.engine:
            self.engine.dry = dry_run
            self.log_message.emit("INFO", "Engine", f"乾跑模式：{'開啟' if dry_run else '關閉'}")

    def get_engine_status(self) -> Dict:
        """獲取引擎狀態"""
        if self.engine:
            return self.engine.get_status()
        return {}

    def run(self):
        """執行緒主循環"""
        # 啟動事件循環
        self.exec()