# src/autobet/lines/entry_evaluator.py
"""
EntryEvaluator - 策略入場條件評估器

職責：
1. 評估策略觸發條件（信號匹配）
2. 檢查 Line 狀態（frozen, armed）
3. 檢查風控封鎖
4. 計算下注方向和金額
5. 生成候選決策（PendingDecision）

不負責：
- 策略註冊管理（由 StrategyRegistry 負責）
- 衝突解決（由 ConflictResolver 負責）
- 倉位結算（由 PositionManager 負責）
- 最終決策生成（由 LineOrchestrator 協調）
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from .config import EntryConfig, StrategyDefinition, CrossTableMode
from .conflict import PendingDecision, BetDirection as ConflictBetDirection
from .signal import SignalTracker
from .state import LineState, LinePhase, LayerProgression


class BetDirection:
    """下注方向枚舉（內部使用）"""
    BANKER = "B"
    PLAYER = "P"
    TIE = "T"


class RiskCoordinatorProtocol:
    """風控協調器接口（避免循環依賴）"""
    def is_blocked(self, strategy_key: str, table_id: str, metadata: Dict) -> bool:
        """檢查策略是否被風控封鎖"""
        ...

    def refresh(self) -> None:
        """刷新風控狀態（解除過期的凍結）"""
        ...


class EntryEvaluationResult:
    """策略評估結果"""
    def __init__(
        self,
        strategy_key: str,
        triggered: bool,
        reason: str = "",
        candidate: Optional[PendingDecision] = None,
    ):
        self.strategy_key = strategy_key
        self.triggered = triggered
        self.reason = reason
        self.candidate = candidate


class EntryEvaluator:
    """策略入場條件評估器

    負責評估每個策略的觸發條件，並生成候選決策。

    使用範例:
        >>> evaluator = EntryEvaluator(
        ...     strategies=strategy_registry.list_all_strategies(),
        ...     signal_trackers=signal_trackers,
        ...     risk_coordinator=risk_coordinator
        ... )
        >>>
        >>> # 評估某桌號的所有策略
        >>> candidates = evaluator.evaluate_table(
        ...     table_id="table1",
        ...     round_id="round-xxx",
        ...     strategies_for_table=strategy_registry.get_strategies_for_table("table1"),
        ...     timestamp=time.time()
        ... )
    """

    def __init__(
        self,
        strategies: Dict[str, StrategyDefinition],
        signal_trackers: Dict[str, SignalTracker],
        risk_coordinator: Optional[RiskCoordinatorProtocol] = None,
    ):
        """初始化評估器

        Args:
            strategies: 策略定義字典 {strategy_key: StrategyDefinition}
            signal_trackers: 信號追蹤器字典 {strategy_key: SignalTracker}
            risk_coordinator: 風控協調器（可選）
        """
        self.strategies = strategies
        self.signal_trackers = signal_trackers
        self.risk_coordinator = risk_coordinator

        # Line 狀態管理 {table_id: {strategy_key: LineState}}
        self.line_states: Dict[str, Dict[str, LineState]] = {}

        # 層數進度管理
        self._line_progressions: Dict[Tuple[str, str], LayerProgression] = {}
        self._shared_progressions: Dict[str, LayerProgression] = {}

        # 事件記錄（用於調試和 UI 顯示）
        self._events: List[Dict] = []
        self._max_events = 1000

    # ===== 主要評估方法 =====

    def evaluate_table(
        self,
        table_id: str,
        round_id: str,
        strategies_for_table: List[Tuple[str, StrategyDefinition]],
        timestamp: float,
    ) -> List[PendingDecision]:
        """評估某桌號的所有策略，返回候選決策

        Args:
            table_id: 桌號
            round_id: 局號
            strategies_for_table: 該桌號綁定的策略列表 [(strategy_key, definition), ...]
            timestamp: 時間戳

        Returns:
            候選決策列表（尚未解決衝突）
        """
        candidates: List[PendingDecision] = []

        # 刷新風控狀態（解除過期的凍結）
        if self.risk_coordinator:
            self.risk_coordinator.refresh()

        for strategy_key, definition in strategies_for_table:
            # 評估單個策略
            result = self._evaluate_strategy(
                table_id=table_id,
                round_id=round_id,
                strategy_key=strategy_key,
                definition=definition,
                timestamp=timestamp,
            )

            # 記錄評估結果（調試用）
            self._record_event(
                "DEBUG",
                f"策略 {strategy_key}: {result.reason}",
                {"table": table_id, "triggered": result.triggered}
            )

            # 如果觸發，添加到候選列表
            if result.triggered and result.candidate:
                candidates.append(result.candidate)

        return candidates

    def _evaluate_strategy(
        self,
        table_id: str,
        round_id: str,
        strategy_key: str,
        definition: StrategyDefinition,
        timestamp: float,
    ) -> EntryEvaluationResult:
        """評估單個策略的觸發條件

        Returns:
            EntryEvaluationResult 包含是否觸發和候選決策
        """
        tracker = self.signal_trackers.get(strategy_key)
        if not tracker:
            return EntryEvaluationResult(
                strategy_key, False, "SignalTracker not found"
            )

        line_state = self._ensure_line_state(table_id, strategy_key)

        # 檢查 1: Line 是否在等待結果
        if line_state.phase == LinePhase.WAITING_RESULT:
            return EntryEvaluationResult(
                strategy_key, False, f"Waiting for result (round={line_state.last_round_id})"
            )

        # 檢查 2: Line 是否被凍結
        if line_state.frozen:
            return EntryEvaluationResult(
                strategy_key, False, f"Line frozen until {line_state.frozen_until}"
            )

        # 檢查 3: 風控封鎖
        if self.risk_coordinator and self.risk_coordinator.is_blocked(
            strategy_key, table_id, definition.metadata
        ):
            return EntryEvaluationResult(
                strategy_key, False, "Blocked by risk coordinator"
            )

        # 檢查 4: 信號觸發
        should_trigger_result = tracker.should_trigger(table_id, round_id, timestamp)

        if not should_trigger_result:
            # 獲取調試信息
            required_length = len(tracker._pattern_sequence(definition.entry.pattern))
            recent_winners = tracker._get_recent_winners(table_id, required_length)
            history_list = list(tracker.history.get(table_id, []))

            reason = (
                f"⏳ 模式 {definition.entry.pattern} | "
                f"歷史長度 {len(history_list)}/{required_length} | "
                f"近期 {recent_winners} | ❌ 未觸發"
            )
            return EntryEvaluationResult(strategy_key, False, reason)

        # 信號觸發成功
        recent_winners = tracker._get_recent_winners(
            table_id,
            len(tracker._pattern_sequence(definition.entry.pattern))
        )
        self._record_event(
            "INFO",
            f"✅ 策略 {strategy_key} 觸發！| 模式 {definition.entry.pattern} | 歷史 {recent_winners}",
            {"table": table_id}
        )

        # 更新 Line 狀態為 ARMED
        line_state.phase = LinePhase.ARMED
        line_state.armed_count += 1

        # 檢查 5: 首次觸發層
        required_triggers = 1 if definition.entry.first_trigger_layer >= 1 else 2
        if line_state.armed_count < required_triggers:
            reason = f"Armed (count={line_state.armed_count}), waiting for first_trigger_layer"
            return EntryEvaluationResult(strategy_key, False, reason)

        # 計算下注方向和金額
        progression = self._get_progression(table_id, strategy_key)
        desired_stake = progression.current_stake()
        base_direction = self._derive_base_direction(definition.entry)
        direction_str, amount = self._resolve_direction(desired_stake, base_direction)

        # 創建候選決策
        candidate = PendingDecision(
            table_id=table_id,
            round_id=round_id,
            strategy_key=strategy_key,
            direction=ConflictBetDirection(direction_str),
            amount=amount,
            layer_index=progression.index,
            timestamp=timestamp,
            metadata=definition.metadata,
        )

        return EntryEvaluationResult(
            strategy_key=strategy_key,
            triggered=True,
            reason=f"✅ Triggered | direction={direction_str} | amount={amount} | layer={progression.index}",
            candidate=candidate,
        )

    # ===== 輔助方法 =====

    def _derive_base_direction(self, entry: EntryConfig) -> str:
        """從 EntryConfig 推導下注方向

        例如: "PBBET P" → "P", "PPBET B" → "B"
        """
        pattern = entry.pattern.upper()
        if "BET" in pattern:
            suffix = pattern.split("BET", 1)[1]
            for ch in suffix:
                if ch in {"B", "P", "T"}:
                    return ch
        return BetDirection.PLAYER

    def _resolve_direction(
        self,
        stake: int,
        base_direction: str
    ) -> Tuple[str, float]:
        """解析下注方向和金額

        Args:
            stake: 期望下注金額（可能為負數表示反向）
            base_direction: 基礎方向 (B/P/T)

        Returns:
            (方向, 金額) 元組
        """
        amount = abs(stake)
        if stake == 0:
            return base_direction, 0.0
        if stake > 0:
            return base_direction, float(amount)
        # 負數表示反向
        opposite = {"B": "P", "P": "B", "T": "T"}
        return opposite.get(base_direction, base_direction), float(amount)

    def _ensure_line_state(self, table_id: str, strategy_key: str) -> LineState:
        """確保 LineState 存在

        如果不存在，創建新的 LineState
        """
        if table_id not in self.line_states:
            self.line_states[table_id] = {}

        if strategy_key not in self.line_states[table_id]:
            self.line_states[table_id][strategy_key] = LineState(
                strategy_key=strategy_key,
                table_id=table_id
            )

        return self.line_states[table_id][strategy_key]

    def _get_progression(self, table_id: str, strategy_key: str) -> LayerProgression:
        """獲取或創建層數進度

        根據 CrossTableMode 決定使用獨立進度還是共享進度
        """
        definition = self.strategies[strategy_key]

        if definition.cross_table_layer.mode == CrossTableMode.ACCUMULATE:
            # 跨桌共享進度
            if strategy_key not in self._shared_progressions:
                self._shared_progressions[strategy_key] = LayerProgression(
                    definition.staking
                )
            return self._shared_progressions[strategy_key]
        else:
            # 獨立進度（每桌每策略）
            key = (table_id, strategy_key)
            if key not in self._line_progressions:
                self._line_progressions[key] = LayerProgression(definition.staking)
            return self._line_progressions[key]

    # ===== 狀態重置和管理 =====

    def reset_line_state(self, table_id: str, strategy_key: str) -> None:
        """重置 Line 狀態（拒絕後調用）

        Args:
            table_id: 桌號
            strategy_key: 策略 key
        """
        line_state = self._ensure_line_state(table_id, strategy_key)
        line_state.phase = LinePhase.IDLE
        line_state.armed_count = 0

    def get_line_state(self, table_id: str, strategy_key: str) -> Optional[LineState]:
        """獲取 Line 狀態（只讀）

        Returns:
            LineState 或 None（如果不存在）
        """
        return self.line_states.get(table_id, {}).get(strategy_key)

    def get_progression(self, table_id: str, strategy_key: str) -> Optional[LayerProgression]:
        """獲取層數進度（只讀）

        Returns:
            LayerProgression 或 None（如果不存在）
        """
        definition = self.strategies.get(strategy_key)
        if not definition:
            return None

        if definition.cross_table_layer.mode == CrossTableMode.ACCUMULATE:
            return self._shared_progressions.get(strategy_key)
        else:
            key = (table_id, strategy_key)
            return self._line_progressions.get(key)

    # ===== 事件記錄 =====

    def _record_event(self, level: str, message: str, metadata: Dict) -> None:
        """記錄評估事件（用於調試和 UI 顯示）

        Args:
            level: 日誌級別 (DEBUG, INFO, WARNING, ERROR)
            message: 消息內容
            metadata: 附加元數據
        """
        event = {
            "timestamp": time.time(),
            "level": level,
            "message": message,
            "metadata": metadata,
        }

        self._events.append(event)

        # 限制事件數量，避免記憶體無限增長
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

    def get_recent_events(self, limit: int = 100) -> List[Dict]:
        """獲取最近的評估事件

        Args:
            limit: 返回的事件數量

        Returns:
            事件列表（最新的在前）
        """
        return list(reversed(self._events[-limit:]))

    def clear_events(self) -> None:
        """清空事件記錄"""
        self._events.clear()

    # ===== 快照和調試 =====

    def snapshot(self) -> Dict:
        """獲取評估器狀態快照（調試用）

        Returns:
            包含完整狀態的字典
        """
        return {
            "total_strategies": len(self.strategies),
            "total_line_states": sum(len(states) for states in self.line_states.values()),
            "line_progressions_count": len(self._line_progressions),
            "shared_progressions_count": len(self._shared_progressions),
            "recent_events_count": len(self._events),
            "line_states": {
                f"{table_id}:{strategy_key}": {
                    "phase": state.phase.value,
                    "armed_count": state.armed_count,
                    "frozen": state.frozen,
                }
                for table_id, states in self.line_states.items()
                for strategy_key, state in states.items()
            },
        }
