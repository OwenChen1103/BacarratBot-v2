# ui/dialogs/template_selection_dialog.py
"""策略範本選擇對話框"""
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
    QComboBox,
)

from src.autobet.strategy_templates import StrategyTemplateLibrary, StrategyTemplate


class TemplateSelectionDialog(QDialog):
    """範本選擇對話框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("選擇策略範本")
        self.setMinimumSize(900, 650)
        self.selected_template: StrategyTemplate = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 標題
        title = QLabel("🎲 選擇預設策略範本")
        title.setStyleSheet("""
            QLabel {
                font-size: 18pt;
                font-weight: bold;
                color: #f9fafb;
                background-color: #1f2937;
                padding: 16px;
                border-radius: 8px;
            }
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 篩選
        filter_layout = QHBoxLayout()
        filter_label = QLabel("難度篩選:")
        filter_label.setStyleSheet("color: #e5e7eb; font-size: 11pt;")

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "新手", "進階", "專家"])
        self.filter_combo.setStyleSheet("""
            QComboBox {
                background-color: #1f2937;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 120px;
            }
            QComboBox:hover {
                background-color: #4b5563;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        self.filter_combo.currentTextChanged.connect(self.apply_filter)

        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_combo)
        filter_layout.addStretch()

        layout.addLayout(filter_layout)

        # 範本列表 (捲動區域)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)

        self.template_container = QWidget()
        self.template_layout = QVBoxLayout(self.template_container)
        self.template_layout.setSpacing(12)
        scroll.setWidget(self.template_container)

        layout.addWidget(scroll, 1)

        # 按鈕
        buttons = QHBoxLayout()
        buttons.setSpacing(12)

        self.btn_use = QPushButton("✅ 使用此範本")
        self.btn_use.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #047857;
            }
            QPushButton:disabled {
                background-color: #1f2937;
                color: #6b7280;
            }
        """)
        self.btn_use.clicked.connect(self.accept)
        self.btn_use.setEnabled(False)

        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #1f2937;
                color: #f3f4f6;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        btn_cancel.clicked.connect(self.reject)

        buttons.addStretch()
        buttons.addWidget(self.btn_use)
        buttons.addWidget(btn_cancel)

        layout.addLayout(buttons)

        # 載入範本
        self.load_templates()

    def load_templates(self):
        """載入所有範本"""
        templates = StrategyTemplateLibrary.get_all_templates()

        for key, template in templates.items():
            card = self.create_template_card(template)
            self.template_layout.addWidget(card)

        self.template_layout.addStretch()

    def create_template_card(self, template: StrategyTemplate) -> QWidget:
        """建立範本卡片"""
        card = QFrame()
        card.setProperty("difficulty", template.difficulty)
        card.setProperty("selected", False)
        card.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 2px solid #374151;
                border-radius: 8px;
                padding: 16px;
            }
            QFrame:hover {
                border-color: #3b82f6;
                background-color: #1e293b;
            }
        """)
        card.setCursor(Qt.PointingHandCursor)

        # 點擊事件
        card.mousePressEvent = lambda e: self.select_template(template, card)

        layout = QHBoxLayout(card)
        layout.setSpacing(16)

        # 圖示
        icon = QLabel(template.icon)
        icon.setStyleSheet("font-size: 48px;")
        icon.setFixedWidth(60)
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        # 資訊
        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)

        # 名稱
        name_label = QLabel(f"<b>{template.name}</b>")
        name_label.setStyleSheet("font-size: 14pt; color: #f9fafb;")
        info_layout.addWidget(name_label)

        # 描述
        desc_label = QLabel(template.description)
        desc_label.setStyleSheet("color: #9ca3af; font-size: 10pt;")
        desc_label.setWordWrap(True)
        info_layout.addWidget(desc_label)

        # 詳細資訊
        staking = template.definition.staking
        entry = template.definition.entry
        risk = template.definition.risk

        details_parts = [
            f"<b>難度:</b> {template.difficulty}",
            f"<b>進場:</b> {entry.pattern}",
            f"<b>層數:</b> {len(staking.sequence)}",
            f"<b>進層規則:</b> {'輸進' if staking.advance_on.value == 'loss' else '贏進'}",
            f"<b>風控:</b> {len(risk.levels)} 個層級",
        ]

        details = QLabel(" | ".join(details_parts))
        details.setStyleSheet("font-size: 9pt; color: #6b7280;")
        info_layout.addWidget(details)

        layout.addLayout(info_layout, 1)

        # 選擇指示
        self.select_indicator = QLabel()
        self.select_indicator.setFixedWidth(40)
        self.select_indicator.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.select_indicator)

        # 儲存引用以便後續更新
        card.select_indicator = self.select_indicator

        return card

    def select_template(self, template: StrategyTemplate, card: QFrame):
        """選擇範本"""
        # 清除所有卡片的選中狀態
        for i in range(self.template_layout.count()):
            item = self.template_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QFrame):
                widget = item.widget()
                widget.setStyleSheet("""
                    QFrame {
                        background-color: #1f2937;
                        border: 2px solid #374151;
                        border-radius: 8px;
                        padding: 16px;
                    }
                    QFrame:hover {
                        border-color: #3b82f6;
                        background-color: #1e293b;
                    }
                """)
                if hasattr(widget, 'select_indicator'):
                    widget.select_indicator.setText("")

        # 標記當前卡片為選中
        card.setStyleSheet("""
            QFrame {
                background-color: #1e3a5f;
                border: 3px solid #3b82f6;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        card.select_indicator.setText("✅")
        card.select_indicator.setStyleSheet("font-size: 24px;")

        self.selected_template = template
        self.btn_use.setEnabled(True)

    def apply_filter(self, difficulty: str):
        """套用難度篩選"""
        for i in range(self.template_layout.count()):
            item = self.template_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, 'property'):
                    widget_difficulty = widget.property("difficulty")
                    if difficulty == "全部":
                        widget.setVisible(True)
                    else:
                        widget.setVisible(widget_difficulty == difficulty)

    def get_selected(self) -> StrategyTemplate:
        """取得選中的範本"""
        return self.selected_template
