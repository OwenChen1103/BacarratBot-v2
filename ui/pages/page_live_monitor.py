# ui/pages/page_live_monitor.py
"""
即時監控頁面

整合所有 UI 組件：
- 總覽面板（上方）
- 桌卡顯示（左側）
- 事件區（右側）
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:
    from ..components import OverviewPanel, TableCardsPanel, EventPanel
except ImportError:
    # For standalone execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from components import OverviewPanel, TableCardsPanel, EventPanel


class LiveMonitorPage(QWidget):
    """即時監控頁面"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.orchestrator = None
        self._build_ui()

    def _build_ui(self) -> None:
        """構建 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 頂部：總覽面板
        self.overview_panel = OverviewPanel()
        main_layout.addWidget(self.overview_panel)

        # 中下部：分割器（桌卡 | 事件區）
        splitter = QSplitter(Qt.Horizontal)

        # 左側：桌卡面板
        self.table_cards_panel = TableCardsPanel()
        splitter.addWidget(self.table_cards_panel)

        # 右側：事件面板
        self.event_panel = EventPanel()
        splitter.addWidget(self.event_panel)

        # 設置初始比例 (60% 桌卡 | 40% 事件)
        splitter.setSizes([600, 400])

        main_layout.addWidget(splitter, 1)  # 可擴展

    def set_orchestrator(self, orchestrator) -> None:
        """
        設置 Orchestrator 數據源

        Args:
            orchestrator: LineOrchestrator 實例
        """
        self.orchestrator = orchestrator

        # 連接所有組件
        self.overview_panel.set_orchestrator(orchestrator)
        self.event_panel.set_orchestrator(orchestrator)

        # TODO: 連接桌卡面板（需要從 orchestrator 獲取桌台信息）

    def update_display(self) -> None:
        """手動更新顯示（如果不使用自動刷新）"""
        if not self.orchestrator:
            return

        # 更新桌台信息
        for table_id in self.orchestrator.table_phases.keys():
            phase = self.orchestrator.table_phases.get(table_id, "idle")

            # 計算桌 PnL
            table_pnl = 0.0
            lines_data = []

            # 獲取該桌的所有 Line 狀態
            table_lines = self.orchestrator.line_states.get(table_id, {})
            for strategy_key, line_state in table_lines.items():
                table_pnl += line_state.pnl

                # 獲取當前層數和注碼
                progression = self.orchestrator._get_progression(table_id, strategy_key)
                current_layer = progression.index
                current_stake = progression.current_stake()

                # 預測下一手方向和金額
                strategy = self.orchestrator.strategies.get(strategy_key)
                if strategy:
                    base_direction = self.orchestrator._derive_base_direction(strategy.entry)
                    direction, amount = self.orchestrator._resolve_direction(current_stake, base_direction)
                    next_direction = direction.value
                    next_amount = amount
                else:
                    next_direction = ""
                    next_amount = 0.0

                lines_data.append({
                    "strategy_key": strategy_key,
                    "current_layer": current_layer,
                    "current_stake": current_stake,
                    "next_direction": next_direction,
                    "next_amount": next_amount,
                    "pnl": line_state.pnl,
                    "frozen": line_state.frozen,
                })

            # 更新桌卡
            self.table_cards_panel.add_or_update_table(
                table_id=table_id,
                phase=phase.value if hasattr(phase, 'value') else str(phase),
                table_pnl=table_pnl,
                lines=lines_data,
            )


# 為了方便測試，創建一個演示函數
def create_demo_page() -> LiveMonitorPage:
    """創建演示頁面"""
    page = LiveMonitorPage()

    # 模擬數據
    page.overview_panel.update_metrics(
        total_pnl=+125.50,
        exposure=300.0,
        win_rate=0.65,
        bet_count=42,
    )

    page.overview_panel.update_risk_status("normal", "全域風控: 正常運行")
    page.overview_panel.update_system_status(
        orchestrator="normal",
        capital="normal",
        risk="normal",
        conflict="normal",
    )

    # 添加桌台
    page.table_cards_panel.add_or_update_table(
        table_id="T1",
        phase="bettable",
        countdown_seconds=6.5,
        table_pnl=+50.00,
        lines=[
            {
                "strategy_key": "BB_P",
                "current_layer": 1,
                "current_stake": 20,
                "next_direction": "P",
                "next_amount": 20.0,
                "pnl": +30.00,
                "frozen": False,
            },
            {
                "strategy_key": "PPP_B",
                "current_layer": 0,
                "current_stake": 10,
                "next_direction": "B",
                "next_amount": 10.0,
                "pnl": +20.00,
                "frozen": False,
            },
        ],
    )

    page.table_cards_panel.add_or_update_table(
        table_id="T2",
        phase="locked",
        table_pnl=-10.00,
        lines=[
            {
                "strategy_key": "BB_P",
                "current_layer": 2,
                "current_stake": 40,
                "next_direction": "P",
                "next_amount": 40.0,
                "pnl": -10.00,
                "frozen": False,
            },
        ],
    )

    page.table_cards_panel.add_or_update_table(
        table_id="T3",
        phase="idle",
        table_pnl=+85.50,
        lines=[
            {
                "strategy_key": "Martingale",
                "current_layer": 0,
                "current_stake": -10,  # 負數 = 反打
                "next_direction": "B",
                "next_amount": 10.0,
                "pnl": +85.50,
                "frozen": True,  # 凍結中
            },
        ],
    )

    # 添加事件
    page.event_panel.add_event("success", "Line BB_P enter P amount=20.0", metadata={"table": "T1", "layer": "1"})
    page.event_panel.add_conflict_event("PPP_B", "Opposite direction conflict, P wins", metadata={"table": "T1"})
    page.event_panel.add_risk_event("table:T2", "pause", metadata={"pnl": "-50.00", "trigger": "stop_loss"})
    page.event_panel.add_event("info", "Line Martingale reset to layer 0", metadata={"table": "T3"})
    page.event_panel.add_error_event("Capital reserve failed: below_min_unit", error_id="ERR_001")

    return page


if __name__ == "__main__":
    """演示模式"""
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # 設置深色主題
    app.setStyleSheet("""
        QWidget {
            background-color: #0f172a;
            color: #f1f5f9;
        }
    """)

    window = create_demo_page()
    window.setWindowTitle("Line 策略即時監控")
    window.resize(1400, 900)
    window.show()

    sys.exit(app.exec())
