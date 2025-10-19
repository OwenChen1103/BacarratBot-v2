# ui/pages/page_chip_profile.py
"""
籌碼組合設定頁面
讓使用者設定 6 顆籌碼的金額並校準位置
"""

import os
from pathlib import Path
from typing import Optional
import pyautogui
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QSpinBox, QFormLayout, QMessageBox, QFrame,
    QGridLayout, QScrollArea, QCheckBox, QSplitter
)
from PySide6.QtCore import Qt, Signal, QTimer, QPoint
from PySide6.QtGui import QFont, QPixmap, QPainter, QPen, QColor, QCursor

from src.autobet.chip_profile_manager import ChipProfileManager, ChipProfile
from ..app_state import emit_toast


class ChipButton(QPushButton):
    """籌碼按鈕（用於校準）"""

    calibration_requested = Signal(int)  # slot number

    def __init__(self, slot: int, label: str, color: str, parent=None):
        super().__init__(parent)
        self.slot = slot
        self.label = label
        self.color = color
        self.is_calibrated = False

        self.setText(f"Chip {slot}\n{label}")
        self.setMinimumHeight(40)
        self.update_style()

        self.clicked.connect(lambda: self.calibration_requested.emit(self.slot))

    def set_calibrated(self, calibrated: bool):
        self.is_calibrated = calibrated
        self.update_style()

    def update_style(self):
        if self.is_calibrated:
            bg_color = "#10b981"  # green
            icon = "✓"
            status = "已校準"
        else:
            bg_color = "#6b7280"  # gray
            icon = "○"
            status = "未校準"

        self.setText(f"{icon} C{self.slot}\n{status}")
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 8pt;
                padding: 4px;
            }}
            QPushButton:hover {{
                opacity: 0.8;
            }}
        """)


class PositionButton(QPushButton):
    """位置按鈕（用於校準下注位置）"""

    calibration_requested = Signal(str)  # position name

    def __init__(self, position_name: str, display_name: str, parent=None):
        super().__init__(parent)
        self.position_name = position_name
        self.display_name = display_name
        self.is_calibrated = False

        self.setMinimumHeight(32)
        self.update_style()

        self.clicked.connect(lambda: self.calibration_requested.emit(self.position_name))

    def set_calibrated(self, calibrated: bool):
        self.is_calibrated = calibrated
        self.update_style()

    def update_style(self):
        if self.is_calibrated:
            icon = "✓"
            color = "#10b981"
            status = "已校準"
        else:
            icon = "✗"
            color = "#ef4444"
            status = "未校準"

        self.setText(f"{icon} {self.display_name}")
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #374151;
                color: {color};
                border: 1px solid {color};
                border-radius: 4px;
                font-size: 8pt;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: #4b5563;
            }}
        """)


class ChipProfilePage(QWidget):
    """籌碼組合設定頁面"""

    profile_updated = Signal(ChipProfile)

    def __init__(self):
        super().__init__()

        self.profile_manager = ChipProfileManager()
        self.current_profile: Optional[ChipProfile] = None
        self.calibrating = False
        self.calibrating_slot: Optional[int] = None
        self.calibrating_position: Optional[str] = None

        # 螢幕截圖相關
        self.screenshot_pixmap: Optional[QPixmap] = None
        self.screenshot_path = "data/screenshots/chip_calib.png"
        self.calibration_marks = {}  # {name: (x, y)}
        self.mouse_pos: Optional[tuple] = None  # 鼠標位置

        self._build_ui()
        self._load_profile()
        self._load_screenshot_if_exists()

        # 放大鏡更新計時器
        self.magnifier_timer = QTimer()
        self.magnifier_timer.timeout.connect(self._update_magnifier)
        self.magnifier_timer.start(50)  # 50ms 更新頻率

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # 標題
        header = QLabel("🎰 籌碼與位置設定")
        header.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                background-color: #1f2937;
                color: #f9fafb;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        main_layout.addWidget(header)

        # 主要內容區：左右分割
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background-color: #4b5563; }")

        # === 左側：螢幕截圖預覽區 ===
        left_widget = self._build_preview_section()
        splitter.addWidget(left_widget)

        # === 右側：設定區 ===
        right_widget = self._build_settings_section()
        splitter.addWidget(right_widget)

        # 設定分割比例 (預覽:設定 = 6:4)
        splitter.setSizes([600, 400])

        main_layout.addWidget(splitter, 1)

        # 底部按鈕
        button_layout = QHBoxLayout()

        self.screenshot_btn = QPushButton("📷 截取螢幕")
        self.screenshot_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        self.screenshot_btn.clicked.connect(self._take_screenshot)

        self.save_btn = QPushButton("💾 保存設定")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.save_btn.clicked.connect(self._save_profile)

        self.reset_btn = QPushButton("🔄 重新載入")
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #6b7280;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        self.reset_btn.clicked.connect(self._load_profile)

        button_layout.addWidget(self.screenshot_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.reset_btn)

        main_layout.addLayout(button_layout)

    def _build_preview_section(self) -> QWidget:
        """建立螢幕截圖預覽區"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 2px solid #374151;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # 標題
        title = QLabel("📸 遊戲畫面預覽")
        title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        title.setStyleSheet("color: #f3f4f6; padding: 4px;")
        layout.addWidget(title)

        # 提示
        hint = QLabel("點擊「截取螢幕」後，點擊校準按鈕，再點擊預覽圖上對應位置")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9ca3af; font-size: 9pt; padding: 4px;")
        layout.addWidget(hint)

        # 預覽標籤（可點擊）
        self.preview_label = QLabel("請先截取螢幕")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #1f2937;
                border: 1px solid #4b5563;
                border-radius: 4px;
                color: #6b7280;
            }
        """)
        self.preview_label.setScaledContents(False)
        self.preview_label.setMouseTracking(True)  # 啟用鼠標追蹤
        self.preview_label.mousePressEvent = self._on_preview_clicked
        self.preview_label.mouseMoveEvent = self._on_preview_mouse_move
        layout.addWidget(self.preview_label, 1)

        # 放大鏡（疊加在預覽標籤右上角）
        self.magnifier = QLabel(self.preview_label)
        self.magnifier.setText("🔍 放大鏡")
        self.magnifier.setFixedSize(120, 120)
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
        self.magnifier.move(8, 8)  # 左上角

        return widget

    def _build_settings_section(self) -> QWidget:
        """建立右側設定區"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)
        layout.setContentsMargins(2, 2, 2, 2)

        # 滾動區域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(8)

        # 重要提示
        warning_bar = QFrame()
        warning_bar.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        warning_layout = QVBoxLayout(warning_bar)
        warning_layout.setContentsMargins(6, 6, 6, 6)

        warning_text = QLabel(
            "💡 <b>流程：</b>截圖→設金額→點校準→點預覽圖→保存"
        )
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet("color: #d1d5db; font-size: 8pt;")
        warning_layout.addWidget(warning_text)
        scroll_layout.addWidget(warning_bar)

        # 籌碼金額設定區
        self._build_chip_values_section(scroll_layout)

        # 籌碼位置校準區
        self._build_chip_calibration_section(scroll_layout)

        # 下注位置校準區
        self._build_position_calibration_section(scroll_layout)

        # 限額設定區
        self._build_constraints_section(scroll_layout)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)

        return widget


    def _build_chip_values_section(self, parent_layout: QVBoxLayout):
        """建立籌碼金額設定區"""
        group = QGroupBox("💰 籌碼金額")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 9pt;
                border: 1px solid #374151;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: #1f2937;
                color: #f3f4f6;
            }
        """)

        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        # 提示訊息 - 統一深色風格
        info = QLabel("💡 只設定實際使用的籌碼即可")
        info.setWordWrap(True)
        info.setStyleSheet("""
            QLabel {
                background-color: #4b5563;
                color: #e5e7eb;
                padding: 6px;
                border-radius: 4px;
                border: 1px solid #6b7280;
                font-size: 8pt;
            }
        """)
        layout.addWidget(info)

        # 常用預設按鈕 - 緊湊版
        presets_layout = QHBoxLayout()
        presets_label = QLabel("預設:")
        presets_label.setStyleSheet("color: #9ca3af; font-size: 8pt;")
        presets_layout.addWidget(presets_label)

        preset_buttons = [
            ("基礎", [100, 1000, 0, 0, 0, 0]),
            ("標準", [100, 1000, 5000, 0, 0, 0]),
            ("進階", [100, 1000, 5000, 10000, 0, 0]),
        ]

        for btn_text, values in preset_buttons:
            btn = QPushButton(btn_text)
            btn.setStyleSheet("""
                QPushButton {
                    color: #d1d5db;
                    border: 1px solid #4b5563;
                    border-radius: 3px;
                    padding: 4px 8px;
                    font-size: 8pt;
                }
                QPushButton:hover {
                    background-color: #4b5563;
                }
            """)
            btn.clicked.connect(lambda checked, v=values: self._apply_preset(v))
            presets_layout.addWidget(btn)

        presets_layout.addStretch()
        layout.addLayout(presets_layout)

        # 籌碼設定表單
        form_layout = QFormLayout()
        form_layout.setSpacing(6)

        self.chip_value_spinboxes = []
        self.chip_enable_checkboxes = []

        chip_colors = ["🔴", "🟠", "🔵", "🟢", "🟣", "⚫"]
        default_values = [100, 1000, 5000, 10000, 50000, 100000]
        default_enabled = [True, True, False, False, False, False]  # 預設只啟用前 2 顆

        for i in range(6):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            # 啟用 checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(default_enabled[i])
            checkbox.setStyleSheet("QCheckBox { color: #e5e7eb; }")
            checkbox.toggled.connect(lambda checked, idx=i: self._toggle_chip(idx, checked))

            # 金額輸入框
            spinbox = QSpinBox()
            spinbox.setRange(100, 1000000)
            spinbox.setValue(default_values[i])
            spinbox.setSuffix(" 元")
            spinbox.setEnabled(default_enabled[i])
            spinbox.setStyleSheet("""
                QSpinBox {
                    color: #f3f4f6;
                    border: 1px solid #4b5563;
                    border-radius: 3px;
                    padding: 4px;
                    font-size: 8pt;
                }
                QSpinBox:disabled {
                    color: #6b7280;
                }
            """)

            row_layout.addWidget(checkbox)
            row_layout.addWidget(spinbox, 1)

            label = QLabel(f"{chip_colors[i]} C{i+1}:")
            label.setStyleSheet("color: #e5e7eb; font-size: 8pt; background-color: transparent;")

            form_layout.addRow(label, row_layout)
            self.chip_value_spinboxes.append(spinbox)
            self.chip_enable_checkboxes.append(checkbox)

        layout.addLayout(form_layout)

        # 智能建議區域 - 緊湊版
        suggestion_frame = QFrame()
        suggestion_frame.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        suggestion_layout = QVBoxLayout(suggestion_frame)

        suggestion_header = QLabel("💡 建議")
        suggestion_header.setStyleSheet("color: #f3f4f6; font-weight: bold; font-size: 8pt;")
        suggestion_layout.addWidget(suggestion_header)

        self.suggestion_label = QLabel("點擊分析...")
        self.suggestion_label.setWordWrap(True)
        self.suggestion_label.setStyleSheet("color: #d1d5db; font-size: 7pt;")
        suggestion_layout.addWidget(self.suggestion_label)

        analyze_btn = QPushButton("📊 分析")
        analyze_btn.setStyleSheet("""
            QPushButton {
                background-color: #4b5563;
                color: white;
                border: 1px solid #6b7280;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #6b7280;
            }
        """)
        analyze_btn.clicked.connect(self._analyze_strategies)
        suggestion_layout.addWidget(analyze_btn)

        layout.addWidget(suggestion_frame)
        parent_layout.addWidget(group)

    def _apply_preset(self, values: list):
        """套用預設值"""
        for i, value in enumerate(values):
            if i < len(self.chip_value_spinboxes):
                self.chip_value_spinboxes[i].setValue(value if value > 0 else 100)
                enabled = value > 0
                self.chip_enable_checkboxes[i].setChecked(enabled)
                self.chip_value_spinboxes[i].setEnabled(enabled)

    def _toggle_chip(self, index: int, enabled: bool):
        """切換籌碼啟用狀態"""
        if index < len(self.chip_value_spinboxes):
            self.chip_value_spinboxes[index].setEnabled(enabled)
            if hasattr(self, 'chip_buttons') and index < len(self.chip_buttons):
                # 更新校準按鈕狀態
                self.chip_buttons[index].setEnabled(enabled)
                # 更新按鈕文字
                chip_value = self.chip_value_spinboxes[index].value()
                self.chip_buttons[index].label = self._format_chip_label(chip_value)
                self.chip_buttons[index].update_style()
                if not enabled:
                    self.chip_buttons[index].set_calibrated(False)

    def _build_chip_calibration_section(self, parent_layout: QVBoxLayout):
        """建立籌碼位置校準區"""
        group = QGroupBox("🎯 籌碼校準")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 9pt;
                border: 1px solid #374151;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: #1f2937;
                color: #f3f4f6;
            }
        """)

        layout = QVBoxLayout(group)

        info = QLabel("點按鈕→點預覽圖")
        info.setStyleSheet("color: #9ca3af; padding: 4px; font-size: 8pt;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # 使用 Grid 排列籌碼按鈕（3x2）
        grid = QGridLayout()
        grid.setSpacing(6)

        self.chip_buttons = []
        chip_colors = ["red", "orange", "blue", "green", "purple", "black"]

        for i in range(6):
            row = i // 3
            col = i % 3

            btn = ChipButton(i + 1, f"{self.chip_value_spinboxes[i].value()}", chip_colors[i])
            btn.calibration_requested.connect(self._start_chip_calibration)
            grid.addWidget(btn, row, col)
            self.chip_buttons.append(btn)

        layout.addLayout(grid)

        # 測試按鈕 - 緊湊版
        test_layout = QHBoxLayout()
        test_current_btn = QPushButton("測試")
        test_current_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        test_current_btn.clicked.connect(self._test_current_chip)

        test_all_btn = QPushButton("全部")
        test_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b;
                color: white;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
        """)
        test_all_btn.clicked.connect(self._test_all_chips)

        test_layout.addWidget(test_current_btn)
        test_layout.addWidget(test_all_btn)
        layout.addLayout(test_layout)

        parent_layout.addWidget(group)

    def _build_position_calibration_section(self, parent_layout: QVBoxLayout):
        """建立下注位置校準區"""
        group = QGroupBox("📍 位置校準")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 9pt;
                border: 1px solid #374151;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: #1f2937;
                color: #f3f4f6;
            }
        """)

        layout = QVBoxLayout(group)

        info = QLabel("點按鈕→點預覽圖")
        info.setStyleSheet("color: #9ca3af; padding: 4px; font-size: 8pt;")
        info.setWordWrap(True)
        layout.addWidget(info)

        positions_layout = QGridLayout()
        positions_layout.setSpacing(6)

        self.position_buttons = {}
        positions = [
            ("banker", "莊家區域"),
            ("player", "閒家區域"),
            ("tie", "和局區域"),
            ("confirm", "確認按鈕"),
            ("cancel", "取消按鈕"),
        ]

        for i, (pos_name, display_name) in enumerate(positions):
            btn = PositionButton(pos_name, display_name)
            btn.calibration_requested.connect(self._start_position_calibration)
            positions_layout.addWidget(btn, i // 2, i % 2)
            self.position_buttons[pos_name] = btn

        layout.addLayout(positions_layout)

        # 測試按鈕 - 緊湊版
        test_pos_layout = QHBoxLayout()
        test_pos_current_btn = QPushButton("測試")
        test_pos_current_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        test_pos_current_btn.clicked.connect(self._test_current_position)

        test_pos_all_btn = QPushButton("全部")
        test_pos_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b;
                color: white;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
        """)
        test_pos_all_btn.clicked.connect(self._test_all_positions)

        test_pos_layout.addWidget(test_pos_current_btn)
        test_pos_layout.addWidget(test_pos_all_btn)
        layout.addLayout(test_pos_layout)

        parent_layout.addWidget(group)

    def _build_constraints_section(self, parent_layout: QVBoxLayout):
        """建立限額設定區"""
        group = QGroupBox("⚙️ 限額")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 9pt;
                border: 1px solid #374151;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: #1f2937;
                color: #f3f4f6;
            }
        """)

        layout = QFormLayout(group)
        layout.setSpacing(4)

        self.min_bet_spinbox = QSpinBox()
        self.min_bet_spinbox.setRange(100, 100000)
        self.min_bet_spinbox.setValue(100)
        self.min_bet_spinbox.setSuffix(" 元")

        self.max_bet_spinbox = QSpinBox()
        self.max_bet_spinbox.setRange(100, 1000000)
        self.max_bet_spinbox.setValue(10000)
        self.max_bet_spinbox.setSuffix(" 元")

        self.max_clicks_spinbox = QSpinBox()
        self.max_clicks_spinbox.setRange(1, 50)
        self.max_clicks_spinbox.setValue(8)
        self.max_clicks_spinbox.setSuffix(" 次")

        for spinbox in [self.min_bet_spinbox, self.max_bet_spinbox, self.max_clicks_spinbox]:
            spinbox.setStyleSheet("""
                QSpinBox {
                    color: #f3f4f6;
                    border: 1px solid #4b5563;
                    border-radius: 3px;
                    padding: 4px;
                    font-size: 8pt;
                }
            """)

        min_label = QLabel("最小:")
        min_label.setStyleSheet("color: #e5e7eb; font-size: 8pt;")
        max_label = QLabel("最大:")
        max_label.setStyleSheet("color: #e5e7eb; font-size: 8pt;")
        clicks_label = QLabel("點擊上限:")
        clicks_label.setStyleSheet("color: #e5e7eb; font-size: 8pt;")

        layout.addRow(min_label, self.min_bet_spinbox)
        layout.addRow(max_label, self.max_bet_spinbox)
        layout.addRow(clicks_label, self.max_clicks_spinbox)

        parent_layout.addWidget(group)

    def _load_profile(self):
        """載入 Profile"""
        try:
            self.current_profile = self.profile_manager.load_profile("default")

            # 更新籌碼金額
            for i, chip in enumerate(self.current_profile.chips):
                if i < len(self.chip_value_spinboxes):
                    self.chip_value_spinboxes[i].setValue(chip.value)
                    self.chip_buttons[i].label = chip.label
                    self.chip_buttons[i].set_calibrated(chip.calibrated)

            # 更新下注位置
            for pos_name, btn in self.position_buttons.items():
                pos = self.current_profile.get_bet_position(pos_name)
                if pos:
                    btn.set_calibrated(pos.get("calibrated", False))

            # 更新限額
            constraints = self.current_profile.constraints
            self.min_bet_spinbox.setValue(constraints.get("min_bet", 100))
            self.max_bet_spinbox.setValue(constraints.get("max_bet", 10000))
            self.max_clicks_spinbox.setValue(constraints.get("max_clicks_per_hand", 8))

            emit_toast("籌碼組合已載入", "success")

        except Exception as e:
            QMessageBox.warning(self, "載入失敗", f"無法載入籌碼組合:\n{e}")

    def _save_profile(self):
        """保存 Profile"""
        if not self.current_profile:
            QMessageBox.warning(self, "錯誤", "沒有可保存的籌碼組合")
            return

        try:
            # 更新籌碼金額
            for i, chip in enumerate(self.current_profile.chips):
                if i < len(self.chip_value_spinboxes):
                    chip.value = self.chip_value_spinboxes[i].value()
                    chip.label = self._format_chip_label(chip.value)

            # 更新限額
            self.current_profile.constraints["min_bet"] = self.min_bet_spinbox.value()
            self.current_profile.constraints["max_bet"] = self.max_bet_spinbox.value()
            self.current_profile.constraints["max_clicks_per_hand"] = self.max_clicks_spinbox.value()

            # 驗證
            validation = self.profile_manager.validate_profile(self.current_profile)

            if validation.errors:
                error_msg = "\n".join(validation.errors)
                reply = QMessageBox.question(
                    self,
                    "驗證失敗",
                    f"籌碼組合不完整:\n\n{error_msg}\n\n是否仍要保存?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return

            # 顯示確認對話框，強調金額必須匹配
            if not self._show_save_confirmation():
                return

            # 保存
            success = self.profile_manager.save_profile(self.current_profile, "default")

            if success:
                emit_toast("籌碼組合已保存", "success")
                self.profile_updated.emit(self.current_profile)

                # 顯示驗證警告（如果有）
                if validation.warnings:
                    warning_msg = "\n".join(validation.warnings)
                    QMessageBox.information(
                        self,
                        "提醒",
                        f"籌碼組合已保存，但有以下建議:\n\n{warning_msg}"
                    )
            else:
                QMessageBox.critical(self, "保存失敗", "無法保存籌碼組合")

        except Exception as e:
            QMessageBox.critical(self, "保存失敗", f"保存時發生錯誤:\n{e}")

    def _show_save_confirmation(self) -> bool:
        """
        顯示保存確認對話框，強調金額必須與遊戲內一致

        Returns:
            True if user confirms, False otherwise
        """
        # 收集啟用的籌碼資訊
        enabled_chips = []
        calibrated_chips = []

        for i in range(6):
            if i < len(self.chip_enable_checkboxes) and self.chip_enable_checkboxes[i].isChecked():
                chip_value = self.chip_value_spinboxes[i].value()
                chip_label = self._format_chip_label(chip_value)
                is_calibrated = self.chip_buttons[i].is_calibrated

                enabled_chips.append((i + 1, chip_value, chip_label, is_calibrated))
                if is_calibrated:
                    calibrated_chips.append((i + 1, chip_value, chip_label))

        if not enabled_chips:
            QMessageBox.warning(
                self,
                "無法保存",
                "至少需要啟用並設定一顆籌碼！"
            )
            return False

        # 構建確認訊息
        msg = "⚠️ 保存前最後確認 ⚠️\n\n"
        msg += "您即將保存以下籌碼設定:\n\n"

        for slot, value, label, calibrated in enabled_chips:
            status = "✓ 已校準" if calibrated else "✗ 未校準"
            msg += f"  Chip {slot}: {value} 元 ({label}) - {status}\n"

        msg += "\n" + "="*50 + "\n"
        msg += "🚨 重要提醒 🚨\n"
        msg += "="*50 + "\n\n"

        msg += "請確認以下事項:\n\n"
        msg += "1. 遊戲內「自定義籌碼」的金額是否與上述設定【完全一致】？\n"
        msg += "   例如：遊戲內籌碼1=100, 籌碼2=1000\n"
        msg += "        系統內 Chip 1=100, Chip 2=1000\n\n"

        msg += "2. 遊戲內籌碼的【順序】是否與系統一致？\n"
        msg += "   (遊戲內的籌碼1 = 系統的 Chip 1)\n\n"

        msg += "3. 已校準的籌碼位置是否正確？\n\n"

        msg += "⚠️ 如果金額不一致，系統下注金額將會錯誤！\n"
        msg += "⚠️ 例如：遊戲內是500元，系統設100元 → 實際下注500元！\n\n"

        msg += "確認以上設定無誤嗎？"

        # 使用自定義對話框
        reply = QMessageBox.question(
            self,
            "⚠️ 確認保存",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No  # 預設為 No，強制使用者主動確認
        )

        return reply == QMessageBox.Yes

    def _start_chip_calibration(self, slot: int):
        """開始校準籌碼"""
        if not self.screenshot_pixmap:
            emit_toast("請先截取螢幕！", "warning")
            QMessageBox.warning(self, "無法校準", "請先點擊「截取螢幕」按鈕截取遊戲畫面")
            return

        self.calibrating = True
        self.calibrating_slot = slot
        self.calibrating_position = None

        emit_toast(f"請點擊預覽圖上的 Chip {slot} 位置", "info")

        # 改變鼠標樣式以提示使用者
        self.preview_label.setCursor(QCursor(Qt.CrossCursor))

    def _start_position_calibration(self, position_name: str):
        """開始校準下注位置"""
        if not self.screenshot_pixmap:
            emit_toast("請先截取螢幕！", "warning")
            QMessageBox.warning(self, "無法校準", "請先點擊「截取螢幕」按鈕截取遊戲畫面")
            return

        self.calibrating = True
        self.calibrating_slot = None
        self.calibrating_position = position_name

        display_name = self.position_buttons[position_name].display_name
        emit_toast(f"請點擊預覽圖上的 {display_name}", "info")

        # 改變鼠標樣式以提示使用者
        self.preview_label.setCursor(QCursor(Qt.CrossCursor))

    def _on_calibration_complete(self, x: int, y: int):
        """校準完成回調"""
        if not self.calibrating or not self.current_profile:
            return

        try:
            if self.calibrating_slot is not None:
                # 校準籌碼
                success = self.profile_manager.update_chip_calibration(
                    self.current_profile,
                    self.calibrating_slot,
                    x, y
                )
                if success:
                    self.chip_buttons[self.calibrating_slot - 1].set_calibrated(True)
                    emit_toast(f"Chip {self.calibrating_slot} 校準成功", "success")

            elif self.calibrating_position is not None:
                # 校準下注位置
                success = self.profile_manager.update_position_calibration(
                    self.current_profile,
                    self.calibrating_position,
                    x, y
                )
                if success:
                    self.position_buttons[self.calibrating_position].set_calibrated(True)
                    emit_toast(f"{self.position_buttons[self.calibrating_position].display_name} 校準成功", "success")

        except Exception as e:
            QMessageBox.warning(self, "校準失敗", f"校準時發生錯誤:\n{e}")

        finally:
            self.calibrating = False
            self.calibrating_slot = None
            self.calibrating_position = None
            # 恢復鼠標樣式
            self.preview_label.setCursor(QCursor(Qt.ArrowCursor))

    def _analyze_strategies(self):
        """分析策略並給出籌碼建議"""
        try:
            # 載入所有策略
            from pathlib import Path
            import json

            strategy_dir = Path("configs/line_strategies")
            if not strategy_dir.exists():
                self.suggestion_label.setText("⚠️ 找不到策略檔案")
                return

            all_amounts = set()
            strategy_files = list(strategy_dir.glob("*.json"))

            if not strategy_files:
                self.suggestion_label.setText("⚠️ 沒有找到策略檔案")
                return

            # 收集所有策略的金額
            for strategy_file in strategy_files:
                try:
                    with open(strategy_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        sequence = data.get("staking", {}).get("sequence", [])
                        all_amounts.update(sequence)
                except:
                    continue

            if not all_amounts:
                self.suggestion_label.setText("⚠️ 策略中沒有找到序列資料")
                return

            # 分析最大金額
            max_amount = max(all_amounts)
            min_amount = min(all_amounts)

            # 智能推薦籌碼
            recommended_chips = self._recommend_chips(min_amount, max_amount, all_amounts)

            # 顯示建議
            suggestion_text = f"📊 策略分析結果:\n\n"
            suggestion_text += f"• 最小金額: {min_amount} 元\n"
            suggestion_text += f"• 最大金額: {max_amount} 元\n"
            suggestion_text += f"• 找到 {len(all_amounts)} 種不同金額\n\n"
            suggestion_text += f"💡 建議設定這些籌碼:\n"

            for chip_value, reason in recommended_chips:
                chip_label = self._format_chip_label(chip_value)
                suggestion_text += f"  ✓ {chip_label} - {reason}\n"

            self.suggestion_label.setText(suggestion_text)

            # 提供一鍵套用按鈕
            if hasattr(self, 'apply_suggestion_btn'):
                self.apply_suggestion_btn.setParent(None)

            self.apply_suggestion_btn = QPushButton("✨ 一鍵套用建議")
            self.apply_suggestion_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3b82f6;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2563eb;
                }
            """)

            recommended_values = [chip[0] for chip in recommended_chips]
            # 補齊到 6 個
            while len(recommended_values) < 6:
                recommended_values.append(0)

            self.apply_suggestion_btn.clicked.connect(
                lambda: self._apply_preset(recommended_values[:6])
            )

            # 加到 suggestion_frame
            suggestion_frame = self.suggestion_label.parent()
            suggestion_frame.layout().addWidget(self.apply_suggestion_btn)

        except Exception as e:
            self.suggestion_label.setText(f"❌ 分析失敗: {str(e)}")

    def _recommend_chips(self, min_amount: int, max_amount: int, amounts: set) -> list:
        """
        根據金額範圍推薦籌碼

        Returns:
            List of (chip_value, reason) tuples
        """
        recommendations = []

        # 基礎籌碼（必須）
        recommendations.append((100, "基礎籌碼，用於湊零頭"))

        # 根據最常見金額決定主力籌碼
        if max_amount >= 1000:
            recommendations.append((1000, "主力籌碼，覆蓋大部分金額"))

        # 根據最大金額決定是否需要更大籌碼
        if max_amount >= 5000:
            recommendations.append((5000, f"減少大額下注點擊次數"))

        if max_amount >= 10000:
            recommendations.append((10000, f"支援萬元級下注"))

        if max_amount >= 50000:
            recommendations.append((50000, f"支援大額下注"))

        # 根據金額的最大公因數優化
        from math import gcd
        from functools import reduce

        if len(amounts) > 1:
            amounts_list = list(amounts)
            common_divisor = reduce(gcd, amounts_list)

            # 如果有公因數且不是 100 的倍數
            if common_divisor > 100 and common_divisor not in [100, 1000, 5000, 10000]:
                # 檢查是否為 500
                if common_divisor == 500 or (max_amount % 500 == 0 and max_amount < 5000):
                    if 500 not in [r[0] for r in recommendations]:
                        recommendations.insert(1, (500, "策略金額為 500 的倍數"))

        return recommendations

    @staticmethod
    def _format_chip_label(value: int) -> str:
        """格式化籌碼標籤"""
        if value >= 1000:
            return f"{value // 1000}K"
        else:
            return str(value)

    def _take_screenshot(self):
        """截取螢幕"""
        try:
            # 延遲以便最小化視窗
            emit_toast("3秒後開始截圖...", "info")
            QTimer.singleShot(300, self._do_screenshot)
        except Exception as e:
            QMessageBox.warning(self, "截圖失敗", f"無法截取螢幕:\n{e}")

    def _do_screenshot(self):
        """執行截圖"""
        try:
            time.sleep(2.7)  # 3秒總延遲

            # 使用 pyautogui 截圖
            screenshot = pyautogui.screenshot()

            # 保存
            os.makedirs(os.path.dirname(self.screenshot_path), exist_ok=True)
            screenshot.save(self.screenshot_path)

            # 載入到 Qt
            self.screenshot_pixmap = QPixmap(self.screenshot_path)
            self._update_preview()

            emit_toast("截圖成功！請開始校準", "success")

        except Exception as e:
            QMessageBox.warning(self, "截圖失敗", f"截圖時發生錯誤:\n{e}")

    def _load_screenshot_if_exists(self):
        """載入已存在的截圖"""
        if os.path.exists(self.screenshot_path):
            self.screenshot_pixmap = QPixmap(self.screenshot_path)
            self._update_preview()

    def _update_preview(self):
        """更新預覽圖"""
        if not self.screenshot_pixmap or self.screenshot_pixmap.isNull():
            return

        # 縮放圖片以適應 label 大小
        label_size = self.preview_label.size()
        scaled_pixmap = self.screenshot_pixmap.scaled(
            label_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        # 在圖片上繪製標記（標記直接繪製在縮放後的圖片上，不需要偏移）
        if self.calibration_marks:
            painter = QPainter(scaled_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)

            # 計算縮放比例（從原始截圖到顯示的 pixmap）
            scale_x = scaled_pixmap.width() / self.screenshot_pixmap.width()
            scale_y = scaled_pixmap.height() / self.screenshot_pixmap.height()

            for name, (x, y) in self.calibration_marks.items():
                # 將原始座標縮放到顯示尺寸
                px = int(x * scale_x)
                py = int(y * scale_y)

                # 繪製十字準星
                pen = QPen(QColor("#3b82f6"), 2)
                painter.setPen(pen)

                # 橫線
                painter.drawLine(px - 10, py, px + 10, py)
                # 豎線
                painter.drawLine(px, py - 10, px, py + 10)

                # 繪製圓圈
                pen.setWidth(2)
                painter.setPen(pen)
                painter.setBrush(QColor(59, 130, 246, 50))  # 半透明藍色
                painter.drawEllipse(QPoint(px, py), 15, 15)

                # 繪製標籤
                pen.setColor(QColor("#f3f4f6"))
                painter.setPen(pen)
                painter.drawText(px + 20, py - 5, name)

            painter.end()

        self.preview_label.setPixmap(scaled_pixmap)

    def _on_preview_clicked(self, event):
        """預覽圖被點擊"""
        if not self.calibrating or not self.screenshot_pixmap:
            return

        # 獲取點擊位置（相對於 label）
        click_pos = event.pos()

        # 獲取當前顯示的 pixmap
        current_pixmap = self.preview_label.pixmap()
        if not current_pixmap:
            return

        # 計算圖片在 label 中的偏移（因為 KeepAspectRatio 會居中）
        label_size = self.preview_label.size()
        pixmap_width = current_pixmap.width()
        pixmap_height = current_pixmap.height()

        offset_x = (label_size.width() - pixmap_width) // 2
        offset_y = (label_size.height() - pixmap_height) // 2

        # 調整點擊座標（減去偏移）
        adjusted_x = click_pos.x() - offset_x
        adjusted_y = click_pos.y() - offset_y

        # 檢查點擊是否在圖片範圍內
        if adjusted_x < 0 or adjusted_y < 0 or adjusted_x >= pixmap_width or adjusted_y >= pixmap_height:
            return

        # 計算縮放比例（從顯示的 pixmap 到原始截圖）
        scale_x = self.screenshot_pixmap.width() / pixmap_width
        scale_y = self.screenshot_pixmap.height() / pixmap_height

        # 計算實際座標
        x = int(adjusted_x * scale_x)
        y = int(adjusted_y * scale_y)

        # 添加標記
        if self.calibrating_slot is not None:
            mark_name = f"Chip {self.calibrating_slot}"
        elif self.calibrating_position is not None:
            mark_name = self.calibrating_position
        else:
            return

        self.calibration_marks[mark_name] = (x, y)

        # 完成校準
        self._on_calibration_complete(x, y)

        # 更新預覽
        self._update_preview()

    def _test_current_chip(self):
        """測試當前選中的籌碼位置"""
        if not self.screenshot_pixmap:
            emit_toast("請先截取螢幕", "warning")
            return

        # 找到第一個已校準的籌碼
        for i, btn in enumerate(self.chip_buttons):
            if btn.is_calibrated:
                chip = self.current_profile.chips[i]
                self._move_to_position(chip.x, chip.y, f"Chip {i+1}")
                return

        emit_toast("沒有已校準的籌碼", "warning")

    def _test_all_chips(self):
        """測試所有已校準的籌碼位置"""
        if not self.screenshot_pixmap:
            emit_toast("請先截取螢幕", "warning")
            return

        calibrated_chips = []
        for i, btn in enumerate(self.chip_buttons):
            if btn.is_calibrated and self.chip_enable_checkboxes[i].isChecked():
                chip = self.current_profile.chips[i]
                calibrated_chips.append((i+1, chip.x, chip.y))

        if not calibrated_chips:
            emit_toast("沒有已校準的籌碼", "warning")
            return

        emit_toast(f"開始測試 {len(calibrated_chips)} 個籌碼位置", "info")

        # 依序測試每個籌碼
        for slot, x, y in calibrated_chips:
            self._move_to_position(x, y, f"Chip {slot}")
            QTimer.singleShot(0, lambda: None)  # 處理事件
            time.sleep(1)  # 1秒延遲

        emit_toast("測試完成", "success")

    def _test_current_position(self):
        """測試當前選中的下注位置"""
        if not self.screenshot_pixmap:
            emit_toast("請先截取螢幕", "warning")
            return

        # 找到第一個已校準的位置
        for pos_name, btn in self.position_buttons.items():
            if btn.is_calibrated:
                pos = self.current_profile.get_bet_position(pos_name)
                if pos:
                    self._move_to_position(pos["x"], pos["y"], btn.display_name)
                    return

        emit_toast("沒有已校準的位置", "warning")

    def _test_all_positions(self):
        """測試所有已校準的下注位置"""
        if not self.screenshot_pixmap:
            emit_toast("請先截取螢幕", "warning")
            return

        calibrated_positions = []
        for pos_name, btn in self.position_buttons.items():
            if btn.is_calibrated:
                pos = self.current_profile.get_bet_position(pos_name)
                if pos:
                    calibrated_positions.append((btn.display_name, pos["x"], pos["y"]))

        if not calibrated_positions:
            emit_toast("沒有已校準的位置", "warning")
            return

        emit_toast(f"開始測試 {len(calibrated_positions)} 個下注位置", "info")

        # 依序測試每個位置
        for name, x, y in calibrated_positions:
            self._move_to_position(x, y, name)
            QTimer.singleShot(0, lambda: None)  # 處理事件
            time.sleep(1)  # 1秒延遲

        emit_toast("測試完成", "success")

    def _move_to_position(self, x: int, y: int, name: str):
        """移動鼠標到指定位置"""
        try:
            # 使用 pyautogui 移動鼠標
            import pyautogui
            pyautogui.FAILSAFE = False
            pyautogui.moveTo(x, y, duration=0.2)

            # 在預覽圖上繪製十字準星
            if self.screenshot_pixmap:
                # 暫時添加標記
                temp_mark_name = f"_test_{name}"
                self.calibration_marks[temp_mark_name] = (x, y)
                self._update_preview()

                # 1秒後移除標記
                QTimer.singleShot(1000, lambda: self._remove_test_mark(temp_mark_name))

            emit_toast(f"移動到 {name} ({x}, {y})", "info")

        except Exception as e:
            emit_toast(f"移動失敗: {e}", "error")

    def _remove_test_mark(self, mark_name: str):
        """移除測試標記"""
        if mark_name in self.calibration_marks:
            del self.calibration_marks[mark_name]
            self._update_preview()

    def _on_preview_mouse_move(self, event):
        """處理預覽圖上的鼠標移動事件"""
        if not self.screenshot_pixmap or self.screenshot_pixmap.isNull():
            return

        # 獲取鼠標位置（相對於 label）
        click_pos = event.pos()

        # 獲取當前顯示的 pixmap
        current_pixmap = self.preview_label.pixmap()
        if not current_pixmap:
            return

        # 計算圖片在 label 中的偏移（因為 KeepAspectRatio 會居中）
        label_size = self.preview_label.size()
        pixmap_width = current_pixmap.width()
        pixmap_height = current_pixmap.height()

        offset_x = (label_size.width() - pixmap_width) // 2
        offset_y = (label_size.height() - pixmap_height) // 2

        # 調整鼠標座標（減去偏移）
        adjusted_x = click_pos.x() - offset_x
        adjusted_y = click_pos.y() - offset_y

        # 檢查鼠標是否在圖片範圍內
        if adjusted_x < 0 or adjusted_y < 0 or adjusted_x >= pixmap_width or adjusted_y >= pixmap_height:
            self.mouse_pos = None
            return

        # 計算縮放比例（從顯示的 pixmap 到原始截圖）
        scale_x = self.screenshot_pixmap.width() / pixmap_width
        scale_y = self.screenshot_pixmap.height() / pixmap_height

        # 計算實際座標
        x = int(adjusted_x * scale_x)
        y = int(adjusted_y * scale_y)

        # 保存鼠標位置
        self.mouse_pos = (x, y)

    def _update_magnifier(self):
        """更新放大鏡顯示"""
        if not self.screenshot_pixmap or not self.mouse_pos or self.screenshot_pixmap.isNull():
            return

        try:
            x, y = self.mouse_pos

            # 獲取放大鏡區域（50x50像素區域）
            magnified = self._get_magnifier_region(x, y, 50)
            if magnified.isNull():
                return

            # 放大到 120x120
            scaled = magnified.scaled(120, 120, Qt.KeepAspectRatio, Qt.FastTransformation)
            if scaled.isNull():
                return

            # 繪製十字準星
            result = QPixmap(scaled.size())
            result.fill(Qt.transparent)

            painter = QPainter(result)
            try:
                painter.setRenderHint(QPainter.Antialiasing)

                # 繪製放大的圖像
                painter.drawPixmap(0, 0, scaled)

                # 繪製十字準星（中心）
                pen = QPen(QColor("#60a5fa"), 2)
                painter.setPen(pen)
                center_x = scaled.width() // 2
                center_y = scaled.height() // 2
                painter.drawLine(center_x - 10, center_y, center_x + 10, center_y)
                painter.drawLine(center_x, center_y - 10, center_x, center_y + 10)

            finally:
                painter.end()

            self.magnifier.setPixmap(result)

        except Exception:
            # 靜默處理放大鏡錯誤，避免影響主功能
            pass

    def _get_magnifier_region(self, center_x: int, center_y: int, size: int = 50) -> QPixmap:
        """獲取放大鏡區域"""
        if not self.screenshot_pixmap or self.screenshot_pixmap.isNull():
            return QPixmap()

        # 計算放大鏡區域
        half_size = size // 2
        x = max(0, min(center_x - half_size, self.screenshot_pixmap.width() - size))
        y = max(0, min(center_y - half_size, self.screenshot_pixmap.height() - size))

        from PySide6.QtCore import QRect
        rect = QRect(x, y, size, size)
        return self.screenshot_pixmap.copy(rect)
