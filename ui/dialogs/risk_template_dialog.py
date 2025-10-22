# ui/dialogs/risk_template_dialog.py
"""風控範本選擇對話框"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QFrame,
    QButtonGroup,
    QRadioButton,
)

from src.autobet.risk_templates import RiskTemplate, RiskTemplateLibrary


class RiskTemplateCard(QFrame):
    """風控範本卡片"""

    def __init__(self, template: RiskTemplate, parent=None):
        super().__init__(parent)
        self.template = template
        self.radio = QRadioButton()
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 2px solid #374151;
                border-radius: 8px;
                padding: 12px;
            }
            QFrame:hover {
                border-color: #60a5fa;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 頂部: 圖示 + 標題 + Radio
        header_layout = QHBoxLayout()

        icon_label = QLabel(self.template.icon)
        icon_label.setStyleSheet("font-size: 24pt;")
        header_layout.addWidget(icon_label)

        title = QLabel(self.template.name)
        title.setStyleSheet("""
            font-weight: bold;
            font-size: 12pt;
            color: #f3f4f6;
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.radio.setStyleSheet("QRadioButton::indicator { width: 18px; height: 18px; }")
        header_layout.addWidget(self.radio)

        layout.addLayout(header_layout)

        # 描述
        desc = QLabel(self.template.description)
        desc.setWordWrap(True)
        desc.setStyleSheet("""
            color: #9ca3af;
            font-size: 10pt;
        """)
        layout.addWidget(desc)

        # 層級資訊
        levels_info = QLabel(f"📊 包含 {len(self.template.levels)} 個風控層級")
        levels_info.setStyleSheet("""
            color: #60a5fa;
            font-size: 9pt;
            font-weight: bold;
        """)
        layout.addWidget(levels_info)

        # 層級詳情
        for i, level in enumerate(self.template.levels):
            level_text = f"  • {level.scope.value}"
            if level.take_profit:
                level_text += f" | 停利: {level.take_profit:,.0f}"
            if level.stop_loss:
                level_text += f" | 停損: {level.stop_loss:,.0f}"
            if level.max_drawdown_losses:
                level_text += f" | 連輸: {level.max_drawdown_losses}"

            level_label = QLabel(level_text)
            level_label.setStyleSheet("""
                color: #d1d5db;
                font-size: 9pt;
                font-family: 'Consolas', monospace;
            """)
            layout.addWidget(level_label)


class RiskTemplateDialog(QDialog):
    """風控範本選擇對話框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("風控範本選擇")
        self.setMinimumSize(700, 600)
        self.selected_template: RiskTemplate | None = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 標題
        title = QLabel("🛡️ 選擇風控範本")
        title.setStyleSheet("""
            font-size: 16pt;
            font-weight: bold;
            color: #f3f4f6;
            padding: 12px;
            background-color: #1f2937;
            border-radius: 8px;
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 說明
        hint = QLabel("選擇一個預設風控範本快速設定,或點擊「取消」手動配置")
        hint.setWordWrap(True)
        hint.setStyleSheet("""
            color: #9ca3af;
            font-size: 10pt;
            padding: 8px;
        """)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # 範本卡片區域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)

        container = QWidget()
        cards_layout = QVBoxLayout(container)
        cards_layout.setSpacing(12)

        # 建立 Radio Button Group
        self.button_group = QButtonGroup(self)

        # 建立所有範本卡片
        templates = RiskTemplateLibrary.get_all()
        self.template_cards = []

        for template in templates:
            card = RiskTemplateCard(template)
            self.button_group.addButton(card.radio)
            self.template_cards.append(card)
            cards_layout.addWidget(card)

            # 點擊卡片任意位置都可以選中
            card.mousePressEvent = lambda e, c=card: c.radio.setChecked(True)

        cards_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # 按鈕
        button_layout = QHBoxLayout()

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 30px;
                background-color: #1f2937;
                color: #f3f4f6;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        cancel_btn.clicked.connect(self.reject)

        apply_btn = QPushButton("套用範本")
        apply_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 30px;
                background-color: #2563eb;
                color: white;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:disabled {
                background-color: #1f2937;
                color: #6b7280;
            }
        """)
        apply_btn.clicked.connect(self.accept)
        apply_btn.setEnabled(False)

        # 當選擇改變時啟用按鈕
        self.button_group.buttonClicked.connect(lambda: apply_btn.setEnabled(True))

        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(apply_btn)

        layout.addLayout(button_layout)

    def get_selected(self) -> RiskTemplate | None:
        """取得選擇的範本"""
        for card in self.template_cards:
            if card.radio.isChecked():
                return card.template
        return None
