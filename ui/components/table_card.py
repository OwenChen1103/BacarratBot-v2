# ui/components/table_card.py
"""
桌卡顯示組件

顯示內容（§K）：
- 桌號與開/關盤狀態
- 倒數計時
- 桌 PnL
- 各 Line 層數與下一手預告（方向+金額）
- 凍結徽章
"""
from __future__ import annotations

from typing import Dict, List, Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class LineStatusBadge(QWidget):
    """Line 狀態徽章"""

    def __init__(
        self,
        strategy_key: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.strategy_key = strategy_key

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # 策略名稱
        self.name_label = QLabel(strategy_key)
        self.name_label.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        self.name_label.setStyleSheet("color: #f3f4f6;")
        layout.addWidget(self.name_label)

        # 當前層數與注碼
        self.layer_label = QLabel("第 0 層 | 10")
        self.layer_label.setFont(QFont("Microsoft YaHei UI", 8))
        self.layer_label.setStyleSheet("color: #9ca3af;")
        layout.addWidget(self.layer_label)

        # 下一手預告
        self.next_bet_label = QLabel("下手: 閒 10")
        self.next_bet_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.next_bet_label.setStyleSheet("color: #10b981;")
        layout.addWidget(self.next_bet_label)

        # PnL
        self.pnl_label = QLabel("PnL: +0.00")
        self.pnl_label.setFont(QFont("Microsoft YaHei UI", 8))
        self.pnl_label.setStyleSheet("color: #10b981;")
        layout.addWidget(self.pnl_label)

        # 凍結徽章（初始隱藏）
        self.frozen_badge = QLabel("🧊 凍結")
        self.frozen_badge.setFont(QFont("Microsoft YaHei UI", 8))
        self.frozen_badge.setStyleSheet("""
            QLabel {
                background-color: #dc2626;
                color: white;
                padding: 2px 6px;
                border-radius: 4px;
            }
        """)
        self.frozen_badge.hide()
        layout.addWidget(self.frozen_badge)

        # 設置背景
        self.setStyleSheet("""
            QWidget {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 6px;
            }
        """)

    def update_status(
        self,
        current_layer: int = 0,
        current_stake: int = 0,
        next_direction: str = "",
        next_amount: float = 0.0,
        pnl: float = 0.0,
        frozen: bool = False,
    ) -> None:
        """更新狀態"""
        # 更新層數與注碼
        stake_sign = "+" if current_stake > 0 else ""
        self.layer_label.setText(f"第 {current_layer} 層 | {stake_sign}{current_stake}")

        # 更新下一手預告
        if next_direction and next_amount > 0:
            direction_text = {"B": "莊", "P": "閒", "T": "和"}.get(next_direction, next_direction)
            self.next_bet_label.setText(f"下手: {direction_text} {next_amount:.0f}")
            self.next_bet_label.show()
        else:
            self.next_bet_label.setText("下手: 待觸發")
            self.next_bet_label.setStyleSheet("color: #6b7280;")

        # 更新 PnL
        pnl_color = "#10b981" if pnl >= 0 else "#ef4444"
        pnl_text = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
        self.pnl_label.setText(f"PnL: {pnl_text}")
        self.pnl_label.setStyleSheet(f"color: {pnl_color};")

        # 顯示/隱藏凍結徽章
        if frozen:
            self.frozen_badge.show()
            self.setStyleSheet("""
                QWidget {
                    background-color: #1f2937;
                    border: 2px solid #dc2626;
                    border-radius: 6px;
                }
            """)
        else:
            self.frozen_badge.hide()
            self.setStyleSheet("""
                QWidget {
                    background-color: #1f2937;
                    border: 1px solid #374151;
                    border-radius: 6px;
                }
            """)


class TableCard(QFrame):
    """桌卡組件"""

    def __init__(
        self,
        table_id: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.table_id = table_id
        self.line_badges: Dict[str, LineStatusBadge] = {}

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 2px solid #374151;
                border-radius: 12px;
                padding: 12px;
            }
        """)

        self._build_ui()

        # 定時刷新倒數
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._update_countdown)
        self.countdown_timer.start(100)  # 100ms 更新一次

        self.countdown_end_time: Optional[float] = None

    def _build_ui(self) -> None:
        """構建 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 頂部：桌號與狀態
        header_layout = QHBoxLayout()

        self.table_label = QLabel(f"🎲 {self.table_id}")
        self.table_label.setFont(QFont("Microsoft YaHei UI", 14, QFont.Bold))
        self.table_label.setStyleSheet("color: #f9fafb;")
        header_layout.addWidget(self.table_label)

        header_layout.addStretch()

        self.status_label = QLabel("● 等待中")
        self.status_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.status_label.setStyleSheet("color: #6b7280;")
        header_layout.addWidget(self.status_label)

        layout.addLayout(header_layout)

        # 倒數計時條
        self.countdown_label = QLabel("倒數: --")
        self.countdown_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.countdown_label.setStyleSheet("color: #9ca3af;")
        layout.addWidget(self.countdown_label)

        self.countdown_bar = QProgressBar()
        self.countdown_bar.setRange(0, 100)
        self.countdown_bar.setValue(0)
        self.countdown_bar.setTextVisible(False)
        self.countdown_bar.setFixedHeight(6)
        self.countdown_bar.setStyleSheet("""
            QProgressBar {
                background-color: #374151;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.countdown_bar)

        # 桌 PnL
        self.table_pnl_label = QLabel("桌 PnL: +0.00")
        self.table_pnl_label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        self.table_pnl_label.setStyleSheet("color: #10b981;")
        layout.addWidget(self.table_pnl_label)

        # Line 狀態區（可滾動）
        lines_label = QLabel("策略狀態")
        lines_label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        lines_label.setStyleSheet("color: #d1d5db;")
        layout.addWidget(lines_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        self.lines_container = QWidget()
        self.lines_layout = QVBoxLayout(self.lines_container)
        self.lines_layout.setSpacing(8)
        self.lines_layout.setContentsMargins(0, 0, 0, 0)
        self.lines_layout.addStretch()

        scroll.setWidget(self.lines_container)
        layout.addWidget(scroll, 1)  # 可擴展

    def update_table_status(
        self,
        phase: str = "idle",
        countdown_seconds: Optional[float] = None,
        table_pnl: float = 0.0,
    ) -> None:
        """
        更新桌狀態

        Args:
            phase: 桌階段 ("idle", "bettable", "locked", "resulting")
            countdown_seconds: 倒數秒數
            table_pnl: 桌 PnL
        """
        # 更新狀態標籤
        status_map = {
            "idle": ("● 等待中", "#6b7280"),
            "bettable": ("● 可下注", "#10b981"),
            "locked": ("● 已鎖定", "#f59e0b"),
            "resulting": ("● 開獎中", "#3b82f6"),
        }
        text, color = status_map.get(phase, ("● 未知", "#6b7280"))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

        # 更新倒數
        if countdown_seconds is not None and countdown_seconds > 0:
            import time
            self.countdown_end_time = time.time() + countdown_seconds
        else:
            self.countdown_end_time = None

        # 更新桌 PnL
        pnl_color = "#10b981" if table_pnl >= 0 else "#ef4444"
        pnl_text = f"+{table_pnl:.2f}" if table_pnl >= 0 else f"{table_pnl:.2f}"
        self.table_pnl_label.setText(f"桌 PnL: {pnl_text}")
        self.table_pnl_label.setStyleSheet(f"color: {pnl_color};")

    def add_or_update_line(
        self,
        strategy_key: str,
        current_layer: int = 0,
        current_stake: int = 0,
        next_direction: str = "",
        next_amount: float = 0.0,
        pnl: float = 0.0,
        frozen: bool = False,
    ) -> None:
        """添加或更新 Line 狀態"""
        if strategy_key not in self.line_badges:
            # 創建新徽章
            badge = LineStatusBadge(strategy_key)
            self.line_badges[strategy_key] = badge
            # 插入到 stretch 之前
            self.lines_layout.insertWidget(self.lines_layout.count() - 1, badge)

        # 更新徽章
        badge = self.line_badges[strategy_key]
        badge.update_status(
            current_layer=current_layer,
            current_stake=current_stake,
            next_direction=next_direction,
            next_amount=next_amount,
            pnl=pnl,
            frozen=frozen,
        )

    def remove_line(self, strategy_key: str) -> None:
        """移除 Line"""
        if strategy_key in self.line_badges:
            badge = self.line_badges.pop(strategy_key)
            self.lines_layout.removeWidget(badge)
            badge.deleteLater()

    def _update_countdown(self) -> None:
        """更新倒數顯示"""
        if self.countdown_end_time is None:
            self.countdown_label.setText("倒數: --")
            self.countdown_bar.setValue(0)
            return

        import time
        remaining = self.countdown_end_time - time.time()

        if remaining <= 0:
            self.countdown_label.setText("倒數: 0.0s")
            self.countdown_bar.setValue(100)
            self.countdown_end_time = None
            return

        self.countdown_label.setText(f"倒數: {remaining:.1f}s")

        # 假設總時間是 10 秒（可以根據實際調整）
        total_time = 10.0
        progress = int((1 - remaining / total_time) * 100)
        progress = max(0, min(100, progress))
        self.countdown_bar.setValue(progress)

        # 快結束時變紅
        if remaining < 2.0:
            self.countdown_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #374151;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #ef4444;
                    border-radius: 3px;
                }
            """)
        else:
            self.countdown_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #374151;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #3b82f6;
                    border-radius: 3px;
                }
            """)


class TableCardsPanel(QWidget):
    """桌卡面板容器"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.table_cards: Dict[str, TableCard] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        """構建 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 標題
        header = QLabel("🎰 桌台狀態")
        header.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        header.setStyleSheet("color: #f9fafb; padding: 8px 0;")
        main_layout.addWidget(header)

        # 滾動區
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.addStretch()

        scroll.setWidget(self.cards_container)
        main_layout.addWidget(scroll)

    def add_or_update_table(
        self,
        table_id: str,
        phase: str = "idle",
        countdown_seconds: Optional[float] = None,
        table_pnl: float = 0.0,
        lines: Optional[List[Dict]] = None,
    ) -> None:
        """
        添加或更新桌卡

        Args:
            table_id: 桌號
            phase: 桌階段
            countdown_seconds: 倒數秒數
            table_pnl: 桌 PnL
            lines: Line 狀態列表
        """
        if table_id not in self.table_cards:
            # 創建新桌卡
            card = TableCard(table_id)
            self.table_cards[table_id] = card
            # 插入到 stretch 之前
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

        card = self.table_cards[table_id]
        card.update_table_status(phase, countdown_seconds, table_pnl)

        # 更新 Lines
        if lines:
            for line_data in lines:
                card.add_or_update_line(
                    strategy_key=line_data.get("strategy_key", ""),
                    current_layer=line_data.get("current_layer", 0),
                    current_stake=line_data.get("current_stake", 0),
                    next_direction=line_data.get("next_direction", ""),
                    next_amount=line_data.get("next_amount", 0.0),
                    pnl=line_data.get("pnl", 0.0),
                    frozen=line_data.get("frozen", False),
                )

    def remove_table(self, table_id: str) -> None:
        """移除桌卡"""
        if table_id in self.table_cards:
            card = self.table_cards.pop(table_id)
            self.cards_layout.removeWidget(card)
            card.deleteLater()
