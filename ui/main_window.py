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
from .pages.page_overlay import OverlayPage
from .pages.page_chip_profile import ChipProfilePage
from .pages.page_strategy import StrategyPage
from .pages.page_events import EventsPage
from .pages.page_dashboard import DashboardPage
from .pages.page_sessions import SessionsPage
from .pages.page_settings import SettingsPage
from .pages.page_live_monitor import LiveMonitorPage
from .pages.page_result_detection import PageResultDetection
from .widgets.compact_monitor_window import CompactMonitorWindow
from .app_state import APP_STATE
from .components.toast import show_toast
from .dialogs.setup_wizard import SetupWizard
from src.utils.config_validator import ConfigValidator

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
        self.status_label = QLabel("準備就緒（預設乾跑）")
        self.status.addPermanentWidget(self.status_label)

        # 頁面註冊
        self.pages = {}
        home_page = HomePage()
        home_page.navigate_to.connect(self.switch_to_page)
        self.add_page("home", home_page, "首頁")

        # ===== 主要功能（常用） =====
        dashboard_page = DashboardPage()
        dashboard_page.navigate_to.connect(self.switch_to_page)
        self.add_page("dashboard", dashboard_page, "實戰主控台")

        self.add_page("chip_profile", ChipProfilePage(), "籌碼設定")
        self.add_page("strategy", StrategyPage(), "策略設定")

        # ===== 珠盤檢測設定 =====
        self.add_page("result_detection", PageResultDetection(), "珠盤檢測設定")

        # ===== 輔助功能（較少使用，可選） =====
        # self.add_page("templates", TemplatesPage(), "模板管理")  # 隱藏：很少使用
        self.add_page("overlay", OverlayPage(), "可下注判斷")
        # self.add_page("live_monitor", LiveMonitorPage(), "即時監控")  # 隱藏：已整合到Dashboard
        # self.add_page("events", EventsPage(), "事件來源")  # 暫時移除，直接使用 overlay 檢測
        self.add_page("sessions", SessionsPage(), "記錄回放")
        self.add_page("settings", SettingsPage(), "系統設定")

        self.nav.setCurrentRow(0)

        # 精簡監控視窗（初始隱藏）
        self.compact_monitor = None

        # 選單（最少可用）
        self._build_menu()

        # 連接全域事件
        self._connect_app_state()

        # 初始化時檢查現有配置狀態
        self._check_initial_state()

        # 延遲顯示設定精靈 (讓主視窗先顯示)
        QTimer.singleShot(500, self._show_setup_wizard_if_needed)

    def _build_menu(self):
        menubar = self.menuBar()

        # 檔案選單
        file_menu = menubar.addMenu("檔案")
        act_quit = QAction("離開", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # 視窗選單
        view_menu = menubar.addMenu("視窗")
        self.act_compact_monitor = QAction("精簡監控視窗", self)
        self.act_compact_monitor.setCheckable(True)
        self.act_compact_monitor.setShortcut("F9")
        self.act_compact_monitor.triggered.connect(self.toggle_compact_monitor)
        view_menu.addAction(self.act_compact_monitor)

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

        # 檢查線路策略 (新系統)
        strategy_dir = "configs/line_strategies"
        if os.path.exists(strategy_dir):
            try:
                strategy_files = [f for f in os.listdir(strategy_dir) if f.endswith('.json')]
                if strategy_files:
                    APP_STATE.strategyChanged.emit({
                        'complete': True,
                        'count': len(strategy_files)
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

    def _show_setup_wizard_if_needed(self):
        """顯示設定精靈 (如果需要)"""
        # 檢查是否跳過精靈
        settings_path = "configs/settings.json"
        skip_wizard = False

        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    skip_wizard = settings.get("skip_setup_wizard", False)
            except:
                pass

        if skip_wizard:
            return

        # 檢查配置完整度
        validator = ConfigValidator()
        summary = validator.get_config_summary()

        # 如果未完成,顯示精靈
        if not summary['ready_for_battle']:
            wizard = SetupWizard(self)
            result = wizard.exec()

            # 儲存「不再顯示」偏好
            if wizard.should_save_preference():
                self._save_wizard_preference(True)

            # 如果用戶點擊「前往設定」,跳轉到對應頁面
            if result == SetupWizard.Accepted:
                target_page = wizard.get_target_page()
                if target_page:
                    page_mapping = {
                        "chip_setup": "chip_profile",
                        "roi_setup": "overlay",
                        "strategy_setup": "strategy",
                        "overlay_setup": "overlay",
                    }
                    page_key = page_mapping.get(target_page)
                    if page_key:
                        self.switch_to_page(page_key)

    def _save_wizard_preference(self, skip: bool):
        """儲存精靈偏好設定"""
        import json
        settings_path = "configs/settings.json"
        settings = {}

        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            except:
                pass

        settings["skip_setup_wizard"] = skip

        try:
            os.makedirs("configs", exist_ok=True)
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"儲存設定失敗: {e}")

    def toggle_compact_monitor(self, checked: bool):
        """切換精簡監控視窗（F9 快捷鍵）"""
        if checked:
            if not self.compact_monitor:
                # 創建精簡監控視窗
                self.compact_monitor = CompactMonitorWindow()
                self.compact_monitor.emergency_stop_clicked.connect(self._on_compact_emergency_stop)
                self.compact_monitor.show_main_window_clicked.connect(self._on_show_main_from_compact)

                # 連接 Dashboard 的狀態更新信號
                if "dashboard" in self.pages:
                    dashboard = self.pages["dashboard"]

                    # 狀態更新
                    dashboard.compact_status_updated.connect(
                        self.compact_monitor.update_status
                    )

                    # 策略資訊更新
                    dashboard.compact_strategy_updated.connect(
                        self.compact_monitor.update_strategy
                    )

                    # 盈虧更新
                    dashboard.compact_pnl_updated.connect(
                        self.compact_monitor.update_pnl
                    )

                    # 下注狀態更新
                    dashboard.compact_bet_status_updated.connect(
                        self.compact_monitor.update_bet_status
                    )

                    # 歷史記錄更新
                    print("[MainWindow] Connecting compact_history_updated signal to compact_monitor.update_history")
                    dashboard.compact_history_updated.connect(
                        self.compact_monitor.update_history
                    )
                    print("[MainWindow] Signal connected successfully")

                    # 警告訊息
                    dashboard.compact_warning.connect(
                        self.compact_monitor.show_warning
                    )
                    dashboard.compact_warning_clear.connect(
                        self.compact_monitor.hide_warning
                    )

            self.compact_monitor.show()
        else:
            if self.compact_monitor:
                self.compact_monitor.hide()

    def _on_compact_emergency_stop(self):
        """從精簡視窗觸發緊急停止"""
        if "dashboard" in self.pages:
            dashboard = self.pages["dashboard"]
            dashboard.stop_engine()  # 停止引擎

    def _on_show_main_from_compact(self):
        """從精簡視窗顯示主視窗"""
        self.show()
        self.raise_()
        self.activateWindow()