# ui/main_window.py
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QStackedWidget, QStatusBar, QToolBar,
    QMenuBar, QMenu, QLabel, QFrame, QSplitter
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction, QIcon, QFont

from .pages.page_home import HomePage
from .pages.page_templates import TemplatesPage
from .pages.page_positions import PositionsPage
from .pages.page_overlay import OverlayPage
from .pages.page_strategy import StrategyPage
from .pages.page_events import EventsPage
from .pages.page_dashboard import DashboardPage
from .pages.page_sessions import SessionsPage
from .pages.page_settings import SettingsPage
from .app_state import APP_STATE
from .components.toast import show_toast

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoBet Bot — 百家樂自動投注機器人")
        self.resize(1200, 800)

        root = QWidget(self)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        self.setCentralWidget(root)

        # 側邊欄
        self.nav = QListWidget()
        self.nav.setFixedWidth(180)
        self.nav.currentRowChanged.connect(self.on_nav_changed)
        layout.addWidget(self.nav)

        # 頁面堆疊
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # 狀態列
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status_label = QLabel("🔌 準備就緒（預設乾跑）")
        self.status.addPermanentWidget(self.status_label)

        # 頁面註冊
        self.pages = {}
        home_page = HomePage()
        home_page.navigate_to.connect(self.switch_to_page)
        self.add_page("home", home_page, "首頁")

        self.add_page("templates", TemplatesPage(), "模板管理")
        self.add_page("positions", PositionsPage(), "位置校準")
        self.add_page("overlay", OverlayPage(), "可下注判斷")
        self.add_page("strategy", StrategyPage(), "策略設定")

        dashboard_page = DashboardPage()
        dashboard_page.navigate_to.connect(self.switch_to_page)
        self.add_page("dashboard", dashboard_page, "實戰主控台")

        # self.add_page("events", EventsPage(), "📡 事件來源")  # 暫時移除，直接使用 overlay 檢測
        self.add_page("sessions", SessionsPage(), "記錄回放")
        self.add_page("settings", SettingsPage(), "系統設定")

        self.nav.setCurrentRow(0)

        # 選單（最少可用）
        self._build_menu()

        # 連接全域事件
        self._connect_app_state()

        # 初始化時檢查現有配置狀態
        self._check_initial_state()

    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("檔案")
        act_quit = QAction("離開", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

    def add_page(self, key: str, widget: QWidget, label: str):
        self.pages[key] = widget
        self.stack.addWidget(widget)
        self.nav.addItem(label)

    def on_nav_changed(self, idx: int):
        self.stack.setCurrentIndex(idx)

    def switch_to_page(self, key: str):
        # 由頁面發出的 navigate_to 事件切換
        keys = list(self.pages.keys())
        if key in self.pages:
            self.stack.setCurrentWidget(self.pages[key])
            self.nav.setCurrentRow(keys.index(key))

    def _connect_app_state(self):
        """連接應用狀態事件"""
        APP_STATE.toastRequested.connect(self._show_toast)
        APP_STATE.bannerRequested.connect(self._show_banner)

    def _show_toast(self, data):
        """顯示 Toast 訊息"""
        message = data.get('message', '')
        toast_type = data.get('type', 'success')
        duration = data.get('duration', 2200)
        show_toast(self, message, toast_type, duration)

    def _show_banner(self, data):
        """顯示 Banner 訊息"""
        # TODO: 實作 Banner 組件
        message = data.get('message', '')
        banner_type = data.get('type', 'error')
        print(f"Banner ({banner_type}): {message}")  # 暫時用 print

    def _check_initial_state(self):
        """檢查並發送初始配置狀態"""
        import os
        import json

        # 檢查 positions.json
        if os.path.exists("configs/positions.json"):
            try:
                with open("configs/positions.json", "r", encoding="utf-8") as f:
                    pos_data = json.load(f)

                # 發送 positions 狀態
                point_count = len(pos_data.get("points", {}))
                required_keys = ["banker", "chip_1k", "confirm"]
                APP_STATE.positionsChanged.emit({
                    'complete': point_count >= len(required_keys),
                    'count': point_count,
                    'required': required_keys
                })

                # 發送 overlay 狀態
                roi_data = pos_data.get("roi", {})
                params = pos_data.get("overlay_params", {})
                has_roi = bool(roi_data.get("overlay") and roi_data.get("timer"))
                threshold = params.get("ncc_threshold", 0)
                APP_STATE.overlayChanged.emit({
                    'has_roi': has_roi,
                    'threshold': threshold,
                    'ready': has_roi and threshold > 0
                })
            except:
                pass

        # 檢查 strategy.json
        if os.path.exists("configs/strategy.json"):
            try:
                with open("configs/strategy.json", "r", encoding="utf-8") as f:
                    strategy_data = json.load(f)
                APP_STATE.strategyChanged.emit({
                    'complete': True,
                    'target': strategy_data.get('target', ''),
                    'unit': strategy_data.get('unit', 0)
                })
            except:
                pass

        # 檢查 overlay 模板配置（從 positions.json 中讀取）
        template_ready = False
        try:
            if os.path.exists("configs/positions.json"):
                with open("configs/positions.json", "r", encoding="utf-8") as f:
                    pos_data = json.load(f)
                template_paths = pos_data.get("overlay_params", {}).get("template_paths", {})
                qing_path = template_paths.get("qing")
                template_ready = bool(qing_path and os.path.exists(qing_path))
        except:
            pass

        APP_STATE.templatesChanged.emit({
            'complete': template_ready,
            'missing': [] if template_ready else ['qing'],
            'total': 1 if template_ready else 0
        })