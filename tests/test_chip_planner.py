# tests/test_chip_planner.py
# -*- coding: utf-8 -*-
"""
測試 SmartChipPlanner 的湊注邏輯
"""

import sys
import io
from pathlib import Path

# 設定 stdout 為 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加專案根目錄到路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.autobet.chip_planner import Chip, SmartChipPlanner, BettingPolicy


def test_basic_planning():
    """測試基本湊注"""
    print("=" * 60)
    print("測試 1: 基本湊注（2 顆籌碼: 1K + 100）")
    print("=" * 60)

    chips = [
        Chip(slot=1, value=100, label="100", calibrated=True),
        Chip(slot=2, value=1000, label="1K", calibrated=True),
    ]

    planner = SmartChipPlanner(chips)

    test_amounts = [100, 500, 1000, 1500, 2000, 2500]

    for amount in test_amounts:
        plan = planner.plan_bet(amount)

        print(f"\n目標: {amount} 元")
        print(f"  成功: {plan.success}")
        print(f"  實際: {plan.actual_amount} 元")
        print(f"  配方: {plan.recipe}")

        if plan.warnings:
            for warning in plan.warnings:
                print(f"  ⚠️  {warning}")

        if not plan.success:
            print(f"  ❌ 失敗: {plan.reason}")


def test_with_max_clicks():
    """測試點擊次數限制"""
    print("\n" + "=" * 60)
    print("測試 2: 點擊次數限制（最多 8 次）")
    print("=" * 60)

    chips = [
        Chip(slot=1, value=100, label="100", calibrated=True),
        Chip(slot=2, value=1000, label="1K", calibrated=True),
    ]

    planner = SmartChipPlanner(chips, BettingPolicy(fallback=BettingPolicy.FLOOR))

    # 測試會超過點擊限制的金額
    test_amounts = [800, 1000, 1500, 2000]
    max_clicks = 8

    for amount in test_amounts:
        plan = planner.plan_bet(amount, max_clicks=max_clicks)

        print(f"\n目標: {amount} 元 (限制 {max_clicks} 次點擊)")
        print(f"  成功: {plan.success}")
        print(f"  實際: {plan.actual_amount} 元")
        print(f"  點擊: {plan.clicks} 次")
        print(f"  配方: {plan.recipe}")

        if plan.warnings:
            for warning in plan.warnings:
                print(f"  ⚠️  {warning}")


def test_with_large_chips():
    """測試使用大面額籌碼"""
    print("\n" + "=" * 60)
    print("測試 3: 使用多種面額籌碼 (100/1K/5K)")
    print("=" * 60)

    chips = [
        Chip(slot=1, value=100, label="100", calibrated=True),
        Chip(slot=2, value=1000, label="1K", calibrated=True),
        Chip(slot=3, value=5000, label="5K", calibrated=True),
    ]

    planner = SmartChipPlanner(chips)

    test_amounts = [500, 1500, 5000, 6300, 12000]

    for amount in test_amounts:
        plan = planner.plan_bet(amount)

        print(f"\n目標: {amount} 元")
        print(f"  成功: {plan.success}")
        print(f"  實際: {plan.actual_amount} 元")
        print(f"  點擊: {plan.clicks} 次")
        print(f"  配方: {plan.recipe}")


def test_recipe_preview():
    """測試批量配方預覽"""
    print("\n" + "=" * 60)
    print("測試 4: 批量配方預覽（用於 UI 顯示）")
    print("=" * 60)

    chips = [
        Chip(slot=1, value=100, label="100", calibrated=True),
        Chip(slot=2, value=1000, label="1K", calibrated=True),
    ]

    planner = SmartChipPlanner(chips)

    # 模擬策略序列
    sequence = [1000, 2000, 4000, 8000]

    recipes = planner.get_recipe_preview(sequence)

    print("\n策略序列配方:")
    for i, amount in enumerate(sequence, 1):
        print(f"  第 {i} 層 ({amount} 元): {recipes[amount]}")


def test_validation():
    """測試金額驗證"""
    print("\n" + "=" * 60)
    print("測試 5: 金額驗證（限額檢查）")
    print("=" * 60)

    chips = [
        Chip(slot=1, value=100, label="100", calibrated=True),
        Chip(slot=2, value=1000, label="1K", calibrated=True),
    ]

    planner = SmartChipPlanner(chips)

    min_bet = 100
    max_bet = 10000
    max_clicks = 8

    test_cases = [
        (50, "低於最小"),
        (100, "最小值"),
        (1500, "正常"),
        (10000, "最大值"),
        (15000, "超過最大"),
    ]

    for amount, desc in test_cases:
        is_valid, error = planner.validate_amount(amount, min_bet, max_bet, max_clicks)

        status = "✓" if is_valid else "✗"
        print(f"\n{status} {amount} 元 ({desc})")
        if error:
            print(f"    錯誤: {error}")


if __name__ == "__main__":
    test_basic_planning()
    test_with_max_clicks()
    test_with_large_chips()
    test_recipe_preview()
    test_validation()

    print("\n" + "=" * 60)
    print("所有測試完成！")
    print("=" * 60)
