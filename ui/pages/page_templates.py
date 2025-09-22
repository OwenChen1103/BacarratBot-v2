# ui/pages/page_templates.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class TemplatesPage(QWidget):
    """模板管理頁面"""
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        placeholder = QLabel("🖼️ 模板管理頁面\n\n即將實現：\n• 模板縮圖顯示\n• NCC 品質檢查\n• 一鍵檢查全部模板")
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