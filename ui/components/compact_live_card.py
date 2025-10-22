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
        self._build_ui()
        self.setMouseTracking(True)  # 啟用滑鼠追蹤

    def _build_ui(self) -> None:
        """構建 UI"""
        self.setFrameStyle(QFrame.StyledPanel)
        self._set_normal_style()

        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.LINE_SPACING_NORMAL)
        layout.setContentsMargins(
            Spacing.PADDING_LG,
            Spacing.PADDING_MD,
            Spacing.PADDING_LG,
            Spacing.PADDING_MD
        )

        # === 第1行：狀態標題 ===
        self.line1_label = QLabel(f"{Icons.IDLE} 等待啟動...")
        self.line1_label.setFont(FontStyle.title())
        self.line1_label.setStyleSheet(f"color: {Colors.TEXT_CRITICAL}; padding: 4px;")
        layout.addWidget(self.line1_label)

        # === 分隔線 ===
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(StyleSheet.divider())
        layout.addWidget(divider)

        # === 第2行：路單歷史 ===
        self.line2_label = QLabel("路單  等待數據...")
        self.line2_label.setFont(FontStyle.body())
        self.line2_label.setStyleSheet(f"color: {Colors.TEXT_NORMAL}; padding: 4px;")
        self.line2_label.setWordWrap(True)
        layout.addWidget(self.line2_label)

        # === 第3行：盈虧/下注資訊（使用水平佈局）===
        self.line3_container = QHBoxLayout()
        self.line3_container.setSpacing(Spacing.MARGIN_MD)

        self.pnl_label = QLabel(f"{Icons.MONEY} 等待數據...")
        self.pnl_label.setFont(FontStyle.body())
        self.pnl_label.setStyleSheet(f"color: {Colors.TEXT_NORMAL}; padding: 4px;")
        self.line3_container.addWidget(self.pnl_label)

        layout.addLayout(self.line3_container)

        # === 第4行：進度條 + 風控/預測 ===
        self.line4_container = QWidget()
        self.line4_layout = QVBoxLayout(self.line4_container)
        self.line4_layout.setContentsMargins(0, 0, 0, 0)
        self.line4_layout.setSpacing(4)

        # 層級進度條
        self.layer_progress = QProgressBar()
        self.layer_progress.setRange(0, 3)
        self.layer_progress.setValue(0)
        self.layer_progress.setTextVisible(True)
        self.layer_progress.setFormat("層級 0/3")
        self.layer_progress.setFixedHeight(20)
        self.layer_progress.setStyleSheet(StyleSheet.progress_bar())
        self.line4_layout.addWidget(self.layer_progress)

        # 風控/預測文字
        self.line4_label = QLabel("")
        self.line4_label.setFont(FontStyle.caption())
        self.line4_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; padding: 2px;")
        self.line4_layout.addWidget(self.line4_label)

        layout.addWidget(self.line4_container)

        layout.addStretch()

    def _set_normal_style(self) -> None:
        """設置正常樣式"""
        self.setStyleSheet(StyleSheet.card(
            bg_color=Colors.BG_PRIMARY,
            border_color=Colors.BORDER_DEFAULT,
            padding=Spacing.PADDING_LG,
            radius=Spacing.RADIUS_LG
        ))

    def _set_highlight_style(self, status: str = 'ready') -> None:
        """設置高亮樣式"""
        bg_color = Colors.status_bg(status)
        border_color = Colors.status_border(status)
        self.setStyleSheet(StyleSheet.card(
            bg_color=bg_color,
            border_color=border_color,
            padding=Spacing.PADDING_LG,
            radius=Spacing.RADIUS_LG
        ))

    # ============================================================
    # 滑鼠互動
    # ============================================================

    def enterEvent(self, event) -> None:
        """滑鼠懸停"""
        self.setStyleSheet(StyleSheet.card(
            bg_color=Colors.BG_HOVER,
            border_color=Colors.BORDER_HOVER,
            padding=Spacing.PADDING_LG,
            radius=Spacing.RADIUS_LG
        ))

    def leaveEvent(self, event) -> None:
        """滑鼠離開"""
        if self.current_phase == "ready_to_bet":
            self._set_highlight_style('ready')
        else:
            self._set_normal_style()

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
        self.line1_label.setText(f"{Icons.IDLE} 等待啟動...")
        self.line1_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; padding: 4px;")
        self.line2_label.setText("路單  等待數據...")
        self.pnl_label.setText(f"{Icons.MONEY} 等待數據...")
        self.layer_progress.setValue(0)
        self.layer_progress.setFormat("層級 0/3")
        self.line4_label.setText("")
        self._set_normal_style()

    def _show_waiting_trigger(self, snapshot: Dict[str, Any], table_id: str) -> None:
        """顯示：等待觸發"""
        # === 第1行：狀態 ===
        self.line1_label.setText(f"{Icons.WAITING} 等待觸發  round_???  {Icons.CHECK} 可下注")
        self.line1_label.setStyleSheet(f"color: {Colors.TEXT_CRITICAL}; padding: 4px;")

        # === 第2行：路單 ===
        history_html = self._format_history_html()
        self.line2_label.setText(f"路單  {history_html}  <span style='color: {Colors.TEXT_MUTED};'>[等待]</span>")

        # === 第3行：盈虧 ===
        table_pnl, global_pnl = self._get_pnl(snapshot, table_id)
        self._update_pnl_display(table_pnl, global_pnl)

        # === 第4行：層級進度條 ===
        current_layer, max_layer, stake = self._get_layer_info(snapshot, table_id)
        self._update_layer_progress(current_layer, max_layer)
        self.line4_label.setText(f"待命 {stake}元  {self._get_risk_status_html(snapshot, table_id)}")

        self._set_normal_style()

    def _show_ready_to_bet(self, snapshot: Dict[str, Any], table_id: str) -> None:
        """顯示：準備下注（高亮狀態）"""
        # === 第1行：狀態（高亮） ===
        self.line1_label.setText(f"{Icons.READY} 策略觸發！ round_???  {Icons.CHECK} 可下注 7秒")
        self.line1_label.setStyleSheet(f"color: {Colors.SUCCESS_100}; padding: 4px; font-weight: bold;")

        # === 第2行：路單 ===
        history_html = self._format_history_html()
        self.line2_label.setText(
            f"路單  {history_html}  "
            f"<b style='color: {Colors.SUCCESS_500};'>[下注]</b>  "
            f"<span style='color: {Colors.SUCCESS_300};'>← 已觸發！</span>"
        )

        # === 第3行：下注資訊 ===
        bet_info_html = self._get_bet_info_html(snapshot, table_id)
        self.pnl_label.setText(f"{Icons.READY} {bet_info_html}")

        # === 第4行：預測 ===
        current_layer, max_layer, stake = self._get_layer_info(snapshot, table_id)
        self._update_layer_progress(current_layer, max_layer)
        prediction_html = self._get_prediction_html(snapshot, table_id)
        self.line4_label.setText(f"預測  {prediction_html}")

        self._set_highlight_style('ready')

    def _show_waiting_result(self, snapshot: Dict[str, Any], table_id: str) -> None:
        """顯示：等待開獎"""
        # === 第1行：狀態 ===
        self.line1_label.setText(f"{Icons.WAITING} 等待開獎  round_???  🔒 已鎖定 (發牌中)")
        self.line1_label.setStyleSheet(f"color: {Colors.WARNING_100}; padding: 4px; font-weight: bold;")

        # === 第2行：路單 ===
        history_html = self._format_history_html()
        bet_direction = self._get_current_bet_direction(snapshot, table_id)
        self.line2_label.setText(
            f"路單  {history_html}  "
            f"<b style='color: {Colors.WARNING_500};'>[{bet_direction}]</b>  "
            f"<span style='color: {Colors.WARNING_300};'>← 已下注</span>"
        )

        # === 第3行：盈虧 ===
        table_pnl, global_pnl = self._get_pnl(snapshot, table_id)
        self._update_pnl_display(table_pnl, global_pnl)

        # === 第4行：預測 ===
        current_layer, max_layer, stake = self._get_layer_info(snapshot, table_id)
        self._update_layer_progress(current_layer, max_layer)
        prediction_html = self._get_prediction_html(snapshot, table_id)
        self.line4_label.setText(f"預測  {prediction_html}  <span style='color: {Colors.TEXT_MUTED};'>等待結果...</span>")

        self._set_highlight_style('waiting')

    # ============================================================
    # 輔助函數
    # ============================================================

    def _update_pnl_display(self, table_pnl: float, global_pnl: float) -> None:
        """更新盈虧顯示（使用等寬字體 + 色彩標籤）"""
        table_color = Colors.pnl_color(table_pnl)
        global_color = Colors.pnl_color(global_pnl)
        table_icon = Icons.UP if table_pnl > 0 else (Icons.DOWN if table_pnl < 0 else Icons.NEUTRAL)
        global_icon = Icons.UP if global_pnl > 0 else (Icons.DOWN if global_pnl < 0 else Icons.NEUTRAL)

        html = f"""
            {Icons.MONEY} 單桌 <b style='color: {table_color}; font-family: {FontStyle.FAMILY_MONO};'>{table_pnl:+.0f}</b> {table_icon}
            全局 <b style='color: {global_color}; font-family: {FontStyle.FAMILY_MONO};'>{global_pnl:+.0f}</b> {global_icon}
        """
        self.pnl_label.setText(html)

    def _update_layer_progress(self, current: int, total: int) -> None:
        """更新層級進度條"""
        self.layer_progress.setRange(0, total)
        self.layer_progress.setValue(current)
        percentage = (current / total * 100) if total > 0 else 0
        self.layer_progress.setFormat(f"層級 {current}/{total} ({percentage:.0f}%)")

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
        """
        self.history.append(winner)
        # 保持最多10個
        if len(self.history) > 10:
            self.history = self.history[-10:]
