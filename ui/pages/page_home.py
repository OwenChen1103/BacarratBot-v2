# ui/pages/page_home.py
import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QProgressBar, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap

from ..app_state import APP_STATE

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

        title = QLabel("快速動作")
        title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 動作按鈕
        actions = [
            ("位置校準", "positions", "primary"),
            ("可下注判斷", "overlay", "primary"),
            ("策略設定", "strategy", "primary"),
            ("開始實戰", "dashboard", "success")
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

class HealthIndicator(QFrame):
    """系統健康度指示器"""

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self._t = {'complete': False}
        self._p = {'complete': False}
        self._o = {'has_roi': False}
        self._s = {'complete': False}

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border: 1px solid #4b5563;
                border-radius: 8px;
                padding: 16px;
            }
        """)

        layout = QVBoxLayout(self)

        # 主健康狀態
        self.health_label = QLabel("🔴 Blocked — complete setup first")
        self.health_label.setFont(QFont("Microsoft YaHei UI", 14, QFont.Bold))
        self.health_label.setAlignment(Qt.AlignCenter)
        self.health_label.setStyleSheet("color: #ef4444; padding: 8px;")

        # 子系統狀態
        status_layout = QHBoxLayout()
        self.template_status = QLabel("❌ Templates")
        self.position_status = QLabel("❌ Positions")
        self.overlay_status = QLabel("❌ Overlay")
        self.strategy_status = QLabel("❌ Strategy")

        for label in [self.template_status, self.position_status, self.overlay_status, self.strategy_status]:
            label.setFont(QFont("Microsoft YaHei UI", 10))
            label.setAlignment(Qt.AlignCenter)
            status_layout.addWidget(label)

        layout.addWidget(self.health_label)
        layout.addLayout(status_layout)

    def update_health(self, t=None, p=None, o=None, s=None):
        """更新健康狀態"""
        if t: self._t = t
        if p: self._p = p
        if o: self._o = o
        if s: self._s = s

        # 更新子狀態
        self.template_status.setText("✅ Templates" if self._t.get('complete') else "❌ Templates")
        self.template_status.setStyleSheet(f"color: {'#10b981' if self._t.get('complete') else '#ef4444'};")

        self.position_status.setText("✅ Positions" if self._p.get('complete') else "❌ Positions")
        self.position_status.setStyleSheet(f"color: {'#10b981' if self._p.get('complete') else '#ef4444'};")

        self.overlay_status.setText("✅ Overlay" if self._o.get('has_roi') else "❌ Overlay")
        self.overlay_status.setStyleSheet(f"color: {'#10b981' if self._o.get('has_roi') else '#ef4444'};")

        self.strategy_status.setText("✅ Strategy" if self._s.get('complete') else "❌ Strategy")
        self.strategy_status.setStyleSheet(f"color: {'#10b981' if self._s.get('complete') else '#ef4444'};")

        # 更新主狀態
        all_ready = (self._t.get('complete') and self._p.get('complete') and
                    self._o.get('has_roi') and self._s.get('complete'))
        partial_ready = (self._t.get('complete') or self._p.get('complete') or
                        self._o.get('has_roi') or self._s.get('complete'))

        if all_ready:
            self.health_label.setText("Ready — 前置準備已就緒")
            self.health_label.setStyleSheet("color: #10b981; padding: 8px;")
        elif partial_ready:
            self.health_label.setText("Needs Attention — 待設定")
            self.health_label.setStyleSheet("color: #f59e0b; padding: 8px;")
        else:
            self.health_label.setText("Blocked — 須完成設定")
            self.health_label.setStyleSheet("color: #ef4444; padding: 8px;")

class ReadyChecklist(QFrame):
    """準備就緒檢查清單"""

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
                padding: 16px;
            }
        """)

        layout = QVBoxLayout(self)

        title = QLabel("📋 準備就緒檢查清單")
        title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 檢查項目
        self.chk_templates = QCheckBox("🖼️ Templates loaded")
        self.chk_positions = QCheckBox("📍 Positions calibrated")
        self.chk_overlay = QCheckBox("🎯 Overlay ready (ROI + threshold)")
        self.chk_strategy = QCheckBox("⚙️ Strategy configured")

        for chk in [self.chk_templates, self.chk_positions, self.chk_overlay, self.chk_strategy]:
            chk.setFont(QFont("Microsoft YaHei UI", 10))
            chk.setEnabled(False)  # 只顯示狀態，不允許手動勾選
            layout.addWidget(chk)

class HomePage(QWidget):
    navigate_to = Signal(str)

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 標題
        header = QLabel("AutoBet Bot 控制中心")
        header.setFont(QFont("Microsoft YaHei UI", 18, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #374151;
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 8px;
            }
        """)

        # 健康度指示器
        self.health_indicator = HealthIndicator()

        # 準備清單
        self.ready_checklist = ReadyChecklist()

        # 快速操作
        self.quick_actions = QuickActionCard()
        self.quick_actions.action_clicked.connect(self.navigate_to.emit)

        # 最近會話
        self.recent_sessions = RecentSessionsCard()

        # 佈局
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.health_indicator, 2)
        top_layout.addWidget(self.ready_checklist, 1)

        middle_layout = QHBoxLayout()
        middle_layout.addWidget(self.quick_actions, 1)
        middle_layout.addWidget(self.recent_sessions, 1)

        layout.addWidget(header)
        layout.addLayout(top_layout)
        layout.addLayout(middle_layout)
        layout.addStretch()

    def connect_signals(self):
        """連接 AppState 事件"""
        APP_STATE.templatesChanged.connect(self.on_templates_changed)
        APP_STATE.positionsChanged.connect(self.on_positions_changed)
        APP_STATE.overlayChanged.connect(self.on_overlay_changed)
        APP_STATE.strategyChanged.connect(self.on_strategy_changed)

    def on_templates_changed(self, data):
        """模板狀態變更"""
        self.health_indicator.update_health(t=data)
        self.ready_checklist.chk_templates.setChecked(data.get('complete', False))

    def on_positions_changed(self, data):
        """位置狀態變更"""
        self.health_indicator.update_health(p=data)
        self.ready_checklist.chk_positions.setChecked(data.get('complete', False))

    def on_overlay_changed(self, data):
        """Overlay 狀態變更"""
        self.health_indicator.update_health(o=data)
        self.ready_checklist.chk_overlay.setChecked(data.get('has_roi', False))

    def on_strategy_changed(self, data):
        """策略狀態變更"""
        self.health_indicator.update_health(s=data)
        self.ready_checklist.chk_strategy.setChecked(data.get('complete', False))