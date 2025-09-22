# ui/pages/page_overlay.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class OverlayPage(QWidget):
    """UI 門檻頁面"""
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        placeholder = QLabel("🎯 UI 門檻頁面\n\n即將實現：\n• ROI 可拖拽調整\n• 即時灰階值顯示\n• 門檻校準向導")
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