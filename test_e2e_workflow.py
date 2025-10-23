# test_e2e_workflow.py
"""
端到端測試腳本
測試從策略觸發 → 下注執行 → 結果計算的完整流程
"""

import time
from src.autobet.lines import LineOrchestrator, StrategyDefinition, EntryConfig, StakingConfig, DedupMode
from src.autobet.payout_manager import PayoutManager


def test_dedup_modes():
    """測試 Dedup 模式"""
    print("=" * 60)
    print("測試 1: Dedup 模式")
    print("=" * 60)

    # 策略: PP then bet B
    entry_overlap = EntryConfig(pattern="PP then bet B", dedup=DedupMode.OVERLAP)
    entry_strict = EntryConfig(pattern="PP then bet B", dedup=DedupMode.STRICT)
    staking = StakingConfig(sequence=[100, 200, 400])

    # 測試 OVERLAP 模式
    print("\n【OVERLAP 模式】")
    orch_overlap = LineOrchestrator()
    strategy_overlap = StrategyDefinition(
        strategy_key="test_overlap",
        entry=entry_overlap,
        staking=staking
    )
    orch_overlap.register_strategy(strategy_overlap, tables=["main"])

    # 模擬歷史: P → P → P
    from src.autobet.lines.signal import SignalTracker
    tracker_overlap = SignalTracker(entry_overlap)
    tracker_overlap.record("main", "round-1", "P", time.time())
    tracker_overlap.record("main", "round-2", "P", time.time())

    trigger1 = tracker_overlap.should_trigger("main", "round-3", time.time())
    print(f"  round-3 (第2個P): {'✅ 觸發' if trigger1 else '❌ 不觸發'}")

    tracker_overlap.record("main", "round-3", "P", time.time())
    trigger2 = tracker_overlap.should_trigger("main", "round-4", time.time())
    print(f"  round-4 (第3個P): {'✅ 觸發' if trigger2 else '❌ 不觸發'}")

    # 測試 STRICT 模式
    print("\n【STRICT 模式】")
    tracker_strict = SignalTracker(entry_strict)
    tracker_strict.record("main", "round-1", "P", time.time())
    tracker_strict.record("main", "round-2", "P", time.time())

    trigger3 = tracker_strict.should_trigger("main", "round-3", time.time())
    print(f"  round-3 (第2個P): {'✅ 觸發' if trigger3 else '❌ 不觸發'}")

    tracker_strict.record("main", "round-3", "P", time.time())
    trigger4 = tracker_strict.should_trigger("main", "round-4", time.time())
    print(f"  round-4 (第3個P): {'✅ 觸發' if trigger4 else '❌ 不觸發'}")

    # 驗證結果
    assert trigger1 is True, "OVERLAP 模式應該在第2個P觸發"
    assert trigger2 is True, "OVERLAP 模式應該在第3個P再次觸發"
    assert trigger3 is True, "STRICT 模式應該在第2個P觸發"
    assert trigger4 is False, "STRICT 模式不應該在第3個P觸發 (歷史重疊)"

    print("\n✅ Dedup 模式測試通過")


def test_payout_calculation():
    """測試賠率計算"""
    print("\n" + "=" * 60)
    print("測試 2: 賠率計算")
    print("=" * 60)

    pm = PayoutManager()
    print(f"\n當前賠率: {pm.get_rates_summary()}")

    # 測試案例
    test_cases = [
        # (金額, 結果, 方向, 預期盈虧)
        (100, "WIN", "banker", 95.0),   # 莊家贏 100 → +95
        (100, "WIN", "player", 100.0),  # 閒家贏 100 → +100
        (100, "WIN", "tie", 800.0),     # 和局贏 100 → +800
        (100, "LOSS", "banker", -100.0),  # 失敗 → -100
        (100, "SKIPPED", "banker", 0.0),  # 和局跳過 → 0
        (200, "WIN", "banker", 190.0),  # 莊家贏 200 → +190
    ]

    print("\n測試案例:")
    for amount, outcome, direction, expected in test_cases:
        result = pm.calculate_pnl(amount, outcome, direction)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {amount}元 {direction} {outcome} → {result:.1f} (預期 {expected:.1f})")
        assert result == expected, f"計算錯誤: {result} != {expected}"

    print("\n✅ 賠率計算測試通過")


def test_complete_workflow():
    """測試完整工作流程"""
    print("\n" + "=" * 60)
    print("測試 3: 完整工作流程")
    print("=" * 60)

    # 創建策略
    entry = EntryConfig(pattern="BPP then bet B", dedup=DedupMode.STRICT)
    staking = StakingConfig(
        sequence=[100, 200, 400, 800],
        advance_on="loss",
        reset_on_win=True
    )
    strategy = StrategyDefinition(
        strategy_key="martingale_test",
        entry=entry,
        staking=staking
    )

    # 創建 Orchestrator
    orch = LineOrchestrator()
    orch.register_strategy(strategy, tables=["main"])

    print("\n【流程模擬】")
    print("策略: BPP then bet B (閒閒莊 打莊)")
    print("注碼序列: [100, 200, 400, 800]")
    print("進層規則: 輸進層, 贏重置\n")

    # 階段1: 歷史累積
    print("階段1: 累積歷史")
    orch.handle_result("main", "round-1", "B", time.time())
    print("  round-1: 開獎 B (莊)")
    time.sleep(0.1)

    orch.handle_result("main", "round-2", "P", time.time())
    print("  round-2: 開獎 P (閒)")
    time.sleep(0.1)

    # 階段2: 模式匹配，觸發下注
    print("\n階段2: 模式匹配 [B, P, P] ✅")
    orch.handle_result("main", "round-3", "P", time.time())
    print("  round-3: 開獎 P (閒) → 歷史 [B, P, P]")

    # 觸發檢查
    decisions = orch.update_table_phase("main", "round-4", "bettable", time.time())
    if decisions:
        decision = decisions[0]
        print(f"  ✅ 觸發下注: {decision.direction.value} {decision.amount}元 (第{decision.layer_index + 1}層)")
        assert decision.direction.value == "B", "應該下注莊家"
        assert decision.amount == 100, "第一層應該下注100元"
    else:
        raise AssertionError("應該要觸發下注")

    # 階段3: 開獎失敗 (下注莊家, 開閒家)
    print("\n階段3: 開獎結果 - 失敗")
    orch.handle_result("main", "round-4", "P", time.time())
    print("  round-4: 開獎 P (閒) → 失敗 -100元")

    # 檢查層數前進
    line_state = orch.line_states["main"]["martingale_test"]
    progression = orch._get_progression("main", "martingale_test")
    print(f"  層數更新: {progression.index + 1} (下一注 {progression.current_stake()}元)")
    assert progression.index == 1, "失敗後應該前進到第2層"
    assert line_state.pnl == -100, f"PnL應該是-100, 實際: {line_state.pnl}"

    # 階段4: 再次觸發 (第2層)
    print("\n階段4: 繼續累積歷史")
    orch.handle_result("main", "round-5", "B", time.time())
    orch.handle_result("main", "round-6", "P", time.time())
    orch.handle_result("main", "round-7", "P", time.time())
    print("  歷史: [B, P, P] ✅ 再次匹配")

    decisions2 = orch.update_table_phase("main", "round-8", "bettable", time.time())
    if decisions2:
        decision2 = decisions2[0]
        print(f"  ✅ 觸發下注: {decision2.direction.value} {decision2.amount}元 (第{decision2.layer_index + 1}層)")
        assert decision2.amount == 200, "第二層應該下注200元"

    # 階段5: 開獎成功 (下注莊家, 開莊家)
    print("\n階段5: 開獎結果 - 成功")
    orch.handle_result("main", "round-8", "B", time.time())
    print("  round-8: 開獎 B (莊) → 成功 +190元 (200 * 0.95)")

    # 檢查層數重置
    progression_after_win = orch._get_progression("main", "martingale_test")
    print(f"  層數更新: {progression_after_win.index + 1} (重置)")
    print(f"  累計 PnL: {line_state.pnl:.0f}元")

    assert progression_after_win.index == 0, "獲勝後應該重置到第1層"
    assert line_state.pnl == 90, f"PnL應該是90 (-100+190), 實際: {line_state.pnl}"

    print("\n✅ 完整工作流程測試通過")


if __name__ == "__main__":
    try:
        test_dedup_modes()
        test_payout_calculation()
        test_complete_workflow()

        print("\n" + "=" * 60)
        print("🎉 所有測試通過！")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 測試失敗: {e}")
    except Exception as e:
        print(f"\n❌ 執行錯誤: {e}")
        import traceback
        traceback.print_exc()
