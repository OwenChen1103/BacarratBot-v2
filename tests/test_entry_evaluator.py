# tests/test_entry_evaluator.py
"""
EntryEvaluator 單元測試

測試覆蓋：
1. 策略觸發條件評估
2. Line 狀態管理（frozen, armed）
3. 風控封鎖檢查
4. 方向和金額計算
5. 候選決策生成
"""
import time
import pytest
from src.autobet.lines.entry_evaluator import EntryEvaluator, RiskCoordinatorProtocol
from src.autobet.lines.signal import SignalTracker
from src.autobet.lines.config import (
    StrategyDefinition,
    EntryConfig,
    StakingConfig,
    DedupMode,
    CrossTableMode,
    CrossTableLayerConfig,
)
from src.autobet.lines.state import LinePhase


class MockRiskCoordinator(RiskCoordinatorProtocol):
    """Mock 風控協調器"""
    def __init__(self):
        self.blocked_strategies = set()

    def is_blocked(self, strategy_key: str, table_id: str, metadata: dict) -> bool:
        return strategy_key in self.blocked_strategies

    def refresh(self) -> None:
        pass

    def block_strategy(self, strategy_key: str):
        """測試用：封鎖策略"""
        self.blocked_strategies.add(strategy_key)

    def unblock_strategy(self, strategy_key: str):
        """測試用：解除封鎖"""
        self.blocked_strategies.discard(strategy_key)


@pytest.fixture
def sample_strategy():
    """創建範例策略"""
    return StrategyDefinition(
        strategy_key="PB_BET_P",
        entry=EntryConfig(
            pattern="PB THEN BET P",
            dedup=DedupMode.STRICT,
            first_trigger_layer=1,
        ),
        staking=StakingConfig(
            sequence=[100, 200, 400],
            reset_on_win=True,
        ),
    )


@pytest.fixture
def another_strategy():
    """創建另一個策略"""
    return StrategyDefinition(
        strategy_key="PP_BET_B",
        entry=EntryConfig(
            pattern="PP THEN BET B",
            dedup=DedupMode.OVERLAP,
            first_trigger_layer=1,
        ),
        staking=StakingConfig(
            sequence=[50, 100],
            reset_on_win=True,
        ),
    )


@pytest.fixture
def shared_progression_strategy():
    """創建跨桌共享進度的策略"""
    return StrategyDefinition(
        strategy_key="SHARED_PROG",
        entry=EntryConfig(
            pattern="PB THEN BET P",
            dedup=DedupMode.STRICT,
        ),
        staking=StakingConfig(
            sequence=[100, 200],
            reset_on_win=True,
        ),
        cross_table_layer=CrossTableLayerConfig(
            mode=CrossTableMode.ACCUMULATE  # 跨桌共享
        ),
    )


@pytest.fixture
def evaluator(sample_strategy, another_strategy):
    """創建 EntryEvaluator"""
    strategies = {
        "PB_BET_P": sample_strategy,
        "PP_BET_B": another_strategy,
    }

    signal_trackers = {
        "PB_BET_P": SignalTracker(sample_strategy.entry),
        "PP_BET_B": SignalTracker(another_strategy.entry),
    }

    risk_coordinator = MockRiskCoordinator()

    return EntryEvaluator(
        strategies=strategies,
        signal_trackers=signal_trackers,
        risk_coordinator=risk_coordinator,
    )


class TestBasicEvaluation:
    """測試基本評估功能"""

    def test_evaluate_no_trigger_insufficient_history(self, evaluator, sample_strategy):
        """測試歷史記錄不足時不觸發"""
        table_id = "table1"
        round_id = "round1"
        timestamp = time.time()

        # 沒有記錄任何歷史
        candidates = evaluator.evaluate_table(
            table_id=table_id,
            round_id=round_id,
            strategies_for_table=[("PB_BET_P", sample_strategy)],
            timestamp=timestamp,
        )

        assert len(candidates) == 0  # 不應觸發

    def test_evaluate_trigger_with_matching_pattern(self, evaluator, sample_strategy):
        """測試模式匹配時觸發"""
        table_id = "table1"
        timestamp = time.time()

        # 記錄歷史：P, B (符合 PB 模式)
        tracker = evaluator.signal_trackers["PB_BET_P"]
        tracker.record(table_id, "round0", "P", timestamp - 2)
        tracker.record(table_id, "round1", "B", timestamp - 1)

        # 評估
        candidates = evaluator.evaluate_table(
            table_id=table_id,
            round_id="round2",
            strategies_for_table=[("PB_BET_P", sample_strategy)],
            timestamp=timestamp,
        )

        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.strategy_key == "PB_BET_P"
        assert candidate.direction.value == "P"  # BET P
        assert candidate.amount == 100  # 第一層
        assert candidate.layer_index == 0

    def test_evaluate_no_trigger_wrong_pattern(self, evaluator, sample_strategy):
        """測試模式不匹配時不觸發"""
        table_id = "table1"
        timestamp = time.time()

        # 記錄歷史：B, B (不符合 PB 模式)
        tracker = evaluator.signal_trackers["PB_BET_P"]
        tracker.record(table_id, "round0", "B", timestamp - 2)
        tracker.record(table_id, "round1", "B", timestamp - 1)

        # 評估
        candidates = evaluator.evaluate_table(
            table_id=table_id,
            round_id="round2",
            strategies_for_table=[("PB_BET_P", sample_strategy)],
            timestamp=timestamp,
        )

        assert len(candidates) == 0  # 不應觸發


class TestLineStateManagement:
    """測試 Line 狀態管理"""

    def test_line_state_armed_on_trigger(self, evaluator, sample_strategy):
        """測試觸發時 Line 狀態變為 ARMED"""
        table_id = "table1"
        timestamp = time.time()

        # 準備歷史
        tracker = evaluator.signal_trackers["PB_BET_P"]
        tracker.record(table_id, "round0", "P", timestamp - 2)
        tracker.record(table_id, "round1", "B", timestamp - 1)

        # 評估
        evaluator.evaluate_table(
            table_id=table_id,
            round_id="round2",
            strategies_for_table=[("PB_BET_P", sample_strategy)],
            timestamp=timestamp,
        )

        # 檢查 Line 狀態
        line_state = evaluator.get_line_state(table_id, "PB_BET_P")
        assert line_state is not None
        assert line_state.phase == LinePhase.ARMED
        assert line_state.armed_count == 1

    def test_frozen_line_not_evaluated(self, evaluator, sample_strategy):
        """測試凍結的 Line 不被評估"""
        table_id = "table1"
        timestamp = time.time()

        # 準備歷史
        tracker = evaluator.signal_trackers["PB_BET_P"]
        tracker.record(table_id, "round0", "P", timestamp - 2)
        tracker.record(table_id, "round1", "B", timestamp - 1)

        # 手動凍結 Line
        line_state = evaluator._ensure_line_state(table_id, "PB_BET_P")
        line_state.frozen = True
        line_state.frozen_until = timestamp + 100

        # 評估
        candidates = evaluator.evaluate_table(
            table_id=table_id,
            round_id="round2",
            strategies_for_table=[("PB_BET_P", sample_strategy)],
            timestamp=timestamp,
        )

        assert len(candidates) == 0  # 凍結狀態不應觸發

    def test_reset_line_state(self, evaluator):
        """測試重置 Line 狀態"""
        table_id = "table1"

        # 創建並修改 Line 狀態
        line_state = evaluator._ensure_line_state(table_id, "PB_BET_P")
        line_state.phase = LinePhase.ARMED
        line_state.armed_count = 3

        # 重置
        evaluator.reset_line_state(table_id, "PB_BET_P")

        # 驗證
        line_state = evaluator.get_line_state(table_id, "PB_BET_P")
        assert line_state.phase == LinePhase.IDLE
        assert line_state.armed_count == 0


class TestRiskCoordinator:
    """測試風控協調器集成"""

    def test_blocked_strategy_not_evaluated(self, evaluator, sample_strategy):
        """測試被封鎖的策略不被評估"""
        table_id = "table1"
        timestamp = time.time()

        # 準備歷史
        tracker = evaluator.signal_trackers["PB_BET_P"]
        tracker.record(table_id, "round0", "P", timestamp - 2)
        tracker.record(table_id, "round1", "B", timestamp - 1)

        # 封鎖策略
        evaluator.risk_coordinator.block_strategy("PB_BET_P")

        # 評估
        candidates = evaluator.evaluate_table(
            table_id=table_id,
            round_id="round2",
            strategies_for_table=[("PB_BET_P", sample_strategy)],
            timestamp=timestamp,
        )

        assert len(candidates) == 0  # 被封鎖不應觸發

    def test_unblocked_strategy_can_trigger(self, evaluator, sample_strategy):
        """測試解除封鎖後策略可以觸發"""
        table_id = "table1"
        timestamp = time.time()

        # 準備歷史
        tracker = evaluator.signal_trackers["PB_BET_P"]
        tracker.record(table_id, "round0", "P", timestamp - 2)
        tracker.record(table_id, "round1", "B", timestamp - 1)

        # 先封鎖再解除
        evaluator.risk_coordinator.block_strategy("PB_BET_P")
        evaluator.risk_coordinator.unblock_strategy("PB_BET_P")

        # 評估
        candidates = evaluator.evaluate_table(
            table_id=table_id,
            round_id="round2",
            strategies_for_table=[("PB_BET_P", sample_strategy)],
            timestamp=timestamp,
        )

        assert len(candidates) == 1  # 應該觸發


class TestDirectionAndAmount:
    """測試方向和金額計算"""

    def test_derive_direction_from_pattern(self, evaluator):
        """測試從模式推導方向"""
        # BET P
        entry_p = EntryConfig(pattern="PB THEN BET P", dedup=DedupMode.STRICT)
        direction_p = evaluator._derive_base_direction(entry_p)
        assert direction_p == "P"

        # BET B
        entry_b = EntryConfig(pattern="PP THEN BET B", dedup=DedupMode.STRICT)
        direction_b = evaluator._derive_base_direction(entry_b)
        assert direction_b == "B"

        # BET T
        entry_t = EntryConfig(pattern="PT THEN BET T", dedup=DedupMode.STRICT)
        direction_t = evaluator._derive_base_direction(entry_t)
        assert direction_t == "T"

    def test_resolve_direction_positive_stake(self, evaluator):
        """測試正數 stake（正向下注）"""
        direction, amount = evaluator._resolve_direction(100, "P")
        assert direction == "P"
        assert amount == 100.0

    def test_resolve_direction_negative_stake(self, evaluator):
        """測試負數 stake（反向下注）"""
        direction, amount = evaluator._resolve_direction(-100, "P")
        assert direction == "B"  # 反向
        assert amount == 100.0

    def test_resolve_direction_zero_stake(self, evaluator):
        """測試零 stake"""
        direction, amount = evaluator._resolve_direction(0, "P")
        assert direction == "P"
        assert amount == 0.0

    def test_candidate_amount_uses_progression(self, evaluator, sample_strategy):
        """測試候選決策使用正確的進度金額"""
        table_id = "table1"
        timestamp = time.time()

        # 準備歷史
        tracker = evaluator.signal_trackers["PB_BET_P"]
        tracker.record(table_id, "round0", "P", timestamp - 2)
        tracker.record(table_id, "round1", "B", timestamp - 1)

        # 第一次評估（第一層）
        candidates = evaluator.evaluate_table(
            table_id=table_id,
            round_id="round2",
            strategies_for_table=[("PB_BET_P", sample_strategy)],
            timestamp=timestamp,
        )

        assert len(candidates) == 1
        assert candidates[0].amount == 100  # sequence[0]
        assert candidates[0].layer_index == 0


class TestProgressionManagement:
    """測試層數進度管理"""

    def test_independent_progression_per_table(self, evaluator, sample_strategy):
        """測試每桌獨立進度"""
        # table1 的進度
        prog_table1 = evaluator._get_progression("table1", "PB_BET_P")
        assert prog_table1 is not None
        assert prog_table1.index == 0

        # table2 的進度（應該是獨立的）
        prog_table2 = evaluator._get_progression("table2", "PB_BET_P")
        assert prog_table2 is not None
        assert prog_table2.index == 0

        # 修改 table1 的進度
        prog_table1.index = 2

        # 驗證 table2 的進度不受影響
        prog_table2_check = evaluator._get_progression("table2", "PB_BET_P")
        assert prog_table2_check.index == 0

    def test_shared_progression_across_tables(self, shared_progression_strategy):
        """測試跨桌共享進度"""
        strategies = {"SHARED_PROG": shared_progression_strategy}
        signal_trackers = {"SHARED_PROG": SignalTracker(shared_progression_strategy.entry)}

        evaluator = EntryEvaluator(
            strategies=strategies,
            signal_trackers=signal_trackers,
        )

        # table1 和 table2 應該共享進度
        prog_table1 = evaluator._get_progression("table1", "SHARED_PROG")
        prog_table2 = evaluator._get_progression("table2", "SHARED_PROG")

        # 應該是同一個對象
        assert prog_table1 is prog_table2

        # 修改應該同步
        prog_table1.index = 1
        assert prog_table2.index == 1


class TestMultipleStrategies:
    """測試多策略評估"""

    def test_evaluate_multiple_strategies_single_table(self, evaluator, sample_strategy, another_strategy):
        """測試評估多個策略"""
        table_id = "table1"
        timestamp = time.time()

        # 準備歷史（同時符合兩個模式）
        tracker_pb = evaluator.signal_trackers["PB_BET_P"]
        tracker_pb.record(table_id, "round0", "P", timestamp - 2)
        tracker_pb.record(table_id, "round1", "B", timestamp - 1)

        tracker_pp = evaluator.signal_trackers["PP_BET_B"]
        tracker_pp.record(table_id, "round0", "P", timestamp - 2)
        tracker_pp.record(table_id, "round1", "P", timestamp - 1)

        # 評估兩個策略
        candidates = evaluator.evaluate_table(
            table_id=table_id,
            round_id="round2",
            strategies_for_table=[
                ("PB_BET_P", sample_strategy),
                ("PP_BET_B", another_strategy),
            ],
            timestamp=timestamp,
        )

        # 兩個策略都應該觸發
        assert len(candidates) == 2
        strategy_keys = {c.strategy_key for c in candidates}
        assert strategy_keys == {"PB_BET_P", "PP_BET_B"}


class TestEventRecording:
    """測試事件記錄"""

    def test_events_recorded_during_evaluation(self, evaluator, sample_strategy):
        """測試評估時記錄事件"""
        table_id = "table1"
        timestamp = time.time()

        # 準備歷史
        tracker = evaluator.signal_trackers["PB_BET_P"]
        tracker.record(table_id, "round0", "P", timestamp - 2)
        tracker.record(table_id, "round1", "B", timestamp - 1)

        # 清空事件
        evaluator.clear_events()

        # 評估
        evaluator.evaluate_table(
            table_id=table_id,
            round_id="round2",
            strategies_for_table=[("PB_BET_P", sample_strategy)],
            timestamp=timestamp,
        )

        # 檢查事件
        events = evaluator.get_recent_events()
        assert len(events) > 0

        # 應該有觸發事件
        trigger_events = [e for e in events if "觸發" in e["message"]]
        assert len(trigger_events) > 0

    def test_get_recent_events_limit(self, evaluator):
        """測試獲取事件限制"""
        # 記錄多個事件
        for i in range(50):
            evaluator._record_event("DEBUG", f"Event {i}", {})

        # 獲取最近 10 個
        events = evaluator.get_recent_events(limit=10)
        assert len(events) == 10

    def test_clear_events(self, evaluator):
        """測試清空事件"""
        evaluator._record_event("DEBUG", "Test event", {})
        assert len(evaluator._events) > 0

        evaluator.clear_events()
        assert len(evaluator._events) == 0


class TestSnapshot:
    """測試快照功能"""

    def test_snapshot_contains_all_states(self, evaluator, sample_strategy):
        """測試快照包含所有狀態"""
        table_id = "table1"

        # 創建一些狀態
        evaluator._ensure_line_state(table_id, "PB_BET_P")
        evaluator._get_progression(table_id, "PB_BET_P")

        snapshot = evaluator.snapshot()

        assert "total_strategies" in snapshot
        assert "total_line_states" in snapshot
        assert "line_progressions_count" in snapshot
        assert "line_states" in snapshot

        assert snapshot["total_strategies"] == 2
        assert snapshot["total_line_states"] >= 1
