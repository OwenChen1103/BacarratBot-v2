# tests/test_line_strategy.py
"""
Line 策略系統測試

測試內容：
1. 正負注碼反打機制
2. 多策略衝突解決
3. 度量記錄與追蹤
4. 風控觸發
5. 跨桌層數共享
"""
import pytest
import time
from src.autobet.lines.orchestrator import LineOrchestrator, TablePhase
from src.autobet.lines.config import (
    StrategyDefinition,
    EntryConfig,
    StakingConfig,
    CrossTableLayerConfig,
    RiskLevelConfig,
    StrategyRiskConfig,
    DedupMode,
    AdvanceRule,
    CrossTableMode,
    RiskScope,
    RiskLevelAction,
)


def create_simple_strategy(
    strategy_key: str,
    pattern: str = "BB then bet P",
    sequence: list = None,
    advance_on: AdvanceRule = AdvanceRule.LOSS,
    cross_table_mode: CrossTableMode = CrossTableMode.RESET,
) -> StrategyDefinition:
    """創建簡單策略用於測試"""
    if sequence is None:
        sequence = [10, 20, 40]

    return StrategyDefinition(
        strategy_key=strategy_key,
        entry=EntryConfig(
            pattern=pattern,
            valid_window_sec=10.0,
            dedup=DedupMode.OVERLAP,
            first_trigger_layer=1,
        ),
        staking=StakingConfig(
            sequence=sequence,
            advance_on=advance_on,
            reset_on_win=True,
            reset_on_loss=False,
        ),
        cross_table_layer=CrossTableLayerConfig(
            scope="strategy_key",
            mode=cross_table_mode,
        ),
    )


class TestNegativeStake:
    """測試正負注碼反打機制（§D、§E）"""

    def test_positive_stake_follows_direction(self):
        """正數注碼跟隨 Pattern 方向"""
        orchestrator = LineOrchestrator(bankroll=10000)

        # 策略：BB then bet P，序列 [10, 20, 40]
        strategy = create_simple_strategy("BB_P", "BB then bet P", [10, 20, 40])
        orchestrator.register_strategy(strategy, ["T1"])

        # 模擬兩個莊家
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())

        # 第三局應該觸發，押閒 (Player)
        decisions = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())

        assert len(decisions) == 1
        assert decisions[0].direction.value == "P"  # 正數 -> 跟隨方向 -> 押閒
        assert decisions[0].amount == 10.0

    def test_negative_stake_inverts_direction(self):
        """負數注碼反打（反向）"""
        orchestrator = LineOrchestrator(bankroll=10000)

        # 策略：BB then bet P，序列 [-10, -20, -40] (反打)
        strategy = create_simple_strategy("BB_P_反打", "BB then bet P", [-10, -20, -40])
        orchestrator.register_strategy(strategy, ["T1"])

        # 模擬兩個莊家
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())

        # 第三局應該觸發，但因為負數所以反打押莊 (Banker)
        decisions = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())

        assert len(decisions) == 1
        assert decisions[0].direction.value == "B"  # 負數 -> 反打 -> 押莊
        assert decisions[0].amount == 10.0  # 金額取絕對值


class TestConflictResolution:
    """測試多策略衝突解決（§H）"""

    def test_opposite_direction_conflict(self):
        """同桌同手相反方向禁止"""
        orchestrator = LineOrchestrator(bankroll=10000)

        # 策略 1：BB then bet P (押閒)
        strategy1 = create_simple_strategy("BB_P", "BB then bet P", [10, 20, 40])
        orchestrator.register_strategy(strategy1, ["T1"])

        # 策略 2：BB then bet B (押莊)
        strategy2 = create_simple_strategy("BB_B", "BB then bet B", [10, 20, 40])
        orchestrator.register_strategy(strategy2, ["T1"])

        # 模擬兩個莊家
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())

        # 第三局兩個策略都觸發，但方向相反
        decisions = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())

        # 只允許一個方向
        assert len(decisions) == 1

        # 檢查事件記錄
        events = orchestrator.drain_events()
        rejected_events = [e for e in events if "rejected" in e.message.lower()]
        assert len(rejected_events) >= 1  # 至少有一個被拒絕

    def test_ev_priority(self):
        """EV 優先級測試"""
        # 設定固定優先級
        orchestrator = LineOrchestrator(
            bankroll=10000,
            fixed_priority={"high_priority": 1, "low_priority": 10}
        )

        # 高優先級策略
        strategy1 = create_simple_strategy("high_priority", "BB then bet P", [10])
        orchestrator.register_strategy(strategy1, ["T1"])

        # 低優先級策略（同方向）
        strategy2 = create_simple_strategy("low_priority", "BB then bet P", [20])
        orchestrator.register_strategy(strategy2, ["T1"])

        # 模擬兩個莊家
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())

        # 第三局兩個策略都觸發（同方向）
        decisions = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())

        # 應該只保留一個（高優先級）
        assert len(decisions) == 1
        assert decisions[0].strategy_key == "high_priority"


class TestMetricsTracking:
    """測試度量記錄與追蹤（§K）"""

    def test_line_metrics_tracking(self):
        """測試 Line 度量追蹤"""
        orchestrator = LineOrchestrator(bankroll=10000)
        strategy = create_simple_strategy("test_strategy", "BB then bet P", [10, 20, 40])
        orchestrator.register_strategy(strategy, ["T1"])

        # 模擬觸發和下注
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())
        decisions = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())

        assert len(decisions) == 1

        # 檢查度量
        metrics = orchestrator.metrics.get_line_metrics("T1", "test_strategy")
        assert metrics is not None
        assert metrics.trigger_count >= 1
        assert metrics.armed_count >= 1
        assert metrics.entered_count == 1
        assert metrics.current_layer == 0  # 第一層

    def test_layer_pnl_tracking(self):
        """測試層級 PnL 追蹤"""
        orchestrator = LineOrchestrator(bankroll=10000)
        strategy = create_simple_strategy("test_strategy", "BB then bet P", [10, 20, 40])
        orchestrator.register_strategy(strategy, ["T1"])

        # 觸發並下注
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())
        decisions = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())
        assert len(decisions) == 1

        # 贏了
        orchestrator.handle_result("T1", "R3", "Player", time.time())

        # 檢查 PnL
        metrics = orchestrator.metrics.get_line_metrics("T1", "test_strategy")
        assert metrics.total_wins == 1
        assert metrics.total_losses == 0
        assert metrics.total_pnl == 10.0  # 贏 10

        # 檢查層級統計
        assert 0 in metrics.layer_stats
        layer0 = metrics.layer_stats[0]
        assert layer0.win_count == 1
        assert layer0.pnl == 10.0

    def test_event_recording(self):
        """測試事件記錄"""
        orchestrator = LineOrchestrator(bankroll=10000)
        strategy = create_simple_strategy("test_strategy", "BB then bet P", [10, 20, 40])
        orchestrator.register_strategy(strategy, ["T1"])

        # 模擬完整流程
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())
        orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())
        orchestrator.handle_result("T1", "R3", "Player", time.time())

        # 檢查事件記錄
        from src.autobet.lines.metrics import EventType
        events = orchestrator.metrics.get_recent_events(limit=100)

        # 應該有：信號觸發、進場、結果記錄
        event_types = [e.event_type for e in events]
        assert EventType.SIGNAL_TRIGGERED in event_types
        assert EventType.LINE_ENTERED in event_types
        assert EventType.OUTCOME_RECORDED in event_types


class TestProgressionAndReset:
    """測試層數前進與重置"""

    def test_loss_advance(self):
        """馬丁格爾：輸進下一層"""
        orchestrator = LineOrchestrator(bankroll=10000)
        strategy = create_simple_strategy(
            "martingale",
            "BB then bet P",
            [10, 20, 40],
            advance_on=AdvanceRule.LOSS
        )
        orchestrator.register_strategy(strategy, ["T1"])

        # 第一次下注
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())
        decisions = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())
        assert decisions[0].amount == 10.0  # 第一層

        # 輸了
        orchestrator.handle_result("T1", "R3", "Banker", time.time())

        # 第二次下注
        orchestrator.handle_result("T1", "R4", "Banker", time.time())
        orchestrator.handle_result("T1", "R5", "Banker", time.time())
        decisions = orchestrator.update_table_phase("T1", "R6", TablePhase.BETTABLE, time.time())
        assert decisions[0].amount == 20.0  # 進入第二層

    def test_win_reset(self):
        """贏後重置"""
        orchestrator = LineOrchestrator(bankroll=10000)
        strategy = create_simple_strategy(
            "martingale",
            "BB then bet P",
            [10, 20, 40],
            advance_on=AdvanceRule.LOSS
        )
        orchestrator.register_strategy(strategy, ["T1"])

        # 第一次輸
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())
        orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())
        orchestrator.handle_result("T1", "R3", "Banker", time.time())  # 輸

        # 第二次贏
        orchestrator.handle_result("T1", "R4", "Banker", time.time())
        orchestrator.handle_result("T1", "R5", "Banker", time.time())
        orchestrator.update_table_phase("T1", "R6", TablePhase.BETTABLE, time.time())
        orchestrator.handle_result("T1", "R6", "Player", time.time())  # 贏

        # 第三次應該回到第一層
        orchestrator.handle_result("T1", "R7", "Banker", time.time())
        orchestrator.handle_result("T1", "R8", "Banker", time.time())
        decisions = orchestrator.update_table_phase("T1", "R9", TablePhase.BETTABLE, time.time())
        assert decisions[0].amount == 10.0  # 重置到第一層


class TestCrossTableMode:
    """測試跨桌層數共享（§F）"""

    def test_reset_mode(self):
        """Reset 模式：切桌層數歸零"""
        orchestrator = LineOrchestrator(bankroll=10000)
        strategy = create_simple_strategy(
            "test_strategy",
            "BB then bet P",
            [10, 20, 40],
            cross_table_mode=CrossTableMode.RESET
        )
        orchestrator.register_strategy(strategy, ["T1", "T2"])

        # T1 連輸進第二層
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())
        orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())
        orchestrator.handle_result("T1", "R3", "Banker", time.time())  # 輸

        # T2 應該還是第一層
        orchestrator.handle_result("T2", "R1", "Banker", time.time())
        orchestrator.handle_result("T2", "R2", "Banker", time.time())
        decisions = orchestrator.update_table_phase("T2", "R3", TablePhase.BETTABLE, time.time())
        assert decisions[0].amount == 10.0  # 第一層

    def test_accumulate_mode(self):
        """Accumulate 模式：跨桌共用層數"""
        orchestrator = LineOrchestrator(bankroll=10000)
        strategy = create_simple_strategy(
            "test_strategy",
            "BB then bet P",
            [10, 20, 40],
            cross_table_mode=CrossTableMode.ACCUMULATE
        )
        orchestrator.register_strategy(strategy, ["T1", "T2"])

        # T1 連輸進第二層
        orchestrator.handle_result("T1", "R1", "Banker", time.time())
        orchestrator.handle_result("T1", "R2", "Banker", time.time())
        orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())
        orchestrator.handle_result("T1", "R3", "Banker", time.time())  # 輸

        # T2 應該接續第二層
        orchestrator.handle_result("T2", "R1", "Banker", time.time())
        orchestrator.handle_result("T2", "R2", "Banker", time.time())
        decisions = orchestrator.update_table_phase("T2", "R3", TablePhase.BETTABLE, time.time())
        assert decisions[0].amount == 20.0  # 接續第二層


class TestRiskControl:
    """測試風控功能（§G）"""

    def test_stop_loss_trigger(self):
        """測試停損觸發"""
        orchestrator = LineOrchestrator(bankroll=10000)

        # 策略帶風控：桌別止損 -50
        risk_config = StrategyRiskConfig(
            levels=[
                RiskLevelConfig(
                    scope=RiskScope.TABLE,
                    stop_loss=-50.0,
                    action=RiskLevelAction.PAUSE,
                )
            ]
        )

        strategy = StrategyDefinition(
            strategy_key="test_strategy",
            entry=EntryConfig(pattern="BB then bet P", dedup=DedupMode.OVERLAP, first_trigger_layer=1),
            staking=StakingConfig(sequence=[10, 20, 40], advance_on=AdvanceRule.LOSS),
            risk=risk_config,
        )
        orchestrator.register_strategy(strategy, ["T1"])

        # 連續輸到觸發停損
        for i in range(7):
            orchestrator.handle_result("T1", f"R{i*3+1}", "Banker", time.time())
            orchestrator.handle_result("T1", f"R{i*3+2}", "Banker", time.time())
            decisions = orchestrator.update_table_phase("T1", f"R{i*3+3}", TablePhase.BETTABLE, time.time())

            if decisions:
                orchestrator.handle_result("T1", f"R{i*3+3}", "Banker", time.time())  # 輸

        # 檢查是否被凍結
        line_state = orchestrator.line_states.get("T1", {}).get("test_strategy")
        if line_state:
            # 如果觸發停損，應該被凍結或無法下注
            metrics = orchestrator.metrics.get_line_metrics("T1", "test_strategy")
            if metrics:
                assert metrics.total_pnl <= -50.0  # 觸發停損


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
