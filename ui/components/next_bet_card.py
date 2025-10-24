# ui/components/next_bet_card.py
"""
下一手詳情卡片 - 永久顯示版
顯示當前下注狀態和結果信息

✨ 2025 現代設計：
- 永久顯示，不隱藏
- 與策略資訊卡片風格統一
- 清晰的視覺層次和分隔
- 大號金額顯示
"""

from typing import Dict, Any
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtGui import QFont


class NextBetCard(QFrame):
    """下一手詳情卡片（永久顯示）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.setVisible(True)  # ✅ 永久顯示

    def _build_ui(self) -> None:
        """構建 UI - 現代設計感版本"""
        self.setFrameStyle(QFrame.NoFrame)
        self.setStyleSheet("""
            QFrame {
                background-color: #1e2128;
                border: 1px solid #2d3139;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 14, 16, 14)

        # === 標題欄 ===
        header_container = QHBoxLayout()
        header_container.setSpacing(12)

        self.result_header = QLabel("⚡ 結果局")
        self.result_header.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        self.result_header.setStyleSheet("color: #e5e7eb; background: transparent; border: none;")
        header_container.addWidget(self.result_header)

        header_container.addStretch()

        # 狀態指示
        self.result_status_dot = QLabel("● 未觸發")
        self.result_status_dot.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        self.result_status_dot.setStyleSheet("color: #6b7280; background: transparent; border: none;")
        header_container.addWidget(self.result_status_dot)

        layout.addLayout(header_container)

        # === 分隔線 ===
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #2d3139; min-height: 1px; max-height: 1px; border: none;")
        layout.addWidget(separator)

        # === 下注資訊區域 ===
        self.result_info_label = QLabel("<span style='color: #6b7280;'>等待觸發...</span>")
        self.result_info_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.result_info_label.setStyleSheet("color: #d1d5db; background: transparent; border: none; padding: 2px 0px;")
        self.result_info_label.setWordWrap(True)
        layout.addWidget(self.result_info_label)

        # === 分隔線 ===
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setStyleSheet("background-color: #2d3139; min-height: 1px; max-height: 1px; border: none;")
        layout.addWidget(separator2)

        # === 影響預測區域 ===
        self.result_impact_label = QLabel("")
        self.result_impact_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.result_impact_label.setStyleSheet("color: #9ca3af; background: transparent; border: none; padding: 2px 0px;")
        self.result_impact_label.setWordWrap(True)
        layout.addWidget(self.result_impact_label)

        # 填滿剩餘空間
        layout.addStretch()

    # === 狀態方法 ===

    def show_idle(self) -> None:
        """顯示待機狀態（未觸發）"""
        self.result_header.setText("⚡ 結果局")
        self.result_status_dot.setText("● 未觸發")
        self.result_status_dot.setStyleSheet("color: #6b7280; background: transparent; border: none;")
        self.result_info_label.setText("<span style='color: #6b7280;'>等待觸發...</span>")
        self.result_impact_label.setText("")

        # 重置邊框為灰色
        self.setStyleSheet("""
            QFrame {
                background-color: #1e2128;
                border: 1px solid #2d3139;
                border-radius: 10px;
            }
        """)

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
                "sequence": [100, 200, 400, 800],
                "on_win": "RESET" | "ADVANCE",
                "on_loss": "ADVANCE" | "RESET"
            }
        """
        # 更新標題和狀態
        self.result_header.setText("⚡ 結果局 - 等待開獎")
        self.result_status_dot.setText("● 等待中")
        self.result_status_dot.setStyleSheet("color: #f59e0b; background: transparent; border: none;")

        # 邊框改為黃色
        self.setStyleSheet("""
            QFrame {
                background-color: #1e2128;
                border: 1px solid #f59e0b;
                border-radius: 10px;
            }
        """)

        # 方向映射
        direction_map = {
            "banker": ("莊", "#ef4444"),
            "player": ("閒", "#3b82f6"),
            "tie": ("和", "#10b981"),
            "B": ("莊", "#ef4444"),
            "P": ("閒", "#3b82f6"),
            "T": ("和", "#10b981"),
        }
        direction_text, direction_color = direction_map.get(
            data.get("direction", "").lower(), ("?", "#6b7280")
        )

        # 基本資訊
        amount = data.get("amount", 0)
        current_layer = data.get("current_layer", 0)
        total_layers = data.get("total_layers", 0)

        # 顯示下注資訊（大號金額）
        info_html = (
            f"<span style='color: #9ca3af;'>方向</span>  "
            f"<span style='color: {direction_color}; font-weight: bold; font-size: 11pt;'>{direction_text}</span><br>"
            f"<span style='color: #9ca3af;'>金額</span>  "
            f"<span style='color: #fbbf24; font-weight: bold; font-size: 12pt;'>{amount}</span> "
            f"<span style='color: #9ca3af;'>元</span><br>"
            f"<span style='color: #9ca3af;'>層數</span>  "
            f"<span style='color: #d1d5db;'>第 {current_layer}/{total_layers} 層</span>"
        )
        self.result_info_label.setText(info_html)

        # 計算影響預測
        sequence = data.get("sequence", [])
        on_win = data.get("on_win", "RESET")
        on_loss = data.get("on_loss", "ADVANCE")

        # 獲勝影響
        if on_win == "RESET":
            win_amount = sequence[0] if sequence else 0
            win_text = f"回第1層 ({win_amount}元)"
        else:
            win_next_layer = min(current_layer + 1, total_layers)
            win_amount = sequence[win_next_layer - 1] if win_next_layer <= len(sequence) else "?"
            win_text = f"進第{win_next_layer}層 ({win_amount}元)"

        # 失敗影響
        if on_loss == "ADVANCE":
            loss_next_layer = min(current_layer + 1, total_layers)
            loss_amount = sequence[loss_next_layer - 1] if loss_next_layer <= len(sequence) else "?"
            loss_text = f"進第{loss_next_layer}層 ({loss_amount}元)"
        else:
            loss_amount = sequence[0] if sequence else 0
            loss_text = f"回第1層 ({loss_amount}元)"

        # 顯示影響預測
        impact_html = (
            f"<span style='color: #6b7280;'>預測</span><br>"
            f"<span style='color: #10b981;'>✓ 贏</span>  {win_text}<br>"
            f"<span style='color: #ef4444;'>✗ 輸</span>  {loss_text}<br>"
            f"<span style='color: #6b7280;'>= 和</span>  維持({amount}元)"
        )
        self.result_impact_label.setText(impact_html)

    def update_result_outcome(self, outcome: str, pnl: float) -> None:
        """
        更新結果局的開獎結果

        Args:
            outcome: "win" | "loss" | "skip"
            pnl: 盈虧金額
        """
        # 結果映射
        outcome_map = {
            "win": ("✓ 獲勝", "#10b981"),
            "loss": ("✗ 失敗", "#ef4444"),
            "skip": ("= 和局", "#6b7280"),
        }
        outcome_text, outcome_color = outcome_map.get(
            outcome.lower(), ("?", "#6b7280")
        )

        # 更新標題
        pnl_color = "#10b981" if pnl > 0 else ("#ef4444" if pnl < 0 else "#6b7280")
        pnl_sign = "+" if pnl > 0 else ""

        self.result_header.setText(f"⚡ 結果局 - {outcome_text}")
        self.result_status_dot.setText(f"● {outcome_text}")
        self.result_status_dot.setStyleSheet(f"color: {outcome_color}; background: transparent; border: none; font-weight: bold;")

        # 邊框改為結果顏色
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1e2128;
                border: 2px solid {outcome_color};
                border-radius: 10px;
            }}
        """)

        # 顯示盈虧（大號顯示）
        pnl_html = (
            f"<span style='color: #9ca3af;'>本局盈虧</span><br>"
            f"<span style='color: {pnl_color}; font-weight: bold; font-size: 14pt;'>{pnl_sign}{pnl:.0f}</span> "
            f"<span style='color: #9ca3af;'>元</span>"
        )
        self.result_info_label.setText(pnl_html)

        # 2秒後恢復待機狀態
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self.show_idle)
