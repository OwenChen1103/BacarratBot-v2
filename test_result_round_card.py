# test_result_round_card.py
"""
ResultRoundCard 組件測試腳本
用於獨立測試結果局卡片的顯示效果
"""

import sys
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget, QPushButton
from ui.components.result_round_card import ResultRoundCard


class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ResultRoundCard 測試")
        self.setGeometry(100, 100, 500, 600)
        self.setStyleSheet("background-color: #111827;")

        layout = QVBoxLayout(self)

        # 結果局卡片
        self.card = ResultRoundCard()
        layout.addWidget(self.card)

        # 測試按鈕區
        btn_layout = QVBoxLayout()

        # 按鈕1: 顯示莊家下注
        btn_show_banker = QPushButton("顯示 - 莊家 200元 (第2層)")
        btn_show_banker.clicked.connect(self.test_show_banker)
        btn_layout.addWidget(btn_show_banker)

        # 按鈕2: 顯示閒家下注
        btn_show_player = QPushButton("顯示 - 閒家 400元 (第3層)")
        btn_show_player.clicked.connect(self.test_show_player)
        btn_layout.addWidget(btn_show_player)

        # 按鈕3: 獲勝結果
        btn_win = QPushButton("結果 - 獲勝 (+200)")
        btn_win.clicked.connect(lambda: self.card.update_outcome("win", 200))
        btn_layout.addWidget(btn_win)

        # 按鈕4: 失敗結果
        btn_loss = QPushButton("結果 - 失敗 (-200)")
        btn_loss.clicked.connect(lambda: self.card.update_outcome("loss", -200))
        btn_layout.addWidget(btn_loss)

        # 按鈕5: 和局跳過
        btn_skip = QPushButton("結果 - 和局 (0)")
        btn_skip.clicked.connect(lambda: self.card.update_outcome("skip", 0))
        btn_layout.addWidget(btn_skip)

        # 按鈕6: 隱藏卡片
        btn_hide = QPushButton("隱藏卡片")
        btn_hide.clicked.connect(self.card.hide_card)
        btn_layout.addWidget(btn_hide)

        layout.addLayout(btn_layout)

    def test_show_banker(self):
        """測試顯示莊家下注"""
        self.card.show_pending_bet({
            "strategy": "martingale_bpp",
            "direction": "banker",
            "amount": 200,
            "current_layer": 2,
            "total_layers": 4,
            "round_id": "detect-1234567890123",
            "sequence": [100, 200, 400, 800],
            "on_win": "RESET",
            "on_loss": "ADVANCE"
        })

    def test_show_player(self):
        """測試顯示閒家下注"""
        self.card.show_pending_bet({
            "strategy": "anti_martingale",
            "direction": "player",
            "amount": 400,
            "current_layer": 3,
            "total_layers": 5,
            "round_id": "detect-9876543210987",
            "sequence": [100, 200, 400, 800, 1600],
            "on_win": "ADVANCE",
            "on_loss": "RESET"
        })


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())
