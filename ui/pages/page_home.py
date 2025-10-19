# ui/pages/page_home.py
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ..components.config_status_card import ConfigStatusCard

class QuickActionCard(QFrame):
    """快速動作卡片"""
    action_clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 16px;
            }
            QPushButton {
                background-color: #1f2937;
                border: 1px solid #4b5563;
                border-radius: 6px;
                padding: 12px;
                color: #e5e7eb;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #374151;
                border-color: #6b7280;
            }
            QPushButton[class="primary"] {
                background-color: #2563eb;
                border-color: #1d4ed8;
            }
            QPushButton[class="primary"]:hover {
                background-color: #1d4ed8;
            }
            QPushButton[class="success"] {
                background-color: #059669;
                border-color: #047857;
            }
            QPushButton[class="success"]:hover {
                background-color: #047857;
            }
        """)

        layout = QVBoxLayout(self)

        title = QLabel("⚡ 快速操作")
        title.setFont(QFont("Microsoft YaHei UI", 14, QFont.Bold))
        title.setStyleSheet("color: #e5e7eb; margin-bottom: 8px;")
        layout.addWidget(title)

        # 動作按鈕
        actions = [
            ("🎯 籌碼校準", "chip_profile", "primary"),
            ("📍 位置設定", "positions", "primary"),
            ("🎲 策略配置", "strategy", "primary"),
            ("▶️ 開始實戰", "dashboard", "success")
        ]

        for text, action, style_class in actions:
            btn = QPushButton(text)
            btn.setProperty("class", style_class)
            btn.setMinimumHeight(50)
            btn.clicked.connect(lambda checked, a=action: self.action_clicked.emit(a))
            layout.addWidget(btn)

        layout.addStretch()

class WelcomeCard(QFrame):
    """歡迎卡片"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 20px;
            }
        """)

        layout = QVBoxLayout(self)

        # 標題
        title = QLabel("👋 歡迎使用 Baccarat Bot")
        title.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        title.setStyleSheet("color: #e5e7eb; margin-bottom: 12px;")
        layout.addWidget(title)

        # 說明文字
        desc = QLabel(
            "這是您的配置中心。請確保完成以下所有配置項目：\n\n"
            "1️⃣ 籌碼設定 - 校準6顆籌碼的位置和金額\n"
            "2️⃣ ROI設定 - 設定檢測區域（覆蓋層、計時器）\n"
            "3️⃣ 策略設定 - 配置下注策略和風險管理\n"
            "4️⃣ 檢測模板 - 設定圖像識別參數\n\n"
            "✅ 配置完成後，點擊右側的「開始實戰」按鈕即可開始使用。"
        )
        desc.setFont(QFont("Microsoft YaHei UI", 10))
        desc.setStyleSheet("color: #d1d5db; line-height: 1.6;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addStretch()

class HomePage(QWidget):
    navigate_to = Signal(str)

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # 頁面標題
        header = QLabel("🏠 控制中心")
        header.setFont(QFont("Microsoft YaHei UI", 20, QFont.Bold))
        header.setAlignment(Qt.AlignLeft)
        header.setStyleSheet("""
            QLabel {
                color: #ffffff;
                padding: 12px 0;
            }
        """)
        layout.addWidget(header)

        # 配置狀態卡片（從Dashboard移過來的）
        self.config_status_card = ConfigStatusCard()
        self.config_status_card.navigate_requested.connect(
            lambda page: self.navigate_to.emit(page)
        )
        layout.addWidget(self.config_status_card)

        # 下方區域：歡迎卡片 + 快速操作
        bottom_layout = QHBoxLayout()

        # 歡迎說明卡片
        self.welcome_card = WelcomeCard()
        bottom_layout.addWidget(self.welcome_card, 2)

        # 快速操作
        self.quick_actions = QuickActionCard()
        self.quick_actions.action_clicked.connect(self.navigate_to.emit)
        bottom_layout.addWidget(self.quick_actions, 1)

        layout.addLayout(bottom_layout)
        layout.addStretch()
