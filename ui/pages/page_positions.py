# ui/pages/page_positions.py
import json
import os
import time
import logging
from collections import OrderedDict
from typing import Dict, List, Tuple, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QHBoxLayout, QGridLayout, QFrame, QComboBox,
    QCheckBox, QScrollArea, QTextEdit, QSplitter, QGroupBox,
    QDoubleSpinBox, QButtonGroup, QRadioButton
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal, QPoint
from PySide6.QtGui import (
    QFont, QPixmap, QPainter, QPen, QColor, QBrush,
    QKeySequence, QShortcut, QCursor, QGuiApplication
)

from ._utils_positions import (
    get_all_screens, create_backup_filename, validate_position_schema,
    calculate_coordinate_scale, apply_coordinate_transform, get_magnifier_region
)
from ..workers.engine_worker import EngineWorker
from src.autobet.actuator import Actuator
from ..app_state import APP_STATE, emit_toast

logger = logging.getLogger(__name__)

POSITIONS_FILE = "configs/positions.json"
SCREENSHOT_FILE = "data/screenshots/calib.png"

class PositionsPage(QWidget):
    """位置校準頁面（完整功能版）：
    - 多鍵位就緒狀態 & Reset/Undo
    - 存檔合併 + 自動備份 + Schema 檢查
    - 座標可靠性（DPI/多螢幕）
    - 視覺標記與 Try Click（Dry-run）
    - 健康檢查與防呆
    - 鍵盤快捷鍵支持
    """
    unsaved_changes = Signal(bool)
    def __init__(self, engine_worker: Optional[EngineWorker] = None):
        super().__init__()
        self.engine_worker = engine_worker
        self.screenshot_path = SCREENSHOT_FILE
        self.current_screen_index = 0
        self.screens_info = get_all_screens()
        self.active_key = None
        self.buttons = {}
        self.status_badges = {}
        self.reset_buttons = {}
        self.preview_max_width = 900
        self.has_unsaved_changes = False
        self.undo_stack = []  # 只保存一層 undo
        self.mouse_pos = None
        self.magnifier_timer = QTimer()
        self.magnifier_timer.timeout.connect(self.update_magnifier)
        self.magnifier_timer.start(50)  # 50ms 更新頻率

        # 初始 positions 容器
        self.positions = {
            "version": 2,
            "description": "GUI Positions Calibrator",
            "screen": {"width": 1920, "height": 1080, "dpi_scale": 1.0},
            "points": {},
            "roi": {
                "overlay": {"x": 1450, "y": 360, "w": 420, "h": 50},
                "player_stack": {"x": 720, "y": 670, "w": 120, "h": 60},
                "banker_stack": {"x": 1140, "y": 670, "w": 120, "h": 60},
                "tie_stack": {"x": 930, "y": 620, "w": 120, "h": 60}
            },
            "validation": {"min_click_gap_ms": 40}
        }

        # 原始截圖（用於準確座標計算）
        self.original_pixmap = None

        # 鍵位配置（順序對應數字鍵 1-7）
        self.key_meta = OrderedDict([
            ("banker",  "莊 banker"),
            ("player",  "閒 player"),
            ("tie",     "和 tie"),
            ("confirm", "確認 confirm"),
            ("cancel",  "取消 cancel"),
            ("chip_1k", "籌碼 1k"),
            ("chip_100","籌碼 100"),
        ])

        # 必要點位（健康檢查用）
        self.required_keys = ["banker", "chip_1k", "confirm"]

        # 顏色配置
        self.key_colors = {
            "banker":  "#ef4444",
            "player":  "#10b981",
            "tie":     "#f59e0b",
            "confirm": "#60a5fa",
            "cancel":  "#a3a3a3",
            "chip_1k": "#8b5cf6",
            "chip_100":"#f472b6",
        }

        # 創建 actuator 實例用於 dry-run 測試
        self.actuator = None

        # 測試模式與計時器狀態
        self.test_mode = "dry"          # "dry" | "move"
        self.step_delay_ms = 2000       # 預設 2 秒
        self._test_timer = None
        self._test_queue = []
        self._test_idx = 0

        self.setup_ui()
        self.setup_shortcuts()
        self.load_positions_file()
        self.refresh_preview()
        self.update_screen_info()
        self.check_health()

        # 縮放狀態
        self.zoom = 100
        self.fit_width = True

    # ---------- UI Setup ----------
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # 標題列 - 包含螢幕信息
        self.setup_header(main_layout)

        # 主面板 - 水平分割
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # 左邊 - 截圖預覽與放大鏡
        left_panel = self.create_preview_panel()
        self.splitter.addWidget(left_panel)

        # 右邊 - 控制面板
        right_panel = self.create_control_panel()
        self.splitter.addWidget(right_panel)

        # 設定分割比例（右欄預設較窄）
        self.splitter.setSizes([max(320, self.width() - 380), 380])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        # 狀態列
        self.status_label = QLabel("狀態：等待操作")
        self.status_label.setStyleSheet("color: #10b981; font-weight: bold; padding: 4px;")
        main_layout.addWidget(self.status_label)

    def create_bottom_panel(self):
        # 已復原：不再使用底部分頁
        container = QWidget()
        return container

    def setup_header(self, layout):
        """設定標題區域"""
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        header_layout = QVBoxLayout(header)

        title_row = QHBoxLayout()
        title = QLabel("📍 位置校準（完整版）")
        title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        title.setStyleSheet("color: #f3f4f6;")
        title_row.addWidget(title)

        # 復原：移除 Zoom/Fit/收合控制
        title_row.addStretch()
        header_layout.addLayout(title_row)

        # 螢幕信息列
        screen_row = QHBoxLayout()
        screen_row.addWidget(QLabel("螢幕:"))

        self.screen_combo = QComboBox()
        self.screen_combo.currentIndexChanged.connect(self.on_screen_changed)
        screen_row.addWidget(self.screen_combo)

        self.screen_info_label = QLabel("無螢幕")
        self.screen_info_label.setStyleSheet("color: #9ca3af; font-family: monospace;")
        screen_row.addWidget(self.screen_info_label)

        screen_row.addStretch()
        header_layout.addLayout(screen_row)

        layout.addWidget(header)

    def create_preview_panel(self):
        """創建預覽面板"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(panel)

        # 操作按鈕列
        btn_row = QHBoxLayout()
        btn_cap = self.create_styled_button("截取螢幕", "#1e40af", self.capture_screen)
        btn_load = self.create_styled_button("載入截圖", "#059669", self.load_existing)
        btn_row.addWidget(btn_cap)
        btn_row.addWidget(btn_load)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 縮放控制列
        zoom_row = QHBoxLayout()
        self.fit_width_chk = QCheckBox("Fit width")
        self.fit_width_chk.setChecked(True)
        self.fit_width_chk.stateChanged.connect(lambda _: self.on_zoom_changed())

        from PySide6.QtWidgets import QSlider
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(lambda _: self.on_zoom_changed())

        reset_btn = self.create_styled_button("100%", "#374151", self.reset_zoom)

        zoom_row.addWidget(QLabel("縮放"))
        zoom_row.addWidget(self.zoom_slider)
        zoom_row.addWidget(self.fit_width_chk)
        zoom_row.addWidget(reset_btn)
        layout.addLayout(zoom_row)

        # 預覽區域
        preview_container = QFrame()
        preview_layout = QHBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # 截圖預覽（包在可調整大小的 ScrollArea 內）
        self.preview = QLabel("請先截圖或載入截圖")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(400)
        self.preview.setStyleSheet("""
            QLabel {
                border: 1px dashed #6b7280;
                background-color: #1f2937;
                color: #9ca3af;
                border-radius: 4px;
            }
        """)
        self.preview.mousePressEvent = self.on_click
        self.preview.mouseMoveEvent = self.on_mouse_move

        from PySide6.QtWidgets import QScrollArea
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        # 復原：水平捲軸預設關閉，避免影響原版面
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_scroll.setFrameShape(QFrame.NoFrame)
        self.preview_scroll.setWidget(self.preview)
        preview_layout.addWidget(self.preview_scroll)

        # 放大鏡改為疊加在 preview 右上角
        self.magnifier = QLabel(self.preview)
        self.magnifier.setText("放大鏡")
        self.magnifier.setFixedSize(100, 100)
        self.magnifier.setStyleSheet("""
            QLabel {
                border: 2px solid #60a5fa;
                background-color: #1f2937;
                color: #9ca3af;
                border-radius: 4px;
            }
        """)
        self.magnifier.setAlignment(Qt.AlignCenter)
        self.magnifier.raise_()
        self.magnifier.move(self.preview.width() - self.magnifier.width() - 8, 8)

        layout.addWidget(preview_container)
        return panel

    def create_control_panel(self):
        """創建控制面板"""
        panel = QScrollArea()
        panel.setWidgetResizable(True)
        panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(380)

        content = QWidget()
        layout = QVBoxLayout(content)

        # 鍵位控制組
        self.setup_key_controls(layout)

        # 保存操作組
        self.setup_save_controls(layout)

        layout.addStretch()
        panel.setWidget(content)
        return panel

    def create_styled_button(self, text: str, color: str, callback, tooltip: str = ""):
        """創建統一樣式的按鈕"""
        btn = QPushButton(text)
        btn.clicked.connect(callback)
        if tooltip:
            btn.setToolTip(tooltip)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.1);
            }}
            QPushButton:disabled {{
                background: #374151;
                color: #6b7280;
            }}
        """)
        return btn

    def setup_header(self, layout):
        """設定標題區域"""
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        header_layout = QVBoxLayout(header)

        title = QLabel("📍 位置校準（完整版）")
        title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        title.setStyleSheet("color: #f3f4f6;")
        header_layout.addWidget(title)

        # 螢幕信息列
        screen_row = QHBoxLayout()
        screen_row.addWidget(QLabel("螢幕:"))

        self.screen_combo = QComboBox()
        self.screen_combo.currentIndexChanged.connect(self.on_screen_changed)
        screen_row.addWidget(self.screen_combo)

        self.screen_info_label = QLabel("無螢幕")
        self.screen_info_label.setStyleSheet("color: #9ca3af; font-family: monospace;")
        screen_row.addWidget(self.screen_info_label)

        screen_row.addStretch()
        header_layout.addLayout(screen_row)

        layout.addWidget(header)

    def create_preview_panel(self):
        """創建預覽面板"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(panel)

        # 操作按鈕列
        btn_row = QHBoxLayout()
        btn_cap = self.create_styled_button("截取螢幕", "#1e40af", self.capture_screen)
        btn_load = self.create_styled_button("載入截圖", "#059669", self.load_existing)
        btn_row.addWidget(btn_cap)
        btn_row.addWidget(btn_load)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 預覽區域
        preview_container = QFrame()
        preview_layout = QHBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # 截圖預覽（使用 ScrollArea 包住，並將放大鏡疊加在預覽上）
        self.preview = QLabel("請先截圖或載入截圖")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(400)
        self.preview.setStyleSheet("""
            QLabel {
                border: 1px dashed #6b7280;
                background-color: #1f2937;
                color: #9ca3af;
                border-radius: 4px;
            }
        """)
        self.preview.mousePressEvent = self.on_click
        self.preview.mouseMoveEvent = self.on_mouse_move

        from PySide6.QtWidgets import QScrollArea
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_scroll.setFrameShape(QFrame.NoFrame)
        self.preview_scroll.setWidget(self.preview)
        preview_layout.addWidget(self.preview_scroll)

        # 放大鏡改為疊加在 preview 右上角
        self.magnifier = QLabel(self.preview)
        self.magnifier.setText("放大鏡")
        self.magnifier.setFixedSize(100, 100)
        self.magnifier.setStyleSheet("""
            QLabel {
                border: 2px solid #60a5fa;
                background-color: #1f2937;
                color: #9ca3af;
                border-radius: 4px;
            }
        """)
        self.magnifier.setAlignment(Qt.AlignCenter)
        self.magnifier.raise_()

        layout.addWidget(preview_container)
        return panel

    def create_control_panel(self):
        """創建控制面板"""
        panel = QScrollArea()
        panel.setWidgetResizable(True)
        panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)

        # 右欄可收合
        toggle_btn = self.create_styled_button("⟨ 收合右欄", "#374151", self.toggle_sidebar)
        layout.addWidget(toggle_btn)

        # 鍵位控制組
        self.setup_key_controls(layout)

        # 健康檢查組
        self.setup_health_check(layout)

        # Try Click 組
        self.setup_try_click(layout)

        # 保存操作組
        self.setup_save_controls(layout)

        layout.addStretch()
        panel.setWidget(content)
        return panel

    def create_styled_button(self, text: str, color: str, callback, tooltip: str = ""):
        """創建統一樣式的按鈕"""
        btn = QPushButton(text)
        btn.clicked.connect(callback)
        if tooltip:
            btn.setToolTip(tooltip)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.1);
            }}
            QPushButton:disabled {{
                background: #374151;
                color: #6b7280;
            }}
        """)
        return btn

    def setup_key_controls(self, layout):
        """設定鍵位控制組"""
        group = QGroupBox("🎯 鍵位設定")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #f3f4f6;
                border: 2px solid #374151;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        group_layout = QVBoxLayout(group)

        # 全域操作按鈕
        global_controls = QHBoxLayout()
        self.undo_btn = self.create_styled_button("Undo", "#f59e0b", self.undo_last_change, "Ctrl+Z")
        self.undo_btn.setEnabled(False)
        global_controls.addWidget(self.undo_btn)
        global_controls.addStretch()
        group_layout.addLayout(global_controls)

        # 鍵位按鈕網格
        keys_grid = QGridLayout()
        keys_grid.setSpacing(4)

        for i, (key, label) in enumerate(self.key_meta.items()):
            row, col = divmod(i, 2)

            # 主按鈕
            btn = QPushButton(f"{i+1}. {label}")
            btn.setCheckable(True)
            btn.setMinimumHeight(35)
            btn.clicked.connect(lambda checked, k=key: self.set_active_key(k))
            self.buttons[key] = btn

            # 狀態徽章
            badge = QLabel("✗")
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedSize(20, 20)
            badge.setStyleSheet("""
                QLabel {
                    background: #dc2626;
                    color: white;
                    border-radius: 10px;
                    font-weight: bold;
                    font-size: 12px;
                }
            """)
            self.status_badges[key] = badge

            # Reset 按鈕
            reset_btn = QPushButton("R")
            reset_btn.setFixedSize(25, 25)
            reset_btn.setToolTip(f"Reset {key}")
            reset_btn.clicked.connect(lambda _, k=key: self.reset_key(k))
            reset_btn.setStyleSheet("""
                QPushButton {
                    background: #6b7280;
                    color: white;
                    border: none;
                    border-radius: 12px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #ef4444;
                }
            """)
            self.reset_buttons[key] = reset_btn

            # 佈局
            key_row = QHBoxLayout()
            key_row.addWidget(btn)
            key_row.addWidget(badge)
            key_row.addWidget(reset_btn)

            keys_grid.addLayout(key_row, row, col)

        group_layout.addLayout(keys_grid)
        layout.addWidget(group)

    def setup_health_check(self, layout):
        """設定健康檢查組"""
        group = QGroupBox("👨‍⚕️ 健康檢查")
        group.setStyleSheet(group.styleSheet())  # 繼承樣式
        group_layout = QVBoxLayout(group)

        # 檢查按鈕
        check_btn = self.create_styled_button("立即檢查", "#8b5cf6", self.check_health)
        group_layout.addWidget(check_btn)

        # 檢查結果
        self.health_result = QLabel("尚未檢查")
        self.health_result.setWordWrap(True)
        self.health_result.setStyleSheet("""
            QLabel {
                background: #1f2937;
                color: #9ca3af;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 8px;
                min-height: 60px;
            }
        """)
        group_layout.addWidget(self.health_result)

        layout.addWidget(group)

    def setup_try_click(self, layout):
        """設定 Try Click 組"""
        group = QGroupBox("🔄 測試模式")
        group.setStyleSheet(group.styleSheet())  # 繼承樣式
        group_layout = QVBoxLayout(group)

        # 模式選擇與延遲控制 - 使用互斥的 RadioButton
        mode_bar = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.btn_dry = QRadioButton("Dry-run")
        self.btn_move = QRadioButton("Move-only")
        self.btn_dry.setChecked(True)

        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.btn_dry)
        self.mode_group.addButton(self.btn_move)

        self.btn_dry.toggled.connect(lambda c: self.on_mode_changed("dry") if c else None)
        self.btn_move.toggled.connect(lambda c: self.on_mode_changed("move") if c else None)

        delay_lbl = QLabel("Delay (s)")
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.2, 5.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setValue(self.step_delay_ms/1000)
        self.delay_spin.valueChanged.connect(lambda v: setattr(self, "step_delay_ms", int(v*1000)))

        mode_bar.addWidget(self.btn_dry)
        mode_bar.addWidget(self.btn_move)
        mode_bar.addSpacing(10)
        mode_bar.addWidget(delay_lbl)
        mode_bar.addWidget(self.delay_spin)
        mode_bar.addStretch()
        group_layout.addLayout(mode_bar)

        # Try Click 按鈕
        try_controls = QHBoxLayout()
        try_current_btn = self.create_styled_button("測試當前", "#10b981", self.on_test_current)
        try_all_btn = self.create_styled_button("測試全部", "#f59e0b", self.on_test_all)
        try_controls.addWidget(try_current_btn)
        try_controls.addWidget(try_all_btn)
        group_layout.addLayout(try_controls)

        # 日誌顯示
        self.log_display = QTextEdit()
        self.log_display.setMaximumHeight(120)
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("""
            QTextEdit {
                background: #111827;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
        """)
        group_layout.addWidget(self.log_display)

        layout.addWidget(group)

    def setup_save_controls(self, layout):
        """設定保存控制組"""
        group = QGroupBox("💾 保存控制")
        group.setStyleSheet(group.styleSheet())  # 繼承樣式
        group_layout = QVBoxLayout(group)

        # 變更狀態指示
        self.changes_indicator = QLabel("無更改")
        self.changes_indicator.setAlignment(Qt.AlignCenter)
        self.changes_indicator.setStyleSheet("""
            QLabel {
                background: #10b981;
                color: white;
                padding: 4px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
        group_layout.addWidget(self.changes_indicator)

        # 保存按鈕
        save_btn = self.create_styled_button("保存變更", "#dc2626", self.save_positions, "Ctrl+S")
        group_layout.addWidget(save_btn)

        layout.addWidget(group)

    def setup_shortcuts(self):
        """設定鍵盤快捷鍵"""
        # 數字鍵 1-7 對應鍵位切換
        for i, key in enumerate(self.key_meta.keys()):
            shortcut = QShortcut(QKeySequence(str(i + 1)), self)
            shortcut.activated.connect(lambda k=key: self.set_active_key(k))

        # Ctrl+S 保存
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self.save_positions)

        # Ctrl+Z Undo
        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self.undo_last_change)

    # ---------- 核心功能 ----------
    def _get_pixmap_display_rect(self):
        """回傳 pixmap 在 self.preview 裡的顯示矩形 (x, y, w, h)（置中補償後）"""
        pm = self.preview.pixmap()
        if not pm:
            return 0, 0, 0, 0
        lw, lh = self.preview.width(), self.preview.height()
        pw, ph = pm.width(), pm.height()
        ox = max(0, (lw - pw) // 2)
        oy = max(0, (lh - ph) // 2)
        return ox, oy, pw, ph
    def set_active_key(self, key: str):
        """設定當前活躍鍵位"""
        self.active_key = key
        for k, btn in self.buttons.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {"#2563eb" if k==key else "#374151"};
                    color: white; border: none; padding: 8px 12px;
                    border-radius: 6px; font-weight: bold;
                }}
                QPushButton:hover {{ background-color: rgba(255,255,255,0.1); }}
            """)
        self.status_ok(f"已選取鍵位：{key}（下一次點擊會設定此鍵）")

    def reset_key(self, key: str):
        """重設指定鍵位"""
        if key in self.positions.get("points", {}):
            # 保存到 undo stack
            self.save_undo_state()
            # 刪除鍵位
            del self.positions["points"][key]
            self.set_unsaved_changes(True)
            self.update_key_status()
            self.refresh_preview()
            self.status_ok(f"已重設鍵位：{key}")
        else:
            self.status_warn(f"鍵位 {key} 尚未設定")

    def undo_last_change(self):
        """撤銷上一次變更"""
        if not self.undo_stack:
            self.status_warn("無可撤銷的操作")
            return

        self.positions["points"] = self.undo_stack.pop().copy()
        self.set_unsaved_changes(True)
        self.update_key_status()
        self.refresh_preview()
        self.undo_btn.setEnabled(len(self.undo_stack) > 0)
        self.status_ok("已撤銷上一次變更")

    def save_undo_state(self):
        """保存當前狀態到 undo stack"""
        current_points = self.positions.get("points", {}).copy()
        self.undo_stack.append(current_points)
        # 只保留最近一次
        if len(self.undo_stack) > 1:
            self.undo_stack = self.undo_stack[-1:]
        self.undo_btn.setEnabled(True)

    def update_key_status(self):
        """更新鍵位狀態徽章"""
        points = self.positions.get("points", {})
        for key, badge in self.status_badges.items():
            if key in points:
                badge.setText("✓")
                badge.setStyleSheet("""
                    QLabel {
                        background: #10b981;
                        color: white;
                        border-radius: 10px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                """)
            else:
                badge.setText("✗")
                badge.setStyleSheet("""
                    QLabel {
                        background: #dc2626;
                        color: white;
                        border-radius: 10px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                """)

    def set_unsaved_changes(self, has_changes: bool):
        """設定未保存變更狀態"""
        self.has_unsaved_changes = has_changes
        self.unsaved_changes.emit(has_changes)

        if has_changes:
            self.changes_indicator.setText("有未保存更改")
            self.changes_indicator.setStyleSheet("""
                QLabel {
                    background: #f59e0b;
                    color: white;
                    padding: 4px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
        else:
            self.changes_indicator.setText("無更改")
            self.changes_indicator.setStyleSheet("""
                QLabel {
                    background: #10b981;
                    color: white;
                    padding: 4px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)

    def on_screen_changed(self, index: int):
        """螢幕選擇變更"""
        if 0 <= index < len(self.screens_info):
            self.current_screen_index = index
            self.update_screen_info()
            self.status_ok(f"已切換到螢幕 {index + 1}")

    def update_screen_info(self):
        """更新螢幕信息顯示"""
        # 暫時斷開信號連接以避免遞歸
        self.screen_combo.currentIndexChanged.disconnect()

        try:
            self.screen_combo.clear()

            if not self.screens_info:
                self.screen_info_label.setText("無可用螢幕")
                return

            for i, screen in enumerate(self.screens_info):
                geom = screen['geometry']
                name = screen.get('name', f'Screen {i+1}')
                self.screen_combo.addItem(f"{i+1}. {name}")

            if self.current_screen_index < len(self.screens_info):
                self.screen_combo.setCurrentIndex(self.current_screen_index)
                screen = self.screens_info[self.current_screen_index]
                geom = screen['geometry']
                dpr = screen.get('device_pixel_ratio', 1.0)
                info_text = f"{geom['width']}x{geom['height']} @{dpr:.1f}x"
                self.screen_info_label.setText(info_text)

        finally:
            # 重新連接信號
            self.screen_combo.currentIndexChanged.connect(self.on_screen_changed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 動態調整預覽最大寬度：以 splitter 左側寬度為準，留少量邊距
        left_width = self.splitter.sizes()[0] if hasattr(self, 'splitter') else self.width()
        available = max(320, left_width - 20)
        if available != self.preview_max_width:
            self.preview_max_width = available
            self.refresh_preview()

        # 重新定位疊加放大鏡
        if hasattr(self, "magnifier") and self.magnifier.parent() is self.preview:
            mw, mh = self.magnifier.width(), self.magnifier.height()
            self.magnifier.move(self.preview.width() - mw - 8, 8)

    def _on_splitter_moved(self, pos, index):
        try:
            left_width = self.splitter.sizes()[0]
            available = max(320, left_width - 20)
            if available != self.preview_max_width:
                self.preview_max_width = available
                self.refresh_preview()
        except Exception:
            pass

    def on_zoom_changed(self):
        self.zoom = self.zoom_slider.value()
        self.fit_width = self.fit_width_chk.isChecked()
        self.refresh_preview()

    def reset_zoom(self):
        self.zoom_slider.setValue(100)
        self.fit_width_chk.setChecked(True)

    def on_preview_wheel(self, event):
        if QGuiApplication.keyboardModifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            step = 5 if abs(delta) < 120 else 10
            new_val = max(10, min(200, self.zoom + (step if delta > 0 else -step)))
            self.zoom_slider.setValue(new_val)
            event.accept()
        else:
            super(type(self.preview), self.preview).wheelEvent(event)

    def toggle_sidebar(self):
        if not hasattr(self, "splitter"):
            return
        sizes = self.splitter.sizes()
        # 已收合：展開
        if sizes[1] < 40:
            self.splitter.setSizes([max(320, self.width()-360), 360])
        else:
            # 收到最小
            self.splitter.setSizes([self.width()-12, 12])

    

    def capture_screen(self):
        """截取選定螢幕"""
        try:
            os.makedirs(os.path.dirname(self.screenshot_path), exist_ok=True)

            if not self.screens_info:
                return self.status_err("無可用螢幕")

            if self.current_screen_index >= len(self.screens_info):
                self.current_screen_index = 0

            app = QGuiApplication.instance()
            screen = app.screens()[self.current_screen_index]

            # 截圖
            img = screen.grabWindow(0)
            img.save(self.screenshot_path)

            # 更新螢幕信息到 positions
            geom = screen.geometry()
            self.positions["screen"] = {
                "width": geom.width(),
                "height": geom.height(),
                "dpi_scale": screen.devicePixelRatio()
            }

            self.original_pixmap = QPixmap(self.screenshot_path)
            self.refresh_preview()
            self.status_ok(f"截圖完成（螢幕 {self.current_screen_index + 1}）")

        except Exception as e:
            self.status_err(f"截圖失敗：{e}")

    def load_existing(self):
        """載入既有截圖"""
        if os.path.exists(self.screenshot_path):
            self.original_pixmap = QPixmap(self.screenshot_path)
            self.refresh_preview()
            self.status_ok("已載入截圖")
        else:
            self.status_warn("尚無截圖，請先截取螢幕")

    def on_click(self, event):
        """處理預覽區域點擊"""
        if not self.preview.pixmap() or not self.original_pixmap:
            return self.status_warn("請先載入截圖")

        if not self.active_key:
            return self.status_warn("請先選擇要設定的鍵位")

        try:
            # 考慮置中補償與邊界
            ox, oy, pw, ph = self._get_pixmap_display_rect()
            ex = int(event.position().x())
            ey = int(event.position().y())
            if ex < ox or ey < oy or ex > ox + pw or ey > oy + ph:
                return

            # 轉為圖內座標
            lx, ly = ex - ox, ey - oy

            # 計算縮放比例和實際座標
            display_pixmap = self.preview.pixmap()
            scale = calculate_coordinate_scale(
                (self.original_pixmap.width(), self.original_pixmap.height()),
                (display_pixmap.width(), display_pixmap.height())
            )

            actual_x, actual_y = apply_coordinate_transform(lx, ly, scale)

            # 保存 undo 狀態
            self.save_undo_state()

            # 寫入座標
            self.positions.setdefault("points", {})
            self.positions["points"][self.active_key] = {"x": actual_x, "y": actual_y}

            self.set_unsaved_changes(True)
            self.update_key_status()
            self.refresh_preview()
            self.check_health()  # 自動健康檢查

            self.status_ok(f"[{self.active_key}] → ({actual_x}, {actual_y})")

        except Exception as e:
            self.status_err(f"座標計算失敗：{e}")

    def on_mouse_move(self, event):
        """處理鼠標移動（更新座標顯示和放大鏡）"""
        if self.preview.pixmap() and self.original_pixmap:
            display_pixmap = self.preview.pixmap()
            ox, oy, pw, ph = self._get_pixmap_display_rect()
            ex = int(event.position().x())
            ey = int(event.position().y())
            # 在圖外直接忽略/提示
            if ex < ox or ey < oy or ex > ox + pw or ey > oy + ph:
                self.status_label.setText("狀態：游標在圖外")
                return

            lx, ly = ex - ox, ey - oy

            scale = calculate_coordinate_scale(
                (self.original_pixmap.width(), self.original_pixmap.height()),
                (display_pixmap.width(), display_pixmap.height())
            )

            actual_x, actual_y = apply_coordinate_transform(lx, ly, scale)

            self.mouse_pos = (actual_x, actual_y)

            # 更新狀態顯示座標
            if self.active_key:
                self.status_label.setText(f"狀態：{self.active_key} - 游標位置 ({actual_x}, {actual_y})")
            else:
                self.status_label.setText(f"狀態：游標位置 ({actual_x}, {actual_y})")

    def update_magnifier(self):
        """更新放大鏡顯示"""
        if not self.original_pixmap or not self.mouse_pos or self.original_pixmap.isNull():
            return

        try:
            x, y = self.mouse_pos

            # 安全地獲取放大鏡區域
            magnified = get_magnifier_region(self.original_pixmap, x, y, 50)
            if magnified.isNull():
                return

            # 放大到100x100
            scaled = magnified.scaled(100, 100, Qt.KeepAspectRatio, Qt.FastTransformation)
            if scaled.isNull():
                return

            # 創建新的 pixmap 來繪製十字準星，避免直接修改 scaled
            result = QPixmap(scaled.size())
            result.fill(Qt.transparent)

            painter = QPainter(result)
            try:
                painter.setRenderHint(QPainter.Antialiasing)

                # 先繪製放大的圖像
                painter.drawPixmap(0, 0, scaled)

                # 繪製十字準星
                painter.setPen(QPen(QColor("#60a5fa"), 2))
                center = 50
                painter.drawLine(center-10, center, center+10, center)
                painter.drawLine(center, center-10, center, center+10)
            finally:
                painter.end()

            self.magnifier.setPixmap(result)
        except Exception as e:
            # 靜默處理放大鏡錯誤，避免影響主功能
            pass

    # ---------- 檔案 I/O ----------
    def load_positions_file(self):
        """載入 positions 檔案"""
        if not os.path.exists(POSITIONS_FILE):
            self.update_key_status()
            return

        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                old_data = json.load(f)

            # Schema 檢查與修復
            is_valid, errors, fixed_data = validate_position_schema(old_data)

            if errors:
                error_msg = "\n".join(errors)
                self.status_warn(f"Schema 問題：\n{error_msg}")

            # 合併數據
            for key in ["version", "description", "screen", "roi", "validation"]:
                if key in fixed_data:
                    self.positions[key] = fixed_data[key]

            # 合併 points
            if "points" in fixed_data:
                self.positions["points"].update(fixed_data["points"])

            # 載入測試設定
            if "meta" in fixed_data:
                meta = fixed_data["meta"]
                if "test_mode" in meta:
                    self.test_mode = meta["test_mode"]
                    if self.test_mode == "move":
                        self.btn_move.setChecked(True)
                        self.on_mode_changed("move")
                    else:
                        self.btn_dry.setChecked(True)
                        self.on_mode_changed("dry")

                if "test_delay_ms" in meta:
                    self.step_delay_ms = int(meta["test_delay_ms"])
                    self.delay_spin.setValue(self.step_delay_ms / 1000.0)

            self.update_key_status()
            self.status_ok(f"已載入配置檔 ({len(self.positions.get('points', {}))} 個點位)")

        except Exception as e:
            self.status_err(f"讀取配置檔失敗：{e}")

    def save_positions(self):
        """保存 positions 檔案（含備份和合併）"""
        try:
            # 1. 創建備份
            if os.path.exists(POSITIONS_FILE):
                backup_path = create_backup_filename(POSITIONS_FILE)
                import shutil
                shutil.copy2(POSITIONS_FILE, backup_path)
                logger.info(f"已創建備份: {backup_path}")

            # 2. 讀取既有檔案
            merged = {}
            if os.path.exists(POSITIONS_FILE):
                with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                    merged = json.load(f)

            # 3. Schema 檢查與合併
            for key in ["version", "description", "screen", "roi", "validation"]:
                merged[key] = self.positions.get(key, merged.get(key, {}))

            # 4. 合併 points（只覆蓋變更的鍵位）
            merged_points = merged.get("points", {})
            for k, v in self.positions.get("points", {}).items():
                merged_points[k] = v
            merged["points"] = merged_points

            # 5. 添加 metadata 與測試設定
            merged.setdefault("meta", {})
            merged["meta"]["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            merged["meta"]["total_keys"] = len(merged_points)
            merged["meta"]["test_mode"] = self.test_mode
            merged["meta"]["test_delay_ms"] = self.step_delay_ms

            # 6. 最終 schema 驗證
            is_valid, errors, final_data = validate_position_schema(merged)
            if errors:
                self.log_message(f"⚠️  Schema 修復: {'; '.join(errors)}")

            # 7. 寫入檔案
            os.makedirs(os.path.dirname(POSITIONS_FILE), exist_ok=True)
            with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)

            self.set_unsaved_changes(False)
            self.undo_stack.clear()
            self.undo_btn.setEnabled(False)

            point_count = len(final_data.get("points", {}))
            self.status_ok(f"✅ 已保存 {point_count} 個點位")
            self.log_message(f"💾 保存成功: {point_count} 個點位")

            # 發送狀態更新事件
            required_count = len(self.required_keys)
            complete = point_count >= required_count
            APP_STATE.positionsChanged.emit({
                'complete': complete,
                'count': point_count,
                'required': self.required_keys
            })

            # 發送 Toast 通知
            emit_toast(f"Positions saved ({point_count} points)", "success")

        except Exception as e:
            self.status_err(f"保存失敗: {e}")
            self.log_message(f"❌ 保存失敗: {e}")

    # ---------- 視覺渲染 ----------
    def refresh_preview(self):
        """刷新預覽顯示"""
        if not self.original_pixmap or self.original_pixmap.isNull():
            self.preview.setText("請先截圖或載入截圖")
            return

        try:
            # 目標寬度：Fit width 優先，否則用原圖寬 * zoom%
            target_w = int(self.original_pixmap.width() * (self.zoom / 100.0))
            if self.fit_width:
                target_w = min(self.preview_max_width, target_w)
            display_pixmap = self.original_pixmap.scaledToWidth(
                max(50, target_w), Qt.SmoothTransformation
            )
            if display_pixmap.isNull():
                self.preview.setText("截圖處理失敗")
                return

            # 創建一個可繪製的副本
            result_pixmap = QPixmap(display_pixmap.size())
            result_pixmap.fill(Qt.transparent)

            painter = QPainter(result_pixmap)
            try:
                painter.setRenderHint(QPainter.Antialiasing)

                # 先繪製原始圖像
                painter.drawPixmap(0, 0, display_pixmap)

                # 計算縮放比例
                scale = display_pixmap.width() / self.original_pixmap.width()

                # 繪製每個已設定的鍵位標記
                for key, data in self.positions.get("points", {}).items():
                    if not isinstance(data, dict):
                        continue

                    x, y = data.get("x", -1), data.get("y", -1)
                    if x < 0 or y < 0:
                        continue

                    # 轉換座標
                    display_x = int(x * scale)
                    display_y = int(y * scale)

                    # 獲取顏色
                    color = QColor(self.key_colors.get(key, "#ffffff"))

                    # 繪製圓圈標記
                    painter.setPen(QPen(color, 3))
                    painter.setBrush(QBrush(color))
                    painter.drawEllipse(display_x - 6, display_y - 6, 12, 12)

                    # 繪製標籤背景
                    label_rect = painter.fontMetrics().boundingRect(key)
                    label_rect.moveTopLeft(QPoint(display_x + 10, display_y - 15))
                    label_rect.adjust(-2, -2, 2, 2)

                    painter.setPen(QPen(color, 2))
                    painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
                    painter.drawRoundedRect(label_rect, 3, 3)

                    # 繪製標籤文字
                    painter.setPen(QPen(QColor("white")))
                    painter.drawText(label_rect, Qt.AlignCenter, key)
            finally:
                painter.end()

            self.preview.setPixmap(result_pixmap)

        except Exception as e:
            self.preview.setText(f"預覽更新失敗: {e}")
            logger.error(f"Preview refresh failed: {e}")

    # ---------- 測試模式控制 ----------
    def on_mode_changed(self, mode: str):
        """模式切換事件處理器"""
        self.test_mode = mode
        mode_text = "Move-only" if mode == "move" else "Dry-run"
        self.log_message(f"Mode: {mode_text}")

        # 更新按鈕樣式高亮
        if mode == "dry":
            self.btn_dry.setStyleSheet("QRadioButton { color: #10b981; font-weight: bold; }")
            self.btn_move.setStyleSheet("QRadioButton { color: #9ca3af; }")
        else:
            self.btn_move.setStyleSheet("QRadioButton { color: #f59e0b; font-weight: bold; }")
            self.btn_dry.setStyleSheet("QRadioButton { color: #9ca3af; }")

    def draw_crosshair(self, pos: tuple):
        """在預覽上繪製十字準星"""
        x, y = pos
        if not self.preview.pixmap():
            return

        base = QPixmap(self.screenshot_path)
        if base.isNull():
            return

        disp = self.preview.pixmap().copy()
        scale = self.preview.pixmap().width() / base.width()
        dx, dy = int(x * scale), int(y * scale)

        painter = QPainter(disp)
        try:
            pen = QPen(QColor("#ffffff"))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawLine(dx-15, dy, dx+15, dy)
            painter.drawLine(dx, dy-15, dx, dy+15)

            # 外圈黑線增加對比
            pen.setColor(QColor("#000000"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(dx-16, dy, dx+16, dy)
            painter.drawLine(dx, dy-16, dx, dy+16)
        finally:
            painter.end()

        self.preview.setPixmap(disp)
        # 1秒後恢復原狀
        QTimer.singleShot(1000, self.refresh_preview)

    def sleep_ms(self, delay_ms: int):
        """非阻塞延遲"""
        QTimer.singleShot(delay_ms, lambda: None)
        # 等待指定時間
        start_time = time.time()
        while (time.time() - start_time) * 1000 < delay_ms:
            QGuiApplication.processEvents()
            time.sleep(0.01)

    def try_dryrun(self, key: str, x: int, y: int, delay_ms: int):
        """只畫十字+log"""
        self.draw_crosshair((x, y))
        self.log_message(f"[DRY] {key} -> ({x},{y})")
        self.sleep_ms(delay_ms)

    def try_move(self, key: str, x: int, y: int, delay_ms: int):
        """真的移動滑鼠（有 fallback）+畫十字"""
        moved = False

        # 1) 優先走 Actuator
        try:
            if hasattr(self, "actuator") and self.actuator and hasattr(self.actuator, "move_to"):
                self.actuator.move_to(x, y)
                moved = True
        except Exception:
            pass

        # 2) fallback: pyautogui
        if not moved:
            try:
                import pyautogui
                pyautogui.FAILSAFE = False
                pyautogui.moveTo(x, y, duration=0)
                moved = True
            except Exception:
                pass

        # 3) fallback: Win32 SetCursorPos
        if not moved:
            try:
                import ctypes
                ctypes.windll.user32.SetCursorPos(int(x), int(y))
                moved = True
            except Exception:
                pass

        self.draw_crosshair((x, y))
        status = "*" if moved else " (fallback failed)"
        self.log_message(f"[MOVE{status}] {key} -> ({x},{y})")
        self.sleep_ms(delay_ms)

    # ---------- 測試功能 ----------
    def on_test_current(self):
        """測試當前選中的鍵位"""
        if not self.preview.pixmap():
            QMessageBox.information(self, "提示", "請先截圖/載入截圖")
            return

        key = self.active_key or "banker"
        pt = self.positions.get("points", {}).get(key)
        if not pt:
            QMessageBox.information(self, "提示", f"{key} 尚未設定位置")
            return

        delay_ms = int(self.step_delay_ms)
        x, y = int(pt["x"]), int(pt["y"])

        if self.test_mode == "move":
            self.try_move(key, x, y, delay_ms)
        else:
            self.try_dryrun(key, x, y, delay_ms)

    def on_test_all(self):
        """測試所有已設定的鍵位"""
        if not self.preview.pixmap():
            QMessageBox.information(self, "提示", "請先截圖/載入截圖")
            return

        pts = self.positions.get("points", {})
        required = ["banker", "chip_1k", "confirm"]

        # 檢查必要鍵位
        missing = [k for k in required if k not in pts]
        if missing:
            QMessageBox.warning(self, "缺少必要點",
                              f"請先設好 {' / '.join(missing)}")
            return

        # 測試順序：必要鍵 + 其他已設定鍵位按字母序
        other_keys = sorted([k for k in pts.keys() if k not in required])
        test_order = required + other_keys
        delay_ms = int(self.step_delay_ms)

        self.log_message(f"🚀 開始測試 {len(test_order)} 個鍵位...")

        for i, key in enumerate(test_order):
            x, y = int(pts[key]["x"]), int(pts[key]["y"])
            self.log_message(f"[{i+1}/{len(test_order)}] {key}")

            if self.test_mode == "move":
                self.try_move(key, x, y, delay_ms)
            else:
                self.try_dryrun(key, x, y, delay_ms)

        self.log_message("🏁 測試完成")

    def create_actuator(self):
        """創建 actuator 實例"""
        try:
            ui_config = {
                "click": {
                    "jitter_px": 2,
                    "move_delay_ms": [40, 120],
                    "click_delay_ms": [40, 80]
                },
                "safety": {
                    "pre_confirm_guard_ms": 120
                }
            }
            # 在 Move-only 模式下，依然使用 dry_run=False 來允許真實移動
            dry_run = (self.test_mode == "dry")
            self.actuator = Actuator(self.positions, ui_config, dry_run=dry_run)
        except Exception as e:
            self.status_err(f"創建測試器失敗: {e}")
            self.actuator = None

    def log_message(self, message: str):
        """添加日誌消息"""
        timestamp = time.strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {message}"
        self.log_display.append(formatted_msg)

        # 保持日誌行數限制
        document = self.log_display.document()
        if document.blockCount() > 50:
            cursor = self.log_display.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.BlockUnderCursor)
            cursor.removeSelectedText()

        # 滾動到底部
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ---------- 健康檢查 ----------
    def check_health(self):
        """檢查配置健康狀態"""
        points = self.positions.get("points", {})
        issues = []

        # 檢查必要鍵位
        missing_required = [key for key in self.required_keys if key not in points]
        if missing_required:
            issues.append(f"❌ 缺少必備鍵位: {', '.join(missing_required)}")

        # 檢查座標有效性
        screen = self.positions.get("screen", {})
        screen_w = screen.get("width", 1920)
        screen_h = screen.get("height", 1080)

        invalid_coords = []
        for key, data in points.items():
            if isinstance(data, dict):
                x, y = data.get("x", 0), data.get("y", 0)
                if x < 0 or y < 0 or x > screen_w or y > screen_h:
                    invalid_coords.append(key)

        if invalid_coords:
            issues.append(f"⚠️  座標超出範圍: {', '.join(invalid_coords)}")

        # 檢查重複座標
        coord_map = {}
        duplicates = []
        for key, data in points.items():
            if isinstance(data, dict):
                coord = (data.get("x", 0), data.get("y", 0))
                if coord in coord_map:
                    duplicates.append(f"{coord_map[coord]}, {key}")
                else:
                    coord_map[coord] = key

        if duplicates:
            issues.append(f"⚠️  重複座標: {'; '.join(duplicates)}")

        # 更新顯示
        if issues:
            result_text = "\n".join(issues)
            self.health_result.setStyleSheet("""
                QLabel {
                    background: #7f1d1d;
                    color: #fca5a5;
                    border: 1px solid #dc2626;
                    border-radius: 4px;
                    padding: 8px;
                }
            """)
        else:
            total_keys = len(points)
            result_text = f"✅ 健康狀態良好\n\n已設定 {total_keys} 個鍵位\n必備鍵位完整"
            self.health_result.setStyleSheet("""
                QLabel {
                    background: #14532d;
                    color: #86efac;
                    border: 1px solid #16a34a;
                    border-radius: 4px;
                    padding: 8px;
                }
            """)

        self.health_result.setText(result_text)
        return len(issues) == 0

    # ---------- 事件處理 ----------
    def closeEvent(self, event):
        """頁面關閉事件"""
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self, "未保存的變更",
                "您有未保存的變更，是否要先保存？",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )

            if reply == QMessageBox.Yes:
                self.save_positions()
                event.accept()
            elif reply == QMessageBox.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    # ---------- 狀態消息 ----------
    def status_ok(self, msg: str):
        self.status_label.setText(f"狀態：{msg}")
        self.status_label.setStyleSheet("color: #10b981; font-weight: bold;")

    def status_warn(self, msg: str):
        self.status_label.setText(f"狀態：{msg}")
        self.status_label.setStyleSheet("color: #f59e0b; font-weight: bold;")

    def status_err(self, msg: str):
        self.status_label.setText(f"狀態：{msg}")
        self.status_label.setStyleSheet("color: #dc2626; font-weight: bold;")