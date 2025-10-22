# ui/widgets/risk_control_widget.py
"""風控設定 Widget - 支援簡易/進階雙模式"""
from __future__ import annotations

from typing import List, Dict, Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QFrame,
)

from src.autobet.lines.config import (
    RiskLevelConfig,
    RiskScope,
    RiskLevelAction,
)


class RiskControlWidget(QWidget):
    """風控設定 Widget - 支援簡易/進階雙模式"""

    risk_changed = Signal()  # 當風控設定改變時發送信號

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.mode = "simple"  # simple | advanced
        self.setup_ui()

    def setup_ui(self):
        """建立 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        # 模式切換按鈕
        mode_layout = QHBoxLayout()
        mode_label = QLabel("設定模式:")
        mode_label.setStyleSheet("font-weight: bold; color: #f3f4f6; font-size: 11pt;")

        self.simple_btn = QPushButton("📱 簡易模式 (推薦)")
        self.advanced_btn = QPushButton("⚙️ 進階模式")

        for btn in [self.simple_btn, self.advanced_btn]:
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 8px 16px;
                    border-radius: 6px;
                    background-color: #1f2937;
                    color: #9ca3af;
                    border: 2px solid #374151;
                    font-size: 10pt;
                }
                QPushButton:checked {
                    background-color: #2563eb;
                    color: #ffffff;
                    border: 2px solid #3b82f6;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #4b5563;
                }
            """)

        self.simple_btn.setChecked(True)
        self.simple_btn.clicked.connect(lambda: self.switch_mode("simple"))
        self.advanced_btn.clicked.connect(lambda: self.switch_mode("advanced"))

        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.simple_btn)
        mode_layout.addWidget(self.advanced_btn)
        mode_layout.addStretch()

        main_layout.addLayout(mode_layout)

        # 簡易模式面板
        self.simple_panel = self.create_simple_panel()
        main_layout.addWidget(self.simple_panel)

        # 進階模式面板
        self.advanced_panel = self.create_advanced_panel()
        self.advanced_panel.setVisible(False)
        main_layout.addWidget(self.advanced_panel)

    def create_simple_panel(self) -> QWidget:
        """建立簡易模式面板"""
        panel = QGroupBox("🛡️ 保護機制")
        panel.setStyleSheet("""
            QGroupBox {
                background-color: #1f2937;
                border: 2px solid #374151;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                font-weight: bold;
                color: #60a5fa;
                font-size: 12pt;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout(panel)
        layout.setSpacing(16)

        # 單桌保護
        table_group = QFrame()
        table_group.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        table_layout = QFormLayout(table_group)

        table_title = QLabel("📊 單桌保護")
        table_title.setStyleSheet("font-weight: bold; color: #f3f4f6; font-size: 11pt;")
        table_layout.addRow(table_title)

        self.table_stop_loss = QDoubleSpinBox()
        self.table_stop_loss.setRange(-999999, 0)
        self.table_stop_loss.setValue(-500)
        self.table_stop_loss.setSuffix(" 元")
        self.table_stop_loss.setStyleSheet(self._spinbox_style())
        self.table_stop_loss.valueChanged.connect(self.risk_changed.emit)
        table_layout.addRow("  單桌止損:", self.table_stop_loss)

        self.table_take_profit = QDoubleSpinBox()
        self.table_take_profit.setRange(0, 999999)
        self.table_take_profit.setValue(1000)
        self.table_take_profit.setSuffix(" 元")
        self.table_take_profit.setStyleSheet(self._spinbox_style())
        self.table_take_profit.valueChanged.connect(self.risk_changed.emit)
        table_layout.addRow("  單桌止盈:", self.table_take_profit)

        self.max_losses = QSpinBox()
        self.max_losses.setRange(1, 20)
        self.max_losses.setValue(5)
        self.max_losses.setSuffix(" 次")
        self.max_losses.setStyleSheet(self._spinbox_style())
        self.max_losses.valueChanged.connect(self.risk_changed.emit)
        table_layout.addRow("  最大連輸:", self.max_losses)

        layout.addWidget(table_group)

        # 全域保護
        global_group = QFrame()
        global_group.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        global_layout = QFormLayout(global_group)

        global_title = QLabel("🌐 全域保護")
        global_title.setStyleSheet("font-weight: bold; color: #f3f4f6; font-size: 11pt;")
        global_layout.addRow(global_title)

        self.global_stop_loss = QDoubleSpinBox()
        self.global_stop_loss.setRange(-999999, 0)
        self.global_stop_loss.setValue(-2000)
        self.global_stop_loss.setSuffix(" 元")
        self.global_stop_loss.setStyleSheet(self._spinbox_style())
        self.global_stop_loss.valueChanged.connect(self.risk_changed.emit)
        global_layout.addRow("  當日止損:", self.global_stop_loss)

        self.global_take_profit = QDoubleSpinBox()
        self.global_take_profit.setRange(0, 999999)
        self.global_take_profit.setValue(5000)
        self.global_take_profit.setSuffix(" 元")
        self.global_take_profit.setStyleSheet(self._spinbox_style())
        self.global_take_profit.valueChanged.connect(self.risk_changed.emit)
        global_layout.addRow("  當日止盈:", self.global_take_profit)

        layout.addWidget(global_group)

        # 觸發動作
        action_group = QFrame()
        action_group.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        action_layout = QFormLayout(action_group)

        action_title = QLabel("⚙️ 觸發後動作")
        action_title.setStyleSheet("font-weight: bold; color: #f3f4f6; font-size: 11pt;")
        action_layout.addRow(action_title)

        self.action_combo = QComboBox()
        self.action_combo.addItems(["暫停策略", "全面停用", "僅提醒"])
        self.action_combo.setCurrentText("暫停策略")
        self.action_combo.setStyleSheet("""
            QComboBox {
                background-color: #1f2937;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        self.action_combo.currentTextChanged.connect(self.risk_changed.emit)
        action_layout.addRow("  動作:", self.action_combo)

        layout.addWidget(action_group)

        # 提示
        hint = QLabel("💡 簡易模式自動設定兩層風控:全域保護(優先)與單桌保護")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9ca3af; font-size: 9pt; padding: 8px;")
        layout.addWidget(hint)

        return panel

    def create_advanced_panel(self) -> QWidget:
        """建立進階模式面板 (使用原有的 RiskTableWidget)"""
        from ui.pages.page_strategy import RiskTableWidget

        panel = QWidget()
        layout = QVBoxLayout(panel)

        # 提示
        hint = QLabel("⚙️ 進階模式:完整五層風控階層設定 (從上到下優先級遞減)")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #60a5fa; font-size: 10pt; font-weight: bold; padding: 8px;")
        layout.addWidget(hint)

        # 風控表格
        self.risk_table = RiskTableWidget()
        layout.addWidget(self.risk_table)

        # 按鈕列
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 新增層級")
        remove_btn = QPushButton("- 移除層級")
        clear_btn = QPushButton("清空全部")

        for btn in (add_btn, remove_btn, clear_btn):
            btn.setStyleSheet("""
                QPushButton {
                    padding: 6px 12px;
                    border-radius: 6px;
                    background-color: #1f2937;
                    color: #f3f4f6;
                }
                QPushButton:hover {
                    background-color: #4b5563;
                }
            """)

        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        add_btn.clicked.connect(self.risk_table.add_row)
        remove_btn.clicked.connect(self._remove_last_row)
        clear_btn.clicked.connect(self._clear_all_rows)

        # 說明
        hint2 = QLabel("💡 提示: 風控層級由上到下優先級遞減。建議從全域→桌別→策略設定多層保護。")
        hint2.setWordWrap(True)
        hint2.setStyleSheet("color: #9ca3af; font-size: 9pt; padding: 8px;")
        layout.addWidget(hint2)

        return panel

    def _remove_last_row(self):
        """移除最後一行"""
        if self.risk_table.rowCount() == 0:
            return
        self.risk_table.removeRow(self.risk_table.rowCount() - 1)
        self.risk_changed.emit()

    def _clear_all_rows(self):
        """清空所有行"""
        self.risk_table.setRowCount(0)
        self.risk_changed.emit()

    def switch_mode(self, mode: str):
        """切換模式"""
        self.mode = mode

        if mode == "simple":
            self.simple_panel.setVisible(True)
            self.advanced_panel.setVisible(False)
            self.simple_btn.setChecked(True)
            self.advanced_btn.setChecked(False)
        else:  # advanced
            self.simple_panel.setVisible(False)
            self.advanced_panel.setVisible(True)
            self.simple_btn.setChecked(False)
            self.advanced_btn.setChecked(True)

    def get_risk_levels(self) -> List[Dict[str, Any]]:
        """取得風控設定 (轉換為標準格式)"""
        if self.mode == "simple":
            return self._convert_simple_to_levels()
        else:
            return self.risk_table.levels()

    def _convert_simple_to_levels(self) -> List[Dict[str, Any]]:
        """將簡易模式設定轉換為標準風控層級"""
        levels = []

        # 層級 1: 全域保護 (優先級最高)
        levels.append({
            "scope": RiskScope.GLOBAL_DAY.value,
            "take_profit": self.global_take_profit.value(),
            "stop_loss": self.global_stop_loss.value(),
            "max_drawdown_losses": None,
            "action": self._get_action_value(),
            "cooldown_sec": 300.0
        })

        # 層級 2: 單桌保護
        levels.append({
            "scope": RiskScope.TABLE.value,
            "take_profit": self.table_take_profit.value(),
            "stop_loss": self.table_stop_loss.value(),
            "max_drawdown_losses": self.max_losses.value(),
            "action": self._get_action_value(),
            "cooldown_sec": 180.0
        })

        return levels

    def _get_action_value(self) -> str:
        """取得動作設定值"""
        mapping = {
            "暫停策略": RiskLevelAction.PAUSE.value,
            "全面停用": RiskLevelAction.STOP_ALL.value,
            "僅提醒": RiskLevelAction.NOTIFY.value
        }
        return mapping.get(self.action_combo.currentText(), RiskLevelAction.PAUSE.value)

    def load_levels(self, levels: List[Dict[str, Any]]):
        """載入風控層級"""
        if not levels:
            # 空列表,使用簡易模式預設值
            self.switch_mode("simple")
            return

        # 判斷是否為簡易模式格式 (只有2層: GLOBAL_DAY + TABLE)
        if len(levels) == 2:
            scopes = [lvl.get("scope") for lvl in levels]
            if (RiskScope.GLOBAL_DAY.value in scopes and
                RiskScope.TABLE.value in scopes):
                # 簡易模式
                self._load_simple_mode(levels)
                self.switch_mode("simple")
                return

        # 進階模式
        self.switch_mode("advanced")
        from src.autobet.lines.config import parse_risk_level
        level_configs = [parse_risk_level(lvl) for lvl in levels]
        self.risk_table.load_levels(level_configs)

    def _load_simple_mode(self, levels: List[Dict[str, Any]]):
        """載入簡易模式資料"""
        for level in levels:
            scope = level.get("scope")
            if scope == RiskScope.GLOBAL_DAY.value:
                if level.get("stop_loss"):
                    self.global_stop_loss.setValue(level["stop_loss"])
                if level.get("take_profit"):
                    self.global_take_profit.setValue(level["take_profit"])
            elif scope == RiskScope.TABLE.value:
                if level.get("stop_loss"):
                    self.table_stop_loss.setValue(level["stop_loss"])
                if level.get("take_profit"):
                    self.table_take_profit.setValue(level["take_profit"])
                if level.get("max_drawdown_losses"):
                    self.max_losses.setValue(level["max_drawdown_losses"])

            # 動作
            action = level.get("action")
            if action:
                reverse_mapping = {
                    RiskLevelAction.PAUSE.value: "暫停策略",
                    RiskLevelAction.STOP_ALL.value: "全面停用",
                    RiskLevelAction.NOTIFY.value: "僅提醒"
                }
                action_text = reverse_mapping.get(action, "暫停策略")
                self.action_combo.setCurrentText(action_text)

    @staticmethod
    def _spinbox_style() -> str:
        """SpinBox 樣式"""
        return """
            QDoubleSpinBox, QSpinBox {
                background-color: #1f2937;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 6px;
            }
            QDoubleSpinBox:focus, QSpinBox:focus {
                border-color: #3b82f6;
            }
        """
