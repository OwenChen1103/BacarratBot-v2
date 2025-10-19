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
        self.strategy_data = None
        self._build_ui()
        self._load_strategy()

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
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # 標題與狀態指示器（合併在一行）
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        header = QLabel("⚙️ 策略狀態")
        header.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        header.setStyleSheet("color: #f3f4f6;")
        header_layout.addWidget(header)

        header_layout.addStretch()

        self.status_indicator = QLabel("●")
        self.status_indicator.setFont(QFont("Arial", 12))
        self.status_indicator.setStyleSheet("color: #6b7280;")
        header_layout.addWidget(self.status_indicator)

        self.status_label = QLabel("等待啟動")
        self.status_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.status_label.setStyleSheet("color: #9ca3af;")
        header_layout.addWidget(self.status_label)

        layout.addLayout(header_layout)

        # 策略配置（緊湊版）
        self.strategy_config_label = QLabel()
        self.strategy_config_label.setFont(QFont("Microsoft YaHei UI", 8))
        self.strategy_config_label.setStyleSheet("""
            QLabel {
                color: #d1d5db;
                background-color: #1f2937;
                border: 1px solid #4b5563;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        self.strategy_config_label.setWordWrap(True)
        self.strategy_config_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(self.strategy_config_label)

        # 分隔線
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #4b5563; max-height: 1px;")
        layout.addWidget(separator)

        # 下一手詳情（緊湊版）
        next_bet_header = QLabel("🎯 下一手")
        next_bet_header.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        next_bet_header.setStyleSheet("color: #d1d5db;")
        layout.addWidget(next_bet_header)

        # 桌台與層數信息
        self.table_layer_label = QLabel("等待啟動引擎...")
        self.table_layer_label.setFont(QFont("Microsoft YaHei UI", 8))
        self.table_layer_label.setStyleSheet("color: #9ca3af;")
        self.table_layer_label.setWordWrap(True)
        layout.addWidget(self.table_layer_label)

        # 下注方向與金額
        self.direction_amount_label = QLabel()
        self.direction_amount_label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        self.direction_amount_label.setStyleSheet("color: #ffffff;")
        self.direction_amount_label.setWordWrap(True)
        layout.addWidget(self.direction_amount_label)

        # 配方詳情
        self.recipe_label = QLabel()
        self.recipe_label.setFont(QFont("Consolas", 8))
        self.recipe_label.setStyleSheet("""
            QLabel {
                color: #d1d5db;
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        self.recipe_label.setWordWrap(True)
        self.recipe_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(self.recipe_label)

        layout.addStretch()

    def _load_strategy(self) -> None:
        """載入策略配置 - 優先載入 line_strategies"""
        # 優先載入 line_strategies (新系統)
        line_strategies_dir = "configs/line_strategies"
        if os.path.exists(line_strategies_dir):
            try:
                # 載入第一個策略 (假設用戶使用策略 "1")
                strategy_files = [f for f in os.listdir(line_strategies_dir) if f.endswith('.json')]
                if strategy_files:
                    # 載入第一個找到的策略
                    first_strategy = os.path.join(line_strategies_dir, strategy_files[0])
                    with open(first_strategy, 'r', encoding='utf-8') as f:
                        self.strategy_data = json.load(f)
                    self.strategy_data['_type'] = 'line_strategy'  # 標記類型
                    self._update_strategy_display()
                    return
            except Exception as e:
                pass  # 如果失敗，回退到舊系統

        # 回退到舊系統 strategy.json
        strategy_path = "configs/strategy.json"
        if os.path.exists(strategy_path):
            try:
                with open(strategy_path, 'r', encoding='utf-8') as f:
                    self.strategy_data = json.load(f)
                self.strategy_data['_type'] = 'legacy_strategy'  # 標記類型
                self._update_strategy_display()
            except Exception as e:
                self.strategy_config_label.setText(f"❌ 策略載入失敗: {e}")
        else:
            self.strategy_config_label.setText("❌ 策略配置文件不存在")

    def _update_strategy_display(self) -> None:
        """更新策略配置顯示"""
        if not self.strategy_data:
            self.strategy_config_label.setText("❌ 未載入策略")
            return

        strategy_type = self.strategy_data.get('_type', 'unknown')

        if strategy_type == 'line_strategy':
            # 新系統：line_strategies 格式
            self._display_line_strategy()
        else:
            # 舊系統：strategy.json 格式
            self._display_legacy_strategy()

    def _display_line_strategy(self) -> None:
        """顯示 line_strategy 格式的策略"""
        strategy_key = self.strategy_data.get('strategy_key', '未知')
        entry = self.strategy_data.get('entry', {})
        staking = self.strategy_data.get('staking', {})

        # 觸發模式
        pattern = entry.get('pattern', '未設定')

        # 注碼序列
        sequence = staking.get('sequence', [])
        sequence_text = ' → '.join([f"{s}元" for s in sequence])

        # 進階規則
        advance_on = staking.get('advance_on', 'loss')
        advance_text = "輸進層" if advance_on == 'loss' else "贏進層"

        # 重置規則
        reset_on_win = staking.get('reset_on_win', False)
        reset_text = "贏重置" if reset_on_win else ""

        # 疊注策略
        stack_policy = staking.get('stack_policy', 'none')
        stack_map = {'none': '禁止疊注', 'merge': '合併注單', 'parallel': '平行下注'}
        stack_text = stack_map.get(stack_policy, stack_policy)

        config_text = (
            f"策略:{strategy_key} | 模式:{pattern}\n"
            f"序列:{sequence_text}\n"
            f"{advance_text} | {reset_text} | {stack_text}"
        )

        self.strategy_config_label.setText(config_text)

    def _display_legacy_strategy(self) -> None:
        """顯示舊格式 strategy.json 的策略"""
        # 基本策略信息
        unit = self.strategy_data.get('unit', 0)
        targets = self.strategy_data.get('targets', self.strategy_data.get('target', []))
        if isinstance(targets, str):
            targets = [targets]

        # 目標轉換
        target_map = {
            'banker': '莊',
            'player': '閒',
            'tie': '和'
        }
        target_text = '/'.join([target_map.get(t, t) for t in targets])

        # 馬丁格爾設定
        martingale = self.strategy_data.get('martingale', {})
        martingale_enabled = martingale.get('enabled', False)
        max_level = martingale.get('max_level', 0)

        # 風控設定
        risk = self.strategy_data.get('risk_control', {})
        max_loss = risk.get('max_loss', 0)
        max_win = risk.get('max_win', 0)

        # 限制設定
        limits = self.strategy_data.get('limits', {})
        per_round_cap = limits.get('per_round_cap', 0)

        # 構建緊湊顯示文本（兩列顯示）
        martingale_text = f"開 Lv{max_level}" if martingale_enabled else "關"

        config_text = (
            f"單位:{unit}元 | 目標:{target_text} | 單局上限:{per_round_cap}元\n"
            f"馬丁:{martingale_text} | 止損:{max_loss}元 | 止盈:{max_win}元"
        )

        self.strategy_config_label.setText(config_text)

    def set_engine_running(self, running: bool) -> None:
        """設置引擎運行狀態"""
        if running:
            self.status_indicator.setStyleSheet("color: #10b981;")  # 綠色
            self.status_label.setText("策略運行中")
            self.status_label.setStyleSheet("color: #10b981; font-weight: bold;")
            self.table_layer_label.setText("等待檢測下注時機...")
            self.table_layer_label.setStyleSheet("color: #e5e7eb;")
        else:
            self.status_indicator.setStyleSheet("color: #6b7280;")  # 灰色
            self.status_label.setText("等待啟動")
            self.status_label.setStyleSheet("color: #9ca3af; font-weight: bold;")
            self.table_layer_label.setText("等待啟動引擎...")
            self.table_layer_label.setStyleSheet("color: #9ca3af;")
            self.direction_amount_label.setText("")
            self.recipe_label.setText("")

    def update_next_bet(
        self,
        table: str,
        strategy: str,
        current_layer: int,
        direction: str,
        amount: int,
        recipe: str,
        win_action: str = "",
        loss_action: str = ""
    ) -> None:
        """
        更新下一手詳情

        Args:
            table: 桌號
            strategy: 策略名稱
            current_layer: 當前層數
            direction: 下注方向 (B/P/T)
            amount: 下注金額
            recipe: 下注配方
            win_action: 獲勝後的動作
            loss_action: 失敗後的動作
        """
        # 桌台與層數
        self.table_layer_label.setText(
            f"桌台: {table} | 策略: {strategy} | 第 {current_layer} 層"
        )
        self.table_layer_label.setStyleSheet("color: #e5e7eb;")

        # 方向與金額
        direction_map = {
            "B": ("莊家", "#ef4444"),
            "P": ("閒家", "#3b82f6"),
            "T": ("和局", "#10b981"),
            "banker": ("莊家", "#ef4444"),
            "player": ("閒家", "#3b82f6"),
            "tie": ("和局", "#10b981"),
        }
        direction_text, direction_color = direction_map.get(direction, (direction, "#ffffff"))

        self.direction_amount_label.setText(
            f"方向: {direction_text} | 金額: {amount} 元"
        )
        self.direction_amount_label.setStyleSheet(f"color: {direction_color}; font-weight: bold;")

        # 配方
        self.recipe_label.setText(recipe or "等待生成配方...")

    def set_recipe_steps(self, steps: list) -> None:
        """
        設定配方步驟列表

        Args:
            steps: 步驟列表，例如 ["1. 點擊 Chip 2 (1K籌碼)", "2. 點擊莊家區域", ...]
        """
        if not steps:
            self.recipe_label.setText("無配方")
            return

        recipe_text = "\n".join(steps)
        self.recipe_label.setText(recipe_text)

    def clear(self) -> None:
        """清空下一手詳情（保留策略配置）"""
        self.table_layer_label.setText("等待檢測下注時機...")
        self.table_layer_label.setStyleSheet("color: #9ca3af;")
        self.direction_amount_label.setText("")
        self.recipe_label.setText("")

    def reload_strategy(self) -> None:
        """重新載入策略配置"""
        self._load_strategy()
