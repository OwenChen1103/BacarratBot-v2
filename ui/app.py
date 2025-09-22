# ui/app.py
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont
from .main_window import MainWindow

class BaccaratBotApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.setup_app()
        self.main_window = MainWindow()

    def setup_app(self):
        """設定應用程式屬性"""
        self.app.setApplicationName("百家樂自動投注機器人")
        self.app.setApplicationVersion("1.0.0")
        self.app.setOrganizationName("AutoBet Team")

        # 設定暗色主題
        self.app.setStyleSheet(self.get_dark_theme())

        # 設定字體
        font = QFont("Microsoft YaHei UI", 9)
        self.app.setFont(font)

    def get_dark_theme(self):
        """暗色主題樣式"""
        return """
        QMainWindow {
            background-color: #2b2b2b;
            color: #ffffff;
        }

        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
            selection-background-color: #3d8ec9;
        }

        QPushButton {
            background-color: #404040;
            border: 1px solid #555555;
            padding: 6px 12px;
            border-radius: 4px;
            color: #ffffff;
        }

        QPushButton:hover {
            background-color: #4a4a4a;
            border-color: #777777;
        }

        QPushButton:pressed {
            background-color: #353535;
        }

        QPushButton:disabled {
            background-color: #2a2a2a;
            color: #666666;
            border-color: #333333;
        }

        /* 特殊按鈕樣式 */
        QPushButton[class="primary"] {
            background-color: #0e7490;
            border-color: #0891b2;
        }

        QPushButton[class="primary"]:hover {
            background-color: #0891b2;
        }

        QPushButton[class="danger"] {
            background-color: #dc2626;
            border-color: #ef4444;
        }

        QPushButton[class="danger"]:hover {
            background-color: #ef4444;
        }

        QPushButton[class="success"] {
            background-color: #059669;
            border-color: #10b981;
        }

        QPushButton[class="success"]:hover {
            background-color: #10b981;
        }

        QListWidget {
            background-color: #353535;
            border: 1px solid #555555;
            border-radius: 4px;
            outline: none;
        }

        QListWidget::item {
            padding: 8px 12px;
            border-bottom: 1px solid #404040;
        }

        QListWidget::item:selected {
            background-color: #0e7490;
            color: #ffffff;
        }

        QListWidget::item:hover {
            background-color: #404040;
        }

        QTextEdit, QPlainTextEdit {
            background-color: #1e1e1e;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 4px;
            font-family: 'Consolas', 'Monaco', monospace;
        }

        QLineEdit {
            background-color: #353535;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 6px;
        }

        QLineEdit:focus {
            border-color: #0891b2;
        }

        QTabWidget::pane {
            border: 1px solid #555555;
            background-color: #2b2b2b;
        }

        QTabBar::tab {
            background-color: #404040;
            color: #ffffff;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }

        QTabBar::tab:selected {
            background-color: #0e7490;
        }

        QTabBar::tab:hover {
            background-color: #4a4a4a;
        }

        QStatusBar {
            background-color: #353535;
            border-top: 1px solid #555555;
            color: #ffffff;
        }

        QMenuBar {
            background-color: #353535;
            border-bottom: 1px solid #555555;
        }

        QMenuBar::item {
            background-color: transparent;
            padding: 6px 12px;
        }

        QMenuBar::item:selected {
            background-color: #404040;
        }

        QMenu {
            background-color: #353535;
            border: 1px solid #555555;
        }

        QMenu::item {
            padding: 6px 20px;
        }

        QMenu::item:selected {
            background-color: #0e7490;
        }

        QToolBar {
            background-color: #353535;
            border-bottom: 1px solid #555555;
            spacing: 4px;
        }

        QScrollBar:vertical {
            background-color: #2b2b2b;
            width: 12px;
            border-radius: 6px;
        }

        QScrollBar::handle:vertical {
            background-color: #555555;
            border-radius: 6px;
            min-height: 20px;
        }

        QScrollBar::handle:vertical:hover {
            background-color: #666666;
        }
        """

    def run(self):
        """啟動應用程式"""
        self.main_window.show()
        return self.app.exec()

def main():
    """主要入口點"""
    app = BaccaratBotApp()
    sys.exit(app.run())

if __name__ == "__main__":
    main()