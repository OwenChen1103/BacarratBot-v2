# src/autobet/strategy_simulator.py
"""策略模擬器 - 基於歷史牌路測試策略"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from .lines.config import StrategyDefinition, DedupMode, AdvanceRule


@dataclass
class SimulationResult:
    """模擬結果"""
    total_hands: int  # 總手數
    triggered_count: int  # 觸發次數
    win_count: int  # 贏的次數
    loss_count: int  # 輸的次數
    total_profit: float  # 總盈虧
    max_profit: float  # 最大盈利
    max_drawdown: float  # 最大回撤
    max_layer_reached: int  # 達到的最大層數
    win_rate: float  # 勝率
    roi: float  # 投資回報率 (總盈虧 / 總投入)
    bet_history: List[Tuple[int, str, float, float]]  # (手數, 下注方向, 金額, 盈虧)


class StrategySimulator:
    """策略模擬器"""

    def __init__(self, definition: StrategyDefinition):
        self.definition = definition
        self.pattern_regex = re.compile(
            r"^([BPT]+)\s+then\s+bet\s+([BP])$", re.IGNORECASE
        )

    def simulate(self, road_str: str) -> SimulationResult:
        """
        模擬策略在歷史牌路上的表現

        Args:
            road_str: 牌路字符串,例如 "BPBPBBPPPBBB"
                     B=莊, P=閒, T=和 (和局通常忽略)

        Returns:
            SimulationResult
        """
        # 解析 Pattern
        match = self.pattern_regex.match(self.definition.entry.pattern)
        if not match:
            raise ValueError(f"Invalid pattern: {self.definition.entry.pattern}")

        condition = match.group(1).upper()
        bet_side = match.group(2).upper()

        # 移除和局 (T)
        road = [c for c in road_str.upper() if c in ['B', 'P']]

        # 模擬變數
        current_layer = 0
        total_profit = 0.0
        max_profit = 0.0
        max_drawdown = 0.0
        triggered_count = 0
        win_count = 0
        loss_count = 0
        max_layer_reached = 0
        bet_history = []

        # 跟隨或反向
        sequence = self.definition.staking.sequence
        is_reverse = sequence[0] < 0 if sequence else False
        abs_sequence = [abs(x) for x in sequence]

        # 信號匹配
        signals = self._find_signals(road, condition)

        for hand_idx, signal_idx in signals:
            triggered_count += 1

            # 決定下注方向
            if is_reverse:
                actual_bet = 'P' if bet_side == 'B' else 'B'
            else:
                actual_bet = bet_side

            # 下注金額
            layer_idx = min(current_layer, len(abs_sequence) - 1)
            bet_amount = abs_sequence[layer_idx]

            # 結果
            if hand_idx < len(road):
                result = road[hand_idx]
                is_win = (result == actual_bet)

                if is_win:
                    profit = bet_amount * 0.95  # 莊家抽水 5%
                    win_count += 1
                else:
                    profit = -bet_amount
                    loss_count += 1

                total_profit += profit
                max_profit = max(max_profit, total_profit)
                max_drawdown = min(max_drawdown, total_profit)

                bet_history.append((hand_idx, actual_bet, bet_amount, profit))

                # 更新層數
                if self.definition.staking.advance_on == AdvanceRule.LOSS:
                    if not is_win:
                        current_layer += 1
                    if is_win and self.definition.staking.reset_on_win:
                        current_layer = 0
                else:  # advance_on == WIN
                    if is_win:
                        current_layer += 1
                    if not is_win and self.definition.staking.reset_on_loss:
                        current_layer = 0

                max_layer_reached = max(max_layer_reached, current_layer)

        # 計算統計
        win_rate = (win_count / triggered_count * 100) if triggered_count > 0 else 0.0
        total_bet = sum([bet[2] for bet in bet_history])
        roi = (total_profit / total_bet * 100) if total_bet > 0 else 0.0

        return SimulationResult(
            total_hands=len(road),
            triggered_count=triggered_count,
            win_count=win_count,
            loss_count=loss_count,
            total_profit=total_profit,
            max_profit=max_profit,
            max_drawdown=max_drawdown,
            max_layer_reached=max_layer_reached + 1,  # +1 因為層數從 0 開始
            win_rate=win_rate,
            roi=roi,
            bet_history=bet_history,
        )

    def _find_signals(self, road: List[str], condition: str) -> List[Tuple[int, int]]:
        """
        找出符合條件的信號位置

        Returns:
            List of (hand_idx, signal_idx) - hand_idx 是下注的手數
        """
        signals = []
        condition_len = len(condition)

        for i in range(len(road) - condition_len):
            # 檢查是否匹配
            match = True
            for j, required in enumerate(condition):
                if required != 'T' and road[i + j] != required:
                    match = False
                    break

            if match:
                # 信號匹配,下一手下注
                bet_hand = i + condition_len
                signals.append((bet_hand, i))

        # 去重處理
        if self.definition.entry.dedup == DedupMode.STRICT:
            # 嚴格去重: 信號之間不能重疊
            filtered = []
            last_end = -1
            for bet_hand, signal_idx in signals:
                if signal_idx > last_end:
                    filtered.append((bet_hand, signal_idx))
                    last_end = signal_idx + len(condition) - 1
            signals = filtered

        elif self.definition.entry.dedup == DedupMode.OVERLAP:
            # 重疊去重: 允許重疊但跳過完全重複
            # (簡化實現: 連續信號只取第一個)
            filtered = []
            last_bet = -999
            for bet_hand, signal_idx in signals:
                if bet_hand != last_bet:
                    filtered.append((bet_hand, signal_idx))
                    last_bet = bet_hand
            signals = filtered

        # NONE: 不去重,保留所有信號

        return signals


def generate_sample_roads() -> List[Tuple[str, str]]:
    """生成範例牌路"""
    return [
        ("範例 1 - 平衡牌路", "BPBPBPBPBPBPBPBPBPBPBPBPBPBPBPBPBPBP"),
        ("範例 2 - 莊龍", "BBBBBBBPBPBBBBBPPPBBBBBBBPBPB"),
        ("範例 3 - 閒龍", "PPPPPPBPBPPPPPBBBPPPPPPPBPBP"),
        ("範例 4 - 混亂路", "BPBBPPPBBPBPPPBBBPPBPBPPPBBBPPB"),
        ("範例 5 - 雙跳", "BBPPBBPPBBPPBBPPBBPPBBPPBBPPBBPP"),
    ]
