# ui/components/config_status_card.py
"""
配置狀態卡片 - 顯示系統配置完整性
"""
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QGridLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.utils.config_validator import ConfigValidator


class ConfigStatusCard(QFrame):
    """配置狀態顯示卡片"""

    navigate_requested = Signal(str)  # 請求跳轉到指定頁面

    def __init__(self):
        super().__init__()
        self.validator = ConfigValidator()
        self.setup_ui()
        self.refresh_status()

    def setup_ui(self):
        """建立UI"""
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 2px solid #3b82f6;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 標題行
        header_layout = QHBoxLayout()

        icon = QLabel("📊")
        icon.setFont(QFont("Segoe UI Emoji", 14))
        header_layout.addWidget(icon)

        title = QLabel("系統配置狀態")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        title.setStyleSheet("color: #f9fafb;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 刷新按鈕
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(32, 32)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14pt;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        self.refresh_btn.clicked.connect(self.refresh_status)
        header_layout.addWidget(self.refresh_btn)

        layout.addLayout(header_layout)

        # 完成度進度條
        progress_layout = QHBoxLayout()

        self.completion_label = QLabel("完成度:")
        self.completion_label.setStyleSheet("color: #d1d5db; font-weight: bold;")
        progress_layout.addWidget(self.completion_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #4b5563;
                border-radius: 4px;
                background-color: #374151;
                text-align: center;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.progress_bar, 1)

        self.status_text = QLabel("0/4")
        self.status_text.setStyleSheet("color: #d1d5db; font-weight: bold;")
        progress_layout.addWidget(self.status_text)

        layout.addLayout(progress_layout)

        # 配置項目狀態網格
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(8)

        # 配置項目
        self.config_items = {}
        configs = [
            ('chip_profile', '籌碼設定', 'chip_profile'),
            ('positions', 'ROI設定', 'overlay'),
            ('strategy', '策略設定', 'strategy'),
            ('overlay', '檢測模板', 'overlay'),
        ]

        for idx, (key, label, page) in enumerate(configs):
            row = idx // 2
            col = idx % 2

            item_widget = self._create_config_item(key, label, page)
            self.config_items[key] = item_widget
            self.grid_layout.addWidget(item_widget, row, col)

        layout.addLayout(self.grid_layout)

    def _create_config_item(self, key: str, label: str, page: str):
        """創建配置項目小部件"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 6px;
                padding: 8px;
            }
            QFrame:hover {
                background-color: #4b5563;
            }
        """)
        widget.setCursor(Qt.PointingHandCursor)
        widget.mousePressEvent = lambda event: self.navigate_requested.emit(page)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # 狀態圖標
        status_icon = QLabel("○")
        status_icon.setFont(QFont("Segoe UI Emoji", 12))
        status_icon.setStyleSheet("color: #9ca3af;")
        layout.addWidget(status_icon)

        # 標籤
        text_label = QLabel(label)
        text_label.setStyleSheet("color: #e5e7eb; font-weight: bold;")
        layout.addWidget(text_label, 1)

        # 詳情標籤
        detail_label = QLabel("")
        detail_label.setStyleSheet("color: #9ca3af; font-size: 9pt;")
        layout.addWidget(detail_label)

        # 保存引用
        widget.status_icon = status_icon
        widget.detail_label = detail_label
        widget.key = key

        return widget

    def refresh_status(self):
        """刷新配置狀態"""
        try:
            summary = self.validator.get_config_summary()
            results = summary['results']

            # 更新進度條
            completion = int(summary['completion_rate'] * 100)
            self.progress_bar.setValue(completion)

            completed = summary['completed_modules']
            total = summary['total_modules']
            self.status_text.setText(f"{completed}/{total}")

            # 更新各配置項目
            for key, widget in self.config_items.items():
                result = results.get(key)
                if result:
                    # 更新圖標和顏色
                    if result.complete:
                        widget.status_icon.setText("✅")
                        widget.status_icon.setStyleSheet("color: #10b981;")
                    else:
                        widget.status_icon.setText("❌")
                        widget.status_icon.setStyleSheet("color: #ef4444;")

                    # 更新詳情
                    if result.details:
                        detail = result.details[0]  # 顯示第一條詳情
                        # 移除emoji前綴
                        detail = detail.replace("✅ ", "").replace("❌ ", "").replace("⚠️ ", "")
                        widget.detail_label.setText(detail[:20] + "..." if len(detail) > 20 else detail)

            # 更新整體狀態文字顏色
            if summary['ready_for_battle']:
                self.completion_label.setStyleSheet("color: #10b981; font-weight: bold;")
            else:
                self.completion_label.setStyleSheet("color: #f59e0b; font-weight: bold;")

        except Exception as e:
            print(f"刷新配置狀態失敗: {e}")
            self.status_text.setText("錯誤")
            self.progress_bar.setValue(0)
