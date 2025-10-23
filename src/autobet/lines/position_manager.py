# src/autobet/lines/position_manager.py
"""
PositionManager - 倉位生命週期管理器

職責：
1. 創建和儲存待處理倉位
2. 結算倉位（計算結果和 PnL）
3. 倉位查詢和追蹤
4. UI 顯示用的倉位快照

不負責：
- 策略評估（由 EntryEvaluator 負責）
- 衝突解決（由 ConflictResolver 負責）
- 風控檢查（由 RiskCoordinator 負責）
- 層數前進（由 LineOrchestrator 協調）
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .state import LayerOutcome
from src.autobet.payout_manager import PayoutManager


@dataclass
class PendingPosition:
    """待處理倉位"""
    table_id: str
    round_id: str
    strategy_key: str
    direction: str  # "B", "P", or "T"
    amount: float
    layer_index: int
    timestamp: float

    def to_dict(self) -> Dict:
        """轉換為字典（UI 顯示用）"""
        return {
            "table_id": self.table_id,
            "round_id": self.round_id,
            "strategy_key": self.strategy_key,
            "direction": self.direction,
            "amount": self.amount,
            "layer_index": self.layer_index,
            "timestamp": self.timestamp,
        }


@dataclass
class SettlementResult:
    """結算結果"""
    outcome: LayerOutcome
    pnl_delta: float
    position: PendingPosition

    def to_dict(self) -> Dict:
        """轉換為字典（UI 顯示用）"""
        return {
            "outcome": self.outcome.value,
            "pnl_delta": self.pnl_delta,
            "position": self.position.to_dict(),
        }


class PositionTracker:
    """
    倉位追蹤器（僅用於 UI 顯示）

    職責：
    - 追蹤當前活躍倉位數量
    - 不做資金檢查，不影響下注決策
    - 只用於 UI 顯示「當前有幾個策略在跑」
    """
    def __init__(self) -> None:
        self.active_positions: Dict[Tuple[str, str], float] = {}  # (table_id, strategy_key) -> amount

    def add_position(self, table_id: str, strategy_key: str, amount: float) -> None:
        """記錄新倉位（下注後）"""
        key = (table_id, strategy_key)
        self.active_positions[key] = amount

    def remove_position(self, table_id: str, strategy_key: str) -> None:
        """移除倉位（結算後）"""
        key = (table_id, strategy_key)
        self.active_positions.pop(key, None)

    def get_position_count(self) -> int:
        """獲取當前倉位數"""
        return len(self.active_positions)

    def get_total_exposure(self) -> float:
        """獲取當前總曝險（所有倉位金額總和）"""
        return sum(self.active_positions.values())

    def snapshot(self) -> Dict:
        """獲取快照（UI 顯示用）"""
        return {
            "position_count": self.get_position_count(),
            "total_exposure": self.get_total_exposure(),
            "positions": [
                {"table_id": tid, "strategy_key": sk, "amount": amt}
                for (tid, sk), amt in self.active_positions.items()
            ]
        }


class PositionManager:
    """倉位生命週期管理器

    負責創建、儲存、查詢和結算倉位。

    使用範例:
        >>> manager = PositionManager()
        >>>
        >>> # 創建倉位
        >>> position = manager.create_position(
        ...     table_id="table1",
        ...     round_id="round1",
        ...     strategy_key="PB_BET_P",
        ...     direction="P",
        ...     amount=100.0,
        ...     layer_index=0
        ... )
        >>>
        >>> # 結算倉位
        >>> result = manager.settle_position(
        ...     table_id="table1",
        ...     round_id="round1",
        ...     strategy_key="PB_BET_P",
        ...     winner="P"
        ... )
        >>> print(result.outcome, result.pnl_delta)
    """

    def __init__(self, payout_manager: Optional[PayoutManager] = None):
        """初始化倉位管理器

        Args:
            payout_manager: 賠率管理器（可選，默認創建新實例）
        """
        # 待處理倉位 {(table_id, round_id, strategy_key): PendingPosition}
        self._pending: Dict[Tuple[str, str, str], PendingPosition] = {}

        # UI 顯示用的倉位追蹤器
        self.tracker = PositionTracker()

        # 賠率管理器（用於計算真實賠率）
        self.payout_manager = payout_manager or PayoutManager()

        # 結算歷史（最近 100 筆）
        self._settlement_history: List[SettlementResult] = []
        self._max_history = 100

    # ===== 倉位創建 =====

    def create_position(
        self,
        table_id: str,
        round_id: str,
        strategy_key: str,
        direction: str,
        amount: float,
        layer_index: int,
        timestamp: Optional[float] = None,
    ) -> PendingPosition:
        """創建待處理倉位

        Args:
            table_id: 桌號
            round_id: 局號
            strategy_key: 策略 key
            direction: 下注方向 ("B", "P", "T")
            amount: 下注金額
            layer_index: 層數索引
            timestamp: 時間戳（可選，默認當前時間）

        Returns:
            PendingPosition 倉位對象

        Raises:
            ValueError: 如果該倉位已存在

        Note:
            創建後自動添加到 tracker 用於 UI 顯示
        """
        key = (table_id, round_id, strategy_key)

        if key in self._pending:
            raise ValueError(
                f"Position already exists: table={table_id}, "
                f"round={round_id}, strategy={strategy_key}"
            )

        position = PendingPosition(
            table_id=table_id,
            round_id=round_id,
            strategy_key=strategy_key,
            direction=direction,
            amount=amount,
            layer_index=layer_index,
            timestamp=timestamp or time.time(),
        )

        self._pending[key] = position

        # 添加到 tracker（UI 顯示用）
        self.tracker.add_position(table_id, strategy_key, amount)

        return position

    # ===== 倉位結算 =====

    def settle_position(
        self,
        table_id: str,
        round_id: str,
        strategy_key: str,
        winner: Optional[str],
    ) -> Optional[SettlementResult]:
        """結算倉位

        Args:
            table_id: 桌號
            round_id: 局號
            strategy_key: 策略 key
            winner: 贏家 ("B", "P", "T", None)

        Returns:
            SettlementResult 或 None（如果倉位不存在）

        Note:
            結算後自動從 pending 和 tracker 中移除
        """
        key = (table_id, round_id, strategy_key)
        position = self._pending.pop(key, None)

        if not position:
            return None

        # 計算結果
        outcome = self._determine_outcome(position.direction, winner)

        # 計算 PnL
        pnl_delta = self._calculate_pnl(
            amount=position.amount,
            outcome=outcome,
            direction=position.direction
        )

        # 創建結算結果
        result = SettlementResult(
            outcome=outcome,
            pnl_delta=pnl_delta,
            position=position,
        )

        # 從 tracker 移除（UI 顯示用）
        self.tracker.remove_position(table_id, strategy_key)

        # 添加到歷史
        self._settlement_history.append(result)
        if len(self._settlement_history) > self._max_history:
            self._settlement_history = self._settlement_history[-self._max_history:]

        return result

    def settle_all_for_round(
        self,
        table_id: str,
        round_id: str,
        winner: Optional[str],
    ) -> List[SettlementResult]:
        """結算某局的所有倉位

        Args:
            table_id: 桌號
            round_id: 局號
            winner: 贏家

        Returns:
            結算結果列表
        """
        results = []

        # 找出該局的所有倉位
        keys_to_settle = [
            key for key in self._pending.keys()
            if key[0] == table_id and key[1] == round_id
        ]

        for key in keys_to_settle:
            _, _, strategy_key = key
            result = self.settle_position(table_id, round_id, strategy_key, winner)
            if result:
                results.append(result)

        return results

    # ===== 結果判定和 PnL 計算 =====

    @staticmethod
    def _determine_outcome(direction: str, winner: Optional[str]) -> LayerOutcome:
        """判定結果

        Args:
            direction: 下注方向 ("B", "P", "T")
            winner: 贏家 ("B", "P", "T", None)

        Returns:
            LayerOutcome

        規則：
        - winner 為 None → CANCELLED
        - winner 為 "T" 且未下注 T → SKIPPED（和局退款）
        - winner 為 "T" 且下注 T → WIN
        - direction == winner → WIN
        - direction != winner → LOSS
        """
        if winner is None:
            return LayerOutcome.CANCELLED

        if winner == "T":
            if direction == "T":
                return LayerOutcome.WIN
            return LayerOutcome.SKIPPED  # 和局退款

        if winner == direction:
            return LayerOutcome.WIN

        return LayerOutcome.LOSS

    def _calculate_pnl(
        self,
        amount: float,
        outcome: LayerOutcome,
        direction: str
    ) -> float:
        """計算 PnL 增量（使用 PayoutManager 處理真實賠率）

        Args:
            amount: 下注金額
            outcome: 結果 (WIN/LOSS/SKIPPED/CANCELLED)
            direction: 下注方向 ("B", "P", "T")

        Returns:
            PnL 增量（正數為贏，負數為輸）

        賠率：
        - Banker WIN: +0.95x (扣除 5% 佣金)
        - Player WIN: +1.0x
        - Tie WIN: +8.0x
        - LOSS: -1.0x
        - SKIPPED/CANCELLED: 0.0
        """
        return self.payout_manager.calculate_pnl(
            amount=amount,
            outcome=outcome.name,
            direction=direction
        )

    # ===== 倉位查詢 =====

    def get_position(
        self,
        table_id: str,
        round_id: str,
        strategy_key: str
    ) -> Optional[PendingPosition]:
        """獲取待處理倉位

        Returns:
            PendingPosition 或 None（如果不存在）
        """
        key = (table_id, round_id, strategy_key)
        return self._pending.get(key)

    def has_position(
        self,
        table_id: str,
        round_id: str,
        strategy_key: str
    ) -> bool:
        """檢查倉位是否存在

        Returns:
            是否存在
        """
        key = (table_id, round_id, strategy_key)
        return key in self._pending

    def has_any_position_for_strategy(
        self,
        table_id: str,
        strategy_key: str
    ) -> bool:
        """檢查某策略是否有任何待處理倉位

        Args:
            table_id: 桌號
            strategy_key: 策略 key

        Returns:
            是否有倉位
        """
        for (tid, _, sk) in self._pending.keys():
            if tid == table_id and sk == strategy_key:
                return True
        return False

    def get_positions_for_table(self, table_id: str) -> List[PendingPosition]:
        """獲取某桌號的所有待處理倉位

        Returns:
            倉位列表
        """
        return [
            pos for (tid, _, _), pos in self._pending.items()
            if tid == table_id
        ]

    def get_positions_for_round(
        self,
        table_id: str,
        round_id: str
    ) -> List[PendingPosition]:
        """獲取某局的所有待處理倉位

        Returns:
            倉位列表
        """
        return [
            pos for (tid, rid, _), pos in self._pending.items()
            if tid == table_id and rid == round_id
        ]

    def get_all_positions(self) -> List[PendingPosition]:
        """獲取所有待處理倉位

        Returns:
            倉位列表
        """
        return list(self._pending.values())

    def count_pending(self) -> int:
        """獲取待處理倉位總數

        Returns:
            倉位數量
        """
        return len(self._pending)

    # ===== 歷史查詢 =====

    def get_settlement_history(self, limit: int = 100) -> List[SettlementResult]:
        """獲取結算歷史

        Args:
            limit: 返回的記錄數量

        Returns:
            結算結果列表（最新的在前）
        """
        return list(reversed(self._settlement_history[-limit:]))

    def get_recent_settlements_for_strategy(
        self,
        strategy_key: str,
        limit: int = 10
    ) -> List[SettlementResult]:
        """獲取某策略的最近結算記錄

        Args:
            strategy_key: 策略 key
            limit: 返回的記錄數量

        Returns:
            結算結果列表（最新的在前）
        """
        filtered = [
            result for result in self._settlement_history
            if result.position.strategy_key == strategy_key
        ]
        return list(reversed(filtered[-limit:]))

    def clear_settlement_history(self) -> None:
        """清空結算歷史"""
        self._settlement_history.clear()

    # ===== 清理和重置 =====

    def remove_position(
        self,
        table_id: str,
        round_id: str,
        strategy_key: str
    ) -> bool:
        """移除倉位（不結算）

        Args:
            table_id: 桌號
            round_id: 局號
            strategy_key: 策略 key

        Returns:
            是否成功移除（False 表示倉位不存在）

        Note:
            這個方法用於異常情況下強制移除倉位，
            正常情況下應該使用 settle_position()
        """
        key = (table_id, round_id, strategy_key)
        position = self._pending.pop(key, None)

        if position:
            self.tracker.remove_position(table_id, strategy_key)
            return True

        return False

    def clear_all_positions(self) -> int:
        """清空所有倉位（慎用！）

        Returns:
            清空的倉位數量

        Note:
            通常用於測試或重新初始化
        """
        count = len(self._pending)
        self._pending.clear()
        self.tracker.active_positions.clear()
        return count

    # ===== 快照和統計 =====

    def snapshot(self) -> Dict:
        """獲取倉位管理器快照（調試用）

        Returns:
            包含完整狀態的字典
        """
        return {
            "total_pending": len(self._pending),
            "tracker_count": self.tracker.get_position_count(),
            "total_exposure": self.tracker.get_total_exposure(),
            "settlement_history_count": len(self._settlement_history),
            "pending_positions": [pos.to_dict() for pos in self._pending.values()],
            "tracker_snapshot": self.tracker.snapshot(),
        }

    def get_statistics(self) -> Dict:
        """獲取統計信息

        Returns:
            統計數據字典
        """
        total_settled = len(self._settlement_history)

        if total_settled == 0:
            return {
                "total_settled": 0,
                "total_pending": len(self._pending),
                "win_count": 0,
                "loss_count": 0,
                "skip_count": 0,
                "cancel_count": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
            }

        win_count = sum(1 for r in self._settlement_history if r.outcome == LayerOutcome.WIN)
        loss_count = sum(1 for r in self._settlement_history if r.outcome == LayerOutcome.LOSS)
        skip_count = sum(1 for r in self._settlement_history if r.outcome == LayerOutcome.SKIPPED)
        cancel_count = sum(1 for r in self._settlement_history if r.outcome == LayerOutcome.CANCELLED)
        total_pnl = sum(r.pnl_delta for r in self._settlement_history)

        # 計算勝率（排除 SKIPPED 和 CANCELLED）
        decided_count = win_count + loss_count
        win_rate = (win_count / decided_count * 100) if decided_count > 0 else 0.0

        return {
            "total_settled": total_settled,
            "total_pending": len(self._pending),
            "win_count": win_count,
            "loss_count": loss_count,
            "skip_count": skip_count,
            "cancel_count": cancel_count,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 2),
        }
