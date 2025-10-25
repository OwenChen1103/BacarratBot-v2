# ui/components/compact_live_card.py
"""
精簡即時狀態卡片（升級版）
動態顯示當前遊戲狀態，根據階段自動切換顯示內容

✨ 改進重點：
- 視覺層級優化
- 盈虧使用等寬字體 + 色彩標籤
- 專業進度條顯示層級
- 狀態切換動畫
- 滑鼠懸停互動
"""

from typing import Optional, Dict, Any, List
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QWidget
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QFont

# 導入設計系統
from ..design_system import FontStyle, Colors, Spacing, Icons, StyleSheet


class CompactLiveCard(QFrame):
    """精簡即時狀態卡片（升級版）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_phase = "idle"
        self.history = []  # 路單歷史 (最多10個)
        self._opacity = 1.0
        self.last_result = None  # 保存最後一次結果
        self._build_ui()
        self.setMouseTracking(True)  # 啟用滑鼠追蹤

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

        # === 標題欄：狀態 ===
        header_container = QHBoxLayout()
        header_container.setSpacing(12)

        self.line1_label = QLabel("📊 即時狀態")
        self.line1_label.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        self.line1_label.setStyleSheet("color: #e5e7eb; background: transparent; border: none;")
        header_container.addWidget(self.line1_label)

        header_container.addStretch()

        # 狀態指示
        self.status_dot = QLabel("● 待機")
        self.status_dot.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        self.status_dot.setStyleSheet("color: #6b7280; background: transparent; border: none;")
        header_container.addWidget(self.status_dot)

        layout.addLayout(header_container)

        # === 分隔線 ===
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #2d3139; min-height: 1px; max-height: 1px; border: none;")
        layout.addWidget(separator)

        # === 路單歷史 ===
        self.line2_label = QLabel("路單  等待數據...")
        self.line2_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.line2_label.setStyleSheet("color: #d1d5db; background: transparent; border: none; padding: 2px 0px;")
        self.line2_label.setWordWrap(True)
        layout.addWidget(self.line2_label)

        # === 當前盈虧 ===
        self.pnl_label = QLabel("盈虧  等待數據...")
        self.pnl_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.pnl_label.setStyleSheet("color: #d1d5db; background: transparent; border: none; padding: 2px 0px;")
        layout.addWidget(self.pnl_label)

        # === 風控狀態 ===
        self.risk_label = QLabel("")
        self.risk_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.risk_label.setStyleSheet("color: #9ca3af; background: transparent; border: none; padding: 2px 0px;")
        layout.addWidget(self.risk_label)

        # === 分隔線 ===
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setStyleSheet("background-color: #2d3139; min-height: 1px; max-height: 1px; border: none;")
        layout.addWidget(separator2)

        # === 上手結果 + 預計下手（並排顯示）===
        result_row = QHBoxLayout()
        result_row.setContentsMargins(0, 0, 0, 0)
        result_row.setSpacing(12)

        self.result_label = QLabel("<span style='color: #6b7280;'>上手結果: 尚未觸發</span>")
        self.result_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.result_label.setStyleSheet("background: transparent; border: none; padding: 2px 0px;")
        self.result_label.setWordWrap(True)

        self.next_bet_label = QLabel("<span style='color: #6b7280;'>預計下手: --</span>")
        self.next_bet_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.next_bet_label.setStyleSheet("background: transparent; border: none; padding: 2px 0px;")
        self.next_bet_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.next_bet_label.setWordWrap(True)

        result_row.addWidget(self.result_label)
        result_row.addStretch()
        result_row.addWidget(self.next_bet_label)

        layout.addLayout(result_row)

        # 填滿整個卡片
        layout.addStretch()

    def _set_normal_style(self) -> None:
        """設置正常樣式（現代化設計 - 無需改變背景）"""
        pass

    def _set_highlight_style(self, status: str = 'ready') -> None:
        """設置高亮樣式（現代化設計 - 使用文字顏色突出）"""
        pass

    # ============================================================
    # 滑鼠互動（現代化設計 - 移除懸停效果）
    # ============================================================

    def enterEvent(self, event) -> None:
        """滑鼠懸停（無效果）"""
        pass

    def leaveEvent(self, event) -> None:
        """滑鼠離開（無效果）"""
        pass

    # ============================================================
    # 狀態更新
    # ============================================================

    def update_from_snapshot(self, snapshot: Dict[str, Any], table_id: str = "main") -> None:
        """
        從 orchestrator.snapshot() 更新顯示

        Args:
            snapshot: orchestrator.snapshot() 的數據
            table_id: 桌號（預設 "main"）
        """
        if not snapshot:
            return

        old_phase = self.current_phase
        new_phase = self._detect_phase(snapshot, table_id)

        # 階段切換動畫
        if old_phase != new_phase:
            self._animate_phase_transition(old_phase, new_phase)

        self.current_phase = new_phase

        # 根據階段顯示對應內容
        if new_phase == "waiting_trigger":
            self._show_waiting_trigger(snapshot, table_id)
        elif new_phase == "ready_to_bet":
            self._show_ready_to_bet(snapshot, table_id)
        elif new_phase == "waiting_result":
            self._show_waiting_result(snapshot, table_id)
        elif new_phase == "idle":
            self._show_idle()

    def _detect_phase(self, snapshot: Dict[str, Any], table_id: str) -> str:
        """
        檢測當前階段

        Returns:
            "idle" | "waiting_trigger" | "ready_to_bet" | "waiting_result"
        """
        lines = snapshot.get("lines", [])
        if not lines:
            return "idle"

        table_lines = [line for line in lines if line.get("table") == table_id]
        if not table_lines:
            return "idle"

        for line in table_lines:
            phase = line.get("phase", "idle")
            if phase == "waiting":
                return "waiting_result"
            elif phase == "armed":
                return "ready_to_bet"

        return "waiting_trigger"

    def _animate_phase_transition(self, from_phase: str, to_phase: str) -> None:
        """階段切換動畫（淡入淡出）"""
        # 這裡可以添加更複雜的動畫效果
        pass

    # ============================================================
    # 不同階段的顯示
    # ============================================================

    def _show_idle(self) -> None:
        """顯示：待機狀態"""
        self.line1_label.setText("📊 即時狀態")
        self.status_dot.setText("● 待機")
        self.status_dot.setStyleSheet("color: #6b7280; background: transparent; border: none;")

        # 路單
        if self.history:
            history_html = self._format_history_html()
            self.line2_label.setText(f"<span style='color: #9ca3af;'>路單</span>  {history_html}")
        else:
            self.line2_label.setText("<span style='color: #9ca3af;'>路單</span>  等待數據...")

        # 盈虧
        self.pnl_label.setText("<span style='color: #9ca3af;'>盈虧</span>  等待數據...")
        self.risk_label.setText("")

        # 上手結果
        if not self.last_result:
            self.result_label.setText("<span style='color: #6b7280;'>上手結果: 尚未觸發</span>")

        # 預計下手 - 顯示預設狀態
        self.next_bet_label.setText("<span style='color: #6b7280;'>預計下手: --</span>")

        self._set_normal_style()

    def _show_waiting_trigger(self, snapshot: Dict[str, Any], table_id: str) -> None:
        """顯示：等待觸發"""
        self.line1_label.setText("📊 即時狀態")
        self.status_dot.setText("● 等待觸發")
        self.status_dot.setStyleSheet("color: #3b82f6; background: transparent; border: none;")

        # 路單
        history_html = self._format_history_html()
        self.line2_label.setText(f"<span style='color: #9ca3af;'>路單</span>  {history_html}")

        # 盈虧
        table_pnl, global_pnl = self._get_pnl(snapshot, table_id)
        self._update_pnl_display(table_pnl, global_pnl)

        # 風控狀態
        self._update_risk_display(snapshot, table_id)

        # 預計下手
        self._update_next_bet_display(snapshot, table_id)

        self._set_normal_style()

    def _show_ready_to_bet(self, snapshot: Dict[str, Any], table_id: str) -> None:
        """顯示：準備下注（高亮狀態）"""
        self.line1_label.setText("📊 即時狀態")
        self.status_dot.setText("● 準備下注")
        self.status_dot.setStyleSheet("color: #10b981; background: transparent; border: none; font-weight: bold;")

        # 路單
        history_html = self._format_history_html()
        self.line2_label.setText(
            f"<span style='color: #9ca3af;'>路單</span>  {history_html}  "
            f"<span style='color: #10b981; font-weight: bold;'>[觸發]</span>"
        )

        # 下注資訊
        bet_info_html = self._get_bet_info_html(snapshot, table_id)
        self.pnl_label.setText(f"<span style='color: #9ca3af;'>下注</span>  {bet_info_html}")

        # 風控狀態
        self._update_risk_display(snapshot, table_id)

        # 預計下手 - 在準備下注階段顯示即將下注的資訊
        self._update_next_bet_display(snapshot, table_id)

        self._set_highlight_style('ready')

    def _show_waiting_result(self, snapshot: Dict[str, Any], table_id: str) -> None:
        """顯示：等待開獎"""
        self.line1_label.setText("📊 即時狀態")
        self.status_dot.setText("● 等待開獎")
        self.status_dot.setStyleSheet("color: #f59e0b; background: transparent; border: none; font-weight: bold;")

        # 路單
        history_html = self._format_history_html()
        bet_direction = self._get_current_bet_direction(snapshot, table_id)
        self.line2_label.setText(
            f"<span style='color: #9ca3af;'>路單</span>  {history_html}  "
            f"<span style='color: #f59e0b; font-weight: bold;'>[下注{bet_direction}]</span>"
        )

        # 盈虧
        table_pnl, global_pnl = self._get_pnl(snapshot, table_id)
        self._update_pnl_display(table_pnl, global_pnl)

        # 風控狀態
        self._update_risk_display(snapshot, table_id)

        # 預計下手 - 在等待開獎階段也顯示
        self._update_next_bet_display(snapshot, table_id)

        self._set_highlight_style('waiting')

    # ============================================================
    # 輔助函數
    # ============================================================

    def _update_pnl_display(self, table_pnl: float, global_pnl: float) -> None:
        """更新盈虧顯示"""
        # 顏色映射
        table_color = "#10b981" if table_pnl > 0 else ("#ef4444" if table_pnl < 0 else "#6b7280")
        global_color = "#10b981" if global_pnl > 0 else ("#ef4444" if global_pnl < 0 else "#6b7280")

        table_sign = "+" if table_pnl > 0 else ""
        global_sign = "+" if global_pnl > 0 else ""

        html = (
            f"<span style='color: #9ca3af;'>盈虧</span>  "
            f"單桌 <span style='color: {table_color}; font-weight: bold;'>{table_sign}{table_pnl:.0f}</span> · "
            f"全局 <span style='color: {global_color}; font-weight: bold;'>{global_sign}{global_pnl:.0f}</span>"
        )
        self.pnl_label.setText(html)

    def _update_risk_display(self, snapshot: Dict[str, Any], table_id: str = "main") -> None:
        """更新風控顯示（止盈止損距離）"""
        _ = table_id  # 保留參數以保持接口一致
        risk = snapshot.get("risk", {})
        global_risk = risk.get("global_day", {})

        pnl = global_risk.get("pnl", 0.0)
        take_profit = global_risk.get("take_profit", 5000.0)
        stop_loss = global_risk.get("stop_loss", -2000.0)

        if pnl > 0:
            # 盈利狀態，顯示距離止盈
            distance = take_profit - pnl
            percentage = (pnl / take_profit * 100) if take_profit > 0 else 0
            risk_html = (
                f"<span style='color: #6b7280;'>風控</span>  "
                f"距止盈 <span style='color: #10b981; font-weight: bold;'>{distance:.0f}</span> "
                f"<span style='color: #6b7280;'>({percentage:.0f}%)</span>"
            )
        else:
            # 虧損狀態，顯示距離止損
            distance = abs(pnl - stop_loss)
            percentage = (abs(pnl) / abs(stop_loss) * 100) if stop_loss < 0 else 0
            risk_html = (
                f"<span style='color: #6b7280;'>風控</span>  "
                f"距止損 <span style='color: #ef4444; font-weight: bold;'>{distance:.0f}</span> "
                f"<span style='color: #6b7280;'>({percentage:.0f}%)</span>"
            )

        self.risk_label.setText(risk_html)

    def _update_next_bet_display(self, snapshot: Dict[str, Any], table_id: str = "main") -> None:
        """更新預計下手顯示"""
        lines = snapshot.get("lines", [])
        table_lines = [line for line in lines if line.get("table") == table_id]

        if not table_lines:
            self.next_bet_label.setText("<span style='color: #6b7280;'>預計下手: --</span>")
            return

        line = table_lines[0]
        next_stake = abs(line.get("next_stake", 0.0))
        direction = line.get("direction", "")

        # 檢查是否為反向層
        is_reverse = (line.get("next_stake", 0.0) < 0)

        if next_stake <= 0:
            self.next_bet_label.setText("<span style='color: #6b7280;'>預計下手: --</span>")
            return

        # 方向映射和顏色
        direction_map = {
            "banker": ("B", Colors.ERROR_500),
            "player": ("P", Colors.INFO_500),
            "tie": ("T", Colors.SUCCESS_500)
        }
        direction_text, direction_color = direction_map.get(direction, ("?", "#6b7280"))

        # 如果是反向層，反轉方向
        if is_reverse:
            opposite_map = {"B": ("P", Colors.INFO_500), "P": ("B", Colors.ERROR_500), "T": ("T", Colors.SUCCESS_500)}
            direction_text, direction_color = opposite_map.get(direction_text, (direction_text, direction_color))

        # 反向標記
        reverse_indicator = ""
        if is_reverse:
            reverse_indicator = "<span style='color: #f59e0b; font-size: 8pt;'>⮌</span>"

        next_bet_html = (
            f"<span style='color: #6b7280;'>預計下手: </span>"
            f"<span style='color: {direction_color}; font-weight: bold;'>{direction_text}</span> "
            f"<span style='color: #d1d5db; font-weight: bold;'>{next_stake:.0f}元</span>{reverse_indicator}"
        )

        self.next_bet_label.setText(next_bet_html)

    def _update_layer_info(self, current: int, total: int, risk_info: str = "") -> None:
        """更新層級資訊（簡化顯示）- 已不使用"""
        pass

    def _format_history_html(self) -> str:
        """格式化路單歷史（HTML）"""
        if not self.history:
            return "<span style='color: #6b7280;'>無歷史</span>"

        # 最多顯示10個
        recent = self.history[-10:]
        html_parts = []
        for winner in recent:
            if winner == "B":
                html_parts.append(f"<b style='color: {Colors.ERROR_500};'>B</b>")
            elif winner == "P":
                html_parts.append(f"<b style='color: {Colors.INFO_500};'>P</b>")
            elif winner == "T":
                html_parts.append(f"<b style='color: {Colors.SUCCESS_500};'>T</b>")
            else:
                html_parts.append(f"<span style='color: {Colors.GRAY_400};'>{winner}</span>")

        return " ".join(html_parts)

    def _get_pnl(self, snapshot: Dict[str, Any], table_id: str) -> tuple[float, float]:
        """獲取盈虧數據"""
        risk = snapshot.get("risk", {})
        table_risk = risk.get(f"table:{table_id}", {})
        global_risk = risk.get("global_day", {})

        table_pnl = table_risk.get("pnl", 0.0)
        global_pnl = global_risk.get("pnl", 0.0)

        return table_pnl, global_pnl

    def _get_layer_info(self, snapshot: Dict[str, Any], table_id: str) -> tuple[int, int, float]:
        """獲取層級資訊"""
        lines = snapshot.get("lines", [])
        table_lines = [line for line in lines if line.get("table") == table_id]

        if table_lines:
            line = table_lines[0]
            current = line.get("current_layer", 0)
            max_layer = line.get("max_layer", 3)
            stake = line.get("stake", 0.0)
            return current, max_layer, stake

        return 0, 3, 0.0

    def _get_bet_info_html(self, snapshot: Dict[str, Any], table_id: str) -> str:
        """獲取下注資訊HTML"""
        lines = snapshot.get("lines", [])
        table_lines = [line for line in lines if line.get("table") == table_id and line.get("phase") == "armed"]

        if table_lines:
            line = table_lines[0]
            direction = line.get("direction", "?")
            amount = line.get("stake", 0.0)
            current_layer = line.get("current_layer", 1)
            max_layer = line.get("max_layer", 3)

            direction_map = {"banker": f"<b style='color: {Colors.ERROR_500};'>莊家 B</b>",
                             "player": f"<b style='color: {Colors.INFO_500};'>玩家 P</b>",
                             "tie": f"<b style='color: {Colors.SUCCESS_500};'>和局 T</b>"}
            direction_text = direction_map.get(direction, direction)

            return f"{direction_text} <b style='font-family: {FontStyle.FAMILY_MONO}; color: {Colors.TEXT_CRITICAL};'>{amount:.0f}元</b>"

        return "等待下注資訊..."

    def _get_prediction_html(self, snapshot: Dict[str, Any], table_id: str) -> str:
        """獲取預測HTML"""
        lines = snapshot.get("lines", [])
        table_lines = [line for line in lines if line.get("table") == table_id]

        if table_lines:
            line = table_lines[0]
            current_layer = line.get("current_layer", 1)
            stake = line.get("stake", 0.0)

            win_html = f"{Icons.WIN} 贏 <b style='color: {Colors.SUCCESS_500}; font-family: {FontStyle.FAMILY_MONO};'>+{stake:.0f}</b> → 回層1"
            loss_html = f"{Icons.LOSS} 輸 <b style='color: {Colors.ERROR_500}; font-family: {FontStyle.FAMILY_MONO};'>-{stake:.0f}</b> → 進層{current_layer + 1}"

            return f"{win_html}  |  {loss_html}"

        return ""

    def _get_risk_status_html(self, snapshot: Dict[str, Any], table_id: str) -> str:
        """獲取風控狀態HTML"""
        risk = snapshot.get("risk", {})
        global_risk = risk.get("global_day", {})

        pnl = global_risk.get("pnl", 0.0)
        take_profit = global_risk.get("take_profit", 5000.0)
        stop_loss = global_risk.get("stop_loss", -2000.0)

        if pnl > 0:
            distance = take_profit - pnl
            percentage = (pnl / take_profit * 100) if take_profit > 0 else 0
            return f"<span style='color: {Colors.SUCCESS_500};'>距止盈 {distance:.0f} ({percentage:.0f}%)</span>"
        else:
            distance = abs(pnl - stop_loss)
            percentage = (abs(pnl) / abs(stop_loss) * 100) if stop_loss < 0 else 0
            return f"<span style='color: {Colors.ERROR_500};'>距止損 {distance:.0f} ({percentage:.0f}%)</span>"

    def _get_current_bet_direction(self, snapshot: Dict[str, Any], table_id: str) -> str:
        """獲取當前下注方向"""
        lines = snapshot.get("lines", [])
        table_lines = [line for line in lines if line.get("table") == table_id]

        if table_lines:
            direction = table_lines[0].get("direction", "?")
            direction_map = {"banker": "莊B", "player": "閒P", "tie": "和T"}
            return direction_map.get(direction, "?")

        return "?"

    # ============================================================
    # 公開方法
    # ============================================================

    def add_history(self, winner: str) -> None:
        """
        添加路單歷史

        Args:
            winner: 開獎結果 (B/P/T)

        Note:
            顯示更新由 update_from_snapshot() 負責（每秒調用一次）
            這樣可以保持狀態一致性，避免手動更新導致的顯示問題
        """
        self.history.append(winner)
        # 保持最多10個
        if len(self.history) > 10:
            self.history = self.history[-10:]

    def reset_result_to_waiting(self) -> None:
        """重置結果區域為等待狀態（當新一輪開始時）"""
        self.result_label.setText("<span style='color: #6b7280;'>上手結果: 等待觸發...</span>")
        # 不清除 last_result，保留歷史記錄

    def update_last_result(self, bet_direction: str, result: str, pnl: float) -> None:
        """更新最後一次結果（永久顯示在結果區域）"""
        print(f"[CompactLiveCard] update_last_result called: bet={bet_direction}, result={result}, pnl={pnl}")

        direction_map = {"banker": "莊", "player": "閒", "tie": "和"}
        bet_text = direction_map.get(bet_direction, bet_direction)
        result_text = direction_map.get(result, result)

        # 判斷輸贏
        if pnl > 0:
            outcome = "✓"
            color = "#10b981"
        elif pnl < 0:
            outcome = "✗"
            color = "#ef4444"
        else:
            outcome = "="
            color = "#6b7280"

        # 格式化結果顯示（簡潔版）
        result_html = (
            f"<span style='color: #6b7280;'>上手結果: </span>"
            f"<span style='color: #d1d5db;'>{bet_text} → {result_text}</span> "
            f"<span style='color: {color}; font-weight: bold;'>{outcome} {pnl:+.0f}</span>"
        )

        print(f"[CompactLiveCard] Setting result_label text: {result_html}")
        self.result_label.setText(result_html)
        self.last_result = {"bet": bet_direction, "result": result, "pnl": pnl}
        print(f"[CompactLiveCard] result_label visibility: {self.result_label.isVisible()}")
