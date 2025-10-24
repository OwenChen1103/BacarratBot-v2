# ui/components/compact_strategy_info_card.py
"""
精簡策略資訊卡片（升級版）
✨ 改進重點：
- 視覺層級優化（字體大小分級）
- 色彩系統統一
- 間距改善（增加呼吸空間）
- 數字使用等寬字體
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

# 導入設計系統
from ..design_system import FontStyle, Colors, Spacing, Icons, StyleSheet


class CompactStrategyInfoCard(QFrame):
    """精簡策略資訊卡片（升級版）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.strategy_data = None
        self.is_running = False
        self._build_ui()
        self._load_strategy()

    def _build_ui(self) -> None:
        """構建 UI"""
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet(StyleSheet.card(
            bg_color=Colors.BG_PRIMARY,
            border_color=Colors.BORDER_DEFAULT,
            padding=Spacing.PADDING_LG,
            radius=Spacing.RADIUS_LG
        ))

        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.LINE_SPACING_NORMAL)  # 從4px增加到8px
        layout.setContentsMargins(
            Spacing.PADDING_LG,
            Spacing.PADDING_MD,
            Spacing.PADDING_LG,
            Spacing.PADDING_MD
        )

        # === 第1行：策略名稱 + 狀態徽章 ===
        line1_container = QHBoxLayout()
        line1_container.setSpacing(Spacing.MARGIN_SM)

        self.strategy_title = QLabel(f"{Icons.STRATEGY} 策略資訊")
        self.strategy_title.setFont(FontStyle.title())
        self.strategy_title.setStyleSheet(f"color: {Colors.TEXT_CRITICAL}; padding: 4px;")
        line1_container.addWidget(self.strategy_title)

        line1_container.addStretch()

        self.status_badge = QLabel(f"{Icons.IDLE} 待機")
        self.status_badge.setFont(FontStyle.body_bold())
        self._update_status_badge(False)
        line1_container.addWidget(self.status_badge)

        layout.addLayout(line1_container)

        # === 分隔線 ===
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(StyleSheet.divider())
        layout.addWidget(divider)

        # === 第2行：觸發條件 + 序列 ===
        self.line2_label = QLabel("載入中...")
        self.line2_label.setFont(FontStyle.body())
        self.line2_label.setStyleSheet(f"color: {Colors.TEXT_NORMAL}; padding: 4px;")
        self.line2_label.setWordWrap(True)
        layout.addWidget(self.line2_label)

        # === 第3行：風控設定 ===
        self.line3_label = QLabel("")
        self.line3_label.setFont(FontStyle.body())
        self.line3_label.setStyleSheet(f"color: {Colors.TEXT_NORMAL}; padding: 4px;")
        self.line3_label.setWordWrap(True)
        layout.addWidget(self.line3_label)

        # === 第4行：今日統計 ===
        self.line4_label = QLabel("")
        self.line4_label.setFont(FontStyle.body())
        self.line4_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; padding: 4px;")
        layout.addWidget(self.line4_label)

        layout.addStretch()

    def _update_status_badge(self, is_running: bool) -> None:
        """更新狀態徽章"""
        if is_running:
            icon = Icons.RUNNING
            text = "運行中"
            bg_color = Colors.SUCCESS_900
            border_color = Colors.SUCCESS_500
            text_color = Colors.SUCCESS_50
        else:
            icon = Icons.IDLE
            text = "待機"
            bg_color = Colors.GRAY_700
            border_color = Colors.GRAY_500
            text_color = Colors.GRAY_300

        self.status_badge.setText(f"{icon} {text}")
        self.status_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                padding: 3px 10px;
                border-radius: {Spacing.RADIUS_SM}px;
                font-weight: bold;
            }}
        """)

    def _load_strategy(self) -> None:
        """載入策略配置"""
        strategy_dir = Path("configs/line_strategies")
        if not strategy_dir.exists():
            self.line2_label.setText(f"{Icons.ALERT} 未找到策略目錄")
            return

        try:
            strategy_files = list(strategy_dir.glob("*.json"))
            if not strategy_files:
                self.line2_label.setText(f"{Icons.ALERT} 未找到策略文件")
                return

            # 載入第一個策略
            with open(strategy_files[0], 'r', encoding='utf-8') as f:
                self.strategy_data = json.load(f)

            self._update_display()
        except Exception as e:
            self.line2_label.setText(f"{Icons.CROSS} 載入失敗: {e}")

    def _update_display(self) -> None:
        """更新顯示"""
        if not self.strategy_data:
            return

        strategy_key = self.strategy_data.get('strategy_key', '未知')
        entry = self.strategy_data.get('entry', {})
        staking = self.strategy_data.get('staking', {})
        risk = self.strategy_data.get('risk', {})

        # === 第1行：策略名稱 ===
        pattern = entry.get('pattern', '未設定')
        self.strategy_title.setText(f"{Icons.STRATEGY} 策略 {strategy_key}  {pattern}")

        # === 第2行：觸發條件 + 序列 + 進層規則 ===
        sequence = staking.get('sequence', [])
        sequence_text = ' → '.join([str(s) for s in sequence])  # 使用更清晰的箭頭

        advance_on = staking.get('advance_on', 'loss')
        advance_text = "輸進層" if advance_on == 'loss' else "贏進層"

        reset_on_win = staking.get('reset_on_win', False)
        reset_text = " / 贏重置" if reset_on_win else ""

        # 使用視覺分組而非 | 符號
        line2 = (
            f"<span style='color: {Colors.TEXT_IMPORTANT};'>觸發</span>  {pattern}     "
            f"<span style='color: {Colors.TEXT_IMPORTANT};'>序列</span>  {sequence_text}     "
            f"<span style='color: {Colors.TEXT_IMPORTANT};'>規則</span>  {advance_text}{reset_text}"
        )
        self.line2_label.setText(line2)

        # === 第3行：風控設定 ===
        levels = risk.get('levels', [])
        risk_parts = []
        for level in levels:
            scope = level.get('scope', '')
            take_profit = level.get('take_profit')
            stop_loss = level.get('stop_loss')

            scope_name = {
                'global_day': '全局',
                'table': '單桌',
                'table_strategy': '單策略'
            }.get(scope, scope)

            tp_text = f"+{int(take_profit)}" if take_profit else "無"
            sl_text = f"{int(stop_loss)}" if stop_loss else "無"
            risk_parts.append(f"{scope_name} <b style='color: {Colors.TEXT_IMPORTANT};'>{tp_text} / {sl_text}</b>")

        line3 = f"{Icons.RISK} 風控     " + "     ".join(risk_parts)  # 使用空格分組
        self.line3_label.setText(line3)

        # === 第4行：今日統計（暫時顯示佔位符）===
        line4 = f"{Icons.STATS} 今日  等待運行數據..."
        self.line4_label.setText(line4)

    def update_stats(self, snapshot: Dict[str, Any]) -> None:
        """
        更新統計數據

        Args:
            snapshot: orchestrator.snapshot() 的數據
        """
        if not snapshot:
            return

        performance = snapshot.get("performance", {})
        if not performance:
            # ✅ 即使沒有 performance 數據，也顯示初始狀態（避免一直顯示"等待運行數據..."）
            self.line4_label.setText(
                f"{Icons.STATS} 今日  "
                f"<span style='color: {Colors.TEXT_IMPORTANT};'>0</span> 觸發  "
                f"<span style='color: {Colors.TEXT_IMPORTANT};'>0</span> 進場  "
                f"<span style='color: {Colors.SUCCESS_500};'>0</span>勝 "
                f"<span style='color: {Colors.ERROR_500};'>0</span>負  "
                f"<b style='color: {Colors.TEXT_MUTED}; font-family: {FontStyle.FAMILY_MONO};'>0</b>元  "
                f"<span style='color: {Colors.TEXT_MUTED};'>(0%)</span>"
            )
            return

        triggers = performance.get("triggers", 0)
        entries = performance.get("entries", 0)
        wins = performance.get("wins", 0)
        losses = performance.get("losses", 0)
        total_pnl = performance.get("total_pnl", 0.0)

        # 計算勝率
        total_games = wins + losses
        win_rate = (wins / total_games * 100) if total_games > 0 else 0

        # 格式化盈虧顏色
        pnl_color = Colors.pnl_color(total_pnl)
        pnl_sign = "+" if total_pnl > 0 else ""

        # 使用等寬字體和顏色標籤顯示數字
        line4 = (
            f"{Icons.STATS} 今日  "
            f"<span style='color: {Colors.TEXT_IMPORTANT};'>{triggers}</span> 觸發  "
            f"<span style='color: {Colors.TEXT_IMPORTANT};'>{entries}</span> 進場  "
            f"<span style='color: {Colors.SUCCESS_500};'>{wins}</span>勝 "
            f"<span style='color: {Colors.ERROR_500};'>{losses}</span>負  "
            f"<b style='color: {pnl_color}; font-family: {FontStyle.FAMILY_MONO};'>{pnl_sign}{total_pnl:.0f}</b>元  "
            f"<span style='color: {Colors.TEXT_MUTED};'>({win_rate:.0f}%)</span>"
        )
        self.line4_label.setText(line4)

    def set_status(self, is_running: bool) -> None:
        """
        設定運行狀態

        Args:
            is_running: 是否運行中
        """
        self.is_running = is_running
        self._update_status_badge(is_running)

        # 更新卡片邊框顏色
        if is_running:
            border_color = Colors.SUCCESS_500
            bg_color = Colors.BG_PRIMARY
        else:
            border_color = Colors.BORDER_DEFAULT
            bg_color = Colors.BG_PRIMARY

        self.setStyleSheet(StyleSheet.card(
            bg_color=bg_color,
            border_color=border_color,
            padding=Spacing.PADDING_LG,
            radius=Spacing.RADIUS_LG
        ))
