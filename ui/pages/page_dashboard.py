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
        self.content_label.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))

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

        self.start_btn = QPushButton("🚀 啟動引擎")
        self.start_btn.setProperty("class", "success")
        self.start_btn.clicked.connect(self.start_engine)

        self.stop_btn = QPushButton("🛑 停止引擎")
        self.stop_btn.setProperty("class", "danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_engine)

        self.dryrun_toggle = QCheckBox("乾跑模式")
        self.dryrun_toggle.setChecked(True)
        self.dryrun_toggle.toggled.connect(self.toggle_dry_run)

        # 事件來源選擇
        self.event_source = QComboBox()
        self.event_source.addItems(["demo", "ndjson"])
        self.event_source.setCurrentText("demo")

        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(QLabel("|"))
        button_layout.addWidget(self.dryrun_toggle)
        button_layout.addWidget(QLabel("事件來源:"))
        button_layout.addWidget(self.event_source)
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

        # 初始化引擎
        success = self.engine_worker.initialize_engine(dry_run=True)
        if success:
            self.log_viewer.add_log("INFO", "Dashboard", "引擎工作執行緒已準備就緒")
        else:
            self.log_viewer.add_log("ERROR", "Dashboard", "引擎初始化失敗")

    def start_engine(self):
        """啟動引擎"""
        if not self.engine_worker:
            return

        # 獲取事件來源設定
        source = self.event_source.currentText()

        kwargs = {}
        if source == "demo":
            kwargs = {"interval": 15, "seed": 42}
        elif source == "ndjson":
            kwargs = {"file_path": "data/sessions/events.sample.ndjson", "interval": 1.2}

        # 如果不是乾跑模式，需要確認
        if not self.dryrun_toggle.isChecked():
            reply = QMessageBox.question(
                self, "確認實戰模式",
                "您即將啟動實戰模式！\n這將執行真實的滑鼠點擊操作。\n\n確定要繼續嗎？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # 啟動引擎
        success = self.engine_worker.start_engine(source, **kwargs)

        if success:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.event_source.setEnabled(False)
            self.start_time = self.get_current_time()

            # 啟動運行時間計時器
            self.runtime_timer = QTimer()
            self.runtime_timer.timeout.connect(self.update_runtime)
            self.runtime_timer.start(1000)  # 每秒更新

    def stop_engine(self):
        """停止引擎"""
        if self.engine_worker:
            self.engine_worker.stop_engine()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.event_source.setEnabled(True)

        if hasattr(self, 'runtime_timer'):
            self.runtime_timer.stop()

    def toggle_dry_run(self, checked):
        """切換乾跑模式"""
        if self.engine_worker:
            self.engine_worker.set_dry_run(checked)

        # 更新模式顯示
        mode = "🧪 乾跑模式" if checked else "⚡ 實戰模式"
        color = "#10b981" if checked else "#ef4444"
        self.mode_card.update_content(mode, color)

    def on_state_changed(self, state):
        """引擎狀態改變"""
        state_display = {
            "idle": "🟢 待機",
            "betting_open": "🟡 下注期",
            "placing_bets": "🔄 下注中",
            "in_round": "🔴 局中",
            "eval_result": "📊 結算中",
            "error": "❌ 錯誤",
            "paused": "⏸️ 暫停"
        }.get(state, f"❓ {state}")

        color = {
            "idle": "#10b981",
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
            self.events_card.update_content("🟢 已連接", "#10b981")
        else:
            self.events_card.update_content("🔴 未連接", "#ef4444")

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