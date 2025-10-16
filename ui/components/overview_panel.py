# ui/components/overview_panel.py
"""
總覽面板組件

顯示內容（§K）：
- 當日 PnL（總盈虧）
- 當下總曝險（已投入資金）
- 全域檔停進度（風控狀態）
- 告警燈（系統狀態指示）
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class MetricCard(QFrame):
    """單個度量卡片"""

    def __init__(
        self,
        title: str,
        value: str = "0",
        unit: str = "",
        color: str = "#3b82f6",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1f2937;
                border: 2px solid {color};
                border-radius: 12px;
                padding: 16px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 標題
        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.title_label.setStyleSheet("color: #9ca3af; border: none;")
        layout.addWidget(self.title_label)

        # 數值 + 單位
        value_layout = QHBoxLayout()
        value_layout.setSpacing(4)

        self.value_label = QLabel(value)
        self.value_label.setFont(QFont("Microsoft YaHei UI", 24, QFont.Bold))
        self.value_label.setStyleSheet(f"color: {color}; border: none;")
        value_layout.addWidget(self.value_label)

        if unit:
            self.unit_label = QLabel(unit)
            self.unit_label.setFont(QFont("Microsoft YaHei UI", 14))
            self.unit_label.setStyleSheet("color: #6b7280; border: none;")
            self.unit_label.setAlignment(Qt.AlignBottom)
            value_layout.addWidget(self.unit_label)

        value_layout.addStretch()
        layout.addLayout(value_layout)

    def update_value(self, value: str, color: Optional[str] = None) -> None:
        """更新數值"""
        self.value_label.setText(value)
        if color:
            self.value_label.setStyleSheet(f"color: {color}; border: none;")


class StatusIndicator(QWidget):
    """狀態指示燈"""

    def __init__(
        self,
        label: str,
        status: str = "normal",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 指示燈
        self.indicator = QLabel()
        self.indicator.setFixedSize(16, 16)
        self.set_status(status)
        layout.addWidget(self.indicator)

        # 標籤
        self.label = QLabel(label)
        self.label.setFont(QFont("Microsoft YaHei UI", 10))
        self.label.setStyleSheet("color: #d1d5db;")
        layout.addWidget(self.label)

        layout.addStretch()

    def set_status(self, status: str) -> None:
        """
        設置狀態

        Args:
            status: "normal" (綠), "warning" (黃), "error" (紅), "disabled" (灰)
        """
        colors = {
            "normal": "#10b981",    # 綠色
            "warning": "#f59e0b",   # 黃色
            "error": "#ef4444",     # 紅色
            "disabled": "#6b7280",  # 灰色
        }
        color = colors.get(status, "#6b7280")

        self.indicator.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 8px;
            }}
        """)


class OverviewPanel(QWidget):
    """總覽面板"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

        # 定時刷新（每秒更新一次）
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.start(1000)  # 1000ms = 1秒

    def _build_ui(self) -> None:
        """構建 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 標題
        header = QLabel("📊 即時總覽")
        header.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        header.setStyleSheet("color: #f9fafb; padding: 8px 0;")
        main_layout.addWidget(header)

        # 度量卡片區
        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(16)

        # 卡片 1: 當日 PnL
        self.pnl_card = MetricCard(
            title="當日 PnL",
            value="0.00",
            unit="",
            color="#10b981",  # 綠色（正）
        )
        metrics_layout.addWidget(self.pnl_card, 0, 0)

        # 卡片 2: 總曝險
        self.exposure_card = MetricCard(
            title="當下曝險",
            value="0",
            unit="",
            color="#3b82f6",  # 藍色
        )
        metrics_layout.addWidget(self.exposure_card, 0, 1)

        # 卡片 3: 勝率
        self.winrate_card = MetricCard(
            title="今日勝率",
            value="0%",
            unit="",
            color="#8b5cf6",  # 紫色
        )
        metrics_layout.addWidget(self.winrate_card, 0, 2)

        # 卡片 4: 下注次數
        self.bet_count_card = MetricCard(
            title="下注次數",
            value="0",
            unit="次",
            color="#f59e0b",  # 橙色
        )
        metrics_layout.addWidget(self.bet_count_card, 0, 3)

        main_layout.addLayout(metrics_layout)

        # 風控狀態區
        risk_frame = QFrame()
        risk_frame.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        risk_layout = QVBoxLayout(risk_frame)
        risk_layout.setSpacing(8)

        risk_title = QLabel("風控狀態")
        risk_title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        risk_title.setStyleSheet("color: #f3f4f6; border: none;")
        risk_layout.addWidget(risk_title)

        # 風控進度條（簡化版，顯示當前狀態）
        self.risk_status_label = QLabel("全域風控: 正常運行")
        self.risk_status_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.risk_status_label.setStyleSheet("color: #10b981; border: none;")
        risk_layout.addWidget(self.risk_status_label)

        main_layout.addWidget(risk_frame)

        # 系統狀態指示燈區
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setSpacing(8)

        status_title = QLabel("系統狀態")
        status_title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        status_title.setStyleSheet("color: #f3f4f6; border: none;")
        status_layout.addWidget(status_title)

        # 狀態指示燈
        indicators_layout = QGridLayout()
        indicators_layout.setSpacing(8)

        self.orchestrator_status = StatusIndicator("策略編排器", "normal")
        indicators_layout.addWidget(self.orchestrator_status, 0, 0)

        self.capital_status = StatusIndicator("資金池", "normal")
        indicators_layout.addWidget(self.capital_status, 0, 1)

        self.risk_status = StatusIndicator("風控系統", "normal")
        indicators_layout.addWidget(self.risk_status, 1, 0)

        self.conflict_status = StatusIndicator("衝突解決器", "normal")
        indicators_layout.addWidget(self.conflict_status, 1, 1)

        status_layout.addLayout(indicators_layout)
        main_layout.addWidget(status_frame)

        main_layout.addStretch()

    def update_metrics(
        self,
        total_pnl: float = 0.0,
        exposure: float = 0.0,
        win_rate: float = 0.0,
        bet_count: int = 0,
    ) -> None:
        """
        更新度量數據

        Args:
            total_pnl: 當日總 PnL
            exposure: 當下總曝險
            win_rate: 勝率（0-1）
            bet_count: 下注次數
        """
        # 更新 PnL（根據正負顯示不同顏色）
        pnl_color = "#10b981" if total_pnl >= 0 else "#ef4444"
        pnl_text = f"+{total_pnl:.2f}" if total_pnl >= 0 else f"{total_pnl:.2f}"
        self.pnl_card.update_value(pnl_text, pnl_color)

        # 更新曝險
        self.exposure_card.update_value(f"{exposure:.0f}")

        # 更新勝率
        winrate_text = f"{win_rate * 100:.1f}%"
        self.winrate_card.update_value(winrate_text)

        # 更新下注次數
        self.bet_count_card.update_value(str(bet_count))

    def update_risk_status(self, status: str, message: str = "") -> None:
        """
        更新風控狀態

        Args:
            status: "normal", "warning", "error"
            message: 狀態訊息
        """
        colors = {
            "normal": "#10b981",
            "warning": "#f59e0b",
            "error": "#ef4444",
        }
        color = colors.get(status, "#10b981")

        text = message or f"全域風控: {status}"
        self.risk_status_label.setText(text)
        self.risk_status_label.setStyleSheet(f"color: {color}; border: none;")

    def update_system_status(
        self,
        orchestrator: str = "normal",
        capital: str = "normal",
        risk: str = "normal",
        conflict: str = "normal",
    ) -> None:
        """
        更新系統狀態指示燈

        Args:
            orchestrator: 編排器狀態
            capital: 資金池狀態
            risk: 風控系統狀態
            conflict: 衝突解決器狀態
        """
        self.orchestrator_status.set_status(orchestrator)
        self.capital_status.set_status(capital)
        self.risk_status.set_status(risk)
        self.conflict_status.set_status(conflict)

    def _auto_refresh(self) -> None:
        """自動刷新（由外部提供數據源時覆蓋此方法）"""
        pass

    def set_orchestrator(self, orchestrator) -> None:
        """
        設置 Orchestrator 數據源

        Args:
            orchestrator: LineOrchestrator 實例
        """
        self.orchestrator = orchestrator

        # 覆蓋自動刷新方法
        def refresh_from_orchestrator():
            if not hasattr(self, 'orchestrator'):
                return

            # 獲取全局統計
            global_stats = self.orchestrator.metrics.get_global_stats()

            # 獲取資金池快照
            capital_snapshot = self.orchestrator.capital.snapshot()

            # 更新度量
            self.update_metrics(
                total_pnl=global_stats.get("total_pnl", 0.0),
                exposure=capital_snapshot.get("bankroll_total", 0.0) - capital_snapshot.get("bankroll_free", 0.0),
                win_rate=global_stats.get("global_win_rate", 0.0),
                bet_count=global_stats.get("total_bets", 0),
            )

            # 更新風控狀態
            # TODO: 從 orchestrator.risk 獲取實際狀態
            self.update_risk_status("normal", "全域風控: 正常運行")

            # 更新系統狀態
            self.update_system_status(
                orchestrator="normal",
                capital="normal" if capital_snapshot.get("bankroll_free", 0) > 0 else "warning",
                risk="normal",
                conflict="normal",
            )

        self._auto_refresh = refresh_from_orchestrator
