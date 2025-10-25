# ui/components/result_round_card.py
"""
結果局卡片組件
顯示已下注、等待開獎的局，讓使用者清楚知道當前局會影響輸贏
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont
from typing import Dict, Any, Optional


class ResultRoundCard(QFrame):
    """結果局卡片 - 顯示已下注、等待開獎的局"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pending_data: Optional[Dict[str, Any]] = None
        self._animation: Optional[QPropertyAnimation] = None
        self._build_ui()
        self.setVisible(False)  # 預設隱藏

    def _build_ui(self) -> None:
        """構建 UI"""
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 2px solid #fbbf24;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # === 標題行 ===
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.header_label = QLabel("⏳ 結果局 - 等待開獎")
        self.header_label.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        self.header_label.setStyleSheet("color: #fbbf24;")
        self.header_label_default = "⏳ 結果局 - 等待開獎"  # 儲存預設標題
        header_layout.addWidget(self.header_label)

        header_layout.addStretch()

        # 狀態指示燈 (動畫閃爍)
        self.status_dot = QLabel("●")
        self.status_dot.setFont(QFont("Arial", 14))
        self.status_dot.setStyleSheet("color: #fbbf24;")
        header_layout.addWidget(self.status_dot)

        layout.addLayout(header_layout)

        # === 進度條 (視覺效果) ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 無限循環模式
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #374151;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #fbbf24, stop:0.5 #f59e0b, stop:1 #fbbf24);
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # === 詳細資訊卡片 ===
        self.info_label = QLabel()
        self.info_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.info_label.setStyleSheet("""
            QLabel {
                color: #e5e7eb;
                background-color: #111827;
                border: 1px solid #4b5563;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        # === 分隔線 ===
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #4b5563; max-height: 1px;")
        layout.addWidget(separator)

        # === 影響預測卡片 ===
        impact_header = QLabel("📊 本局結果將影響:")
        impact_header.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        impact_header.setStyleSheet("color: #d1d5db;")
        layout.addWidget(impact_header)

        self.impact_label = QLabel()
        self.impact_label.setFont(QFont("Microsoft YaHei UI", 8))
        self.impact_label.setStyleSheet("""
            QLabel {
                color: #d1d5db;
                background-color: #0f172a;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        self.impact_label.setWordWrap(True)
        layout.addWidget(self.impact_label)

    def show_pending_bet(self, data: Dict[str, Any]) -> None:
        """
        顯示待處理的下注

        Args:
            data: {
                "strategy": "martingale_bpp",
                "direction": "banker",  # "banker" | "player" | "tie"
                "amount": 200,
                "current_layer": 2,
                "total_layers": 4,
                "round_id": "detect-1234567890",
                "sequence": [100, 200, 400, 800],
                "on_win": "RESET",  # "RESET" | "ADVANCE"
                "on_loss": "ADVANCE"  # "RESET" | "ADVANCE"
            }
        """
        self.pending_data = data

        # ✅ 方向映射 - 支持所有格式
        direction_map = {
            "banker": ("🔴 莊家", "#ef4444"),
            "player": ("🔵 閒家", "#3b82f6"),
            "tie": ("🟢 和局", "#10b981"),
            "B": ("🔴 莊家", "#ef4444"),
            "P": ("🔵 閒家", "#3b82f6"),
            "T": ("🟢 和局", "#10b981"),
            "b": ("🔴 莊家", "#ef4444"),
            "p": ("🔵 閒家", "#3b82f6"),
            "t": ("🟢 和局", "#10b981"),
        }
        direction_raw = data.get("direction", "")
        direction_text, direction_color = direction_map.get(
            direction_raw, ("未知", "#ffffff")
        )

        # 基本資訊
        strategy = data.get("strategy", "未知")
        amount = data.get("amount", 0)
        current_layer = data.get("current_layer", 0)
        total_layers = data.get("total_layers", 0)
        round_id = data.get("round_id", "N/A")
        is_reverse = data.get("is_reverse", False)
        status = data.get("status", "betting")  # ✅ 獲取狀態 (pre_triggered | betting)

        # ✅ 根據狀態調整標題
        if status == "pre_triggered":
            self.header_label.setText("🎯 策略已觸發 - 等待下注時機")
            self.header_label.setStyleSheet("color: #3b82f6;")  # 藍色表示預觸發
        else:
            self.header_label.setText(self.header_label_default)
            self.header_label.setStyleSheet("color: #fbbf24;")  # 黃色表示已下注

        # 反向標記
        reverse_tag = ""
        if is_reverse:
            reverse_tag = " <span style='color:#f59e0b;font-weight:bold;'>(反向)</span>"

        # ✅ 根據狀態調整顯示文字
        status_text = ""
        if status == "pre_triggered":
            status_text = "<span style='color:#3b82f6;font-size:9px;'>(預觸發 - 尚未下注)</span>"

        info_text = (
            f"<b>策略:</b> {strategy} {status_text}<br>"
            f"<b>方向:</b> <span style='color:{direction_color};font-weight:bold;'>{direction_text}</span>{reverse_tag}<br>"
            f"<b>金額:</b> {amount} 元<br>"
            f"<b>層數:</b> 第 {current_layer}/{total_layers} 層<br>"
            f"<b>局號:</b> <span style='color:#9ca3af;font-size:8px;'>{round_id}</span>"
        )
        self.info_label.setText(info_text)

        # 計算影響
        sequence = data.get("sequence", [])
        on_win = data.get("on_win", "RESET")
        on_loss = data.get("on_loss", "ADVANCE")

        # 獲勝影響
        if on_win == "RESET":
            win_next_layer = 1
            win_amount = sequence[0] if sequence else 0
            win_impact = f"重置到第1層 (下注 <b>{win_amount}</b> 元)"
        else:  # ADVANCE
            win_next_layer = min(current_layer + 1, total_layers)
            win_amount = sequence[win_next_layer - 1] if win_next_layer <= len(sequence) else "上限"
            win_impact = f"前進到第{win_next_layer}層 (下注 <b>{win_amount}</b> 元)"

        # 失敗影響
        if on_loss == "ADVANCE":
            loss_next_layer = min(current_layer + 1, total_layers)
            loss_amount = sequence[loss_next_layer - 1] if loss_next_layer <= len(sequence) else "上限"
            loss_impact = f"前進到第{loss_next_layer}層 (下注 <b>{loss_amount}</b> 元)"
        else:  # RESET
            loss_next_layer = 1
            loss_amount = sequence[0] if sequence else 0
            loss_impact = f"重置到第1層 (下注 <b>{loss_amount}</b> 元)"

        impact_text = (
            f"<span style='color:#10b981;'>✅ 獲勝</span> → {win_impact}<br>"
            f"<span style='color:#ef4444;'>❌ 失敗</span> → {loss_impact}<br>"
            f"<span style='color:#6b7280;'>➖ 和局</span> → 層數不變 (繼續下注 <b>{amount}</b> 元)"
        )
        self.impact_label.setText(impact_text)

        # 顯示卡片
        self.setVisible(True)

        # 啟動閃爍動畫
        self._start_blink_animation()

    def _start_blink_animation(self) -> None:
        """啟動狀態指示燈閃爍動畫"""
        timer = QTimer(self)
        timer.timeout.connect(self._toggle_dot_opacity)
        timer.start(800)  # 每800ms切換一次
        self._blink_timer = timer
        self._dot_visible = True

    def _toggle_dot_opacity(self) -> None:
        """切換指示燈顯示/隱藏"""
        if not hasattr(self, '_dot_visible'):
            self._dot_visible = True

        self._dot_visible = not self._dot_visible
        if self._dot_visible:
            self.status_dot.setStyleSheet("color: #fbbf24;")
        else:
            self.status_dot.setStyleSheet("color: transparent;")

    def update_outcome(self, outcome: str, pnl: float) -> None:
        """
        更新開獎結果 (短暫顯示後隱藏)

        Args:
            outcome: "win" | "loss" | "skip"
            pnl: 盈虧金額
        """
        # 停止閃爍動畫
        if hasattr(self, '_blink_timer'):
            self._blink_timer.stop()

        # 結果映射
        outcome_map = {
            "win": ("🎉 獲勝", "#10b981", "恭喜！"),
            "loss": ("😞 失敗", "#ef4444", "下次加油"),
            "skip": ("➖ 跳過 (和局)", "#6b7280", "退回本金"),
        }
        outcome_text, outcome_color, outcome_hint = outcome_map.get(
            outcome.lower(), ("未知", "#ffffff", "")
        )

        # 更新標題
        pnl_sign = "+" if pnl > 0 else ""
        self.header_label.setText(
            f"{outcome_text} | 盈虧: <span style='color:{outcome_color};'>{pnl_sign}{pnl:.0f}</span> 元"
        )
        self.header_label.setStyleSheet(f"color: {outcome_color}; font-weight: bold;")

        # 固定狀態指示燈顏色
        self.status_dot.setStyleSheet(f"color: {outcome_color};")

        # 停止進度條動畫
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #374151;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {outcome_color};
                border-radius: 2px;
            }}
        """)

        # 邊框變色
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1f2937;
                border: 2px solid {outcome_color};
                border-radius: 8px;
                padding: 12px;
            }}
        """)

        # 更新提示文字
        self.info_label.setText(
            f"<div style='text-align:center; padding:20px;'>"
            f"<span style='font-size:24px;'>{outcome_text}</span><br>"
            f"<span style='color:#9ca3af; font-size:10px;'>{outcome_hint}</span>"
            f"</div>"
        )

        # 3秒後隱藏
        QTimer.singleShot(3000, self.hide_card)

    def hide_card(self) -> None:
        """隱藏卡片並重置狀態"""
        self.pending_data = None
        self.setVisible(False)

        # 停止動畫
        if hasattr(self, '_blink_timer'):
            self._blink_timer.stop()

        # 恢復原始樣式
        self.setStyleSheet("""
            QFrame {
                background-color: #1f2937;
                border: 2px solid #fbbf24;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        self.header_label.setText("⏳ 結果局 - 等待開獎")
        self.header_label.setStyleSheet("color: #fbbf24;")
        self.status_dot.setStyleSheet("color: #fbbf24;")

        # 重置進度條
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #374151;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #fbbf24, stop:0.5 #f59e0b, stop:1 #fbbf24);
                border-radius: 2px;
            }
        """)
