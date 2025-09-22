# ui/pages/page_strategy.py
import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QGroupBox, QTabWidget,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QTextEdit, QLineEdit, QMessageBox, QSlider,
    QFormLayout, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QValidator

class StrategyPage(QWidget):
    """策略設定頁面"""
    strategy_changed = Signal(dict)  # 策略變更信號

    def __init__(self):
        super().__init__()
        self.strategy_data = self.load_default_strategy()
        self.setup_ui()
        self.load_strategy()

    def load_default_strategy(self):
        """載入預設策略"""
        return {
            "unit": 100,
            "target": "P",
            "martingale": {
                "enabled": True,
                "max_level": 7,
                "reset_on_win": True,
                "progression": [1, 2, 4, 8, 16, 32, 64]
            },
            "risk_control": {
                "max_loss": 5000,
                "max_win": 3000,
                "session_limit": 50,
                "consecutive_loss_limit": 5
            },
            "betting_logic": {
                "follow_trend": True,
                "switch_after_losses": 3,
                "skip_tie": True
            }
        }

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 標題
        title = QLabel("⚙️ 策略設定")
        title.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #374151;
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 8px;
            }
        """)
        layout.addWidget(title)

        # Tab 控件
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #374151;
                background-color: #1f2937;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #374151;
                color: #e5e7eb;
                padding: 12px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #0e7490;
                color: #ffffff;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #4b5563;
            }
        """)

        # 建立各個頁籤
        self.setup_basic_tab()
        self.setup_martingale_tab()
        self.setup_risk_tab()
        self.setup_logic_tab()
        self.setup_json_tab()

        layout.addWidget(self.tab_widget)

        # 控制按鈕
        self.setup_controls(layout)

    def setup_basic_tab(self):
        """基本設定頁籤"""
        basic_tab = QWidget()
        layout = QVBoxLayout(basic_tab)

        # 基本投注設定
        basic_group = QGroupBox("💰 基本投注設定")
        basic_layout = QFormLayout(basic_group)

        # 單位金額
        self.unit_spin = QSpinBox()
        self.unit_spin.setRange(10, 10000)
        self.unit_spin.setSingleStep(10)
        self.unit_spin.setSuffix(" 元")
        self.unit_spin.setValue(self.strategy_data["unit"])
        basic_layout.addRow("單位金額:", self.unit_spin)

        # 投注目標
        self.target_combo = QComboBox()
        self.target_combo.addItems(["P (閒家)", "B (莊家)", "T (和局)", "AUTO (自動選擇)"])
        target_map = {"P": 0, "B": 1, "T": 2, "AUTO": 3}
        self.target_combo.setCurrentIndex(target_map.get(self.strategy_data["target"], 0))
        basic_layout.addRow("主要投注目標:", self.target_combo)

        layout.addWidget(basic_group)

        # 投注模式
        mode_group = QGroupBox("🎯 投注模式")
        mode_layout = QVBoxLayout(mode_group)

        self.follow_trend_cb = QCheckBox("跟隨趨勢投注")
        self.follow_trend_cb.setChecked(self.strategy_data["betting_logic"]["follow_trend"])
        mode_layout.addWidget(self.follow_trend_cb)

        self.skip_tie_cb = QCheckBox("跳過和局不投注")
        self.skip_tie_cb.setChecked(self.strategy_data["betting_logic"]["skip_tie"])
        mode_layout.addWidget(self.skip_tie_cb)

        # 切換策略設定
        switch_layout = QHBoxLayout()
        switch_layout.addWidget(QLabel("連續輸幾局後切換目標:"))
        self.switch_spin = QSpinBox()
        self.switch_spin.setRange(1, 10)
        self.switch_spin.setValue(self.strategy_data["betting_logic"]["switch_after_losses"])
        switch_layout.addWidget(self.switch_spin)
        switch_layout.addStretch()
        mode_layout.addLayout(switch_layout)

        layout.addWidget(mode_group)
        layout.addStretch()

        self.tab_widget.addTab(basic_tab, "基本設定")

    def setup_martingale_tab(self):
        """馬丁格爾頁籤"""
        martingale_tab = QWidget()
        layout = QVBoxLayout(martingale_tab)

        # 馬丁格爾設定
        martingale_group = QGroupBox("📈 馬丁格爾倍投策略")
        martingale_layout = QVBoxLayout(martingale_group)

        # 啟用開關
        self.martingale_enabled = QCheckBox("啟用馬丁格爾倍投")
        self.martingale_enabled.setChecked(self.strategy_data["martingale"]["enabled"])
        self.martingale_enabled.stateChanged.connect(self.toggle_martingale)
        martingale_layout.addWidget(self.martingale_enabled)

        # 設定區域
        self.martingale_settings = QFrame()
        settings_layout = QFormLayout(self.martingale_settings)

        # 最大層級
        self.max_level_spin = QSpinBox()
        self.max_level_spin.setRange(1, 15)
        self.max_level_spin.setValue(self.strategy_data["martingale"]["max_level"])
        self.max_level_spin.valueChanged.connect(self.update_progression)
        settings_layout.addRow("最大倍投層級:", self.max_level_spin)

        # 獲勝重置
        self.reset_on_win = QCheckBox("獲勝後重置到第一層")
        self.reset_on_win.setChecked(self.strategy_data["martingale"]["reset_on_win"])
        settings_layout.addRow("重置策略:", self.reset_on_win)

        martingale_layout.addWidget(self.martingale_settings)

        # 倍投序列預覽
        preview_group = QGroupBox("📊 倍投序列預覽")
        preview_layout = QVBoxLayout(preview_group)

        self.progression_label = QLabel()
        self.progression_label.setWordWrap(True)
        self.progression_label.setStyleSheet("""
            QLabel {
                background-color: #2a2f3a;
                padding: 12px;
                border-radius: 6px;
                font-family: 'Consolas', monospace;
                border: 1px solid #3a3f4a;
            }
        """)
        preview_layout.addWidget(self.progression_label)

        # 風險計算
        self.risk_label = QLabel()
        self.risk_label.setStyleSheet("""
            QLabel {
                background-color: #7f1d1d;
                color: #ffffff;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
            }
        """)
        preview_layout.addWidget(self.risk_label)

        martingale_layout.addWidget(preview_group)

        layout.addWidget(martingale_group)
        layout.addStretch()

        self.update_progression()  # 初始化顯示
        self.tab_widget.addTab(martingale_tab, "馬丁格爾")

    def setup_risk_tab(self):
        """風控設定頁籤"""
        risk_tab = QWidget()
        layout = QVBoxLayout(risk_tab)

        # 損益控制
        profit_loss_group = QGroupBox("💸 損益控制")
        pl_layout = QFormLayout(profit_loss_group)

        # 最大虧損
        self.max_loss_spin = QSpinBox()
        self.max_loss_spin.setRange(100, 100000)
        self.max_loss_spin.setSingleStep(100)
        self.max_loss_spin.setSuffix(" 元")
        self.max_loss_spin.setValue(self.strategy_data["risk_control"]["max_loss"])
        pl_layout.addRow("單日最大虧損:", self.max_loss_spin)

        # 最大盈利
        self.max_win_spin = QSpinBox()
        self.max_win_spin.setRange(100, 100000)
        self.max_win_spin.setSingleStep(100)
        self.max_win_spin.setSuffix(" 元")
        self.max_win_spin.setValue(self.strategy_data["risk_control"]["max_win"])
        pl_layout.addRow("目標盈利退出:", self.max_win_spin)

        layout.addWidget(profit_loss_group)

        # 局數控制
        session_group = QGroupBox("🔢 局數控制")
        session_layout = QFormLayout(session_group)

        # 單次會話限制
        self.session_limit_spin = QSpinBox()
        self.session_limit_spin.setRange(10, 1000)
        self.session_limit_spin.setValue(self.strategy_data["risk_control"]["session_limit"])
        session_layout.addRow("單次會話最大局數:", self.session_limit_spin)

        # 連續虧損限制
        self.consecutive_loss_spin = QSpinBox()
        self.consecutive_loss_spin.setRange(1, 20)
        self.consecutive_loss_spin.setValue(self.strategy_data["risk_control"]["consecutive_loss_limit"])
        session_layout.addRow("連續虧損停止:", self.consecutive_loss_spin)

        layout.addWidget(session_group)

        # 風險警示
        warning_group = QGroupBox("⚠️ 風險提醒")
        warning_layout = QVBoxLayout(warning_group)

        warning_text = QLabel("""
        <b>重要風險提示:</b><br>
        • 馬丁格爾策略存在巨大風險，可能導致快速虧損<br>
        • 請設定合理的風控限制，切勿超出承受能力<br>
        • 建議先在乾跑模式下充分測試策略<br>
        • 任何投注策略都無法保證盈利
        """)
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet("""
            QLabel {
                background-color: #7f1d1d;
                color: #ffffff;
                padding: 16px;
                border-radius: 8px;
                border: 2px solid #ef4444;
            }
        """)
        warning_layout.addWidget(warning_text)

        layout.addWidget(warning_group)
        layout.addStretch()

        self.tab_widget.addTab(risk_tab, "風控設定")

    def setup_logic_tab(self):
        """投注邏輯頁籤"""
        logic_tab = QWidget()
        layout = QVBoxLayout(logic_tab)

        # 決策邏輯
        decision_group = QGroupBox("🧠 決策邏輯")
        decision_layout = QVBoxLayout(decision_group)

        # 策略說明
        strategy_info = QLabel("""
        <b>當前投注邏輯:</b><br>
        1. 根據歷史結果判斷趨勢<br>
        2. 選擇主要投注目標 (莊/閒)<br>
        3. 連續虧損時考慮切換目標<br>
        4. 應用馬丁格爾倍投策略<br>
        5. 觸發風控條件時停止
        """)
        strategy_info.setWordWrap(True)
        strategy_info.setStyleSheet("""
            QLabel {
                background-color: #374151;
                padding: 16px;
                border-radius: 8px;
                border: 1px solid #4b5563;
            }
        """)
        decision_layout.addWidget(strategy_info)

        layout.addWidget(decision_group)

        # 高級選項
        advanced_group = QGroupBox("🔧 高級選項")
        advanced_layout = QVBoxLayout(advanced_group)

        advanced_placeholder = QLabel("高級策略選項 (待實現):\n• 自定義決策規則\n• 趨勢分析參數\n• 動態投注調整")
        advanced_placeholder.setStyleSheet("""
            QLabel {
                color: #9ca3af;
                background-color: #2a2f3a;
                padding: 20px;
                border-radius: 8px;
                border: 2px dashed #4b5563;
            }
        """)
        advanced_layout.addWidget(advanced_placeholder)

        layout.addWidget(advanced_group)
        layout.addStretch()

        self.tab_widget.addTab(logic_tab, "投注邏輯")

    def setup_json_tab(self):
        """JSON 編輯頁籤"""
        json_tab = QWidget()
        layout = QVBoxLayout(json_tab)

        # JSON 編輯器
        json_group = QGroupBox("📝 JSON 配置編輯")
        json_layout = QVBoxLayout(json_group)

        # 編輯提示
        hint = QLabel("高級用戶可直接編輯 JSON 配置，修改後點擊「套用 JSON」生效")
        hint.setStyleSheet("color: #9ca3af; padding: 8px;")
        json_layout.addWidget(hint)

        # JSON 編輯框
        self.json_editor = QTextEdit()
        self.json_editor.setFont(QFont("Consolas", 10))
        self.json_editor.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        json_layout.addWidget(self.json_editor)

        # JSON 控制按鈕
        json_controls = QHBoxLayout()

        format_btn = QPushButton("🎨 格式化")
        format_btn.clicked.connect(self.format_json)

        apply_btn = QPushButton("✅ 套用 JSON")
        apply_btn.setProperty("class", "primary")
        apply_btn.clicked.connect(self.apply_json)

        reset_btn = QPushButton("🔄 重置")
        reset_btn.clicked.connect(self.reset_json)

        json_controls.addWidget(format_btn)
        json_controls.addWidget(apply_btn)
        json_controls.addWidget(reset_btn)
        json_controls.addStretch()

        json_layout.addLayout(json_controls)
        layout.addWidget(json_group)

        self.tab_widget.addTab(json_tab, "JSON 編輯")

    def setup_controls(self, parent_layout):
        """設定控制按鈕"""
        controls = QFrame()
        controls.setStyleSheet("""
            QFrame {
                background-color: #374151;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        controls_layout = QHBoxLayout(controls)

        # 載入按鈕
        load_btn = QPushButton("📂 載入策略")
        load_btn.clicked.connect(self.load_strategy_file)

        # 儲存按鈕
        save_btn = QPushButton("💾 儲存策略")
        save_btn.setProperty("class", "success")
        save_btn.clicked.connect(self.save_strategy)

        # 測試按鈕
        test_btn = QPushButton("🧪 測試策略")
        test_btn.setProperty("class", "primary")
        test_btn.clicked.connect(self.test_strategy)

        # 重置按鈕
        reset_btn = QPushButton("🔄 重置預設")
        reset_btn.clicked.connect(self.reset_to_default)

        controls_layout.addWidget(load_btn)
        controls_layout.addWidget(save_btn)
        controls_layout.addWidget(test_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(reset_btn)

        parent_layout.addWidget(controls)

    def toggle_martingale(self, enabled):
        """切換馬丁格爾設定"""
        self.martingale_settings.setEnabled(enabled)

    def update_progression(self):
        """更新倍投序列顯示"""
        max_level = self.max_level_spin.value()
        unit = self.unit_spin.value()

        progression = []
        total_risk = 0
        for i in range(max_level):
            multiplier = 2 ** i
            amount = unit * multiplier
            progression.append(f"第{i+1}層: {amount:,}元")
            total_risk += amount

        progression_text = "\n".join(progression)
        self.progression_label.setText(progression_text)

        self.risk_label.setText(f"⚠️ 最大風險: {total_risk:,} 元 (完整序列總投注)")

    def format_json(self):
        """格式化 JSON"""
        try:
            text = self.json_editor.toPlainText()
            if text.strip():
                data = json.loads(text)
                formatted = json.dumps(data, indent=4, ensure_ascii=False)
                self.json_editor.setPlainText(formatted)
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "JSON 錯誤", f"JSON 格式錯誤: {str(e)}")

    def apply_json(self):
        """套用 JSON 配置"""
        try:
            text = self.json_editor.toPlainText()
            new_strategy = json.loads(text)
            self.strategy_data = new_strategy
            self.update_form_from_data()
            QMessageBox.information(self, "成功", "JSON 配置已套用到表單")
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "JSON 錯誤", f"無法解析 JSON: {str(e)}")

    def reset_json(self):
        """重置 JSON 到當前表單狀態"""
        self.update_json_from_form()

    def update_form_from_data(self):
        """從數據更新表單"""
        # 基本設定
        self.unit_spin.setValue(self.strategy_data.get("unit", 100))
        target_map = {"P": 0, "B": 1, "T": 2, "AUTO": 3}
        self.target_combo.setCurrentIndex(target_map.get(self.strategy_data.get("target", "P"), 0))

        # 投注邏輯
        betting_logic = self.strategy_data.get("betting_logic", {})
        self.follow_trend_cb.setChecked(betting_logic.get("follow_trend", True))
        self.skip_tie_cb.setChecked(betting_logic.get("skip_tie", True))
        self.switch_spin.setValue(betting_logic.get("switch_after_losses", 3))

        # 馬丁格爾
        martingale = self.strategy_data.get("martingale", {})
        self.martingale_enabled.setChecked(martingale.get("enabled", True))
        self.max_level_spin.setValue(martingale.get("max_level", 7))
        self.reset_on_win.setChecked(martingale.get("reset_on_win", True))

        # 風控
        risk_control = self.strategy_data.get("risk_control", {})
        self.max_loss_spin.setValue(risk_control.get("max_loss", 5000))
        self.max_win_spin.setValue(risk_control.get("max_win", 3000))
        self.session_limit_spin.setValue(risk_control.get("session_limit", 50))
        self.consecutive_loss_spin.setValue(risk_control.get("consecutive_loss_limit", 5))

        self.update_progression()

    def update_json_from_form(self):
        """從表單更新 JSON"""
        # 收集表單數據
        target_options = ["P", "B", "T", "AUTO"]

        self.strategy_data = {
            "unit": self.unit_spin.value(),
            "target": target_options[self.target_combo.currentIndex()],
            "martingale": {
                "enabled": self.martingale_enabled.isChecked(),
                "max_level": self.max_level_spin.value(),
                "reset_on_win": self.reset_on_win.isChecked(),
                "progression": [2**i for i in range(self.max_level_spin.value())]
            },
            "risk_control": {
                "max_loss": self.max_loss_spin.value(),
                "max_win": self.max_win_spin.value(),
                "session_limit": self.session_limit_spin.value(),
                "consecutive_loss_limit": self.consecutive_loss_spin.value()
            },
            "betting_logic": {
                "follow_trend": self.follow_trend_cb.isChecked(),
                "switch_after_losses": self.switch_spin.value(),
                "skip_tie": self.skip_tie_cb.isChecked()
            }
        }

        # 更新 JSON 編輯器
        json_text = json.dumps(self.strategy_data, indent=4, ensure_ascii=False)
        self.json_editor.setPlainText(json_text)

    def load_strategy(self):
        """載入策略配置"""
        # 從文件載入 (如果存在)
        strategy_file = "configs/strategy.json"
        if os.path.exists(strategy_file):
            try:
                with open(strategy_file, 'r', encoding='utf-8') as f:
                    self.strategy_data = json.load(f)
            except Exception:
                pass  # 使用預設配置

        self.update_form_from_data()
        self.update_json_from_form()

    def load_strategy_file(self):
        """載入策略檔案"""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "載入策略檔案", "configs/", "JSON files (*.json)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.strategy_data = json.load(f)
                self.update_form_from_data()
                self.update_json_from_form()
                QMessageBox.information(self, "成功", f"策略已從 {os.path.basename(file_path)} 載入")
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"載入失敗: {str(e)}")

    def save_strategy(self):
        """儲存策略"""
        self.update_json_from_form()

        # 確保目錄存在
        os.makedirs("configs", exist_ok=True)

        try:
            with open("configs/strategy.json", 'w', encoding='utf-8') as f:
                json.dump(self.strategy_data, f, indent=4, ensure_ascii=False)

            QMessageBox.information(self, "成功", "策略已儲存到 configs/strategy.json")
            self.strategy_changed.emit(self.strategy_data)

        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"儲存失敗: {str(e)}")

    def test_strategy(self):
        """測試策略"""
        self.update_json_from_form()

        # 基本驗證
        issues = []

        if self.strategy_data["unit"] < 10:
            issues.append("單位金額過小 (建議至少 10 元)")

        if self.strategy_data["martingale"]["enabled"]:
            max_level = self.strategy_data["martingale"]["max_level"]
            unit = self.strategy_data["unit"]
            max_bet = unit * (2 ** (max_level - 1))
            if max_bet > self.strategy_data["risk_control"]["max_loss"]:
                issues.append(f"馬丁格爾最大投注 ({max_bet:,}) 超過虧損限制")

        if issues:
            QMessageBox.warning(self, "策略警告", "發現問題:\n" + "\n".join(f"• {issue}" for issue in issues))
        else:
            QMessageBox.information(self, "測試通過", "策略配置看起來合理！")

    def reset_to_default(self):
        """重置為預設策略"""
        reply = QMessageBox.question(
            self, "確認重置",
            "確定要重置為預設策略嗎？\n當前的修改將會遺失。",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.strategy_data = self.load_default_strategy()
            self.update_form_from_data()
            self.update_json_from_form()