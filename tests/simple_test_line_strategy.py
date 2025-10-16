# tests/simple_test_line_strategy.py
"""
Line 策略系統簡單測試（不需要 pytest）

測試內容：
1. 正負注碼反打機制
2. 多策略衝突解決
3. 度量記錄與追蹤
"""
import sys
import time
from pathlib import Path

# 添加項目根目錄到路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

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


def test_positive_stake():
    """測試1：正數注碼跟隨 Pattern 方向"""
    print("\n=== 測試1：正數注碼跟隨方向 ===")

    orchestrator = LineOrchestrator(bankroll=10000)
    strategy = create_simple_strategy("BB_P", "BB then bet P", [10, 20, 40])
    orchestrator.register_strategy(strategy, ["T1"])

    # 模擬兩個莊家
    orchestrator.handle_result("T1", "R1", "Banker", time.time())
    orchestrator.handle_result("T1", "R2", "Banker", time.time())

    # 第三局應該觸發，押閒 (Player)
    decisions = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())

    assert len(decisions) == 1, f"Expected 1 decision, got {len(decisions)}"
    assert decisions[0].direction.value == "P", f"Expected direction 'P', got {decisions[0].direction.value}"
    assert decisions[0].amount == 10.0, f"Expected amount 10.0, got {decisions[0].amount}"

    print("✅ 通過：正數注碼正確跟隨方向（押閒）")
    return True


def test_negative_stake():
    """測試2：負數注碼反打（反向）"""
    print("\n=== 測試2：負數注碼反打 ===")

    orchestrator = LineOrchestrator(bankroll=10000)
    strategy = create_simple_strategy("BB_P_反打", "BB then bet P", [-10, -20, -40])
    orchestrator.register_strategy(strategy, ["T1"])

    # 模擬兩個莊家
    orchestrator.handle_result("T1", "R1", "Banker", time.time())
    orchestrator.handle_result("T1", "R2", "Banker", time.time())

    # 第三局應該觸發，但因為負數所以反打押莊 (Banker)
    decisions = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())

    assert len(decisions) == 1, f"Expected 1 decision, got {len(decisions)}"
    assert decisions[0].direction.value == "B", f"Expected direction 'B' (反打), got {decisions[0].direction.value}"
    assert decisions[0].amount == 10.0, f"Expected amount 10.0, got {decisions[0].amount}"

    print("✅ 通過：負數注碼正確反打（押莊）")
    return True


def test_opposite_direction_conflict():
    """測試3：同桌同手相反方向禁止"""
    print("\n=== 測試3：同桌同手相反方向衝突 ===")

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
    assert len(decisions) == 1, f"Expected 1 decision (conflict resolved), got {len(decisions)}"

    # 檢查事件記錄
    events = orchestrator.drain_events()
    rejected_events = [e for e in events if "rejected" in e.message.lower()]
    assert len(rejected_events) >= 1, "Expected at least 1 rejection event"

    print(f"✅ 通過：衝突解決成功，只允許 1 個方向下注，{len(rejected_events)} 個策略被拒絕")
    return True


def test_metrics_tracking():
    """測試4：度量記錄與追蹤"""
    print("\n=== 測試4：度量記錄與追蹤 ===")

    orchestrator = LineOrchestrator(bankroll=10000)
    strategy = create_simple_strategy("test_strategy", "BB then bet P", [10, 20, 40])
    orchestrator.register_strategy(strategy, ["T1"])

    # 模擬觸發和下注
    orchestrator.handle_result("T1", "R1", "Banker", time.time())
    orchestrator.handle_result("T1", "R2", "Banker", time.time())
    decisions = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())

    assert len(decisions) == 1, f"Expected 1 decision, got {len(decisions)}"

    # 檢查度量
    metrics = orchestrator.metrics.get_line_metrics("T1", "test_strategy")
    assert metrics is not None, "Metrics should exist"
    assert metrics.trigger_count >= 1, f"Expected trigger_count >= 1, got {metrics.trigger_count}"
    assert metrics.armed_count >= 1, f"Expected armed_count >= 1, got {metrics.armed_count}"
    assert metrics.entered_count == 1, f"Expected entered_count == 1, got {metrics.entered_count}"
    assert metrics.current_layer == 0, f"Expected current_layer == 0, got {metrics.current_layer}"

    print("✅ 通過：度量記錄正確")
    print(f"   - 觸發次數: {metrics.trigger_count}")
    print(f"   - Armed 次數: {metrics.armed_count}")
    print(f"   - 進場次數: {metrics.entered_count}")
    print(f"   - 當前層數: {metrics.current_layer}")
    return True


def test_layer_pnl_tracking():
    """測試5：層級 PnL 追蹤"""
    print("\n=== 測試5：層級 PnL 追蹤 ===")

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
    assert metrics.total_wins == 1, f"Expected 1 win, got {metrics.total_wins}"
    assert metrics.total_losses == 0, f"Expected 0 losses, got {metrics.total_losses}"
    assert metrics.total_pnl == 10.0, f"Expected PnL 10.0, got {metrics.total_pnl}"

    # 檢查層級統計
    assert 0 in metrics.layer_stats, "Layer 0 should exist in stats"
    layer0 = metrics.layer_stats[0]
    assert layer0.win_count == 1, f"Expected 1 win in layer 0, got {layer0.win_count}"
    assert layer0.pnl == 10.0, f"Expected PnL 10.0 in layer 0, got {layer0.pnl}"

    print("✅ 通過：PnL 追蹤正確")
    print(f"   - 總勝: {metrics.total_wins}, 總負: {metrics.total_losses}")
    print(f"   - 總 PnL: {metrics.total_pnl}")
    print(f"   - 第 0 層 PnL: {layer0.pnl}")
    return True


def test_loss_advance():
    """測試6：馬丁格爾 - 輸進下一層"""
    print("\n=== 測試6：馬丁格爾 - 輸進下一層 ===")

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
    assert decisions[0].amount == 10.0, f"Expected 10.0 (layer 0), got {decisions[0].amount}"
    print(f"   第1次下注: {decisions[0].amount} (第0層)")

    # 輸了
    orchestrator.handle_result("T1", "R3", "Banker", time.time())

    # 第二次下注
    orchestrator.handle_result("T1", "R4", "Banker", time.time())
    orchestrator.handle_result("T1", "R5", "Banker", time.time())
    decisions = orchestrator.update_table_phase("T1", "R6", TablePhase.BETTABLE, time.time())
    assert decisions[0].amount == 20.0, f"Expected 20.0 (layer 1), got {decisions[0].amount}"
    print(f"   第2次下注: {decisions[0].amount} (第1層)")

    print("✅ 通過：輸後正確進入下一層")
    return True


def test_cross_table_accumulate():
    """測試7：跨桌層數累進"""
    print("\n=== 測試7：跨桌層數累進 (Accumulate 模式) ===")

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
    decisions_t1 = orchestrator.update_table_phase("T1", "R3", TablePhase.BETTABLE, time.time())
    print(f"   T1 第1次: {decisions_t1[0].amount}")
    orchestrator.handle_result("T1", "R3", "Banker", time.time())  # 輸

    # T2 應該接續第二層
    orchestrator.handle_result("T2", "R1", "Banker", time.time())
    orchestrator.handle_result("T2", "R2", "Banker", time.time())
    decisions_t2 = orchestrator.update_table_phase("T2", "R3", TablePhase.BETTABLE, time.time())

    assert decisions_t2[0].amount == 20.0, f"Expected 20.0 (shared layer 1), got {decisions_t2[0].amount}"
    print(f"   T2 第1次: {decisions_t2[0].amount} (接續T1的層數)")

    print("✅ 通過：跨桌層數累進正確")
    return True


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("Line Strategy System Tests")
    print("="*60)

    tests = [
        ("Positive Stake Follows Direction", test_positive_stake),
        ("Negative Stake Inverts Direction", test_negative_stake),
        ("Opposite Direction Conflict", test_opposite_direction_conflict),
        ("Metrics Tracking", test_metrics_tracking),
        ("Layer PnL Tracking", test_layer_pnl_tracking),
        ("Martingale Loss Advance", test_loss_advance),
        ("Cross Table Accumulate", test_cross_table_accumulate),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"❌ 失敗：{name}")
            print(f"   錯誤: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ 錯誤：{name}")
            print(f"   異常: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
