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
    """首頁"""
    navigate_to = Signal(str)

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.load_status()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 歡迎訊息
        welcome_label = QLabel("歡迎使用百家樂自動投注機器人！")
        welcome_label.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        welcome_label.setAlignment(Qt.AlignCenter)
        welcome_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                padding: 20px;
                background-color: #1f2937;
                border-radius: 12px;
                border: 2px solid #374151;
            }
        """)
        layout.addWidget(welcome_label)

        # 主要內容區域
        content_layout = QGridLayout()

        # 左上：檔案載入狀態
        status_group = QGroupBox("📁 配置檔案狀態")
        status_group.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        status_layout = QVBoxLayout(status_group)

        self.positions_card = StatusCard("位置配置", "檢查中...", "📍")
        self.strategy_card = StatusCard("策略設定", "檢查中...", "⚙️")
        self.ui_card = StatusCard("UI 配置", "檢查中...", "🎯")
        self.templates_card = StatusCard("模板資料", "檢查中...", "🖼️")

        status_layout.addWidget(self.positions_card)
        status_layout.addWidget(self.strategy_card)
        status_layout.addWidget(self.ui_card)
        status_layout.addWidget(self.templates_card)

        content_layout.addWidget(status_group, 0, 0)

        # 右上：快速動作
        self.quick_actions = QuickActionCard()
        self.quick_actions.action_clicked.connect(self.navigate_to.emit)
        content_layout.addWidget(self.quick_actions, 0, 1)

        # 下方：最近會話
        self.recent_sessions = RecentSessionsCard()
        content_layout.addLayout(QHBoxLayout(), 1, 0, 1, 2)  # 佔據整個下方

        layout.addLayout(content_layout)
        layout.addWidget(self.recent_sessions)
        layout.addStretch()

    def load_status(self):
        """載入各個配置檔案的狀態"""
        # 檢查 positions.json
        if os.path.exists("configs/positions.json"):
            try:
                with open("configs/positions.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("points"):
                        self.positions_card.update_status("已載入")
                    else:
                        self.positions_card.update_status("空白檔案")
            except:
                self.positions_card.update_status("格式錯誤")
        else:
            self.positions_card.update_status("未載入")

        # 檢查 strategy.json
        if os.path.exists("configs/strategy.json"):
            try:
                with open("configs/strategy.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("unit"):
                        self.strategy_card.update_status("已載入")
                    else:
                        self.strategy_card.update_status("空白檔案")
            except:
                self.strategy_card.update_status("格式錯誤")
        else:
            self.strategy_card.update_status("未載入")

        # 檢查 ui.yaml
        if os.path.exists("configs/ui.yaml"):
            self.ui_card.update_status("已載入")
        else:
            self.ui_card.update_status("未載入")

        # 檢查模板目錄
        templates_dir = "templates"
        if os.path.exists(templates_dir):
            template_count = len([f for f in os.listdir(templates_dir)
                                if f.endswith(('.png', '.jpg', '.jpeg'))])
            if template_count > 0:
                self.templates_card.update_status(f"已載入 ({template_count} 個)")
            else:
                self.templates_card.update_status("空白目錄")
        else:
            self.templates_card.update_status("未載入")

    def refresh_status(self):
        """重新整理狀態"""
        self.load_status()
        self.recent_sessions.load_recent_sessions()