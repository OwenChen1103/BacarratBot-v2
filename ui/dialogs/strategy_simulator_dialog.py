# ui/dialogs/strategy_simulator_dialog.py
"""策略模擬器對話框"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QComboBox,
    QGroupBox,
    QFormLayout,
    QMessageBox,
)

from src.autobet.lines.config import StrategyDefinition
from src.autobet.strategy_simulator import StrategySimulator, generate_sample_roads


class StrategySimulatorDialog(QDialog):
    """策略模擬器對話框"""

    def __init__(self, definition: StrategyDefinition, parent=None):
        super().__init__(parent)
        self.definition = definition
        self.simulator = StrategySimulator(definition)
        self.setWindowTitle(f"策略模擬器 - {definition.strategy_key}")
        self.setMinimumSize(800, 700)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 標題
        title = QLabel(f"🎮 策略模擬器 - {self.definition.strategy_key}")
        title.setStyleSheet("""
            font-size: 16pt;
            font-weight: bold;
            color: #f3f4f6;
            padding: 12px;
            background-color: #1f2937;
            border-radius: 8px;
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 策略摘要
        summary_group = QGroupBox("策略配置摘要")
        summary_layout = QFormLayout(summary_group)
        summary_layout.addRow("Pattern:", QLabel(self.definition.entry.pattern))
        summary_layout.addRow("Dedup:", QLabel(self.definition.entry.dedup.value))
        sequence_text = ", ".join([str(x) for x in self.definition.staking.sequence])
        summary_layout.addRow("Sequence:", QLabel(sequence_text))
        summary_layout.addRow("Advance On:", QLabel(self.definition.staking.advance_on.value))
        layout.addWidget(summary_group)

        # 牌路輸入
        road_group = QGroupBox("歷史牌路輸入")
        road_layout = QVBoxLayout(road_group)

        # 範例選擇
        example_layout = QHBoxLayout()
        example_label = QLabel("快速範例:")
        self.example_combo = QComboBox()
        self.example_combo.addItem("-- 選擇範例 --", "")
        for name, road in generate_sample_roads():
            self.example_combo.addItem(name, road)

        self.example_combo.currentIndexChanged.connect(self._load_example)
        example_layout.addWidget(example_label)
        example_layout.addWidget(self.example_combo)
        example_layout.addStretch()
        road_layout.addLayout(example_layout)

        # 牌路文字框
        hint = QLabel("💡 輸入牌路: B=莊, P=閒, T=和 (例如: BPBPBBPPP)")
        hint.setStyleSheet("color: #9ca3af; font-size: 9pt;")
        road_layout.addWidget(hint)

        self.road_input = QTextEdit()
        self.road_input.setPlaceholderText("請輸入牌路,例如: BPBPBBPPPPBBBPBP...")
        self.road_input.setMaximumHeight(100)
        self.road_input.setStyleSheet("""
            QTextEdit {
                background-color: #1f2937;
                color: #f3f4f6;
                border: 2px solid #374151;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', monospace;
                font-size: 12pt;
            }
        """)
        road_layout.addWidget(self.road_input)

        # 執行按鈕
        run_btn = QPushButton("🚀 執行模擬")
        run_btn.setStyleSheet("""
            QPushButton {
                padding: 12px 24px;
                background-color: #2563eb;
                color: white;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        run_btn.clicked.connect(self._run_simulation)
        road_layout.addWidget(run_btn)

        layout.addWidget(road_group)

        # 結果顯示
        result_group = QGroupBox("模擬結果")
        result_layout = QVBoxLayout(result_group)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("""
            QTextEdit {
                background-color: #1f2937;
                color: #f3f4f6;
                border: 2px solid #374151;
                border-radius: 6px;
                padding: 12px;
                font-family: 'Consolas', monospace;
                font-size: 10pt;
            }
        """)
        self.result_text.setPlaceholderText("模擬結果將顯示於此...")
        result_layout.addWidget(self.result_text)

        layout.addWidget(result_group)

        # 關閉按鈕
        close_btn = QPushButton("關閉")
        close_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 30px;
                background-color: #1f2937;
                color: #f3f4f6;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

    def _load_example(self):
        """載入範例牌路"""
        road = self.example_combo.currentData()
        if road:
            self.road_input.setText(road)

    def _run_simulation(self):
        """執行模擬"""
        road_str = self.road_input.toPlainText().strip()
        if not road_str:
            QMessageBox.warning(self, "錯誤", "請輸入牌路!")
            return

        # 移除空格和換行
        road_str = "".join(road_str.split())

        # 驗證牌路
        invalid_chars = [c for c in road_str.upper() if c not in ['B', 'P', 'T']]
        if invalid_chars:
            QMessageBox.warning(
                self,
                "錯誤",
                f"牌路包含無效字符: {', '.join(set(invalid_chars))}\n僅允許 B, P, T"
            )
            return

        try:
            # 執行模擬
            result = self.simulator.simulate(road_str)

            # 格式化結果
            output = self._format_result(result)
            self.result_text.setText(output)

        except Exception as e:
            QMessageBox.critical(self, "模擬失敗", f"發生錯誤: {str(e)}")

    def _format_result(self, result) -> str:
        """格式化結果為可讀文字"""
        profit_color = "green" if result.total_profit > 0 else "red"
        roi_color = "green" if result.roi > 0 else "red"

        output = f"""
╔═══════════════════════════════════════════════════════════════╗
║                        模 擬 結 果                              ║
╚═══════════════════════════════════════════════════════════════╝

【基本統計】
  總手數:          {result.total_hands} 手
  觸發次數:        {result.triggered_count} 次
  勝場數:          {result.win_count} 次
  敗場數:          {result.loss_count} 次
  勝率:            {result.win_rate:.1f}%

【財務表現】
  總盈虧:          <span style='color:{profit_color}; font-weight:bold;'>{result.total_profit:+,.2f} 元</span>
  最大盈利:        {result.max_profit:+,.2f} 元
  最大回撤:        {result.max_drawdown:+,.2f} 元
  投資回報率:      <span style='color:{roi_color}; font-weight:bold;'>{result.roi:+.2f}%</span>

【風險指標】
  最大層數:        {result.max_layer_reached} 層
  觸發頻率:        {result.triggered_count / result.total_hands * 100:.1f}% (每 {result.total_hands / result.triggered_count if result.triggered_count > 0 else 0:.1f} 手觸發一次)

{"="*63}

【下注記錄】(最近 20 筆)
"""
        # 顯示最後 20 筆下注記錄
        recent_bets = result.bet_history[-20:]
        for hand_idx, bet_side, amount, profit in recent_bets:
            result_icon = "✅" if profit > 0 else "❌"
            side_text = "莊" if bet_side == "B" else "閒"
            output += f"  {result_icon} 手 #{hand_idx+1:03d} | 押{side_text} | {amount:,.0f} 元 | {profit:+,.2f} 元\n"

        if len(result.bet_history) > 20:
            output += f"\n  ... (共 {len(result.bet_history)} 筆記錄,僅顯示最近 20 筆)\n"

        return output
