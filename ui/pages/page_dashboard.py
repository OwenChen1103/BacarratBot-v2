# ui/pages/page_dashboard.py
import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QTextEdit, QGroupBox,
    QProgressBar, QComboBox, QCheckBox, QSpinBox,
    QMessageBox, QInputDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QTabWidget
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QTextCursor, QColor, QPalette

from ..workers.engine_worker import EngineWorker

class StatusCard(QFrame):
    """狀態卡片"""
    def __init__(self, title: str, icon: str = "📊"):
        super().__init__()
        self.title = title
        self.icon = icon
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

        # 標題
        header_layout = QHBoxLayout()
        self.icon_label = QLabel(self.icon)
        self.icon_label.setFont(QFont("Segoe UI Emoji", 14))

        self.title_label = QLabel(self.title)
        self.title_label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))

        header_layout.addWidget(self.icon_label)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        # 內容
        self.content_label = QLabel("待機中...")
        self.content_label.setAlignment(Qt.AlignCenter)
        # 使用支援 emoji 的字體
        content_font = QFont("Microsoft YaHei UI", 12, QFont.Bold)
        content_font.setStyleStrategy(QFont.PreferAntialias)
        self.content_label.setFont(content_font)

        layout.addLayout(header_layout)
        layout.addWidget(self.content_label)

    def update_content(self, content: str, color: str = "#ffffff"):
        """更新內容"""
        self.content_label.setText(content)
        self.content_label.setStyleSheet(f"color: {color};")

class LogViewer(QFrame):
    """日誌檢視器"""
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #404040;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)

        # 標題與篩選
        header_layout = QHBoxLayout()

        title = QLabel("📋 即時日誌")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))

        self.level_filter = QComboBox()
        self.level_filter.addItems(["全部", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.level_filter.setCurrentText("INFO")

        self.module_filter = QComboBox()
        self.module_filter.addItems(["全部", "Engine", "Events", "Config", "Actuator"])

        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear_logs)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(QLabel("等級:"))
        header_layout.addWidget(self.level_filter)
        header_layout.addWidget(QLabel("模組:"))
        header_layout.addWidget(self.module_filter)
        header_layout.addWidget(clear_btn)

        # 日誌文字區域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #0f0f0f;
                color: #e5e5e5;
                border: 1px solid #333333;
                border-radius: 4px;
            }
        """)

        layout.addLayout(header_layout)
        layout.addWidget(self.log_text)

    def add_log(self, level: str, module: str, message: str):
        """添加日誌"""
        # 篩選檢查
        if self.level_filter.currentText() != "全部" and level != self.level_filter.currentText():
            return
        if self.module_filter.currentText() != "全部" and module != self.module_filter.currentText():
            return

        # 顏色對應
        colors = {
            "DEBUG": "#9ca3af",
            "INFO": "#60a5fa",
            "WARNING": "#f59e0b",
            "ERROR": "#ef4444"
        }
        color = colors.get(level, "#ffffff")

        # 格式化訊息
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f'<span style="color: #6b7280;">{timestamp}</span> <span style="color: {color}; font-weight: bold;">[{level}]</span> <span style="color: #a3a3a3;">{module}:</span> <span style="color: #e5e5e5;">{message}</span>'

        # 添加到文字區域
        self.log_text.append(formatted_msg)

        # 自動滾動到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

        # 限制日誌長度 (保持最後 1000 行)
        document = self.log_text.document()
        if document.blockCount() > 1000:
            cursor = QTextCursor(document)
            cursor.movePosition(QTextCursor.Start)
            for _ in range(100):  # 刪除前 100 行
                cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

    def clear_logs(self):
        """清除日誌"""
        self.log_text.clear()

class PlanCard(QFrame):
    """下注計畫卡片"""
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

        title = QLabel("🎯 下注計畫")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        layout.addWidget(title)

        self.plan_text = QTextEdit()
        self.plan_text.setReadOnly(True)
        self.plan_text.setMaximumHeight(120)
        self.plan_text.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                border: 1px solid #404040;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 9pt;
            }
        """)
        self.plan_text.setText("等待下注計畫...")

        layout.addWidget(self.plan_text)

    def update_plan(self, plan_data: dict):
        """更新下注計畫"""
        if not plan_data:
            self.plan_text.setText("無計畫資料")
            return

        # 格式化計畫顯示
        formatted_plan = "📋 本輪下注計畫：\n\n"

        total_amount = 0
        for target, amount in plan_data.items():
            formatted_plan += f"• {target}: {amount:,} 元\n"
            total_amount += amount

        formatted_plan += f"\n💰 總金額: {total_amount:,} 元"

        self.plan_text.setText(formatted_plan)

class StatsCard(QFrame):
    """統計卡片"""
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

        title = QLabel("📊 會話統計")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        layout.addWidget(title)

        # 統計表格
        self.stats_table = QTableWidget(4, 2)
        self.stats_table.setHorizontalHeaderLabels(["項目", "數值"])
        self.stats_table.verticalHeader().setVisible(False)

        # 設定表格樣式
        self.stats_table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                gridline-color: #404040;
                border: 1px solid #555555;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #404040;
            }
        """)

        # 初始化數據
        stats_items = [
            ("局數", "0"),
            ("淨利", "0"),
            ("最後結果", "-"),
            ("運行時間", "00:00:00")
        ]

        for i, (item, value) in enumerate(stats_items):
            self.stats_table.setItem(i, 0, QTableWidgetItem(item))
            self.stats_table.setItem(i, 1, QTableWidgetItem(value))

        # 調整列寬
        header = self.stats_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)

        layout.addWidget(self.stats_table)

    def update_stats(self, stats: dict):
        """更新統計資料"""
        rounds = stats.get("rounds", 0)
        net = stats.get("net", 0)
        last_winner = stats.get("last_winner", "-")

        # 轉換結果顯示
        winner_display = {
            "B": "莊贏", "P": "閒贏", "T": "和局", None: "-"
        }.get(last_winner, str(last_winner))

        self.stats_table.item(0, 1).setText(str(rounds))
        self.stats_table.item(1, 1).setText(f"{net:+d}")
        self.stats_table.item(2, 1).setText(winner_display)

        # 設定淨利顏色
        if net > 0:
            self.stats_table.item(1, 1).setForeground(QColor("#10b981"))
        elif net < 0:
            self.stats_table.item(1, 1).setForeground(QColor("#ef4444"))
        else:
            self.stats_table.item(1, 1).setForeground(QColor("#6b7280"))

class DashboardPage(QWidget):
    """實戰主控台頁面"""
    navigate_to = Signal(str)

    def __init__(self):
        super().__init__()
        self.engine_worker = None
        self.start_time = None
        self.setup_ui()
        self.setup_engine()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 頂部控制區域
        self.setup_control_panel(layout)

        # 主要內容區域 (分割器)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # 左側：日誌區域
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self.log_viewer = LogViewer()
        left_layout.addWidget(self.log_viewer)

        splitter.addWidget(left_frame)

        # 右側：狀態與統計
        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self.plan_card = PlanCard()
        self.stats_card = StatsCard()

        right_layout.addWidget(self.plan_card)
        right_layout.addWidget(self.stats_card)
        right_layout.addStretch()

        splitter.addWidget(right_frame)

        # 設定分割比例 (日誌:狀態 = 2:1)
        splitter.setSizes([800, 400])

    def setup_control_panel(self, parent_layout):
        """設定控制面板"""
        control_frame = QFrame()
        control_frame.setFrameStyle(QFrame.StyledPanel)
        control_frame.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        control_layout = QGridLayout(control_frame)

        # 狀態顯示卡片
        self.state_card = StatusCard("引擎狀態", "🤖")
        self.mode_card = StatusCard("運行模式", "🧪")
        self.events_card = StatusCard("事件來源", "📡")

        control_layout.addWidget(self.state_card, 0, 0)
        control_layout.addWidget(self.mode_card, 0, 1)
        control_layout.addWidget(self.events_card, 0, 2)

        # 控制按鈕
        button_layout = QHBoxLayout()

        # 模擬實戰按鈕
        self.simulate_btn = QPushButton("🎯 模擬實戰")
        self.simulate_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:disabled {
                background-color: #6b7280;
            }
        """)
        self.simulate_btn.clicked.connect(self.start_simulation)

        # 開始實戰按鈕
        self.start_btn = QPushButton("⚡ 開始實戰")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
            QPushButton:disabled {
                background-color: #6b7280;
            }
        """)
        self.start_btn.clicked.connect(self.start_real_battle)

        # 停止按鈕
        self.stop_btn = QPushButton("🛑 停止")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: white;
                border: 1px solid #6b7280;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
            QPushButton:disabled {
                background-color: #1f2937;
                color: #6b7280;
            }
        """)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_engine)

        button_layout.addWidget(self.simulate_btn)
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addStretch()

        control_layout.addLayout(button_layout, 1, 0, 1, 3)

        parent_layout.addWidget(control_frame)

    def setup_engine(self):
        """設定引擎工作執行緒"""
        self.engine_worker = EngineWorker()

        # 連接訊號
        self.engine_worker.state_changed.connect(self.on_state_changed)
        self.engine_worker.session_stats.connect(self.on_stats_updated)
        self.engine_worker.log_message.connect(self.on_log_message)
        self.engine_worker.engine_status.connect(self.on_engine_status)

        # 啟動工作執行緒
        self.engine_worker.start()

        # 初始化引擎（等啟動時再設定模式）
        success = self.engine_worker.initialize_engine()
        if success:
            self.log_viewer.add_log("INFO", "Dashboard", "引擎工作執行緒已準備就緒")
        else:
            self.log_viewer.add_log("ERROR", "Dashboard", "引擎初始化失敗")

        # 設定初始狀態
        self.mode_card.update_content("⏸ 待機中", "#6b7280")
        self.events_card.update_content("🎯 Overlay 檢測", "#10b981")

    def start_simulation(self):
        """啟動模擬實戰模式"""
        if not self.engine_worker:
            return

        # 檢查配置完整性
        if not self._check_config_ready():
            return

        # 啟動模擬模式
        success = self.engine_worker.start_engine(mode="simulation")

        if success:
            self.simulate_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.mode_card.update_content("🎯 模擬實戰中", "#0284c7")
            self.start_time = self.get_current_time()

            # 啟動運行時間計時器
            self.runtime_timer = QTimer()
            self.runtime_timer.timeout.connect(self.update_runtime)
            self.runtime_timer.start(1000)

            self.log_viewer.add_log("INFO", "Dashboard", "🎯 模擬實戰模式已啟動 - 將移動滑鼠但不實際點擊")

    def start_real_battle(self):
        """啟動真實實戰模式"""
        if not self.engine_worker:
            return

        # 檢查配置完整性
        if not self._check_config_ready():
            return

        # 確認對話框
        reply = QMessageBox.question(
            self, "確認實戰模式",
            "⚠️ 您即將啟動實戰模式！\n\n" +
            "系統將會：\n" +
            "• 檢測遊戲畫面的「請下注」狀態\n" +
            "• 根據策略自動移動滑鼠並點擊\n" +
            "• 執行真實的下注操作\n\n" +
            "確定要繼續嗎？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 啟動實戰模式
        success = self.engine_worker.start_engine(mode="real")

        if success:
            self.simulate_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.mode_card.update_content("⚡ 實戰進行中", "#dc2626")
            self.start_time = self.get_current_time()

            # 啟動運行時間計時器
            self.runtime_timer = QTimer()
            self.runtime_timer.timeout.connect(self.update_runtime)
            self.runtime_timer.start(1000)

            self.log_viewer.add_log("WARNING", "Dashboard", "⚡ 實戰模式已啟動 - 將執行真實點擊操作")

    def _check_config_ready(self):
        """檢查配置是否就緒"""
        import os

        # 檢查 positions.json
        if not os.path.exists("configs/positions.json"):
            QMessageBox.warning(self, "配置缺失", "未找到 positions.json\n請先完成位置校準！")
            return False

        # 檢查 strategy.json
        if not os.path.exists("configs/strategy.json"):
            QMessageBox.warning(self, "配置缺失", "未找到 strategy.json\n請先完成策略設定！")
            return False

        # 檢查模板
        if not os.path.exists("templates") or not any(f.endswith('.png') for f in os.listdir("templates")):
            QMessageBox.warning(self, "配置缺失", "未找到模板文件\n請先設定檢測模板！")
            return False

        return True

    def stop_engine(self):
        """停止引擎"""
        if self.engine_worker:
            self.engine_worker.stop_engine()

        # 重置按鈕狀態
        self.simulate_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        # 重置模式顯示
        self.mode_card.update_content("⏸ 已停止", "#6b7280")

        if hasattr(self, 'runtime_timer'):
            self.runtime_timer.stop()

        self.log_viewer.add_log("INFO", "Dashboard", "🛑 引擎已停止")

    def on_state_changed(self, state):
        """引擎狀態改變"""
        state_display = {
            "idle": "● 待機",
            "running": "⚡ 運行中",
            "betting_open": "● 下注期",
            "placing_bets": "⚡ 下注中",
            "in_round": "● 局中",
            "eval_result": "📊 結算中",
            "error": "✗ 錯誤",
            "paused": "⏸ 暫停"
        }.get(state, f"? {state}")

        color = {
            "idle": "#10b981",
            "running": "#3b82f6",
            "betting_open": "#f59e0b",
            "placing_bets": "#3b82f6",
            "in_round": "#ef4444",
            "eval_result": "#8b5cf6",
            "error": "#ef4444",
            "paused": "#6b7280"
        }.get(state, "#ffffff")

        self.state_card.update_content(state_display, color)

    def on_stats_updated(self, stats):
        """統計資料更新"""
        self.stats_card.update_stats(stats)

    def on_log_message(self, level, module, message):
        """接收日誌訊息"""
        self.log_viewer.add_log(level, module, message)

    def on_engine_status(self, status):
        """引擎狀態更新"""
        # 更新事件來源狀態
        if hasattr(self.engine_worker, 'event_feeder') and self.engine_worker.event_feeder:
            if hasattr(self.engine_worker.event_feeder, 'is_running') and self.engine_worker.event_feeder.is_running():
                self.events_card.update_content("● 已連接", "#10b981")
            else:
                self.events_card.update_content("● 連接中", "#f59e0b")
        else:
            self.events_card.update_content("● 未連接", "#ef4444")

    def update_runtime(self):
        """更新運行時間"""
        if self.start_time:
            current_time = self.get_current_time()
            elapsed = current_time - self.start_time

            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60

            runtime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            self.stats_card.stats_table.item(3, 1).setText(runtime_str)

    def get_current_time(self):
        """獲取當前時間戳"""
        import time
        return int(time.time())

    def closeEvent(self, event):
        """頁面關閉事件"""
        if self.engine_worker:
            self.engine_worker.stop_engine()
            self.engine_worker.quit()
            self.engine_worker.wait(3000)  # 等待最多 3 秒
        event.accept()