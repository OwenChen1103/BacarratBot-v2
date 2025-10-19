#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
測試 Line 策略觸發流程
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from pathlib import Path
from src.autobet.lines import LineOrchestrator, load_strategy_definitions, TablePhase

def test_line_trigger_flow():
    """測試完整的觸發流程"""

    # 1. 初始化 LineOrchestrator
    orchestrator = LineOrchestrator(
        bankroll=10000,
        per_hand_risk_pct=0.05,
        per_table_risk_pct=0.1,
        max_concurrent_tables=3,
        min_unit=1.0,
    )

    # 2. 載入策略
    strategy_dir = Path("configs/line_strategies")
    if strategy_dir.exists():
        definitions = load_strategy_definitions(strategy_dir)
        print(f"✅ 載入 {len(definitions)} 條策略")
        for definition in definitions.values():
            orchestrator.register_strategy(definition)
            print(f"   - 策略 {definition.strategy_key}: {definition.entry.pattern}")
    else:
        print(f"❌ 策略目錄不存在: {strategy_dir}")
        return

    # 3. 模擬接收兩個 B 結果
    table_id = "WG8"

    print("\n📊 開始模擬流程...")

    # 第一個 B
    print("\n1️⃣ 收到第一個 B")
    orchestrator.handle_result(table_id, "round_001", "B", 1000.0)

    # 檢查 SignalTracker 的歷史
    tracker = orchestrator.signal_trackers.get("1")
    if tracker:
        history_2 = tracker._get_recent_winners(table_id, 2)  # 取最近 2 個
        all_history = tracker.history.get(table_id)
        print(f"   SignalTracker 歷史(最近2個): {history_2}")
        print(f"   SignalTracker 原始歷史: {list(all_history) if all_history else []}")

    # 刷新事件
    events = orchestrator.drain_events()
    print(f"   事件數量: {len(events)}")
    for event in events:
        print(f"   [{event.level}] {event.message}")

    # 第二個 B
    print("\n2️⃣ 收到第二個 B")
    orchestrator.handle_result(table_id, "round_002", "B", 1001.0)

    # 檢查 SignalTracker 的歷史
    if tracker:
        history_2 = tracker._get_recent_winners(table_id, 2)  # 取最近 2 個
        all_history = tracker.history.get(table_id)
        print(f"   SignalTracker 歷史(最近2個): {history_2}")
        print(f"   SignalTracker 原始歷史: {list(all_history) if all_history else []}")

    # 刷新事件
    events = orchestrator.drain_events()
    print(f"   事件數量: {len(events)}")
    for event in events:
        print(f"   [{event.level}] {event.message}")

    # 3. 觸發 BETTABLE 階段
    print("\n3️⃣ 觸發 BETTABLE 階段檢查")
    decisions = orchestrator.update_table_phase(table_id, "round_003", TablePhase.BETTABLE, 1002.0)

    print(f"   產生決策數量: {len(decisions)}")
    for decision in decisions:
        print(f"   ✅ 決策: 策略={decision.strategy_key} 方向={decision.direction.value} 金額={decision.amount} 層={decision.layer_index}")

    # 刷新事件
    events = orchestrator.drain_events()
    print(f"\n   事件數量: {len(events)}")
    for event in events:
        print(f"   [{event.level}] {event.message} {event.metadata}")

    # 4. 檢查快照
    print("\n4️⃣ 檢查狀態快照")
    snapshot = orchestrator.snapshot()
    print(f"   Capital: {snapshot['capital']}")
    print(f"   Lines: {snapshot['lines']}")

if __name__ == "__main__":
    test_line_trigger_flow()
