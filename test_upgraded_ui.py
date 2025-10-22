#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試升級後的 UI 組件
驗證所有改進功能正常工作
"""

import sys
import os
import time

# 設置環境變量強制 UTF-8
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget
from PySide6.QtCore import QTimer
from ui.components import CompactStrategyInfoCard, CompactLiveCard


def test_upgraded_ui():
    """測試升級後的 UI"""
    app = QApplication(sys.argv)

    print("=" * 70)
    print("🎨 測試升級後的 UI 組件")
    print("=" * 70)

    # 創建主窗口
    window = QMainWindow()
    window.setWindowTitle("升級版 UI 測試 - 所有改進功能")
    window.setGeometry(100, 100, 700, 600)

    # 創建中央 widget
    central = QWidget()
    window.setCentralWidget(central)
    layout = QVBoxLayout(central)

    # 創建 tab widget
    tabs = QTabWidget()
    layout.addWidget(tabs)

    # ============================================================
    # Tab 1: 策略資訊卡片（升級版）
    # ============================================================
    tab1 = QWidget()
    tab1_layout = QVBoxLayout(tab1)
    strategy_card = CompactStrategyInfoCard()
    tab1_layout.addWidget(strategy_card)
    tab1_layout.addStretch()
    tabs.addTab(tab1, "📊 策略資訊")

    print("\n✅ Step 1: CompactStrategyInfoCard 創建成功")
    print("   改進：視覺層級、字體系統、分隔線、狀態徽章")

    # ============================================================
    # Tab 2: 即時狀態卡片（升級版）
    # ============================================================
    tab2 = QWidget()
    tab2_layout = QVBoxLayout(tab2)
    live_card = CompactLiveCard()
    tab2_layout.addWidget(live_card)
    tab2_layout.addStretch()
    tabs.addTab(tab2, "🎮 即時狀態")

    print("✅ Step 2: CompactLiveCard 創建成功")
    print("   改進：進度條、盈虧等寬字體、色彩標籤、滑鼠懸停")

    # ============================================================
    # 測試數據更新
    # ============================================================
    print("\n📡 Step 3: 測試數據更新...")

    # 添加路單歷史
    for winner in ["B", "P", "B", "B", "P", "P", "B"]:
        live_card.add_history(winner)
    print("✅ 路單歷史：B P B B P P B")

    # 模擬等待觸發狀態
    mock_snapshot_waiting = {
        "lines": [
            {
                "table": "main",
                "strategy_key": "1",
                "strategy": "PP then bet B",
                "phase": "idle",  # 等待觸發
                "current_layer": 1,
                "max_layer": 3,
                "stake": 100.0,
                "direction": "banker",
                "frozen": False,
                "pnl": 0.0,
            }
        ],
        "risk": {
            "table:main": {"pnl": 650.0, "stop_loss": -500.0, "take_profit": 1000.0},
            "global_day": {"pnl": 1450.0, "stop_loss": -2000.0, "take_profit": 5000.0},
        },
        "performance": {
            "triggers": 23,
            "entries": 21,
            "wins": 14,
            "losses": 7,
            "total_pnl": 1250.0,
        },
    }

    live_card.update_from_snapshot(mock_snapshot_waiting, table_id="main")
    strategy_card.update_stats(mock_snapshot_waiting)
    print("✅ 階段：等待觸發（顯示盈虧、層級進度條）")

    # 設定策略為運行中
    strategy_card.set_status(True)
    print("✅ 策略狀態：運行中（綠色邊框 + 徽章）")

    # ============================================================
    # 延遲測試：切換到準備下注狀態
    # ============================================================
    def test_ready_to_bet():
        print("\n🎯 Step 4: 切換到「準備下注」狀態...")
        mock_snapshot_ready = {
            "lines": [
                {
                    "table": "main",
                    "strategy_key": "1",
                    "phase": "armed",  # 準備下注
                    "current_layer": 2,
                    "max_layer": 3,
                    "stake": 200.0,
                    "direction": "player",
                }
            ],
            "risk": {
                "table:main": {"pnl": 650.0},
                "global_day": {"pnl": 1450.0},
            },
        }
        live_card.update_from_snapshot(mock_snapshot_ready, table_id="main")
        print("✅ 階段：準備下注（高亮卡片、預測顯示）")

    QTimer.singleShot(2000, test_ready_to_bet)

    # ============================================================
    # 延遲測試：切換到等待開獎狀態
    # ============================================================
    def test_waiting_result():
        print("\n⏳ Step 5: 切換到「等待開獎」狀態...")
        mock_snapshot_waiting_result = {
            "lines": [
                {
                    "table": "main",
                    "strategy_key": "1",
                    "phase": "waiting",  # 等待開獎
                    "current_layer": 2,
                    "max_layer": 3,
                    "stake": 200.0,
                    "direction": "player",
                }
            ],
            "risk": {
                "table:main": {"pnl": 650.0},
                "global_day": {"pnl": 1450.0},
            },
        }
        live_card.update_from_snapshot(mock_snapshot_waiting_result, table_id="main")
        print("✅ 階段：等待開獎（黃色高亮、發牌中）")

    QTimer.singleShot(4000, test_waiting_result)

    # ============================================================
    # 延遲測試：回到等待觸發狀態
    # ============================================================
    def test_back_to_waiting():
        print("\n🔄 Step 6: 回到「等待觸發」狀態...")
        # 添加新結果到歷史
        live_card.add_history("P")

        # 更新盈虧（贏了）
        mock_snapshot_back = {
            "lines": [
                {
                    "table": "main",
                    "strategy_key": "1",
                    "phase": "idle",
                    "current_layer": 1,  # 回到第1層
                    "max_layer": 3,
                    "stake": 100.0,
                    "direction": "banker",
                }
            ],
            "risk": {
                "table:main": {"pnl": 850.0},  # +200
                "global_day": {"pnl": 1650.0},
            },
            "performance": {
                "triggers": 24,
                "entries": 22,
                "wins": 15,  # +1 win
                "losses": 7,
                "total_pnl": 1450.0,
            },
        }
        live_card.update_from_snapshot(mock_snapshot_back, table_id="main")
        strategy_card.update_stats(mock_snapshot_back)
        print("✅ 開獎：P - 贏了！盈虧更新、回層1")

    QTimer.singleShot(6000, test_back_to_waiting)

    # ============================================================
    # 顯示窗口並等待關閉
    # ============================================================
    def show_summary():
        print("\n" + "=" * 70)
        print("✅ 所有 UI 升級測試完成！")
        print("=" * 70)
        print("\n🎨 升級內容摘要：")
        print("  ✓ 字體層級系統（11pt 標題 / 9pt 正文 / 8pt 說明）")
        print("  ✓ 統一色彩系統（綠色盈利 / 紅色虧損 / 黃色等待）")
        print("  ✓ 間距優化（8px 行間距，增加呼吸空間）")
        print("  ✓ 分隔線視覺效果")
        print("  ✓ 狀態徽章（運行中 / 待機）")
        print("  ✓ 專業進度條（層級顯示）")
        print("  ✓ 等寬字體數字（Consolas）")
        print("  ✓ 色彩標籤（盈虧高亮）")
        print("  ✓ 視覺分組（減少 | 符號）")
        print("  ✓ 滑鼠懸停互動")
        print("  ✓ 動態階段切換（idle → ready → waiting）")
        print("\n📌 請手動測試：")
        print("  1. 滑鼠懸停卡片（應該看到高亮效果）")
        print("  2. 查看進度條顯示")
        print("  3. 確認色彩對比度")
        print("  4. 切換不同狀態的視覺效果")
        print("\n窗口將在 10 秒後自動關閉...")

    QTimer.singleShot(8000, show_summary)

    # 10秒後關閉
    def close_window():
        print("🔚 測試完成，關閉窗口...")
        window.close()
        app.quit()

    QTimer.singleShot(18000, close_window)

    window.show()
    return app.exec()


if __name__ == "__main__":
    success = test_upgraded_ui()
    sys.exit(0 if success else 1)
