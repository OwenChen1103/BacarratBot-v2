# src/autobet/lines/orchestrator.py
"""
LineOrchestrator - 重構後的協調器（原 orchestrator_v2.py）

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

重構歷史：
- 原始版本（1069行，God Class）已移至 .archived_code/orchestrator_unrefactored.py
- P1 Task 1: 拆分為 StrategyRegistry, EntryEvaluator, PositionManager
- 當前版本：協調器模式（~500行）
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

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """獲取風控狀態快照（用於 EngineWorker）

        返回格式: Dict[scope_key, tracker_data]
        - scope_key: 例如 "table:strategy"
        - tracker_data: {"pnl": 0.0, "loss_streak": 0, "frozen": False, ...}

        注意：這是佔位符實現，沒有實際追蹤 PnL
        實際 PnL 應該從 PositionManager 獲取
        """
        # 返回空字典，因為這個簡化版本沒有追蹤任何狀態
        # EngineWorker 會遍歷這個字典累加 pnl，空字典意味著 pnl = 0
        return {}


class LineOrchestrator:
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
        generate_decisions: bool = False,
    ) -> List[BetDecision]:
        """更新桌號階段並（可選）生成決策

        Args:
            table_id: 桌號
            round_id: 局號（可選）
            phase: 新階段
            timestamp: 時間戳
            generate_decisions: 是否生成決策（預設 False）

        Returns:
            下注決策列表（僅在 BETTABLE 階段且 generate_decisions=True 時返回）

        Note:
            ✅ 新邏輯：階段更新和決策生成分離
            - GameStateManager 的計時器只更新階段（generate_decisions=False）
            - 只有在「檢測到可下注畫面」時才生成決策（generate_decisions=True）
        """
        # 開始追蹤階段轉換性能
        phase_op_id = f"phase_{table_id}_{phase.value}_{time.time()}"
        self.performance.start_operation(phase_op_id)

        self.table_phases[table_id] = phase
        if round_id:
            self.table_rounds[table_id] = round_id

        self.risk.refresh()

        decisions = []
        if phase == TablePhase.BETTABLE and round_id and generate_decisions:
            # 評估策略並生成決策（只在明確要求時）
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

    def mark_strategies_waiting(
        self,
        table_id: str,
        round_id: str,
        strategy_keys: List[str],
        decisions: Optional[List[BetDecision]] = None,
    ) -> None:
        """
        標記策略為等待結果狀態

        當下注決策被執行後，需要將對應的策略標記為 WAITING_RESULT 階段，
        這樣下一次收到的結果會被用於結算，而不是作為新的信號輸入。

        Args:
            table_id: 桌號
            round_id: 局號
            strategy_keys: 需要標記的策略列表（向下兼容）
            decisions: 完整的決策列表（可選，用於獲取 layer_index）
        """
        if not self.entry_evaluator:
            return

        # 創建 strategy_key -> layer_index 映射
        layer_map = {}
        if decisions:
            for decision in decisions:
                layer_map[decision.strategy_key] = decision.layer_index

        for strategy_key in strategy_keys:
            line_state = self.entry_evaluator.get_line_state(table_id, strategy_key)
            if line_state:
                line_state.mark_waiting()
                line_state.last_round_id = round_id

                # ✅ 如果有 layer_index 資訊，同步更新
                if strategy_key in layer_map:
                    line_state.current_layer_index = layer_map[strategy_key]

                self._record_event(
                    "DEBUG",
                    f"📝 策略標記為等待結果: {strategy_key} | table={table_id} | round={round_id}",
                    {"table": table_id, "round": round_id, "strategy": strategy_key},
                )

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

                # ✅ 同步 line_state 的當前層數索引
                line_state.current_layer_index = progression.index

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
        """獲取協調器狀態快照（調試用 + UI 顯示）

        返回格式兼容舊版 orchestrator，包含 UI 需要的 "lines" 格式
        """
        # ✅ 生成 UI 兼容的 "lines" 格式
        lines = []
        if self.entry_evaluator:
            for table_id, states in self.entry_evaluator.line_states.items():
                for strategy_key, state in states.items():
                    # 獲取策略定義以提取方向
                    strategy_def = self.registry.get_strategy(strategy_key)
                    direction = "unknown"
                    if strategy_def and strategy_def.entry and strategy_def.entry.pattern:
                        # 從 pattern 推斷方向
                        # pattern 格式: "PP" -> player, "BB" -> banker, "T" -> tie
                        # 取最後一個字符作為方向
                        last_char = strategy_def.entry.pattern[-1].upper()
                        if last_char == 'P':
                            direction = "player"
                        elif last_char == 'B':
                            direction = "banker"
                        elif last_char == 'T':
                            direction = "tie"

                    # 獲取當前層級和賭注信息
                    # ✅ 從 LineState 獲取真實的當前層數索引（持久化，不受 pending position 影響）
                    progression_index = state.current_layer_index
                    current_layer = progression_index + 1  # UI 顯示從1開始

                    max_layer = 3  # 預設最大層級
                    stake = 0.0
                    next_stake = 0.0  # 下一手預計金額

                    if strategy_def and strategy_def.staking:
                        max_layer = len(strategy_def.staking.sequence)

                        # 當前層的金額（下一手即將下注的金額）
                        if progression_index < len(strategy_def.staking.sequence):
                            stake = float(strategy_def.staking.sequence[progression_index])
                            # ✅ 「預計下手」就是當前層的金額（下一手要下的那一手）
                            next_stake = stake

                    lines.append({
                        "table": table_id,
                        "strategy": strategy_key,
                        "phase": state.phase.value,  # "idle", "armed", "waiting"
                        "direction": direction,
                        "armed_count": state.armed_count,
                        "frozen": state.frozen,
                        # ✅ UI 層級顯示需要的字段
                        "current_layer": current_layer,
                        "max_layer": max_layer,
                        "stake": stake,
                        "next_stake": next_stake,
                    })

        # ✅ 生成 UI 兼容的 "risk" 格式（PnL 顯示）
        risk_data = {}
        if self.position_manager:
            # 獲取全局統計數據
            stats = self.position_manager.get_statistics()
            global_pnl = stats.get("total_pnl", 0.0)

            pos_snapshot = self.position_manager.snapshot()
            # 提取所有 table 的 PnL（從 settlement history 計算）
            for table_id in pos_snapshot.get("by_table", {}).keys():
                # 計算該桌的 PnL（從結算歷史中篩選）
                table_pnl = sum(
                    r.pnl_delta
                    for r in self.position_manager._settlement_history
                    if r.position.table_id == table_id
                )
                risk_data[f"table:{table_id}"] = {"pnl": round(table_pnl, 2)}

            # 全局 PnL
            risk_data["global_day"] = {"pnl": round(global_pnl, 2)}

        # ✅ 生成 UI 兼容的 "performance" 格式（策略資訊卡片需要）
        performance_data = {}
        if self.position_manager:
            stats = self.position_manager.get_statistics()
            # 從 metrics 獲取觸發和進場次數
            triggers = 0
            entries = 0
            if self.metrics:
                # TODO: 從 MetricsAggregator 獲取實際觸發和進場次數
                # 目前簡化為使用結算數量作為進場次數
                entries = stats.get("total_settled", 0)

            performance_data = {
                "triggers": triggers,
                "entries": entries,
                "wins": stats.get("win_count", 0),
                "losses": stats.get("loss_count", 0),
                "total_pnl": stats.get("total_pnl", 0.0),
                "win_rate": stats.get("win_rate", 0.0),
            }

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
            # ✅ UI 兼容格式
            "lines": lines,
            "risk": risk_data,
            "performance": performance_data,
        }

    def get_statistics(self) -> Dict[str, Any]:
        """獲取統計信息"""
        return {
            "strategies": self.registry.count(),
            "pending_positions": self.position_manager.count_pending(),
            "position_stats": self.position_manager.get_statistics(),
        }

    def drain_events(self) -> List[OrchestratorEvent]:
        """清空並返回所有事件（用於 EngineWorker 消費）"""
        events = self._events[:]
        self._events.clear()
        return events

    def restore_state(self, state: Dict[str, Any]) -> None:
        """從保存的狀態恢復（用於會話恢復）

        注意：重構後的組件化設計使得狀態恢復更簡單
        - 策略註冊狀態由 StrategyRegistry 管理
        - 倉位狀態由 PositionManager 管理
        - 評估器狀態由 EntryEvaluator 管理

        此方法主要恢復桌號階段和附件關聯
        """
        if not isinstance(state, dict):
            return

        # 清空當前狀態
        self.table_phases.clear()
        self.table_rounds.clear()

        # 恢復策略附件關聯
        lines = state.get("lines") or []
        for entry in lines:
            table_id = entry.get("table")
            strategy_key = entry.get("strategy")
            if not table_id or not strategy_key:
                continue

            # 確保策略已註冊
            if not self.registry.has_strategy(strategy_key):
                continue

            # 恢復附件關聯
            if not self.registry.is_attached(table_id, strategy_key):
                try:
                    self.registry.attach_to_table(table_id, strategy_key)
                except Exception:
                    # 如果附件失敗，跳過此策略
                    continue

        # 注意：由於組件化設計，大部分狀態恢復由各組件自行管理
        # EntryEvaluator 會在首次評估時自動初始化 line_states
        # PositionManager 會在首次創建倉位時自動初始化
        # 這比舊的 God Class 設計更健壯

    @property
    def line_states(self) -> Dict[str, Dict[str, Any]]:
        """委託給 EntryEvaluator 的 line_states（用於 EngineWorker 兼容性）

        注意：這是一個兼容性屬性，用於支持 EngineWorker 訪問 line_states
        實際狀態由 EntryEvaluator 管理
        """
        if self.entry_evaluator:
            return self.entry_evaluator.line_states
        return {}

    @property
    def strategies(self) -> Dict[str, StrategyDefinition]:
        """委託給 StrategyRegistry 的策略字典（用於 EngineWorker 兼容性）

        注意：這是一個兼容性屬性
        實際策略管理由 StrategyRegistry 負責

        Returns:
            {strategy_key: StrategyDefinition} 字典
        """
        return self.registry._strategies
