# src/autobet/lines/orchestrator_v2.py
"""
LineOrchestrator V2 - 重構後的協調器

職責：
1. 協調各組件（StrategyRegistry, EntryEvaluator, PositionManager）
2. 處理階段轉換（update_table_phase）
3. 處理結果（handle_result）
4. 協調風控檢查（RiskCoordinator）
5. 協調衝突解決（ConflictResolver）
6. 事件記錄和指標追蹤

不再負責：
- 策略註冊管理（由 StrategyRegistry 負責）
- 策略觸發評估（由 EntryEvaluator 負責）
- 倉位生命週期（由 PositionManager 負責）
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .config import StrategyDefinition
from .conflict import ConflictResolver, PendingDecision, ConflictReason
from .metrics import MetricsTracker, EventRecord, EventType
from .performance import PerformanceTracker
from .signal import SignalTracker
from .state import LayerOutcome, LinePhase
from .strategy_registry import StrategyRegistry
from .entry_evaluator import EntryEvaluator, RiskCoordinatorProtocol
from .position_manager import PositionManager


class TablePhase(str, Enum):
    """桌號階段"""
    IDLE = "idle"
    OPEN = "open"
    BETTABLE = "bettable"
    LOCKED = "locked"
    RESULTING = "resulting"
    SETTLED = "settled"


class BetDirection(str, Enum):
    """下注方向"""
    BANKER = "B"
    PLAYER = "P"
    TIE = "T"


@dataclass
class BetDecision:
    """最終下注決策"""
    table_id: str
    round_id: str
    strategy_key: str
    direction: BetDirection
    amount: float
    layer_index: int
    created_at: float = field(default_factory=time.time)
    reason: str = ""


@dataclass
class ConflictRecord:
    """衝突解決記錄（用於 UI 顯示）"""
    table_id: str
    round_id: str
    timestamp: float
    candidates_count: int
    approved_count: int
    rejected_count: int
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    rejections: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_id": self.table_id,
            "round_id": self.round_id,
            "timestamp": self.timestamp,
            "candidates_count": self.candidates_count,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "candidates": self.candidates,
            "rejections": self.rejections,
        }


@dataclass
class OrchestratorEvent:
    """協調器事件"""
    level: str
    message: str
    metadata: Dict[str, str] = field(default_factory=dict)


class RiskCoordinator(RiskCoordinatorProtocol):
    """風控協調器（佔位符實現）

    TODO: 這裡暫時使用簡單實現，實際應該使用完整的 RiskCoordinator
    """
    def __init__(self):
        self._blocked = set()

    def is_blocked(self, strategy_key: str, table_id: str, metadata: Dict) -> bool:
        return f"{table_id}:{strategy_key}" in self._blocked

    def refresh(self) -> None:
        pass

    def register_strategy(self, definition: StrategyDefinition) -> None:
        pass

    def record(self, strategy_key: str, table_id: str, pnl_delta: float,
               outcome: LayerOutcome, metadata: Dict) -> List:
        return []


class LineOrchestratorV2:
    """重構後的 LineOrchestrator

    使用範例:
        >>> # 創建協調器
        >>> orchestrator = LineOrchestratorV2()
        >>>
        >>> # 註冊策略
        >>> orchestrator.register_strategy(strategy_def, tables=["table1"])
        >>>
        >>> # 階段轉換
        >>> decisions = orchestrator.update_table_phase(
        ...     table_id="table1",
        ...     round_id="round1",
        ...     phase=TablePhase.BETTABLE,
        ...     timestamp=time.time()
        ... )
        >>>
        >>> # 處理結果
        >>> orchestrator.handle_result(
        ...     table_id="table1",
        ...     round_id="round1",
        ...     winner="P",
        ...     timestamp=time.time()
        ... )
    """

    def __init__(
        self,
        *,
        fixed_priority: Optional[Dict[str, int]] = None,
        enable_ev_evaluation: bool = True,
    ):
        """初始化協調器

        Args:
            fixed_priority: 策略固定優先級（用於衝突解決）
            enable_ev_evaluation: 是否啟用 EV 評估（用於衝突解決）
        """
        # ===== 核心組件 =====
        self.registry = StrategyRegistry()
        self.position_manager = PositionManager()
        self.risk = RiskCoordinator()

        # Signal trackers（與 registry 同步）
        self.signal_trackers: Dict[str, SignalTracker] = {}

        # Entry evaluator（依賴 signal_trackers）
        self.entry_evaluator: Optional[EntryEvaluator] = None

        # Conflict resolver
        self.conflict_resolver = ConflictResolver(
            fixed_priority=fixed_priority,
            enable_ev_evaluation=enable_ev_evaluation,
        )

        # ===== 指標和性能追蹤 =====
        self.metrics = MetricsTracker()
        self.performance = PerformanceTracker()

        # ===== 桌號狀態 =====
        self.table_phases: Dict[str, TablePhase] = {}
        self.table_rounds: Dict[str, str] = {}

        # ===== 衝突記錄（UI 顯示用）=====
        self.conflict_history: List[ConflictRecord] = []
        self.max_conflict_history: int = 100

        # ===== 事件記錄 =====
        self._events: List[OrchestratorEvent] = []
        self._max_events = 1000

    # ===== 策略註冊 =====

    def register_strategy(
        self,
        definition: StrategyDefinition,
        tables: Optional[List[str]] = None
    ) -> None:
        """註冊策略

        Args:
            definition: 策略定義
            tables: 可選的初始綁定桌號列表
        """
        # 註冊到 registry
        self.registry.register(definition, tables=tables)

        # 創建 signal tracker
        self.signal_trackers[definition.strategy_key] = SignalTracker(definition.entry)

        # 註冊到風控
        self.risk.register_strategy(definition)

        # 重新創建 entry evaluator（因為 strategies 變更）
        self._recreate_entry_evaluator()

    def attach_strategy(self, table_id: str, strategy_key: str) -> None:
        """將策略綁定到桌號"""
        self.registry.attach_to_table(table_id, strategy_key)

    def _recreate_entry_evaluator(self) -> None:
        """重新創建 EntryEvaluator（當策略變更時）"""
        self.entry_evaluator = EntryEvaluator(
            strategies=self.registry.list_all_strategies(),
            signal_trackers=self.signal_trackers,
            risk_coordinator=self.risk,
        )

    # ===== 階段轉換和決策生成 =====

    def update_table_phase(
        self,
        table_id: str,
        round_id: Optional[str],
        phase: TablePhase,
        timestamp: float,
    ) -> List[BetDecision]:
        """更新桌號階段並生成決策

        Args:
            table_id: 桌號
            round_id: 局號（可選）
            phase: 新階段
            timestamp: 時間戳

        Returns:
            下注決策列表（僅在 BETTABLE 階段返回）
        """
        # 開始追蹤階段轉換性能
        phase_op_id = f"phase_{table_id}_{phase.value}_{time.time()}"
        self.performance.start_operation(phase_op_id)

        self.table_phases[table_id] = phase
        if round_id:
            self.table_rounds[table_id] = round_id

        self.risk.refresh()

        decisions = []
        if phase == TablePhase.BETTABLE and round_id:
            # 評估策略並生成決策
            decisions = self._evaluate_and_decide(table_id, round_id, timestamp)

        # 結束階段轉換追蹤
        self.performance.end_operation(
            phase_op_id,
            PerformanceTracker.OP_PHASE_TRANSITION,
            success=True,
            metadata={
                "table_id": table_id,
                "phase": phase.value,
                "decisions_generated": len(decisions)
            }
        )

        return decisions

    def _evaluate_and_decide(
        self,
        table_id: str,
        round_id: str,
        timestamp: float
    ) -> List[BetDecision]:
        """評估策略並生成最終決策

        流程：
        1. EntryEvaluator 評估觸發條件 → 候選決策
        2. ConflictResolver 解決衝突 → 批准的決策
        3. 創建倉位和最終決策
        """
        if not self.entry_evaluator:
            return []

        # 開始追蹤決策生成性能
        decision_op_id = f"decision_{table_id}_{round_id}"
        self.performance.start_operation(decision_op_id)

        # ===== 階段 1: 評估策略觸發條件 =====
        strategies_for_table = self.registry.get_strategies_for_table(table_id)

        candidates = self.entry_evaluator.evaluate_table(
            table_id=table_id,
            round_id=round_id,
            strategies_for_table=strategies_for_table,
            timestamp=timestamp,
        )

        # ===== 階段 2: 衝突解決 =====
        conflict_op_id = f"conflict_{table_id}_{round_id}"
        self.performance.start_operation(conflict_op_id)

        resolution = self.conflict_resolver.resolve(
            candidates,
            self.registry.list_all_strategies()
        )

        # 結束衝突解決追蹤
        self.performance.end_operation(
            conflict_op_id,
            PerformanceTracker.OP_CONFLICT_RESOLUTION,
            success=True,
            metadata={
                "table_id": table_id,
                "round_id": round_id,
                "candidates_count": len(candidates),
                "approved_count": len(resolution.approved),
                "rejected_count": len(resolution.rejected)
            }
        )

        # 記錄衝突解決過程（用於 UI 顯示）
        if len(candidates) > 1:
            self._record_conflict_resolution(
                table_id, round_id, candidates, resolution, timestamp
            )

        # 處理被拒絕的決策
        for rejected_decision, reason, message in resolution.rejected:
            self._record_event(
                "INFO",
                f"Line {rejected_decision.strategy_key} rejected: {message}",
                {
                    "table": table_id,
                    "round": round_id,
                    "reason": reason.value,
                    "direction": rejected_decision.direction.value,
                },
            )
            # 重置被拒絕的 Line 狀態
            self.entry_evaluator.reset_line_state(table_id, rejected_decision.strategy_key)

        # ===== 階段 3: 生成最終決策並創建倉位 =====
        final_decisions: List[BetDecision] = []

        for approved in resolution.approved:
            # 創建倉位
            self.position_manager.create_position(
                table_id=table_id,
                round_id=round_id,
                strategy_key=approved.strategy_key,
                direction=approved.direction.value,
                amount=approved.amount,
                layer_index=approved.layer_index,
                timestamp=timestamp,
            )

            # 創建最終決策
            decision = BetDecision(
                table_id=table_id,
                round_id=round_id,
                strategy_key=approved.strategy_key,
                direction=BetDirection(approved.direction.value),
                amount=approved.amount,
                layer_index=approved.layer_index,
                created_at=timestamp,
                reason=f"Approved by conflict resolver",
            )
            final_decisions.append(decision)

            # 記錄信號觸發事件
            self.metrics.record_event(EventRecord(
                event_type=EventType.SIGNAL_TRIGGERED,
                timestamp=timestamp,
                table_id=table_id,
                round_id=round_id,
                strategy_key=approved.strategy_key,
            ))

            self._record_event(
                "INFO",
                f"✅ 決策生成: {approved.strategy_key} | {approved.direction.value} | {approved.amount} | layer={approved.layer_index}",
                {"table": table_id, "round": round_id},
            )

        # 結束決策生成追蹤
        self.performance.end_operation(
            decision_op_id,
            PerformanceTracker.OP_DECISION_GENERATION,
            success=True,
            metadata={
                "table_id": table_id,
                "round_id": round_id,
                "decisions_count": len(final_decisions)
            }
        )

        return final_decisions

    # ===== 結果處理 =====

    def handle_result(
        self,
        table_id: str,
        round_id: str,
        winner: Optional[str],
        timestamp: float,
    ) -> None:
        """處理結果並結算倉位

        Args:
            table_id: 桌號
            round_id: 局號
            winner: 贏家 ("B", "P", "T", None)
            timestamp: 時間戳
        """
        self._record_event(
            "INFO",
            f"🎯 handle_result: table={table_id} round={round_id} winner={winner}",
            {"table": table_id},
        )

        winner_code = winner.upper()[0] if winner else None

        for strategy_key, definition in self.registry.get_strategies_for_table(table_id):
            tracker = self.signal_trackers[strategy_key]

            # 檢查是否有待處理倉位（參與局 vs 觀察局）
            settlement = self.position_manager.settle_position(
                table_id=table_id,
                round_id=round_id,
                strategy_key=strategy_key,
                winner=winner_code,
            )

            if not settlement:
                # ✅ 觀察局：沒有倉位，記錄到歷史
                self._record_event(
                    "DEBUG",
                    f"📝 觀察局：記錄到歷史 | strategy={strategy_key}",
                    {"table": table_id},
                )

                tracker.record(table_id, round_id, winner_code or "", timestamp)

                # 記錄歷史狀態
                history_after = tracker._get_recent_winners(table_id, 10)
                self._record_event(
                    "INFO",
                    f"📊 策略 {strategy_key} | 桌號 {table_id} | 開獎 {winner_code} | 歷史記錄 {history_after}",
                    {"table": table_id},
                )
                continue

            # ✅ 參與局：有倉位，結算（不記錄到歷史）
            self._record_event(
                "INFO",
                f"💰 參與局：結算倉位 | strategy={strategy_key} | outcome={settlement.outcome.value} | pnl={settlement.pnl_delta:.2f}",
                {"table": table_id},
            )

            # 獲取 line_state 和 progression
            line_state = self.entry_evaluator.get_line_state(table_id, strategy_key)
            progression = self.entry_evaluator.get_progression(table_id, strategy_key)

            if line_state and progression:
                # 記錄結果到 line_state
                line_state.record_outcome(settlement.outcome, settlement.pnl_delta)

                # 記錄度量數據
                line_metrics = self.metrics.get_or_create_line_metrics(table_id, strategy_key)
                outcome_str = "win" if settlement.outcome == LayerOutcome.WIN else \
                             "loss" if settlement.outcome == LayerOutcome.LOSS else "skip"

                line_metrics.update_layer_stats(
                    layer_index=settlement.position.layer_index,
                    stake=progression.config.sequence[min(
                        settlement.position.layer_index,
                        len(progression.config.sequence) - 1
                    )],
                    outcome=outcome_str,
                    pnl_delta=settlement.pnl_delta,
                )

                # 記錄結果事件
                self.metrics.record_event(EventRecord(
                    event_type=EventType.OUTCOME_RECORDED,
                    timestamp=timestamp,
                    table_id=table_id,
                    round_id=round_id,
                    strategy_key=strategy_key,
                    layer_index=settlement.position.layer_index,
                    amount=settlement.position.amount,
                    pnl_delta=settlement.pnl_delta,
                    outcome=settlement.outcome.value,
                ))

                # 層數前進/重置
                old_index = progression.index
                if settlement.outcome in (LayerOutcome.WIN, LayerOutcome.LOSS):
                    progression.advance(settlement.outcome)
                    if progression.index != old_index:
                        # 記錄層數變化
                        event_type = EventType.LINE_RESET if progression.index < old_index else EventType.LINE_PROGRESSED
                        self.metrics.record_event(EventRecord(
                            event_type=event_type,
                            timestamp=timestamp,
                            table_id=table_id,
                            strategy_key=strategy_key,
                            layer_index=progression.index,
                            metadata={"from_layer": old_index} if event_type == EventType.LINE_PROGRESSED else {},
                        ))

                # 重置為 IDLE
                line_state.phase = LinePhase.IDLE

            # 風控檢查
            risk_events = self.risk.record(
                strategy_key=strategy_key,
                table_id=table_id,
                pnl_delta=settlement.pnl_delta,
                outcome=settlement.outcome,
                metadata=definition.metadata,
            )

            for event in risk_events:
                # TODO: 應用風控事件（凍結 line, 停止策略等）
                self.metrics.record_event(EventRecord(
                    event_type=EventType.RISK_TRIGGERED,
                    timestamp=timestamp,
                    table_id=table_id,
                    strategy_key=strategy_key,
                    reason=f"Risk event: {event}",
                ))

    # ===== 衝突記錄 =====

    def _record_conflict_resolution(
        self,
        table_id: str,
        round_id: str,
        candidates: List[PendingDecision],
        resolution: Any,
        timestamp: float,
    ) -> None:
        """記錄衝突解決過程（UI 顯示用）"""
        record = ConflictRecord(
            table_id=table_id,
            round_id=round_id,
            timestamp=timestamp,
            candidates_count=len(candidates),
            approved_count=len(resolution.approved),
            rejected_count=len(resolution.rejected),
            candidates=[
                {
                    "strategy_key": c.strategy_key,
                    "direction": c.direction.value,
                    "amount": c.amount,
                    "layer_index": c.layer_index,
                }
                for c in candidates
            ],
            rejections=[
                {
                    "strategy_key": d.strategy_key,
                    "reason": r.value,
                    "message": m,
                }
                for d, r, m in resolution.rejected
            ],
        )

        self.conflict_history.append(record)
        if len(self.conflict_history) > self.max_conflict_history:
            self.conflict_history = self.conflict_history[-self.max_conflict_history:]

    # ===== 事件記錄 =====

    def _record_event(self, level: str, message: str, metadata: Dict[str, str]) -> None:
        """記錄事件（調試和 UI 顯示用）"""
        event = OrchestratorEvent(level=level, message=message, metadata=metadata)
        self._events.append(event)

        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

    def get_recent_events(self, limit: int = 100) -> List[OrchestratorEvent]:
        """獲取最近的事件"""
        return list(reversed(self._events[-limit:]))

    # ===== 狀態查詢 =====

    def snapshot(self) -> Dict[str, Any]:
        """獲取協調器狀態快照（調試用）"""
        return {
            "total_strategies": self.registry.count(),
            "total_pending_positions": self.position_manager.count_pending(),
            "total_exposure": self.position_manager.tracker.get_total_exposure(),
            "table_phases": {tid: phase.value for tid, phase in self.table_phases.items()},
            "recent_events_count": len(self._events),
            "conflict_history_count": len(self.conflict_history),
            "registry_snapshot": self.registry.snapshot(),
            "position_manager_snapshot": self.position_manager.snapshot(),
            "evaluator_snapshot": self.entry_evaluator.snapshot() if self.entry_evaluator else {},
        }

    def get_statistics(self) -> Dict[str, Any]:
        """獲取統計信息"""
        return {
            "strategies": self.registry.count(),
            "pending_positions": self.position_manager.count_pending(),
            "position_stats": self.position_manager.get_statistics(),
        }
