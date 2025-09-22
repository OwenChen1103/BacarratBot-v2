#!/usr/bin/env python3
"""
BotConsole Bot控制視窗
策略UI、控制面板、SSE訂閱、日誌顯示
"""
import json
import sys
import logging
import requests
import time
from typing import Dict, Optional
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QFrame, QTextEdit,
                               QGroupBox, QFormLayout, QLineEdit, QSpinBox, QComboBox,
                               QCheckBox, QTabWidget, QTableWidget, QTableWidgetItem,
                               QSplitter, QProgressBar)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QPalette, QTextCursor

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from autobet.autobet_engine import AutoBetEngine


class SSEClient(QThread):
    """SSE客戶端，訂閱Reader事件"""

    event_received = Signal(dict)
    connection_status = Signal(str)  # connected/disconnected/error

    def __init__(self, url: str = "http://localhost:8888/events"):
        super().__init__()
        self.url = url
        self.running = False
        self.logger = logging.getLogger(__name__)

    def run(self):
        """SSE訂閱主循環"""
        self.running = True
        self.connection_status.emit("connecting")

        while self.running:
            try:
                response = requests.get(self.url, stream=True, timeout=30)
                if response.status_code == 200:
                    self.connection_status.emit("connected")

                    for line in response.iter_lines(decode_unicode=True):
                        if not self.running:
                            break

                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])  # 去掉 "data: "
                                self.event_received.emit(data)
                            except json.JSONDecodeError:
                                continue

                else:
                    self.connection_status.emit("error")
                    self.logger.error(f"SSE連接失敗: {response.status_code}")
                    time.sleep(5)  # 重連延遲

            except requests.exceptions.RequestException as e:
                self.connection_status.emit("disconnected")
                self.logger.warning(f"SSE連接中斷: {e}")
                time.sleep(5)  # 重連延遲

            except Exception as e:
                self.logger.error(f"SSE客戶端錯誤: {e}")
                time.sleep(5)

    def stop(self):
        """停止SSE客戶端"""
        self.running = False
        self.wait()


class StrategyEditor(QWidget):
    """策略編輯器"""

    strategy_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.strategy_path = "configs/strategy.json"
        self.init_ui()
        self.load_strategy()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 基本設定
        basic_group = QGroupBox("基本設定")
        basic_layout = QFormLayout(basic_group)

        self.unit_spin = QSpinBox()
        self.unit_spin.setRange(100, 100000)
        self.unit_spin.setValue(1000)
        self.unit_spin.setSuffix(" 元")
        basic_layout.addRow("單位金額:", self.unit_spin)

        self.targets_edit = QLineEdit()
        self.targets_edit.setPlaceholderText("例: banker,lucky6")
        basic_layout.addRow("下注目標:", self.targets_edit)

        layout.addWidget(basic_group)

        # 分配設定
        split_group = QGroupBox("單位分配")
        split_layout = QFormLayout(split_group)

        self.banker_units = QSpinBox()
        self.banker_units.setRange(1, 10)
        self.banker_units.setValue(3)
        split_layout.addRow("莊家單位:", self.banker_units)

        self.player_units = QSpinBox()
        self.player_units.setRange(1, 10)
        self.player_units.setValue(1)
        split_layout.addRow("閒家單位:", self.player_units)

        self.lucky6_units = QSpinBox()
        self.lucky6_units.setRange(1, 10)
        self.lucky6_units.setValue(1)
        split_layout.addRow("幸運6單位:", self.lucky6_units)

        layout.addWidget(split_group)

        # 遞增策略
        staking_group = QGroupBox("遞增策略")
        staking_layout = QFormLayout(staking_group)

        self.staking_type = QComboBox()
        self.staking_type.addItems(["fixed", "martingale"])
        staking_layout.addRow("類型:", self.staking_type)

        self.base_units_spin = QSpinBox()
        self.base_units_spin.setRange(1, 10)
        self.base_units_spin.setValue(1)
        staking_layout.addRow("基礎單位:", self.base_units_spin)

        self.max_steps_spin = QSpinBox()
        self.max_steps_spin.setRange(1, 10)
        self.max_steps_spin.setValue(3)
        staking_layout.addRow("最大步驟:", self.max_steps_spin)

        self.reset_on_win = QCheckBox()
        self.reset_on_win.setChecked(True)
        staking_layout.addRow("贏後重置:", self.reset_on_win)

        layout.addWidget(staking_group)

        # 風控限制
        limits_group = QGroupBox("風控限制")
        limits_layout = QFormLayout(limits_group)

        self.round_cap_spin = QSpinBox()
        self.round_cap_spin.setRange(1000, 100000)
        self.round_cap_spin.setValue(10000)
        self.round_cap_spin.setSuffix(" 元")
        limits_layout.addRow("單局上限:", self.round_cap_spin)

        self.stop_loss_spin = QSpinBox()
        self.stop_loss_spin.setRange(-100000, 0)
        self.stop_loss_spin.setValue(-20000)
        self.stop_loss_spin.setSuffix(" 元")
        limits_layout.addRow("止損額度:", self.stop_loss_spin)

        self.take_profit_spin = QSpinBox()
        self.take_profit_spin.setRange(0, 100000)
        self.take_profit_spin.setValue(30000)
        self.take_profit_spin.setSuffix(" 元")
        limits_layout.addRow("止盈額度:", self.take_profit_spin)

        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setRange(0, 5)
        self.max_retries_spin.setValue(1)
        limits_layout.addRow("補點次數:", self.max_retries_spin)

        layout.addWidget(limits_group)

        # 按鈕
        btn_layout = QHBoxLayout()

        save_btn = QPushButton("💾 儲存策略")
        save_btn.clicked.connect(self.save_strategy)
        btn_layout.addWidget(save_btn)

        load_btn = QPushButton("📁 載入策略")
        load_btn.clicked.connect(self.load_strategy)
        btn_layout.addWidget(load_btn)

        reset_btn = QPushButton("🔄 重置預設")
        reset_btn.clicked.connect(self.reset_to_default)
        btn_layout.addWidget(reset_btn)

        layout.addLayout(btn_layout)

        # 連接信號
        self.unit_spin.valueChanged.connect(self.on_strategy_changed)
        self.targets_edit.textChanged.connect(self.on_strategy_changed)
        self.staking_type.currentTextChanged.connect(self.on_strategy_changed)

    def on_strategy_changed(self):
        """策略變更通知"""
        strategy = self.get_strategy_dict()
        self.strategy_changed.emit(strategy)

    def get_strategy_dict(self) -> Dict:
        """獲取當前策略字典"""
        targets = [t.strip() for t in self.targets_edit.text().split(",") if t.strip()]

        return {
            "unit": self.unit_spin.value(),
            "targets": targets,
            "split_units": {
                "banker": self.banker_units.value(),
                "player": self.player_units.value(),
                "lucky6": self.lucky6_units.value(),
                "tie": 1,
                "p_pair": 1,
                "b_pair": 1
            },
            "staking": {
                "type": self.staking_type.currentText(),
                "base_units": self.base_units_spin.value(),
                "max_steps": self.max_steps_spin.value(),
                "reset_on_win": self.reset_on_win.isChecked()
            },
            "filters": [
                {"when": "last_winner=='P'", "override_targets": ["banker"]}
            ],
            "limits": {
                "per_round_cap": self.round_cap_spin.value(),
                "session_stop_loss": self.stop_loss_spin.value(),
                "session_take_profit": self.take_profit_spin.value(),
                "max_retries": self.max_retries_spin.value()
            },
            "timing": {
                "move_delay_ms": [40, 120],
                "click_delay_ms": [40, 80],
                "pre_confirm_wait_ms": 120
            }
        }

    def set_strategy_dict(self, strategy: Dict):
        """設定策略字典"""
        self.unit_spin.setValue(strategy.get("unit", 1000))

        targets = strategy.get("targets", [])
        self.targets_edit.setText(",".join(targets))

        split_units = strategy.get("split_units", {})
        self.banker_units.setValue(split_units.get("banker", 3))
        self.player_units.setValue(split_units.get("player", 1))
        self.lucky6_units.setValue(split_units.get("lucky6", 1))

        staking = strategy.get("staking", {})
        staking_type = staking.get("type", "fixed")
        index = self.staking_type.findText(staking_type)
        if index >= 0:
            self.staking_type.setCurrentIndex(index)

        self.base_units_spin.setValue(staking.get("base_units", 1))
        self.max_steps_spin.setValue(staking.get("max_steps", 3))
        self.reset_on_win.setChecked(staking.get("reset_on_win", True))

        limits = strategy.get("limits", {})
        self.round_cap_spin.setValue(limits.get("per_round_cap", 10000))
        self.stop_loss_spin.setValue(limits.get("session_stop_loss", -20000))
        self.take_profit_spin.setValue(limits.get("session_take_profit", 30000))
        self.max_retries_spin.setValue(limits.get("max_retries", 1))

    def save_strategy(self):
        """儲存策略到檔案"""
        try:
            os.makedirs("configs", exist_ok=True)
            strategy = self.get_strategy_dict()

            with open(self.strategy_path, 'w', encoding='utf-8') as f:
                json.dump(strategy, f, indent=2, ensure_ascii=False)

            logging.getLogger(__name__).info(f"策略已儲存: {self.strategy_path}")

        except Exception as e:
            logging.getLogger(__name__).error(f"儲存策略失敗: {e}")

    def load_strategy(self):
        """從檔案載入策略"""
        try:
            if Path(self.strategy_path).exists():
                with open(self.strategy_path, 'r', encoding='utf-8') as f:
                    strategy = json.load(f)
                self.set_strategy_dict(strategy)
                logging.getLogger(__name__).info(f"策略已載入: {self.strategy_path}")
            else:
                self.reset_to_default()

        except Exception as e:
            logging.getLogger(__name__).error(f"載入策略失敗: {e}")
            self.reset_to_default()

    def reset_to_default(self):
        """重置為預設策略"""
        default_strategy = {
            "unit": 1000,
            "targets": ["banker", "lucky6"],
            "split_units": {"banker": 3, "lucky6": 1},
            "staking": {
                "type": "martingale",
                "base_units": 1,
                "max_steps": 3,
                "reset_on_win": True
            },
            "limits": {
                "per_round_cap": 10000,
                "session_stop_loss": -20000,
                "session_take_profit": 30000,
                "max_retries": 1
            }
        }
        self.set_strategy_dict(default_strategy)


class BotConsole(QMainWindow):
    """Bot控制台主視窗"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("百家樂自動下注 Bot 控制台")
        self.setMinimumSize(1200, 800)

        # 核心組件
        self.engine = AutoBetEngine()
        self.sse_client: Optional[SSEClient] = None

        # UI組件
        self.init_ui()
        self.init_connections()

        # 狀態更新定時器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status_display)
        self.status_timer.start(1000)  # 每秒更新

        # 初始化
        self.load_initial_data()

    def init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主分割器
        main_splitter = QSplitter(Qt.Horizontal)
        central_widget.setLayout(QHBoxLayout())
        central_widget.layout().addWidget(main_splitter)

        # 左側控制面板
        left_panel = self.create_control_panel()
        main_splitter.addWidget(left_panel)

        # 右側標籤頁
        right_tabs = QTabWidget()

        # 策略編輯標籤
        self.strategy_editor = StrategyEditor()
        right_tabs.addTab(self.strategy_editor, "⚙️ 策略設定")

        # 統計標籤
        stats_widget = self.create_stats_widget()
        right_tabs.addTab(stats_widget, "📊 統計資訊")

        # 日誌標籤
        log_widget = self.create_log_widget()
        right_tabs.addTab(log_widget, "📝 執行日誌")

        main_splitter.addWidget(right_tabs)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)

    def create_control_panel(self) -> QWidget:
        """創建控制面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # 標題
        title = QLabel("🤖 Bot 控制台")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # 連接狀態
        conn_group = QGroupBox("📡 連接狀態")
        conn_layout = QVBoxLayout(conn_group)

        self.sse_status_label = QLabel("❌ 未連接")
        conn_layout.addWidget(self.sse_status_label)

        self.connect_btn = QPushButton("🔗 連接Reader")
        self.connect_btn.clicked.connect(self.toggle_sse_connection)
        conn_layout.addWidget(self.connect_btn)

        layout.addWidget(conn_group)

        # Bot控制
        bot_group = QGroupBox("🎮 Bot控制")
        bot_layout = QVBoxLayout(bot_group)

        self.engine_status_label = QLabel("⏹️ 已停止")
        bot_layout.addWidget(self.engine_status_label)

        self.dry_run_checkbox = QCheckBox("🧪 乾跑模式")
        self.dry_run_checkbox.setChecked(True)
        self.dry_run_checkbox.stateChanged.connect(self.on_dry_run_changed)
        bot_layout.addWidget(self.dry_run_checkbox)

        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("▶️ 啟動")
        self.start_btn.clicked.connect(self.start_engine)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹️ 停止")
        self.stop_btn.clicked.connect(self.stop_engine)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        bot_layout.addLayout(btn_layout)

        self.emergency_btn = QPushButton("🚨 緊急停止")
        self.emergency_btn.clicked.connect(self.emergency_stop)
        self.emergency_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold;")
        bot_layout.addWidget(self.emergency_btn)

        layout.addWidget(bot_group)

        # 當前狀態
        status_group = QGroupBox("📋 當前狀態")
        status_layout = QFormLayout(status_group)

        self.current_state_label = QLabel("stopped")
        status_layout.addRow("狀態機:", self.current_state_label)

        self.current_plan_label = QLabel("無")
        status_layout.addRow("計畫:", self.current_plan_label)

        self.rounds_label = QLabel("0")
        status_layout.addRow("局數:", self.rounds_label)

        self.profit_label = QLabel("0")
        status_layout.addRow("損益:", self.profit_label)

        layout.addWidget(status_group)

        # 最近事件
        events_group = QGroupBox("📨 最近事件")
        events_layout = QVBoxLayout(events_group)

        self.recent_events = QTextEdit()
        self.recent_events.setMaximumHeight(150)
        self.recent_events.setReadOnly(True)
        events_layout.addWidget(self.recent_events)

        layout.addWidget(events_group)

        layout.addStretch()
        return panel

    def create_stats_widget(self) -> QWidget:
        """創建統計視窗"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 會話統計
        session_group = QGroupBox("💰 會話統計")
        session_layout = QFormLayout(session_group)

        self.session_rounds = QLabel("0")
        session_layout.addRow("總局數:", self.session_rounds)

        self.session_profit = QLabel("0")
        session_layout.addRow("淨損益:", self.session_profit)

        self.win_streak = QLabel("0")
        session_layout.addRow("連勝:", self.win_streak)

        self.loss_streak = QLabel("0")
        session_layout.addRow("連敗:", self.loss_streak)

        self.martingale_step = QLabel("0")
        session_layout.addRow("倍投步驟:", self.martingale_step)

        layout.addWidget(session_group)

        # 最近結果表格
        results_group = QGroupBox("📈 最近結果")
        results_layout = QVBoxLayout(results_group)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(["時間", "輪次", "結果", "下注", "損益"])
        results_layout.addWidget(self.results_table)

        layout.addWidget(results_group)

        layout.addStretch()
        return widget

    def create_log_widget(self) -> QWidget:
        """創建日誌視窗"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 控制按鈕
        btn_layout = QHBoxLayout()

        clear_btn = QPushButton("🗑️ 清空")
        clear_btn.clicked.connect(self.clear_logs)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 日誌文本區域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)

        return widget

    def init_connections(self):
        """初始化信號連接"""
        # Engine信號
        self.engine.log_message.connect(self.add_log_message)
        self.engine.state_changed.connect(self.on_engine_state_changed)
        self.engine.betting_plan_ready.connect(self.on_betting_plan_ready)
        self.engine.session_stats_updated.connect(self.on_session_stats_updated)
        self.engine.risk_alert.connect(self.on_risk_alert)

        # 策略編輯器信號
        self.strategy_editor.strategy_changed.connect(self.on_strategy_changed)

    def load_initial_data(self):
        """載入初始資料"""
        # 載入位置資料
        if Path("positions.json").exists():
            self.engine.load_positions("positions.json")
            self.add_log_message("已載入位置資料")
        else:
            self.add_log_message("警告：positions.json不存在，請先運行元素偵測")

        # 載入策略（統一路徑邏輯）
        strategy_path = "configs/strategy.json"
        if Path(strategy_path).exists():
            self.engine.load_strategy(strategy_path)
            self.add_log_message("已載入自定義策略")
        elif Path("configs/strategy.default.json").exists():
            self.engine.load_strategy("configs/strategy.default.json")
            self.add_log_message("已載入默認策略")

    def toggle_sse_connection(self):
        """切換SSE連接"""
        if self.sse_client is None or not self.sse_client.isRunning():
            self.start_sse_connection()
        else:
            self.stop_sse_connection()

    def start_sse_connection(self):
        """啟動SSE連接"""
        self.sse_client = SSEClient()
        self.sse_client.event_received.connect(self.on_sse_event)
        self.sse_client.connection_status.connect(self.on_sse_status)
        self.sse_client.start()

        self.connect_btn.setText("🔌 斷開Reader")
        self.add_log_message("正在連接Reader事件流...")

    def stop_sse_connection(self):
        """停止SSE連接"""
        if self.sse_client:
            self.sse_client.stop()
            self.sse_client = None

        self.connect_btn.setText("🔗 連接Reader")
        self.sse_status_label.setText("❌ 未連接")
        self.add_log_message("已斷開Reader連接")

    def on_sse_event(self, event: Dict):
        """處理SSE事件"""
        event_type = event.get("type", "unknown")

        if event_type == "heartbeat":
            return  # 跳過心跳

        # 顯示事件
        event_text = f"[{event_type}] "
        if "phase" in event:
            event_text += f"Phase: {event['phase']} "
        if "winner" in event:
            event_text += f"Winner: {event['winner']} "
        if "round_id" in event:
            event_text += f"Round: {event['round_id']}"

        self.recent_events.append(event_text)

        # 自動滾動
        cursor = self.recent_events.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.recent_events.setTextCursor(cursor)

        # 轉發給引擎
        if event_type in ["RESULT", "REVOKE", "NEW_ROUND"]:
            self.engine.on_round_detected(event)

    def on_sse_status(self, status: str):
        """更新SSE連接狀態"""
        status_map = {
            "connecting": ("🔄 連接中...", "orange"),
            "connected": ("✅ 已連接", "green"),
            "disconnected": ("⚠️ 連接中斷", "orange"),
            "error": ("❌ 連接錯誤", "red")
        }

        text, color = status_map.get(status, ("❓ 未知狀態", "gray"))
        self.sse_status_label.setText(text)
        self.sse_status_label.setStyleSheet(f"color: {color};")

    def start_engine(self):
        """啟動引擎"""
        self.engine.set_enabled(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.add_log_message("Bot引擎已啟動")

    def stop_engine(self):
        """停止引擎"""
        self.engine.set_enabled(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.add_log_message("Bot引擎已停止")

    def emergency_stop(self):
        """緊急停止"""
        self.stop_engine()
        self.dry_run_checkbox.setChecked(True)
        self.engine.set_dry_run(True)
        self.add_log_message("🚨 緊急停止：已停用引擎並切換到乾跑模式")

    def on_dry_run_changed(self, state):
        """乾跑模式變更"""
        dry_run = state == Qt.Checked
        self.engine.set_dry_run(dry_run)
        mode = "乾跑" if dry_run else "實戰"
        self.add_log_message(f"切換到{mode}模式")

    def on_strategy_changed(self, strategy: Dict):
        """策略變更處理"""
        try:
            # 保存並重新載入策略（使用統一路徑）
            strategy_path = self.strategy_path
            os.makedirs("configs", exist_ok=True)  # 確保目錄存在
            with open(strategy_path, 'w', encoding='utf-8') as f:
                json.dump(strategy, f, indent=2, ensure_ascii=False)
            self.engine.load_strategy(strategy_path)
        except Exception as e:
            self.add_log_message(f"更新策略失敗: {e}")

    def on_engine_state_changed(self, state: str):
        """引擎狀態變更"""
        self.current_state_label.setText(state)

        state_colors = {
            "stopped": "gray",
            "idle": "blue",
            "betting_open": "green",
            "placing_bets": "orange",
            "wait_confirm": "orange",
            "in_round": "purple",
            "paused": "red"
        }

        color = state_colors.get(state, "black")
        self.current_state_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def on_betting_plan_ready(self, plan: Dict):
        """下注計畫就緒"""
        plan_text = f"總額:{plan.get('total_amount', 0)} 目標:{list(plan.get('targets', {}).keys())}"
        self.current_plan_label.setText(plan_text)
        self.add_log_message(f"計畫就緒: {plan_text}")

    def on_session_stats_updated(self, stats: Dict):
        """會話統計更新"""
        self.session_rounds.setText(str(stats.get("rounds_played", 0)))
        self.session_profit.setText(f"{stats.get('net_profit', 0):+}")
        self.win_streak.setText(str(stats.get("win_streak", 0)))
        self.loss_streak.setText(str(stats.get("loss_streak", 0)))
        self.martingale_step.setText(str(stats.get("step_idx", 0)))

        # 更新控制面板顯示
        self.rounds_label.setText(str(stats.get("rounds_played", 0)))
        profit = stats.get("net_profit", 0)
        self.profit_label.setText(f"{profit:+}")

        # 根據損益設定顏色
        color = "green" if profit > 0 else "red" if profit < 0 else "black"
        self.profit_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def on_risk_alert(self, level: str, message: str):
        """風控警告"""
        self.add_log_message(f"🚨 風控警告 [{level}]: {message}")

    def update_status_display(self):
        """更新狀態顯示"""
        # 更新當前時間等定期資訊
        pass

    def add_log_message(self, message: str):
        """添加日誌訊息"""
        timestamp = time.strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        self.log_text.append(log_line)

        # 自動滾動
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    def clear_logs(self):
        """清空日誌"""
        self.log_text.clear()
        self.recent_events.clear()
        self.add_log_message("日誌已清空")

    def closeEvent(self, event):
        """視窗關閉事件"""
        self.stop_engine()
        self.stop_sse_connection()
        super().closeEvent(event)


def main():
    """主函數"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = QApplication(sys.argv)
    app.setApplicationName("百家樂自動下注Bot")

    console = BotConsole()
    console.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()