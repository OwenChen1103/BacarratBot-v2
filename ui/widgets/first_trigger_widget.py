# ui/widgets/first_trigger_widget.py
"""首次觸發行為設定 Widget"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QRadioButton,
    QLabel,
    QFrame,
)


class FirstTriggerWidget(QGroupBox):
    """首次觸發行為設定"""

    value_changed = Signal(int)  # 當值改變時發送信號

    def __init__(self, parent=None):
        super().__init__("🎲 首次符合條件時", parent)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            FirstTriggerWidget {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                font-weight: bold;
                color: #e5e7eb;
                font-size: 11pt;
            }
            FirstTriggerWidget::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: transparent;
            }
            FirstTriggerWidget QLabel {
                background-color: transparent;
                color: #e5e7eb;
            }
            FirstTriggerWidget QWidget {
                background-color: transparent;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 選項 1: 立即下注
        self.radio_immediate = QRadioButton("立即下注第一層")
        self.radio_immediate.setChecked(True)  # 預設
        self.radio_immediate.setStyleSheet("""
            QRadioButton {
                color: #f3f4f6;
                font-size: 11pt;
                padding: 6px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.radio_immediate.toggled.connect(self._on_radio_changed)

        immediate_hint = QLabel("└─ 適合: 積極進場,信號確認即執行")
        immediate_hint.setStyleSheet("""
            color: #9ca3af;
            font-size: 10pt;
            padding-left: 30px;
            font-weight: normal;
        """)

        layout.addWidget(self.radio_immediate)
        layout.addWidget(immediate_hint)

        layout.addSpacing(8)

        # 選項 2: 僅記錄
        self.radio_observe = QRadioButton("僅記錄,下次才下注")
        self.radio_observe.setStyleSheet("""
            QRadioButton {
                color: #f3f4f6;
                font-size: 11pt;
                padding: 6px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.radio_observe.toggled.connect(self._on_radio_changed)

        observe_hint = QLabel("└─ 適合: 確認信號穩定後再進場")
        observe_hint.setStyleSheet("""
            color: #9ca3af;
            font-size: 10pt;
            padding-left: 30px;
            font-weight: normal;
        """)

        layout.addWidget(self.radio_observe)
        layout.addWidget(observe_hint)

        layout.addSpacing(12)

        # 範例說明
        example_box = QFrame()
        example_box.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        example_layout = QVBoxLayout(example_box)

        example_title = QLabel("📖 範例說明:")
        example_title.setStyleSheet("""
            font-weight: bold;
            color: #60a5fa;
            font-size: 10pt;
        """)

        example_text = QLabel(
            "條件: <b>BB then bet P</b> (兩莊後押閒)<br>"
            "實際開牌: <b>莊 → 莊 → ?</b><br><br>"
            "• <span style='color: #10b981;'>立即下注</span>: 第 3 手立即押閒 100 元<br>"
            "• <span style='color: #f59e0b;'>僅記錄</span>: 第 3 手不下注,第 4 手再符合才押閒"
        )
        example_text.setWordWrap(True)
        example_text.setStyleSheet("""
            color: #d1d5db;
            font-size: 10pt;
            font-weight: normal;
        """)

        example_layout.addWidget(example_title)
        example_layout.addWidget(example_text)

        layout.addWidget(example_box)

    def _on_radio_changed(self):
        """當單選按鈕改變時發送信號"""
        self.value_changed.emit(self.get_value())

    def get_value(self) -> int:
        """轉換為技術值 (0 或 1)"""
        if self.radio_immediate.isChecked():
            return 1  # 立即下注
        else:
            return 0  # 僅記錄

    def set_value(self, value: int):
        """從技術值設定 (0 或 1)"""
        if value == 1:
            self.radio_immediate.setChecked(True)
        else:
            self.radio_observe.setChecked(True)
