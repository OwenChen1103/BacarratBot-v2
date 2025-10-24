"""Test result display"""
import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from ui.components.compact_live_card import CompactLiveCard

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Result Display")
        self.setGeometry(100, 100, 500, 300)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create live card
        self.live_card = CompactLiveCard()
        layout.addWidget(self.live_card)

        text = self.live_card.result_label.text()
        visible = self.live_card.result_label.isVisible()
        print(f"[INIT] result_label visible: {visible}")
        print(f"[INIT] result_label text length: {len(text)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()

    # Test update after 2 seconds
    from PySide6.QtCore import QTimer
    def test_update():
        print("\n[UPDATE TEST]")
        window.live_card.update_last_result("banker", "player", -100)
        text = window.live_card.result_label.text()
        print(f"[AFTER UPDATE] result_label text length: {len(text)}")

    QTimer.singleShot(2000, test_update)

    sys.exit(app.exec())
