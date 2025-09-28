# ui/components/toast.py
"""
Toast 通知元件 - 即時成功失敗回饋
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont

class Toast(QWidget):
    """輕量級 Toast 通知"""

    def __init__(self, text: str, toast_type: str = "success", parent=None):
        super().__init__(parent)
        self.setup_ui(text, toast_type)
        self.setup_animation()

    def setup_ui(self, text: str, toast_type: str):
        """設置 UI"""
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 根據類型設置樣式
        styles = {
            "success": "background-color: #059669; border-left: 4px solid #10b981;",
            "error": "background-color: #dc2626; border-left: 4px solid #ef4444;",
            "warning": "background-color: #d97706; border-left: 4px solid #f59e0b;",
            "info": "background-color: #0284c7; border-left: 4px solid #0ea5e9;"
        }

        base_style = """
            color: #ffffff;
            border-radius: 8px;
            padding: 12px 16px;
            font-weight: 500;
            border: 2px solid rgba(255, 255, 255, 0.2);
        """

        self.setStyleSheet(styles.get(toast_type, styles["info"]) + base_style)

        # 佈局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(text)
        label.setFont(QFont("Microsoft YaHei UI", 10))
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        # 調整大小
        self.adjustSize()

    def setup_animation(self):
        """設置動畫"""
        self.setWindowOpacity(0.0)

        # 淡入動畫
        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(300)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(0.95)
        self.fade_in.setEasingCurve(QEasingCurve.OutCubic)

        # 淡出動畫
        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(300)
        self.fade_out.setStartValue(0.95)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.InCubic)
        self.fade_out.finished.connect(self.close)

    def show_toast(self, duration: int = 2200):
        """顯示 Toast"""
        self.show()
        self.fade_in.start()

        # 設置自動關閉
        QTimer.singleShot(duration - 300, self.fade_out.start)

def show_toast(parent, text: str, toast_type: str = "success", duration: int = 2200):
    """顯示 Toast 通知的便利函數"""
    if not parent:
        return

    toast = Toast(text, toast_type, parent)

    # 計算位置 (右上角)
    if hasattr(parent, 'geometry'):
        geo = parent.geometry()
        toast_width = toast.width()
        toast.move(geo.right() - toast_width - 20, geo.top() + 60)

    toast.show_toast(duration)
    return toast