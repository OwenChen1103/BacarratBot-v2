# src/autobet/lines/conflict.py
"""
多策略衝突解決模組

根據規範 §H 實現：
1. 同桌同手相反方向禁止
2. EV（期望值）評估與優先級排序
3. 先到先上機制
4. 固定優先級表
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .config import StrategyDefinition


class ConflictReason(str, Enum):
    """衝突原因"""
    OPPOSITE_DIRECTION = "opposite_direction"  # 相反方向
    RESOURCE_LIMIT = "resource_limit"  # 資源限制
    LOWER_PRIORITY = "lower_priority"  # 優先級較低


class BetDirection(str, Enum):
    """下注方向"""
    BANKER = "B"
    PLAYER = "P"
    TIE = "T"


@dataclass
class PendingDecision:
    """待決策的下注"""
    table_id: str
    round_id: str
    strategy_key: str
    direction: BetDirection
    amount: float
    layer_index: int
    timestamp: float = field(default_factory=time.time)
    ev_score: float = 0.0  # 期望值評分
    priority_score: float = 0.0  # 最終優先級評分
    metadata: Dict[str, any] = field(default_factory=dict)


@dataclass
class ConflictResolution:
    """衝突解決結果"""
    approved: List[PendingDecision]  # 核准的決策
    rejected: List[Tuple[PendingDecision, ConflictReason, str]]  # 拒絕的決策及原因


class ConflictResolver:
    """衝突解決器"""

    def __init__(
        self,
        *,
        fixed_priority: Optional[Dict[str, int]] = None,
        enable_ev_evaluation: bool = True,
    ) -> None:
        """
        初始化衝突解決器

        Args:
            fixed_priority: 固定優先級表 {strategy_key: priority}，數字越小優先級越高
            enable_ev_evaluation: 是否啟用 EV 評估
        """
        self.fixed_priority = fixed_priority or {}
        self.enable_ev_evaluation = enable_ev_evaluation

    def resolve(
        self,
        decisions: List[PendingDecision],
        strategies: Dict[str, StrategyDefinition],
    ) -> ConflictResolution:
        """
        解決多個待決策的衝突

        優先級規則（§H）：
        1. EV（期望/信心）較高者優先
        2. 平手取先到先上
        3. 再平手用固定優先表

        Args:
            decisions: 所有待決策的下注
            strategies: 策略定義字典

        Returns:
            ConflictResolution: 解決結果
        """
        if not decisions:
            return ConflictResolution(approved=[], rejected=[])

        # 按桌和局分組
        groups: Dict[Tuple[str, str], List[PendingDecision]] = {}
        for decision in decisions:
            key = (decision.table_id, decision.round_id)
            if key not in groups:
                groups[key] = []
            groups[key].append(decision)

        approved: List[PendingDecision] = []
        rejected: List[Tuple[PendingDecision, ConflictReason, str]] = []

        # 逐組解決衝突
        for (table_id, round_id), group in groups.items():
            if len(group) == 1:
                # 單一決策，直接通過
                approved.append(group[0])
                continue

            # 檢查相反方向衝突
            approved_in_group, rejected_in_group = self._resolve_direction_conflict(
                group, strategies
            )

            # 如果還有多個同方向決策，按優先級排序
            if len(approved_in_group) > 1:
                approved_in_group, additional_rejected = self._resolve_priority(
                    approved_in_group, strategies
                )
                rejected_in_group.extend(additional_rejected)

            approved.extend(approved_in_group)
            rejected.extend(rejected_in_group)

        return ConflictResolution(approved=approved, rejected=rejected)

    def _resolve_direction_conflict(
        self,
        decisions: List[PendingDecision],
        strategies: Dict[str, StrategyDefinition],
    ) -> Tuple[List[PendingDecision], List[Tuple[PendingDecision, ConflictReason, str]]]:
        """
        解決相反方向衝突

        規則：同桌同手不可雙向對押
        """
        # 按方向分組
        by_direction: Dict[BetDirection, List[PendingDecision]] = {}
        for decision in decisions:
            if decision.direction not in by_direction:
                by_direction[decision.direction] = []
            by_direction[decision.direction].append(decision)

        # 檢查是否有相反方向
        has_banker = BetDirection.BANKER in by_direction
        has_player = BetDirection.PLAYER in by_direction
        has_conflict = has_banker and has_player

        if not has_conflict:
            # 無衝突，全部通過
            return decisions, []

        # 有衝突：需要選擇一個方向
        # 計算每個方向的優先級分數
        direction_scores: Dict[BetDirection, float] = {}
        for direction, group in by_direction.items():
            # 該方向的最高優先級分數
            max_score = max(
                self._calculate_priority_score(d, strategies) for d in group
            )
            direction_scores[direction] = max_score

        # 選擇優先級最高的方向
        winning_direction = max(direction_scores.keys(), key=lambda d: direction_scores[d])

        approved = by_direction[winning_direction]
        rejected = [
            (
                decision,
                ConflictReason.OPPOSITE_DIRECTION,
                f"Opposite direction conflict, {winning_direction.value} wins",
            )
            for direction, group in by_direction.items()
            if direction != winning_direction
            for decision in group
        ]

        return approved, rejected

    def _resolve_priority(
        self,
        decisions: List[PendingDecision],
        strategies: Dict[str, StrategyDefinition],
    ) -> Tuple[List[PendingDecision], List[Tuple[PendingDecision, ConflictReason, str]]]:
        """
        按優先級選擇最優決策

        在同方向的情況下，選擇優先級最高的一個
        """
        # 計算優先級分數
        for decision in decisions:
            decision.priority_score = self._calculate_priority_score(decision, strategies)

        # 排序（分數高的在前）
        sorted_decisions = sorted(decisions, key=lambda d: d.priority_score, reverse=True)

        # 只保留最高分的
        approved = [sorted_decisions[0]]
        rejected = [
            (
                decision,
                ConflictReason.LOWER_PRIORITY,
                f"Lower priority (score={decision.priority_score:.4f})",
            )
            for decision in sorted_decisions[1:]
        ]

        return approved, rejected

    def _calculate_priority_score(
        self,
        decision: PendingDecision,
        strategies: Dict[str, StrategyDefinition],
    ) -> float:
        """
        計算優先級分數

        規則（§H）：
        1. EV（期望/信心）較高者優先
        2. 平手取先到先上（時間戳早的）
        3. 再平手用固定優先表

        分數組成：
        - EV 分數：0-1000
        - 時間戳分數：0-100（越早越高）
        - 固定優先級：0-10
        """
        score = 0.0

        # 1. EV 評估（最重要，權重 1000）
        if self.enable_ev_evaluation:
            ev_score = self._evaluate_ev(decision, strategies)
            score += ev_score * 1000

        # 2. 時間戳（先到先上，權重 100）
        # 使用負時間戳，越早的分數越高
        # 歸一化到 0-100 範圍
        time_score = max(0, 100 - (time.time() - decision.timestamp) * 10)
        score += time_score

        # 3. 固定優先級（權重 10）
        fixed_priority = self.fixed_priority.get(decision.strategy_key, 999)
        # 轉換為分數：優先級越小，分數越高
        priority_score = max(0, 10 - fixed_priority * 0.1)
        score += priority_score

        return score

    def _evaluate_ev(
        self,
        decision: PendingDecision,
        strategies: Dict[str, StrategyDefinition],
    ) -> float:
        """
        評估 EV（期望值/信心）

        返回 0-1 之間的分數

        當前實現：基於策略的 metadata 和層級
        - 層級越低，信心越高（初始層較保守）
        - 可從 metadata 讀取自定義 ev_weight
        """
        strategy = strategies.get(decision.strategy_key)
        if not strategy:
            return 0.5  # 默認中等信心

        # 基礎 EV
        ev = 0.5

        # 從 metadata 讀取自定義權重
        custom_ev = strategy.metadata.get("ev_weight")
        if custom_ev is not None:
            try:
                ev = float(custom_ev)
                ev = max(0.0, min(1.0, ev))  # 限制在 0-1
            except (ValueError, TypeError):
                pass

        # 層級調整：層級越低，信心略高
        # 第一層：+0.1，第二層：+0.05，第三層：0，後續層：負調整
        if decision.layer_index == 0:
            ev += 0.1
        elif decision.layer_index == 1:
            ev += 0.05
        elif decision.layer_index > 3:
            ev -= 0.05 * (decision.layer_index - 3)

        # 確保在 0-1 範圍內
        ev = max(0.0, min(1.0, ev))

        return ev

    def set_fixed_priority(self, priority_map: Dict[str, int]) -> None:
        """設置固定優先級表"""
        self.fixed_priority = priority_map.copy()

    def get_priority_explanation(
        self,
        decision: PendingDecision,
        strategies: Dict[str, StrategyDefinition],
    ) -> str:
        """獲取優先級計算的詳細說明（用於日誌）"""
        ev_score = self._evaluate_ev(decision, strategies) if self.enable_ev_evaluation else 0.0
        time_score = max(0, 100 - (time.time() - decision.timestamp) * 10)
        fixed_priority = self.fixed_priority.get(decision.strategy_key, 999)
        priority_score = max(0, 10 - fixed_priority * 0.1)

        total_score = ev_score * 1000 + time_score + priority_score

        return (
            f"Priority={total_score:.2f} "
            f"(EV={ev_score:.3f}*1000, Time={time_score:.1f}, Fixed={priority_score:.1f})"
        )
