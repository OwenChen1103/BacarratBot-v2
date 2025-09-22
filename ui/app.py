# ui/app.py
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from .main_window import MainWindow

DARK_QSS = """
QMainWindow { background:#111317; color:#e5e7eb; }
QWidget { background:#111317; color:#e5e7eb; }
QStatusBar { background:#0f1115; color:#9ca3af; }
QToolBar { background:#0f1115; border:0; }
QListWidget {
    background:#1f2937;
    color:#e5e7eb;
    border:1px solid #374151;
    border-radius:6px;
    font-size:10pt;
}
QListWidget::item {
    padding:12px 16px;
    color:#e5e7eb;
    border-bottom:1px solid #374151;
    border-radius:4px;
    margin:2px;
}
QListWidget::item:selected {
    background:#0e7490;
    color:#ffffff;
    font-weight:bold;
}
QListWidget::item:hover {
    background:#374151;
    color:#ffffff;
}
QFrame { color:#e5e7eb; background:#111317; }
QLabel { color:#e5e7eb; }
QPushButton {
    background:#2a2f3a;
    color:#e5e7eb;
    border:1px solid #3a3f4a;
    padding:8px 16px;
    border-radius:6px;
    font-weight:bold;
}
QPushButton:hover {
    background:#323846;
    border-color:#4a5568;
}
QPushButton:pressed {
    background:#1a202c;
}
QPushButton[class="success"] {
    background:#14532d;
    border-color:#16a34a;
    color:#ffffff;
}
QPushButton[class="success"]:hover {
    background:#166534;
    border-color:#22c55e;
}
QPushButton[class="danger"] {
    background:#7f1d1d;
    border-color:#dc2626;
    color:#ffffff;
}
QPushButton[class="danger"]:hover {
    background:#991b1b;
    border-color:#ef4444;
}
QPushButton[class="primary"] {
    background:#0e7490;
    border-color:#0891b2;
    color:#ffffff;
}
QPushButton[class="primary"]:hover {
    background:#0891b2;
    border-color:#06b6d4;
}
QComboBox, QCheckBox { color:#e5e7eb; }
QTableWidget { color:#e5e7eb; background:#1f2937; }
QTextEdit, QPlainTextEdit {
    background:#1e1e1e;
    color:#e5e7eb;
    border:1px solid #374151;
    border-radius:4px;
}
QLineEdit {
    background:#2a2f3a;
    color:#e5e7eb;
    border:1px solid #3a3f4a;
    border-radius:4px;
    padding:6px;
}
QGroupBox {
    color:#e5e7eb;
    border:2px solid #374151;
    border-radius:8px;
    margin-top:6px;
    padding-top:6px;
}
QGroupBox::title {
    color:#e5e7eb;
    subcontrol-origin:margin;
    left:10px;
    padding:0 5px 0 5px;
}
"""

class BaccaratBotApp:
    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        font = QFont("Microsoft YaHei UI", 9)
        self.app.setFont(font)
        self.app.setStyleSheet(DARK_QSS)
        self.window = MainWindow()

    def run(self):
        self.window.show()
        return self.app.exec()

def run():
    return BaccaratBotApp().run()

if __name__ == "__main__":
    sys.exit(run())