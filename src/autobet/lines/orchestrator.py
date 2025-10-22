# src/autobet/lines/orchestrator.py
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .config import (
    CrossTableMode,
    EntryConfig,
    RiskLevelConfig,
    RiskLevelAction,
    RiskScope,
    StrategyDefinition,
)
from .conflict import ConflictResolver, PendingDecision, ConflictReason
from .metrics import MetricsTracker, EventRecord, EventType, LatencyMetrics
from .performance import PerformanceTracker
from .signal import SignalTracker
from .state import LayerOutcome, LayerProgression, LinePhase, LineState, LayerState


class TablePhase(str, Enum):
    IDLE = "idle"
    OPEN = "open"
    BETTABLE = "bettable"
    LOCKED = "locked"
    RESULTING = "resulting"
    SETTLED = "settled"


class BetDirection(str, Enum):
    BANKER = "B"
    PLAYER = "P"
    TIE = "T"


@dataclass
class BetDecision:
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
    candidates_count: int  # 候選決策數量
    approved_count: int    # 核准數量
    rejected_count: int    # 拒絕數量
    # 候選決策詳情
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    # 拒絕原因詳情
    rejections: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
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
class PendingPosition:
    table_id: str
    round_id: str
    strategy_key: str
    direction: BetDirection
    amount: float
    layer_index: int
    reserved_at: float = field(default_factory=time.time)


@dataclass
class OrchestratorEvent:
    level: str
    message: str
    metadata: Dict[str, str] = field(default_factory=dict)


# ❌ CapitalPool 已移除
# 系統不再使用「資金池」概念，只追蹤 PnL 並執行止盈止損
# 參考：RiskCoordinator 負責盈虧追蹤和風控

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

    def snapshot(self) -> Dict[str, Any]:
        """獲取快照（UI 顯示用）"""
        return {
            "position_count": self.get_position_count(),
            "total_exposure": self.get_total_exposure(),
            "positions": [
                {"table_id": tid, "strategy_key": sk, "amount": amt}
                for (tid, sk), amt in self.active_positions.items()
            ]
        }


@dataclass
class ScopeTracker:
    pnl: float = 0.0
    loss_streak: int = 0
    frozen_until: Optional[float] = None
    frozen_action: Optional[RiskLevelAction] = None

    def is_active(self, now: float) -> bool:
        if not self.frozen_action:
            return True
        if self.frozen_until is not None and now >= self.frozen_until:
            self.frozen_action = None
            self.frozen_until = None
            return True
        return False

    def mark_loss(self) -> None:
        self.loss_streak += 1

    def mark_win(self) -> None:
        self.loss_streak = 0


@dataclass
class RiskEvent:
    scope_key: Tuple[str, ...]
    level: RiskLevelConfig
    action: RiskLevelAction


class RiskCoordinator:
    def __init__(self) -> None:
        self._strategy_levels: Dict[str, List[RiskLevelConfig]] = {}
        self._trackers: Dict[Tuple[str, ...], ScopeTracker] = {}
        self._frozen_scopes: Dict[Tuple[str, ...], RiskLevelConfig] = {}

    def register_strategy(self, definition: StrategyDefinition) -> None:
        self._strategy_levels[definition.strategy_key] = definition.risk.sorted_levels()

    def refresh(self) -> None:
        now = time.time()
        expired: List[Tuple[str, ...]] = []
        for key, tracker in self._trackers.items():
            if tracker.frozen_action and tracker.is_active(now):
                expired.append(key)
        for key in expired:
            self._frozen_scopes.pop(key, None)

    def is_blocked(
        self,
        strategy_key: str,
        table_id: str,
        metadata: Dict[str, str],
    ) -> bool:
        now = time.time()
        for scope_key in self._iter_scopes(strategy_key, table_id, metadata):
            tracker = self._trackers.get(scope_key)
            if tracker and not tracker.is_active(now):
                return True
        return False

    def record(
        self,
        strategy_key: str,
        table_id: str,
        pnl_delta: float,
        outcome: LayerOutcome,
        metadata: Dict[str, str],
    ) -> List[RiskEvent]:
        events: List[RiskEvent] = []
        levels = self._strategy_levels.get(strategy_key, [])
        if not levels:
            return events

        for level in levels:
            scope_key = self._scope_key(level.scope, strategy_key, table_id, metadata)
            tracker = self._trackers.setdefault(scope_key, ScopeTracker())
            tracker.pnl += pnl_delta
            if outcome == LayerOutcome.LOSS:
                tracker.mark_loss()
            elif outcome == LayerOutcome.WIN:
                tracker.mark_win()

            triggered = self._evaluate_level(tracker, level)
            if triggered:
                tracker.frozen_action = level.action
                if level.cooldown_sec:
                    tracker.frozen_until = time.time() + level.cooldown_sec
                else:
                    tracker.frozen_until = None
                self._frozen_scopes[scope_key] = level
                events.append(RiskEvent(scope_key=scope_key, level=level, action=level.action))
        return events

    def _evaluate_level(self, tracker: ScopeTracker, level: RiskLevelConfig) -> bool:
        if level.action == RiskLevelAction.NOTIFY:
            # Always notify, never freeze
            return True

        if level.take_profit is not None and tracker.pnl >= level.take_profit:
            return True
        if level.stop_loss is not None and tracker.pnl <= level.stop_loss:
            return True
        if level.max_drawdown_losses is not None and tracker.loss_streak >= level.max_drawdown_losses:
            return True
        return False

    def _iter_scopes(self, strategy_key: str, table_id: str, metadata: Dict[str, str]) -> Iterable[Tuple[str, ...]]:
        levels = self._strategy_levels.get(strategy_key, [])
        for level in levels:
            yield self._scope_key(level.scope, strategy_key, table_id, metadata)

    @staticmethod
    def _scope_key(
        scope: RiskScope,
        strategy_key: str,
        table_id: str,
        metadata: Dict[str, str],
    ) -> Tuple[str, ...]:
        if scope == RiskScope.GLOBAL_DAY:
            return ("global_day",)
        if scope == RiskScope.TABLE:
            return ("table", table_id)
        if scope == RiskScope.TABLE_STRATEGY:
            return ("table_strategy", table_id, strategy_key)
        if scope == RiskScope.ALL_TABLES_STRATEGY:
            return ("all_tables_strategy", strategy_key)
        if scope == RiskScope.MULTI_STRATEGY:
            group = metadata.get("risk_group") or strategy_key
            return ("multi_strategy", group)
        return ("unknown", strategy_key)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        return {
            ":".join(key): {
                "pnl": tracker.pnl,
                "loss_streak": tracker.loss_streak,
                "frozen": bool(tracker.frozen_action),
                "frozen_action": tracker.frozen_action.value if tracker.frozen_action else None,
                "frozen_until": tracker.frozen_until,
            }
            for key, tracker in self._trackers.items()
        }

    def restore(self, state: Dict[str, Dict[str, Any]]) -> None:
        self._trackers.clear()
        self._frozen_scopes.clear()
        if not isinstance(state, dict):
            return
        for key_str, payload in state.items():
            key = tuple(key_str.split(":"))
            tracker = ScopeTracker(
                pnl=float(payload.get("pnl") or 0.0),
                loss_streak=int(payload.get("loss_streak") or 0),
            )
            frozen_action = payload.get("frozen_action")
            if frozen_action:
                tracker.frozen_action = RiskLevelAction(frozen_action)
                tracker.frozen_until = payload.get("frozen_until")
            self._trackers[key] = tracker


class LineOrchestrator:
    def __init__(
        self,
        *,
        fixed_priority: Optional[Dict[str, int]] = None,
        enable_ev_evaluation: bool = True,
    ) -> None:
        """
        初始化 LineOrchestrator

        Args:
            fixed_priority: 策略固定優先級（用於衝突解決）
            enable_ev_evaluation: 是否啟用 EV 評估（用於衝突解決）

        注意：不再需要 bankroll, per_hand_risk_pct 等參數
              系統只追蹤 PnL，不做資金檢查
        """
        self.strategies: Dict[str, StrategyDefinition] = {}
        self.signal_trackers: Dict[str, SignalTracker] = {}
        self.line_states: Dict[str, Dict[str, LineState]] = defaultdict(dict)
        self.table_phases: Dict[str, TablePhase] = {}
        self.table_rounds: Dict[str, str] = {}
        self.attachments: Dict[str, List[str]] = defaultdict(list)
        self._events: List[OrchestratorEvent] = []
        self._line_progressions: Dict[Tuple[str, str], LayerProgression] = {}
        self._shared_progressions: Dict[str, LayerProgression] = {}
        self._pending: Dict[Tuple[str, str, str], PendingPosition] = {}

        # ✅ 倉位追蹤器（只用於 UI 顯示，不影響下注決策）
        self.positions = PositionTracker()

        # ✅ 風險協調器（追蹤 PnL 和止盈止損）
        self.risk = RiskCoordinator()

        # ✅ 衝突解決器
        self.conflict_resolver = ConflictResolver(
            fixed_priority=fixed_priority,
            enable_ev_evaluation=enable_ev_evaluation,
        )

        # ✅ 指標追蹤器
        self.metrics = MetricsTracker()
        self.performance = PerformanceTracker()
        self.conflict_history: List[ConflictRecord] = []
        self.max_conflict_history: int = 100

    # ------------------------------------------------------------------
    def register_strategy(self, definition: StrategyDefinition, tables: Optional[Iterable[str]] = None) -> None:
        self.strategies[definition.strategy_key] = definition
        self.signal_trackers[definition.strategy_key] = SignalTracker(definition.entry)
        self.risk.register_strategy(definition)
        if tables:
            for table_id in tables:
                self.attach_strategy(table_id, definition.strategy_key)

    # ------------------------------------------------------------------
    def attach_strategy(self, table_id: str, strategy_key: str) -> None:
        if strategy_key not in self.strategies:
            raise KeyError(f"Strategy '{strategy_key}' not registered")
        if strategy_key not in self.attachments[table_id]:
            self.attachments[table_id].append(strategy_key)
        self._ensure_line_state(table_id, strategy_key)

    # ------------------------------------------------------------------
    def update_table_phase(
        self,
        table_id: str,
        round_id: Optional[str],
        phase: TablePhase,
        timestamp: float,
    ) -> List[BetDecision]:
        # 開始追蹤階段轉換性能
        phase_op_id = f"phase_{table_id}_{phase.value}_{time.time()}"
        self.performance.start_operation(phase_op_id)

        self.table_phases[table_id] = phase
        if round_id:
            self.table_rounds[table_id] = round_id

        self.risk.refresh()

        decisions = []
        if phase == TablePhase.BETTABLE and round_id:
            # 開始追蹤決策生成性能
            decision_op_id = f"decision_{table_id}_{round_id}"
            self.performance.start_operation(decision_op_id)

            decisions = self._evaluate_entries(table_id, round_id, timestamp)

            # 結束決策生成追蹤
            duration_ms = self.performance.end_operation(
                decision_op_id,
                PerformanceTracker.OP_DECISION_GENERATION,
                success=True,
                metadata={
                    "table_id": table_id,
                    "round_id": round_id,
                    "decisions_count": len(decisions)
                }
            )

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

    # ------------------------------------------------------------------
    def handle_result(
        self,
        table_id: str,
        round_id: str,
        winner: Optional[str],
        timestamp: float,
    ) -> None:
        # 🔍 CRITICAL: 記錄 handle_result 被調用
        self._record_event(
            "INFO",
            f"🎯 handle_result 被調用: table={table_id} round={round_id} winner={winner}",
            {"table": table_id},
        )

        winner_code = winner.upper()[0] if winner else None

        for strategy_key, definition in self._strategies_for_table(table_id):
            tracker = self.signal_trackers[strategy_key]

            # 🔍 CRITICAL: 記錄呼叫 tracker.record 之前的狀態
            history_before = tracker._get_recent_winners(table_id, 10)
            self._record_event(
                "DEBUG",
                f"📝 呼叫 tracker.record 之前: strategy={strategy_key} table={table_id} 歷史長度={len(tracker.history.get(table_id, []))} 近期={history_before}",
                {"table": table_id},
            )

            tracker.record(table_id, round_id, winner_code or "", timestamp)

            # 🔍 CRITICAL: 記錄呼叫 tracker.record 之後的狀態
            history_after_record = tracker._get_recent_winners(table_id, 10)
            self._record_event(
                "DEBUG",
                f"✅ tracker.record 完成: strategy={strategy_key} table={table_id} winner_code={winner_code} 歷史長度={len(tracker.history.get(table_id, []))} 近期={history_after_record}",
                {"table": table_id},
            )

            # 記錄關鍵事件：開獎結果和歷史記錄
            history_after = tracker._get_recent_winners(table_id, 10)
            self._record_event(
                "INFO",
                f"📊 策略 {strategy_key} | 桌號 {table_id} | 開獎 {winner_code} | 歷史記錄 {history_after}",
                {"table": table_id},
            )

            pending_key = (table_id, round_id, strategy_key)
            position = self._pending.pop(pending_key, None)
            if not position:
                # 結果到達但找不到對應的待處理倉位
                # 可能原因：
                # 1. 決策被資金池拒絕
                # 2. 決策被衝突解決器拒絕
                # 3. 決策執行失敗
                # 4. round_id 不匹配
                self._record_event(
                    "WARNING",
                    f"⚠️ 結果無匹配的待處理倉位: table={table_id} round={round_id} strategy={strategy_key}",
                    {"table": table_id}
                )

                # 仍然記錄到 tracker，避免歷史數據遺漏
                # （tracker.record 已在前面第421行執行，所以這裡只需 continue）
                continue

            # ✅ 移除倉位追蹤（結算後）
            self.positions.remove_position(table_id, strategy_key)

            line_state = self._ensure_line_state(table_id, strategy_key)
            progression = self._get_progression(table_id, strategy_key)

            outcome = self._determine_outcome(position.direction, winner_code)
            pnl_delta = self._pnl_delta(position.amount, outcome)
            line_state.record_outcome(outcome, pnl_delta)

            # 記錄度量數據
            line_metrics = self.metrics.get_or_create_line_metrics(table_id, strategy_key)
            outcome_str = "win" if outcome == LayerOutcome.WIN else "loss" if outcome == LayerOutcome.LOSS else "skip"
            line_metrics.update_layer_stats(
                layer_index=position.layer_index,
                stake=progression.config.sequence[min(position.layer_index, len(progression.config.sequence) - 1)],
                outcome=outcome_str,
                pnl_delta=pnl_delta,
            )

            # 記錄結果事件
            self.metrics.record_event(EventRecord(
                event_type=EventType.OUTCOME_RECORDED,
                timestamp=timestamp,
                table_id=table_id,
                round_id=round_id,
                strategy_key=strategy_key,
                layer_index=position.layer_index,
                amount=position.amount,
                pnl_delta=pnl_delta,
                outcome=outcome.value,
            ))

            # 層數前進/重置
            old_index = progression.index
            if outcome in (LayerOutcome.WIN, LayerOutcome.LOSS):
                progression.advance(outcome)
                if progression.index != old_index:
                    # 記錄層數變化
                    if progression.index < old_index:
                        self.metrics.record_event(EventRecord(
                            event_type=EventType.LINE_RESET,
                            timestamp=timestamp,
                            table_id=table_id,
                            strategy_key=strategy_key,
                            layer_index=progression.index,
                        ))
                    else:
                        self.metrics.record_event(EventRecord(
                            event_type=EventType.LINE_PROGRESSED,
                            timestamp=timestamp,
                            table_id=table_id,
                            strategy_key=strategy_key,
                            layer_index=progression.index,
                            metadata={"from_layer": old_index},
                        ))

            # release to idle
            line_state.phase = LinePhase.IDLE

            # 風控檢查
            risk_events = self.risk.record(
                strategy_key=strategy_key,
                table_id=table_id,
                pnl_delta=pnl_delta,
                outcome=outcome,
                metadata=definition.metadata,
            )
            for event in risk_events:
                self._apply_risk_event(event, table_id, strategy_key)
                # 記錄風控觸發事件
                self.metrics.record_event(EventRecord(
                    event_type=EventType.RISK_TRIGGERED,
                    timestamp=timestamp,
                    table_id=table_id,
                    strategy_key=strategy_key,
                    reason=f"scope={':'.join(event.scope_key)}, action={event.action.value}",
                ))

            self._record_event(
                "INFO",
                f"Line {strategy_key} resolved {outcome.value} amount={position.amount}",
                {
                    "table": table_id,
                    "round": round_id,
                    "strategy": strategy_key,
                    "pnl": f"{pnl_delta:.2f}",
                    "layer": str(position.layer_index),
                },
            )

    # ------------------------------------------------------------------
    def _evaluate_entries(self, table_id: str, round_id: str, timestamp: float) -> List[BetDecision]:
        """
        評估並生成下注決策

        流程：
        1. 收集所有候選決策
        2. 使用衝突解決器篩選（§H）
        3. 預留資金並生成最終決策
        """
        strategies = list(self._strategies_for_table(table_id))
        if not strategies:
            return []

        # 階段 1: 收集所有候選決策
        candidates: List[PendingDecision] = []

        for strategy_key, definition in strategies:
            line_state = self._ensure_line_state(table_id, strategy_key)
            tracker = self.signal_trackers[strategy_key]

            # 檢查凍結狀態
            if line_state.frozen:
                self._record_event(
                    "DEBUG",
                    f"Line {strategy_key} frozen, skip entry",
                    {"table": table_id},
                )
                continue

            # 檢查風控封鎖
            if self.risk.is_blocked(strategy_key, table_id, definition.metadata):
                self._record_event(
                    "DEBUG",
                    f"Risk scope blocked line {strategy_key}",
                    {"table": table_id},
                )
                continue

            # 檢查信號觸發
            should_trigger_result = tracker.should_trigger(table_id, round_id, timestamp)

            # DEBUG: 記錄 SignalTracker 的歷史和檢查結果
            required_length = len(tracker._pattern_sequence(definition.entry.pattern))
            all_history = tracker.history.get(table_id)
            history_list = list(all_history) if all_history else []
            recent_winners = tracker._get_recent_winners(table_id, required_length)

            if not should_trigger_result:
                # 顯示策略檢查狀態（未觸發）
                if len(history_list) > 0:
                    self._record_event(
                        "INFO",
                        f"⏳ 策略 {strategy_key} | 模式 {definition.entry.pattern} | 歷史長度 {len(history_list)}/{required_length} | 近期 {recent_winners} | ❌ 未觸發",
                        {"table": table_id},
                    )
                continue

            # 顯示策略觸發
            self._record_event(
                "INFO",
                f"✅ 策略 {strategy_key} 觸發！| 模式 {definition.entry.pattern} | 歷史 {recent_winners}",
                {"table": table_id},
            )

            # 記錄信號觸發事件
            line_metrics = self.metrics.get_or_create_line_metrics(
                table_id, strategy_key,
                first_trigger_layer=definition.entry.first_trigger_layer,
                cross_table_mode=definition.cross_table_layer.mode.value,
            )
            line_metrics.record_trigger()
            self.metrics.record_event(EventRecord(
                event_type=EventType.SIGNAL_TRIGGERED,
                timestamp=timestamp,
                table_id=table_id,
                round_id=round_id,
                strategy_key=strategy_key,
            ))

            # 設置為 ARMED 狀態
            line_state.phase = LinePhase.ARMED
            line_state.armed_count += 1
            line_metrics.record_armed()

            # 檢查首次觸發層
            required_triggers = 1 if definition.entry.first_trigger_layer >= 1 else 2
            if line_state.armed_count < required_triggers:
                self._record_event(
                    "DEBUG",
                    f"Line {strategy_key} armed (count={line_state.armed_count}), waiting first_trigger_layer",
                    {"table": table_id},
                )
                continue

            # 計算方向和金額
            progression = self._get_progression(table_id, strategy_key)
            desired_stake = progression.current_stake()
            base_direction = self._derive_base_direction(definition.entry)
            direction, amount = self._resolve_direction(desired_stake, base_direction)

            # 創建候選決策
            from .conflict import BetDirection as ConflictBetDirection
            candidate = PendingDecision(
                table_id=table_id,
                round_id=round_id,
                strategy_key=strategy_key,
                direction=ConflictBetDirection(direction.value),
                amount=amount,
                layer_index=progression.index,
                timestamp=timestamp,
                metadata=definition.metadata,
            )
            candidates.append(candidate)

        # 階段 2: 衝突解決
        conflict_op_id = f"conflict_{table_id}_{round_id}"
        self.performance.start_operation(conflict_op_id)

        resolution = self.conflict_resolver.resolve(candidates, self.strategies)

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
        if len(candidates) > 1:  # 只記錄有多個候選決策的情況
            self._record_conflict_resolution(
                table_id, round_id, candidates, resolution, timestamp
            )

        # 記錄被拒絕的決策
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
            line_state = self._ensure_line_state(table_id, rejected_decision.strategy_key)
            line_state.phase = LinePhase.IDLE
            line_state.armed_count = 0

        # 階段 3: 生成最終決策（不再檢查資金）
        final_decisions: List[BetDecision] = []

        for approved in resolution.approved:
            # ✅ 直接使用批准的金額，不做資金檢查
            actual_amount = approved.amount

            # 追蹤倉位（僅用於 UI 顯示）
            self.positions.add_position(table_id, approved.strategy_key, actual_amount)

            # 創建最終決策
            decision = BetDecision(
                table_id=table_id,
                round_id=round_id,
                strategy_key=approved.strategy_key,
                direction=BetDirection(approved.direction.value),
                amount=actual_amount,
                layer_index=approved.layer_index,
                reason=self.conflict_resolver.get_priority_explanation(approved, self.strategies),
            )

            # 記錄待處理倉位
            self._pending[(table_id, round_id, approved.strategy_key)] = PendingPosition(
                table_id=table_id,
                round_id=round_id,
                strategy_key=approved.strategy_key,
                direction=BetDirection(approved.direction.value),
                amount=actual_amount,
                layer_index=approved.layer_index,
            )

            # 更新 Line 狀態
            line_state = self._ensure_line_state(table_id, approved.strategy_key)
            line_state.enter(approved.layer_index, actual_amount, round_id)
            line_state.mark_waiting()

            # 記錄進場事件與度量
            line_metrics = self.metrics.get_or_create_line_metrics(
                table_id, approved.strategy_key
            )
            line_metrics.record_entered(approved.layer_index)

            # 獲取實際注碼（含正負號）
            progression = self._get_progression(table_id, approved.strategy_key)
            actual_stake = progression.config.sequence[min(approved.layer_index, len(progression.config.sequence) - 1)]

            self.metrics.record_event(EventRecord(
                event_type=EventType.LINE_ENTERED,
                timestamp=time.time(),
                table_id=table_id,
                round_id=round_id,
                strategy_key=approved.strategy_key,
                layer_index=approved.layer_index,
                stake=actual_stake,
                direction=approved.direction.value,
                amount=actual_amount,
                reason=decision.reason,
            ))

            final_decisions.append(decision)

            # 記錄事件
            self._record_event(
                "INFO",
                f"Line {approved.strategy_key} enter {approved.direction.value} amount={actual_amount}",
                {
                    "table": table_id,
                    "round": round_id,
                    "layer": str(approved.layer_index),
                    "stake": str(actual_stake),
                    "priority": decision.reason,
                },
            )

        return final_decisions

    # ------------------------------------------------------------------
    def _derive_base_direction(self, entry: EntryConfig) -> BetDirection:
        pattern = entry.pattern.upper()
        if "BET" in pattern:
            suffix = pattern.split("BET", 1)[1]
            for ch in suffix:
                if ch in {"B", "P", "T"}:
                    return BetDirection(ch)
        return BetDirection.PLAYER

    def _resolve_direction(self, stake: int, base_direction: BetDirection) -> Tuple[BetDirection, float]:
        amount = abs(stake)
        if stake == 0:
            return base_direction, 0.0
        if stake > 0:
            return base_direction, float(amount)
        return self._invert_direction(base_direction), float(amount)

    @staticmethod
    def _invert_direction(direction: BetDirection) -> BetDirection:
        if direction == BetDirection.BANKER:
            return BetDirection.PLAYER
        if direction == BetDirection.PLAYER:
            return BetDirection.BANKER
        return BetDirection.TIE

    @staticmethod
    def _determine_outcome(direction: BetDirection, winner: Optional[str]) -> LayerOutcome:
        if winner is None:
            return LayerOutcome.CANCELLED
        if winner == "T":
            if direction == BetDirection.TIE:
                return LayerOutcome.WIN
            return LayerOutcome.SKIPPED
        if winner == direction.value:
            return LayerOutcome.WIN
        return LayerOutcome.LOSS

    @staticmethod
    def _pnl_delta(amount: float, outcome: LayerOutcome) -> float:
        if outcome == LayerOutcome.WIN:
            return float(amount)
        if outcome == LayerOutcome.LOSS:
            return float(-amount)
        return 0.0

    def _apply_risk_event(self, event: RiskEvent, table_id: str, strategy_key: str) -> None:
        scope = ":".join(event.scope_key)
        metadata = {"scope": scope, "action": event.action.value}

        if event.action == RiskLevelAction.NOTIFY:
            self._record_event("INFO", f"Risk notify {scope}", metadata)
            return

        affected_lines: List[Tuple[str, str]] = []
        if event.level.scope == RiskScope.GLOBAL_DAY:
            affected_lines = [(tbl, strat) for tbl, strategies in self.line_states.items() for strat in strategies]
        elif event.level.scope == RiskScope.TABLE:
            affected_lines = [(table_id, strat) for strat in self.line_states.get(table_id, {})]
        elif event.level.scope == RiskScope.TABLE_STRATEGY:
            affected_lines = [(table_id, strategy_key)]
        elif event.level.scope == RiskScope.ALL_TABLES_STRATEGY:
            affected_lines = [
                (tbl, strat)
                for tbl, strategies in self.line_states.items()
                for strat in strategies
                if strat == strategy_key
            ]
        elif event.level.scope == RiskScope.MULTI_STRATEGY:
            group = event.scope_key[-1]
            affected_lines = [
                (tbl, strat)
                for tbl, strategies in self.line_states.items()
                for strat in strategies
                if self.strategies[strat].metadata.get("risk_group", strat) == group
            ]

        until = time.time() + event.level.cooldown_sec if event.level.cooldown_sec else None
        for tbl, strat in affected_lines:
            state = self._ensure_line_state(tbl, strat)
            state.freeze(until)
        self._record_event("WARNING", f"Risk freeze applied {scope}", metadata)

    def _ensure_line_state(self, table_id: str, strategy_key: str) -> LineState:
        if strategy_key not in self.line_states[table_id]:
            self.line_states[table_id][strategy_key] = LineState(strategy_key=strategy_key, table_id=table_id)
        return self.line_states[table_id][strategy_key]

    def _get_progression(self, table_id: str, strategy_key: str) -> LayerProgression:
        definition = self.strategies[strategy_key]
        if definition.cross_table_layer.mode == CrossTableMode.ACCUMULATE:
            progression = self._shared_progressions.get(strategy_key)
            if not progression:
                progression = LayerProgression(definition.staking)
                self._shared_progressions[strategy_key] = progression
            return progression

        key = (table_id, strategy_key)
        if key not in self._line_progressions:
            self._line_progressions[key] = LayerProgression(definition.staking)
        return self._line_progressions[key]

    def _strategies_for_table(self, table_id: str) -> Iterable[Tuple[str, StrategyDefinition]]:
        strategy_keys = self.attachments.get(table_id)
        if not strategy_keys:
            # Default to all strategies if none explicitly attached
            strategy_keys = list(self.strategies.keys())
            if strategy_keys:
                self.attachments[table_id] = strategy_keys.copy()
        for key in strategy_keys:
            definition = self.strategies.get(key)
            if definition:
                yield key, definition

    def drain_events(self) -> List[OrchestratorEvent]:
        events = self._events[:]
        self._events.clear()
        return events

    def _record_conflict_resolution(
        self,
        table_id: str,
        round_id: str,
        candidates: List[PendingDecision],
        resolution: ConflictResolution,
        timestamp: float
    ) -> None:
        """記錄衝突解決過程（用於 UI 顯示）"""
        # 轉換候選決策為字典格式
        candidates_data = [
            {
                "strategy_key": c.strategy_key,
                "direction": c.direction.value,
                "amount": c.amount,
                "layer_index": c.layer_index,
                "ev_score": c.ev_score,
                "priority_score": c.priority_score,
            }
            for c in candidates
        ]

        # 轉換拒絕的決策（包含原因）
        rejections_data = [
            {
                "strategy_key": decision.strategy_key,
                "direction": decision.direction.value,
                "amount": decision.amount,
                "layer_index": decision.layer_index,
                "reason": reason.value,
                "reason_detail": detail,
            }
            for decision, reason, detail in resolution.rejected
        ]

        # 創建衝突記錄
        conflict_record = ConflictRecord(
            table_id=table_id,
            round_id=round_id,
            timestamp=timestamp,
            candidates_count=len(candidates),
            approved_count=len(resolution.approved),
            rejected_count=len(resolution.rejected),
            candidates=candidates_data,
            rejections=rejections_data,
        )

        # 添加到歷史記錄
        self.conflict_history.append(conflict_record)

        # 維護歷史記錄大小限制
        if len(self.conflict_history) > self.max_conflict_history:
            self.conflict_history = self.conflict_history[-self.max_conflict_history:]

    def _record_event(self, level: str, message: str, metadata: Optional[Dict[str, str]] = None) -> None:
        self._events.append(OrchestratorEvent(level=level, message=message, metadata=metadata or {}))

    def snapshot(self) -> Dict[str, any]:
        lines_snapshot = []
        for table_id, strategies in self.line_states.items():
            for strategy_key, state in strategies.items():
                lines_snapshot.append(
                    {
                        "table": table_id,
                        "strategy": strategy_key,
                        "phase": state.phase.value,
                        "current_layer": state.current_layer_index,
                        "stake": state.layer_state.stake,
                        "pnl": state.pnl,
                        "frozen": state.frozen,
                        "cooldown_until": state.cool_down_until,
                    }
                )
        return {
            "lines": lines_snapshot,
            "positions": self.positions.snapshot(),  # ✅ 倉位追蹤（僅UI顯示）
            "risk": self.risk.snapshot(),            # ✅ 風控追蹤（PnL + 止盈止損）
            "performance": self.performance.get_summary(),
            "conflicts": [record.to_dict() for record in self.conflict_history],
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return

        self.line_states = defaultdict(dict)
        self._line_progressions.clear()
        self._shared_progressions.clear()
        self._pending.clear()
        self.table_phases.clear()
        self.table_rounds.clear()
        self.attachments = defaultdict(list)

        lines = state.get("lines") or []
        shared_max: Dict[str, int] = {}
        for entry in lines:
            table_id = entry.get("table")
            strategy_key = entry.get("strategy")
            if not table_id or not strategy_key or strategy_key not in self.strategies:
                continue

            if strategy_key not in self.attachments.get(table_id, []):
                self.attachments.setdefault(table_id, []).append(strategy_key)

            line_state = self._ensure_line_state(table_id, strategy_key)
            try:
                line_state.phase = LinePhase(entry.get("phase", "idle"))
            except Exception:
                line_state.phase = LinePhase.IDLE
            layer_index = int(entry.get("current_layer", 0) or 0)
            stake = float(entry.get("stake") or 0.0)
            line_state.current_layer_index = layer_index
            line_state.layer_state = LayerState(index=layer_index, stake=int(stake))
            line_state.pnl = float(entry.get("pnl") or 0.0)
            line_state.frozen = bool(entry.get("frozen"))
            cooldown = entry.get("cooldown_until")
            line_state.cool_down_until = float(cooldown) if cooldown is not None else None
            if line_state.frozen:
                line_state.phase = LinePhase.FROZEN

            progression = self._get_progression(table_id, strategy_key)
            progression.index = layer_index
            definition = self.strategies[strategy_key]
            if definition.cross_table_layer.mode == CrossTableMode.ACCUMULATE:
                shared_max[strategy_key] = max(shared_max.get(strategy_key, 0), layer_index)

        for strategy_key, max_layer in shared_max.items():
            progression = self._shared_progressions.get(strategy_key)
            if progression:
                progression.index = max_layer

        # ❌ capital_state 已移除（不再使用資金池）

        risk_state = state.get("risk")
        if isinstance(risk_state, dict):
            self.risk.restore(risk_state)

        self._events.append(OrchestratorEvent("INFO", "Line state restored", {}))
