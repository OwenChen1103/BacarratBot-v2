# ui/components/next_bet_card.py
"""
下一手詳情卡片
顯示當前策略配置和即將執行的下注詳情
"""

import os
import json
from typing import Optional, Dict, Any
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class NextBetCard(QFrame):
    """下一手詳情卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.setVisible(False)  # 預設完全隱藏，只在結果局時顯示

    def _build_ui(self) -> None:
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
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # === 🔥 結果局區塊（預設隱藏，只在下注後顯示）===

        # 結果局容器
        self.result_container = QWidget()
        result_layout = QVBoxLayout(self.result_container)
        result_layout.setSpacing(8)
        result_layout.setContentsMargins(0, 8, 0, 0)

        # 結果局標題
        result_header_layout = QHBoxLayout()
        self.result_header = QLabel("⏳ 結果局 - 等待開獎")
        self.result_header.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        self.result_header.setStyleSheet("color: #fbbf24;")
        result_header_layout.addWidget(self.result_header)

        result_header_layout.addStretch()

        # 狀態指示燈
        self.result_status_dot = QLabel("●")
        self.result_status_dot.setFont(QFont("Arial", 12))
        self.result_status_dot.setStyleSheet("color: #fbbf24;")
        result_header_layout.addWidget(self.result_status_dot)

        result_layout.addLayout(result_header_layout)

        # 結果局詳細資訊
        self.result_info_label = QLabel()
        self.result_info_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.result_info_label.setStyleSheet("""
            QLabel {
                color: #e5e7eb;
                background-color: #111827;
                border: 1px solid #fbbf24;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        self.result_info_label.setWordWrap(True)
        result_layout.addWidget(self.result_info_label)

        # 影響預測
        self.result_impact_label = QLabel()
        self.result_impact_label.setFont(QFont("Microsoft YaHei UI", 8))
        self.result_impact_label.setStyleSheet("""
            QLabel {
                color: #d1d5db;
                background-color: #0f172a;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        self.result_impact_label.setWordWrap(True)
        result_layout.addWidget(self.result_impact_label)

        self.result_container.setVisible(False)  # 預設隱藏
        layout.addWidget(self.result_container)

        layout.addStretch()

    # === 🔥 結果局相關方法 ===

    def show_result_round(self, data: Dict[str, Any]) -> None:
        """
        顯示結果局 (已下注，等待開獎)

        Args:
            data: {
                "strategy": "martingale_bpp",
                "direction": "banker" | "player" | "tie",
                "amount": 200,
                "current_layer": 2,
                "total_layers": 4,
                "round_id": "detect-1234567890",
                "sequence": [100, 200, 400, 800],
                "on_win": "RESET" | "ADVANCE",
                "on_loss": "ADVANCE" | "RESET"
            }
        """
        # 顯示整個卡片和結果局容器
        self.setVisible(True)
        self.result_container.setVisible(True)

        # 方向映射
        direction_map = {
            "banker": ("🔴 莊家", "#ef4444"),
            "player": ("🔵 閒家", "#3b82f6"),
            "tie": ("🟢 和局", "#10b981"),
            "B": ("🔴 莊家", "#ef4444"),
            "P": ("🔵 閒家", "#3b82f6"),
            "T": ("🟢 和局", "#10b981"),
        }
        direction_text, direction_color = direction_map.get(
            data.get("direction", "").lower(), ("未知", "#ffffff")
        )

        # 基本資訊
        strategy = data.get("strategy", "未知")
        amount = data.get("amount", 0)
        current_layer = data.get("current_layer", 0)
        total_layers = data.get("total_layers", 0)
        round_id = data.get("round_id", "N/A")

        info_text = (
            f"<b>策略:</b> {strategy}<br>"
            f"<b>方向:</b> <span style='color:{direction_color};font-weight:bold;'>{direction_text}</span><br>"
            f"<b>金額:</b> {amount} 元<br>"
            f"<b>層數:</b> 第 {current_layer}/{total_layers} 層<br>"
            f"<b>局號:</b> <span style='color:#9ca3af;font-size:8px;'>{round_id}</span>"
        )
        self.result_info_label.setText(info_text)

        # 計算影響預測
        sequence = data.get("sequence", [])
        on_win = data.get("on_win", "RESET")
        on_loss = data.get("on_loss", "ADVANCE")

        # 獲勝影響
        if on_win == "RESET":
            win_amount = sequence[0] if sequence else 0
            win_impact = f"重置到第1層 (下注 <b>{win_amount}</b> 元)"
        else:
            win_next_layer = min(current_layer + 1, total_layers)
            win_amount = sequence[win_next_layer - 1] if win_next_layer <= len(sequence) else "上限"
            win_impact = f"前進到第{win_next_layer}層 (下注 <b>{win_amount}</b> 元)"

        # 失敗影響
        if on_loss == "ADVANCE":
            loss_next_layer = min(current_layer + 1, total_layers)
            loss_amount = sequence[loss_next_layer - 1] if loss_next_layer <= len(sequence) else "上限"
            loss_impact = f"前進到第{loss_next_layer}層 (下注 <b>{loss_amount}</b> 元)"
        else:
            loss_amount = sequence[0] if sequence else 0
            loss_impact = f"重置到第1層 (下注 <b>{loss_amount}</b> 元)"

        impact_text = (
            f"<span style='color:#10b981;'>✅ 獲勝</span> → {win_impact}<br>"
            f"<span style='color:#ef4444;'>❌ 失敗</span> → {loss_impact}<br>"
            f"<span style='color:#6b7280;'>➖ 和局</span> → 層數不變 (繼續下注 <b>{amount}</b> 元)"
        )
        self.result_impact_label.setText(impact_text)

        # 啟動閃爍動畫
        self._start_result_blink()

    def update_result_outcome(self, outcome: str, pnl: float) -> None:
        """
        更新結果局的開獎結果

        Args:
            outcome: "win" | "loss" | "skip"
            pnl: 盈虧金額
        """
        # 停止閃爍
        if hasattr(self, '_result_blink_timer'):
            self._result_blink_timer.stop()

        # 結果映射
        outcome_map = {
            "win": ("🎉 獲勝", "#10b981"),
            "loss": ("😞 失敗", "#ef4444"),
            "skip": ("➖ 跳過 (和局)", "#6b7280"),
        }
        outcome_text, outcome_color = outcome_map.get(
            outcome.lower(), ("未知", "#ffffff")
        )

        # 更新標題
        pnl_sign = "+" if pnl > 0 else ""
        self.result_header.setText(
            f"{outcome_text} | 盈虧: <span style='color:{outcome_color};'>{pnl_sign}{pnl:.0f}</span> 元"
        )
        self.result_header.setStyleSheet(f"color: {outcome_color}; font-weight: bold;")

        # 固定狀態燈顏色
        self.result_status_dot.setStyleSheet(f"color: {outcome_color};")

        # 更新邊框顏色
        self.result_info_label.setStyleSheet(f"""
            QLabel {{
                color: #e5e7eb;
                background-color: #111827;
                border: 2px solid {outcome_color};
                border-radius: 4px;
                padding: 10px;
            }}
        """)

        # 3秒後自動隱藏
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, self.hide_result_round)

    def hide_result_round(self) -> None:
        """隱藏結果局區塊（隱藏整個卡片）"""
        # 停止閃爍
        if hasattr(self, '_result_blink_timer'):
            self._result_blink_timer.stop()

        # 隱藏整個卡片
        self.setVisible(False)
        self.result_container.setVisible(False)

        # 重置樣式
        self.result_header.setText("⏳ 結果局 - 等待開獎")
        self.result_header.setStyleSheet("color: #fbbf24;")
        self.result_status_dot.setStyleSheet("color: #fbbf24;")
        self.result_info_label.setStyleSheet("""
            QLabel {
                color: #e5e7eb;
                background-color: #111827;
                border: 1px solid #fbbf24;
                border-radius: 4px;
                padding: 10px;
            }
        """)

    def _start_result_blink(self) -> None:
        """啟動結果局指示燈閃爍"""
        from PySide6.QtCore import QTimer
        timer = QTimer(self)
        timer.timeout.connect(self._toggle_result_dot)
        timer.start(800)  # 800ms 閃爍一次
        self._result_blink_timer = timer
        self._result_dot_visible = True

    def _toggle_result_dot(self) -> None:
        """切換指示燈顯示/隱藏"""
        if not hasattr(self, '_result_dot_visible'):
            self._result_dot_visible = True

        self._result_dot_visible = not self._result_dot_visible
        if self._result_dot_visible:
            self.result_status_dot.setStyleSheet("color: #fbbf24;")
        else:
            self.result_status_dot.setStyleSheet("color: transparent;")
