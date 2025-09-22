# ui/pages/page_events.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class EventsPage(QWidget):
    """事件來源頁面"""
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        placeholder = QLabel("📡 事件來源頁面\n\n即將實現：\n• Demo/NDJSON/SSE 模式選擇\n• 連線狀態測試\n• 事件流預覽")
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