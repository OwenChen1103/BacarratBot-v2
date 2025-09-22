# ui/pages/page_strategy.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class StrategyPage(QWidget):
    """策略設定頁面"""
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        placeholder = QLabel("⚙️ 策略設定頁面\n\n即將實現：\n• 表單/JSON 雙模式編輯\n• 風控限制設定\n• 策略即時驗證")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setFont(QFont("Microsoft YaHei UI", 12))
        placeholder.setStyleSheet("""
            QLabel {
                color: #9ca3af;
                background-color: #374151;
                padding: 40px;
                border-radius: 12px;
                border: 2px dashed #6b7280;
            }
        """)
        
        layout.addWidget(placeholder)