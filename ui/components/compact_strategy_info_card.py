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
        layout.setSpacing(12)  # 增加間距，讓內容呼吸
        layout.setContentsMargins(16, 14, 16, 14)

        # === 標題欄：策略名稱 + 狀態徽章 ===
        header_container = QHBoxLayout()
        header_container.setSpacing(12)

        self.strategy_title = QLabel(f"{Icons.STRATEGY} 策略資訊")
        self.strategy_title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        self.strategy_title.setStyleSheet("color: #e5e7eb; background: transparent; border: none;")
        header_container.addWidget(self.strategy_title)

        header_container.addStretch()

        self.status_badge = QLabel(f"{Icons.IDLE} 待機")
        self.status_badge.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        self._update_status_badge(False)
        header_container.addWidget(self.status_badge)

        layout.addLayout(header_container)

        # === 分隔線 ===
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #2d3139; min-height: 1px; max-height: 1px; border: none;")
        layout.addWidget(separator)

        # === 內容區域 ===
        # 觸發條件
        self.line2_label = QLabel("載入中...")
        self.line2_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.line2_label.setStyleSheet("color: #d1d5db; background: transparent; border: none; padding: 2px 0px;")
        self.line2_label.setWordWrap(True)
        layout.addWidget(self.line2_label)

        # 下注序列
        self.line3_label = QLabel("")
        self.line3_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.line3_label.setStyleSheet("color: #d1d5db; background: transparent; border: none; padding: 2px 0px;")
        self.line3_label.setWordWrap(True)
        layout.addWidget(self.line3_label)

        # 風控設定
        self.line4_label = QLabel("")
        self.line4_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.line4_label.setStyleSheet("color: #d1d5db; background: transparent; border: none; padding: 2px 0px;")
        layout.addWidget(self.line4_label)

        # === 分隔線 ===
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setStyleSheet("background-color: #2d3139; min-height: 1px; max-height: 1px; border: none;")
        layout.addWidget(separator2)

        # === 底部統計 ===
        self.line5_label = QLabel("")
        self.line5_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.line5_label.setStyleSheet("color: #9ca3af; background: transparent; border: none; padding: 2px 0px;")
        layout.addWidget(self.line5_label)

        # 填滿剩餘空間
        layout.addStretch()

    def _update_status_badge(self, is_running: bool) -> None:
        """更新狀態徽章 - 扁平現代設計"""
        if is_running:
            text = "● 運行中"
            text_color = "#10b981"
        else:
            text = "● 待機"
            text_color = "#6b7280"

        self.status_badge.setText(text)
        self.status_badge.setStyleSheet(f"""
            QLabel {{
                background-color: transparent;
                color: {text_color};
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
            }}
        """)

    def _parse_pattern_to_chinese(self, pattern: str) -> str:
        """
        將策略 pattern 轉換成簡潔的中文
        例如：
        - "PB then bet P" -> "見 閒莊 → 下 閒"
        - "BBB then bet P" -> "見 莊莊莊 → 下 閒"
        """
        if not pattern or pattern == '未知':
            return "觸發: 未設定"

        # 字母對應中文（簡潔版，不用 HTML）
        char_map = {
            'P': '閒',
            'B': '莊',
            'T': '和'
        }

        try:
            # 分割 "XXX then bet Y" 格式
            if 'then bet' in pattern.lower():
                parts = pattern.split('then bet')
                trigger_part = parts[0].strip().upper()
                bet_part = parts[1].strip().upper()

                # 轉換觸發序列
                trigger_cn = ''.join([char_map.get(c, c) for c in trigger_part])

                # 轉換下注方向，帶顏色
                bet_char = bet_part[0] if bet_part else '?'
                bet_cn = char_map.get(bet_char, bet_char)

                # 顏色映射
                if bet_char == 'P':
                    color = '#3b82f6'
                elif bet_char == 'B':
                    color = '#ef4444'
                else:
                    color = '#10b981'

                return f"見 {trigger_cn} → 下 <span style='color: {color}; font-weight: bold;'>{bet_cn}</span>"
            else:
                # 如果格式不符，直接顯示原文
                return f"觸發: {pattern}"

        except Exception as e:
            return f"觸發: {pattern}"

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
        """更新顯示 - 現代設計感版本"""
        if not self.strategy_data:
            return

        strategy_key = self.strategy_data.get('strategy_key', '未知')
        entry = self.strategy_data.get('entry', {})
        staking = self.strategy_data.get('staking', {})
        risk = self.strategy_data.get('risk', {})

        # === 標題：策略名稱 ===
        pattern = entry.get('pattern', '未設定')
        self.strategy_title.setText(f"{Icons.STRATEGY} {pattern}")

        # === 觸發條件 ===
        trigger_desc = self._parse_pattern_to_chinese(pattern)
        self.line2_label.setText(f"<span style='color: #9ca3af;'>觸發</span>  {trigger_desc}")

        # === 下注序列 ===
        sequence = staking.get('sequence', [])
        if len(sequence) > 0:
            # 金額用大號字體，醒目顯示
            seq_parts = []
            for i, amount in enumerate(sequence):
                if i == 0:
                    # 第一層用白色
                    seq_parts.append(f"<span style='color: #e5e7eb; font-weight: bold; font-size: 11pt;'>{amount}</span>")
                else:
                    # 後續層用黃色
                    seq_parts.append(f"<span style='color: #fbbf24; font-weight: bold; font-size: 11pt;'>{amount}</span>")

            seq_display = ' → '.join(seq_parts)
            advance_on = staking.get('advance_on', 'loss')

            if advance_on == 'loss':
                rule = "<span style='color: #ef4444;'>輸進</span>"
            else:
                rule = "<span style='color: #10b981;'>贏進</span>"

            line3 = f"<span style='color: #9ca3af;'>下注</span>  {seq_display} <span style='color: #9ca3af;'>元</span> · {rule}"
        else:
            line3 = "<span style='color: #9ca3af;'>下注</span>  未設定"
        self.line3_label.setText(line3)

        # === 風控 ===
        levels = risk.get('levels', [])
        global_risk = None
        for level in levels:
            if level.get('scope') == 'global_day':
                global_risk = level
                break

        if global_risk:
            tp = int(global_risk.get('take_profit', 0))
            sl = int(global_risk.get('stop_loss', 0))
            line4 = (
                f"<span style='color: #9ca3af;'>風控</span>  "
                f"<span style='color: #10b981; font-weight: bold;'>+{tp}</span> "
                f"<span style='color: #6b7280;'>/</span> "
                f"<span style='color: #ef4444; font-weight: bold;'>{sl}</span>"
            )
        else:
            line4 = "<span style='color: #9ca3af;'>風控</span>  未設定"
        self.line4_label.setText(line4)

        # === 今日統計 ===
        self.line5_label.setText("<span style='color: #6b7280;'>今日</span>  0 觸發 · 0 勝 0 負 · 0 元")

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
            self.line5_label.setText("<span style='color: #6b7280;'>今日</span>  0 觸發 · 0 勝 0 負 · 0 元")
            return

        triggers = performance.get("triggers", 0)
        entries = performance.get("entries", 0)
        wins = performance.get("wins", 0)
        losses = performance.get("losses", 0)
        total_pnl = performance.get("total_pnl", 0.0)

        # 格式化盈虧顏色
        if total_pnl > 0:
            pnl_color = "#10b981"
            pnl_sign = "+"
        elif total_pnl < 0:
            pnl_color = "#ef4444"
            pnl_sign = ""
        else:
            pnl_color = "#9ca3af"
            pnl_sign = ""

        # 現代統計顯示
        line5 = (
            f"<span style='color: #6b7280;'>今日</span>  "
            f"{triggers} 觸發 · "
            f"<span style='color: #10b981;'>{wins}</span> 勝 "
            f"<span style='color: #ef4444;'>{losses}</span> 負 · "
            f"<span style='color: {pnl_color}; font-weight: bold;'>{pnl_sign}{total_pnl:.0f}</span> 元"
        )
        self.line5_label.setText(line5)

    def set_status(self, is_running: bool) -> None:
        """
        設定運行狀態（只更新徽章，不改變卡片大小和樣式）

        Args:
            is_running: 是否運行中
        """
        self.is_running = is_running
        self._update_status_badge(is_running)
        # ✅ 不再改變卡片樣式，保持統一的外觀
