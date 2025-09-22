# ui/pages/page_home.py
import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QProgressBar
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap

class StatusCard(QFrame):
    """狀態卡片元件"""
    def __init__(self, title, status="未載入", icon="❓"):
        super().__init__()
        self.setup_ui(title, status, icon)

    def setup_ui(self, title, status, icon):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        layout = QVBoxLayout(self)

        # 圖示與標題
        header_layout = QHBoxLayout()

        self.icon_label = QLabel(icon)
        self.icon_label.setFont(QFont("Segoe UI Emoji", 16))
        self.icon_label.setAlignment(Qt.AlignCenter)

        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))

        header_layout.addWidget(self.icon_label)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        # 狀態
        self.status_label = QLabel(status)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.update_status(status)

        layout.addLayout(header_layout)
        layout.addWidget(self.status_label)

    def update_status(self, status):
        """更新狀態顯示"""
        self.status_label.setText(status)
        if status == "已載入" or status == "正常":
            color = "#10b981"  # 綠色
            self.icon_label.setText("✅")
        elif status == "未載入" or status == "錯誤":
            color = "#ef4444"  # 紅色
            self.icon_label.setText("❌")
        else:
            color = "#f59e0b"  # 黃色
            self.icon_label.setText("⚠️")

        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

class QuickActionCard(QFrame):
    """快速動作卡片"""
    action_clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)

        title = QLabel("🚀 快速動作")
        title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 動作按鈕
        actions = [
            ("📍 捕捉點位", "positions", "primary"),
            ("🎯 檢查門檻", "overlay", "primary"),
            ("🖼️ 檢查模板", "templates", "secondary"),
            ("🧪 開始乾跑", "dashboard", "success")
        ]

        for text, action, style_class in actions:
            btn = QPushButton(text)
            btn.setProperty("class", style_class)
            btn.clicked.connect(lambda checked, a=action: self.action_clicked.emit(a))
            layout.addWidget(btn)

class RecentSessionsCard(QFrame):
    """最近會話卡片"""
    session_clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)

        title = QLabel("📊 最近會話")
        title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 會話表格
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["時間", "局數", "淨利", "狀態"])

        # 設定表格樣式
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                gridline-color: #404040;
                border: 1px solid #555555;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #404040;
            }
            QTableWidget::item:selected {
                background-color: #0e7490;
            }
        """)

        # 設定表頭
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        # 載入最近會話
        self.load_recent_sessions()

        layout.addWidget(self.table)

    def load_recent_sessions(self):
        """載入最近的會話記錄"""
        sessions_dir = "data/sessions"
        if not os.path.exists(sessions_dir):
            return

        # 獲取 CSV 檔案
        csv_files = [f for f in os.listdir(sessions_dir) if f.startswith("session-") and f.endswith(".csv")]
        csv_files.sort(reverse=True)  # 最新的在前

        self.table.setRowCount(min(len(csv_files), 5))  # 最多顯示 5 筆

        for i, filename in enumerate(csv_files[:5]):
            filepath = os.path.join(sessions_dir, filename)
            try:
                # 解析檔名獲取時間
                time_str = filename.replace("session-", "").replace(".csv", "")
                formatted_time = f"{time_str[:8]} {time_str[9:11]}:{time_str[11:13]}"

                # 讀取 CSV 獲取統計
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    rounds = len(lines) - 1  # 扣除標題行

                    # 簡單統計 (實際應該計算真實盈虧)
                    net_profit = 0  # 目前 MVP 階段都是 0
                    status = "已完成" if rounds > 0 else "空白"

                # 設定表格內容
                self.table.setItem(i, 0, QTableWidgetItem(formatted_time))
                self.table.setItem(i, 1, QTableWidgetItem(str(rounds)))
                self.table.setItem(i, 2, QTableWidgetItem(f"{net_profit:+d}"))
                self.table.setItem(i, 3, QTableWidgetItem(status))

                # 設定顏色
                if net_profit > 0:
                    self.table.item(i, 2).setForeground(Qt.green)
                elif net_profit < 0:
                    self.table.item(i, 2).setForeground(Qt.red)

            except Exception as e:
                print(f"載入會話 {filename} 時發生錯誤: {e}")

class HomePage(QWidget):
    navigate_to = Signal(str)

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def _card(self, title: str, desc: str, btn_text: str, to_key: str):
        card = QFrame()
        card.setFrameStyle(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame { background:#1f2937; border:1px solid #374151; border-radius:10px; }
            QLabel[role="title"] { color:#e5e7eb; font-weight:600; }
            QLabel[role="desc"] { color:#9ca3af; }
        """)
        v = QVBoxLayout(card)
        t = QLabel(title); t.setProperty("role", "title"); t.setFont(QFont("Microsoft YaHei UI", 11))
        d = QLabel(desc); d.setProperty("role", "desc"); d.setWordWrap(True)
        b = QPushButton(btn_text)
        b.clicked.connect(lambda: self.navigate_to.emit(to_key))
        v.addWidget(t); v.addWidget(d); v.addStretch(); v.addWidget(b, alignment=Qt.AlignRight)
        return card

    def setup_ui(self):
        layout = QVBoxLayout(self)
        header = QLabel("歡迎使用 AutoBet Bot")
        header.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        header.setAlignment(Qt.AlignLeft)

        sub = QLabel("建議從左到右依序：模板 → 位置 → 門檻 → 策略 → 主控台（乾跑）")
        sub.setStyleSheet("color:#9ca3af;")

        cards = QHBoxLayout()
        cards.addWidget(self._card("放置模板", "把 chips/bets/controls 模板放進 templates/ 並檢查品質。", "前往模板管理", "templates"))
        cards.addWidget(self._card("校準位置", "雙擊捕捉各元素點位，生成 positions.json。", "前往位置校準", "positions"))
        cards.addWidget(self._card("開始測試", "使用 Demo 事件與乾跑模式，先跑通整條管線。", "前往主控台", "dashboard"))

        layout.addWidget(header)
        layout.addWidget(sub)
        layout.addSpacing(8)
        layout.addLayout(cards)
        layout.addStretch()