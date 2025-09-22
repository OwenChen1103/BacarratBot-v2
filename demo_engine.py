#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
簡化演示：直接測試AutoBetEngine乾跑
不需要GUI，直接驗證狀態機和乾跑邏輯
"""
import json, time, sys, os
from PySide6.QtWidgets import QApplication
from autobet import AutoBetEngine

# 設置控制台編碼
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")

def main():
    app = QApplication([])

    # 創建測試positions.json
    positions = {
        "points": {
            "banker": {"x": 960, "y": 650},
            "lucky6": {"x": 740, "y": 720},
            "chip_100": {"x": 380, "y": 760},
            "chip_1k": {"x": 440, "y": 760},
            "chip_5k": {"x": 500, "y": 760}
        },
        "roi": {
            "overlay": {"x": 900, "y": 360, "w": 600, "h": 100}
        }
    }

    strategy = {
        "unit": 1000,
        "targets": ["banker"],
        "split_units": {"banker": 1},
        "staking": {"type": "fixed", "base_units": 1},
        "limits": {"per_round_cap": 5000}
    }

    # 保存配置
    with open("positions.json", "w") as f:
        json.dump(positions, f)

    with open("configs/strategy.json", "w") as f:
        json.dump(strategy, f)

    # 創建引擎
    engine = AutoBetEngine(dry_run=True)

    # 連接信號
    def on_log(msg):
        print(f"[LOG] {msg}")

    def on_state_change(state):
        print(f"[STATE] {state}")

    def on_plan_ready(plan):
        print(f"[PLAN] {plan}")

    engine.log_message.connect(on_log)
    engine.state_changed.connect(on_state_change)
    engine.betting_plan_ready.connect(on_plan_ready)

    # 載入配置
    engine.load_positions("positions.json")
    engine.load_strategy("configs/strategy.json")

    print("=== Starting AutoBetEngine Demo ===")

    # 啟動引擎
    engine.set_enabled(True)

    # 讓引擎運行幾秒
    start_time = time.time()
    while time.time() - start_time < 5:
        app.processEvents()
        time.sleep(0.1)

    print("\n=== Simulating Result Event ===")

    # 模擬收到結果
    test_event = {
        "type": "RESULT",
        "winner": "B",
        "round_id": "demo-001"
    }
    engine.on_round_detected(test_event)

    # 再運行幾秒
    start_time = time.time()
    while time.time() - start_time < 3:
        app.processEvents()
        time.sleep(0.1)

    # 停止引擎
    engine.set_enabled(False)

    print("\n=== Demo Complete ===")
    print("If you see [DRY] click messages, dry run is working!")

if __name__ == "__main__":
    main()