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
    # 全域訊號
    page_changed = Signal(str)
    status_changed = Signal(str, str)  # (component, status)

    def __init__(self):
        super().__init__()
        self.current_page = "home"
        self.setup_ui()
        self.setup_status_bar()
        self.setup_menu_bar()
        self.setup_toolbar()
        self.connect_signals()

    def setup_ui(self):
        """設定主要 UI 結構"""
        self.setWindowTitle("百家樂自動投注機器人 v1.0")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # 中央 widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主要佈局 (左右分割)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 建立分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # 左側導覽區
        self.setup_sidebar(splitter)

        # 右側內容區
        self.setup_content_area(splitter)

        # 設定分割器比例 (側邊欄:內容 = 1:4)
        splitter.setSizes([250, 1000])
        splitter.setChildrenCollapsible(False)

    def setup_sidebar(self, parent):
        """設定左側導覽欄"""
        sidebar_frame = QFrame()
        sidebar_frame.setFrameStyle(QFrame.StyledPanel)
        sidebar_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border-right: 2px solid #404040;
            }
        """)
        sidebar_frame.setMaximumWidth(280)
        sidebar_frame.setMinimumWidth(200)

        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(8, 8, 8, 8)

        # 標題
        title_label = QLabel("🎰 導覽選單")
        title_label.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                padding: 12px;
                background-color: #2d2d2d;
                border-radius: 6px;
                margin-bottom: 8px;
            }
        """)
        sidebar_layout.addWidget(title_label)

        # 導覽列表
        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet("""
            QListWidget {
                background-color: #252525;
                border: 1px solid #404040;
                border-radius: 6px;
                font-size: 10pt;
            }
            QListWidget::item {
                padding: 12px 16px;
                border-bottom: 1px solid #333333;
                border-radius: 4px;
                margin: 2px;
            }
            QListWidget::item:selected {
                background-color: #0e7490;
                color: #ffffff;
                font-weight: bold;
            }
            QListWidget::item:hover {
                background-color: #374151;
            }
        """)

        # 添加導覽項目
        nav_items = [
            ("🏠 首頁", "home"),
            ("🖼️ 模板管理", "templates"),
            ("📍 位置校準", "positions"),
            ("🎯 UI 門檻", "overlay"),
            ("⚙️ 策略設定", "strategy"),
            ("📡 事件來源", "events"),
            ("🎮 實戰主控台", "dashboard"),
            ("📊 記錄回放", "sessions"),
            ("🔧 系統設定", "settings")
        ]

        for text, page_id in nav_items:
            self.nav_list.addItem(text)

        self.nav_list.setCurrentRow(0)  # 預設選中首頁
        self.nav_list.currentRowChanged.connect(self.on_nav_changed)

        sidebar_layout.addWidget(self.nav_list)
        sidebar_layout.addStretch()

        parent.addWidget(sidebar_frame)

    def setup_content_area(self, parent):
        """設定右側內容區域"""
        content_frame = QFrame()
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(8, 8, 8, 8)

        # 頁面標題區
        self.page_title = QLabel("首頁")
        self.page_title.setFont(QFont("Microsoft YaHei UI", 14, QFont.Bold))
        self.page_title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                padding: 12px 16px;
                background-color: #374151;
                border-radius: 8px;
                margin-bottom: 8px;
            }
        """)
        content_layout.addWidget(self.page_title)

        # 建立堆疊頁面區域
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)

        # 添加各個頁面
        self.pages = {}
        home_page = HomePage()
        home_page.navigate_to.connect(self.switch_to_page)  # 連接首頁導覽信號
        self.add_page("home", home_page, "🏠 首頁")

        self.add_page("templates", TemplatesPage(), "🖼️ 模板管理")
        self.add_page("positions", PositionsPage(), "📍 位置校準")
        self.add_page("overlay", OverlayPage(), "🎯 UI 門檻")
        self.add_page("strategy", StrategyPage(), "⚙️ 策略設定")
        self.add_page("events", EventsPage(), "📡 事件來源")

        dashboard_page = DashboardPage()
        dashboard_page.navigate_to.connect(self.switch_to_page)  # 連接 Dashboard 導覽信號
        self.add_page("dashboard", dashboard_page, "🎮 實戰主控台")

        self.add_page("sessions", SessionsPage(), "📊 記錄回放")
        self.add_page("settings", SettingsPage(), "🔧 系統設定")

        parent.addWidget(content_frame)

    def add_page(self, page_id, widget, title):
        """添加頁面到堆疊器"""
        self.pages[page_id] = {
            'widget': widget,
            'title': title,
            'index': self.stacked_widget.addWidget(widget)
        }

    def setup_status_bar(self):
        """設定狀態列"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 狀態指示器
        self.status_indicators = {}

        # 事件來源狀態
        self.events_status = QLabel("🔌 未連線")
        self.events_status.setStyleSheet("color: #ef4444; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.events_status)

        # 乾跑狀態
        self.dryrun_status = QLabel("🧪 乾跑模式")
        self.dryrun_status.setStyleSheet("color: #10b981; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.dryrun_status)

        # DPI 狀態
        self.dpi_status = QLabel("🖥️ DPI: 1.0")
        self.dpi_status.setStyleSheet("color: #6b7280;")
        self.status_bar.addPermanentWidget(self.dpi_status)

        # 錯誤指示
        self.error_status = QLabel("✅ 正常")
        self.error_status.setStyleSheet("color: #10b981; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.error_status)

        # 預設訊息
        self.status_bar.showMessage("就緒 - 請選擇功能開始使用")

    def setup_menu_bar(self):
        """設定選單列"""
        menubar = self.menuBar()

        # 檔案選單
        file_menu = menubar.addMenu("檔案(&F)")

        open_config_action = QAction("開啟設定檔...", self)
        open_config_action.setShortcut("Ctrl+O")
        file_menu.addAction(open_config_action)

        save_config_action = QAction("儲存設定", self)
        save_config_action.setShortcut("Ctrl+S")
        file_menu.addAction(save_config_action)

        file_menu.addSeparator()

        exit_action = QAction("結束", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 檢視選單
        view_menu = menubar.addMenu("檢視(&V)")

        dashboard_action = QAction("主控台", self)
        dashboard_action.setShortcut("F1")
        dashboard_action.triggered.connect(lambda: self.switch_to_page("dashboard"))
        view_menu.addAction(dashboard_action)

        # 工具選單
        tools_menu = menubar.addMenu("工具(&T)")

        calibrate_action = QAction("校準位置", self)
        calibrate_action.triggered.connect(lambda: self.switch_to_page("positions"))
        tools_menu.addAction(calibrate_action)

        test_templates_action = QAction("檢查模板", self)
        test_templates_action.triggered.connect(lambda: self.switch_to_page("templates"))
        tools_menu.addAction(test_templates_action)

        # 說明選單
        help_menu = menubar.addMenu("說明(&H)")

        about_action = QAction("關於", self)
        help_menu.addAction(about_action)

    def setup_toolbar(self):
        """設定工具列"""
        toolbar = QToolBar("主要工具列")
        self.addToolBar(toolbar)

        # 快速動作按鈕
        dashboard_action = QAction("🎮 主控台", self)
        dashboard_action.triggered.connect(lambda: self.switch_to_page("dashboard"))
        toolbar.addAction(dashboard_action)

        toolbar.addSeparator()

        positions_action = QAction("📍 校準", self)
        positions_action.triggered.connect(lambda: self.switch_to_page("positions"))
        toolbar.addAction(positions_action)

        overlay_action = QAction("🎯 門檻", self)
        overlay_action.triggered.connect(lambda: self.switch_to_page("overlay"))
        toolbar.addAction(overlay_action)

        toolbar.addSeparator()

        # 快速控制 (這些需要連接到實際功能)
        self.dryrun_toggle_action = QAction("🧪 乾跑", self)
        self.dryrun_toggle_action.setCheckable(True)
        self.dryrun_toggle_action.setChecked(True)
        toolbar.addAction(self.dryrun_toggle_action)

    def connect_signals(self):
        """連接訊號"""
        # 定時更新狀態 (每秒)
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)

    def on_nav_changed(self, index):
        """導覽選擇改變"""
        page_ids = ["home", "templates", "positions", "overlay", "strategy",
                   "events", "dashboard", "sessions", "settings"]

        if 0 <= index < len(page_ids):
            page_id = page_ids[index]
            self.switch_to_page(page_id)

    def switch_to_page(self, page_id):
        """切換到指定頁面"""
        if page_id in self.pages:
            page_info = self.pages[page_id]
            self.stacked_widget.setCurrentIndex(page_info['index'])
            self.page_title.setText(page_info['title'])
            self.current_page = page_id
            self.page_changed.emit(page_id)

            # 更新導覽列表選中狀態
            page_ids = ["home", "templates", "positions", "overlay", "strategy",
                       "events", "dashboard", "sessions", "settings"]
            if page_id in page_ids:
                self.nav_list.setCurrentRow(page_ids.index(page_id))

    def update_status(self):
        """更新狀態列資訊"""
        # 這裡之後會連接真實的狀態資訊
        pass

    def update_status_indicator(self, component, status, color="white"):
        """更新特定狀態指示器"""
        if component == "events":
            self.events_status.setText(f"🔌 {status}")
            self.events_status.setStyleSheet(f"color: {color}; font-weight: bold;")
        elif component == "dryrun":
            icon = "🧪" if status == "乾跑模式" else "⚡"
            self.dryrun_status.setText(f"{icon} {status}")
            color = "#10b981" if status == "乾跑模式" else "#ef4444"
            self.dryrun_status.setStyleSheet(f"color: {color}; font-weight: bold;")
        elif component == "error":
            icon = "✅" if status == "正常" else "⚠️"
            self.error_status.setText(f"{icon} {status}")
            color = "#10b981" if status == "正常" else "#ef4444"
            self.error_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def show_message(self, message, timeout=3000):
        """在狀態列顯示臨時訊息"""
        self.status_bar.showMessage(message, timeout)