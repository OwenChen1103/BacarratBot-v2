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
        self.add_page("home", home_page, "🏠 首頁")

        self.add_page("templates", TemplatesPage(), "🖼️ 模板管理")
        self.add_page("positions", PositionsPage(), "📍 位置校準")
        self.add_page("overlay", OverlayPage(), "🎯 UI 門檻")
        self.add_page("strategy", StrategyPage(), "⚙️ 策略設定")

        dashboard_page = DashboardPage()
        dashboard_page.navigate_to.connect(self.switch_to_page)
        self.add_page("dashboard", dashboard_page, "🎮 實戰主控台")

        self.add_page("events", EventsPage(), "📡 事件來源")
        self.add_page("sessions", SessionsPage(), "📊 記錄回放")
        self.add_page("settings", SettingsPage(), "🔧 系統設定")

        self.nav.setCurrentRow(0)

        # 選單（最少可用）
        self._build_menu()

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