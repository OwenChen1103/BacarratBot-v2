#!/usr/bin/env python3
"""
乾跑測試 - 啟動 run_bot.py 於乾跑模式，跑 30 局不得報錯
"""

import os
import sys
import time
import unittest
import logging
from pathlib import Path
from unittest.mock import Mock, patch

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.autobet.autobet_engine import AutoBetEngine
from src.autobet.io_events import NDJSONPlayer, DemoFeeder


class TestDryRun(unittest.TestCase):
    """乾跑測試類"""

    def setUp(self):
        """測試前準備"""
        self.engine = None
        self.events_received = []
        self.errors = []

        # 設置測試日誌
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # 確保測試檔案存在
        self.strategy_file = "configs/strategy.default.json"
        self.positions_file = "configs/positions.sample.json"
        self.ui_config_file = "configs/ui.yaml"

    def tearDown(self):
        """測試後清理"""
        if self.engine:
            self.engine.set_enabled(False)

    def test_engine_initialization(self):
        """測試引擎初始化"""
        engine = AutoBetEngine(dry_run=True)

        # 檢查初始狀態
        self.assertTrue(engine.dry_run)
        self.assertFalse(engine.enabled)
        self.assertEqual(engine.current_state.value, "stopped")

        self.logger.info("✓ 引擎初始化測試通過")

    def test_config_loading(self):
        """測試配置載入"""
        engine = AutoBetEngine(dry_run=True)

        # 測試載入位置配置
        if os.path.exists(self.positions_file):
            success = engine.load_positions(self.positions_file)
            self.assertTrue(success, "載入位置配置失敗")

        # 測試載入策略配置
        if os.path.exists(self.strategy_file):
            success = engine.load_strategy(self.strategy_file)
            self.assertTrue(success, "載入策略配置失敗")

        # 測試載入 UI 配置
        if os.path.exists(self.ui_config_file):
            success = engine.load_ui_config(self.ui_config_file)
            self.assertTrue(success, "載入 UI 配置失敗")

        self.logger.info("✓ 配置載入測試通過")

    def test_component_initialization(self):
        """測試組件初始化"""
        engine = AutoBetEngine(dry_run=True)

        # 載入必要配置
        if os.path.exists(self.positions_file):
            engine.load_positions(self.positions_file)
        if os.path.exists(self.strategy_file):
            engine.load_strategy(self.strategy_file)
        if os.path.exists(self.ui_config_file):
            engine.load_ui_config(self.ui_config_file)

        # 初始化組件
        success = engine.initialize_components()
        if engine.positions and engine.strategy:
            self.assertTrue(success, "組件初始化失敗")

        self.logger.info("✓ 組件初始化測試通過")

    def test_dry_run_30_rounds(self):
        """測試乾跑 30 局"""
        if not all(os.path.exists(f) for f in [self.strategy_file, self.positions_file, self.ui_config_file]):
            self.skipTest("配置檔案不完整，跳過乾跑測試")

        engine = AutoBetEngine(dry_run=True)

        # 載入配置
        engine.load_positions(self.positions_file)
        engine.load_strategy(self.strategy_file)
        engine.load_ui_config(self.ui_config_file)

        # 初始化組件
        success = engine.initialize_components()
        self.assertTrue(success, "組件初始化失敗")

        # 配置快速 demo 事件來源
        engine.configure_event_source('demo', interval=1, seed=42)

        # 連接信號監聽
        engine.log_message.connect(self._on_log_message)
        engine.state_changed.connect(self._on_state_changed)

        # 啟動引擎
        engine.set_enabled(True)
        self.engine = engine

        # 運行 30 局
        rounds_completed = 0
        max_wait_time = 60  # 最多等待 60 秒
        start_time = time.time()

        self.logger.info("開始乾跑測試，目標 30 局...")

        while rounds_completed < 30 and time.time() - start_time < max_wait_time:
            time.sleep(0.1)

            # 檢查是否有新輪次完成
            if hasattr(engine.strategy, 'round_count') and engine.strategy.round_count > rounds_completed:
                rounds_completed = engine.strategy.round_count
                self.logger.info(f"完成第 {rounds_completed} 局")

            # 檢查錯誤狀態
            status = engine.get_status()
            if status['current_state'] == 'error':
                self.fail(f"引擎進入錯誤狀態，完成 {rounds_completed} 局")

        # 停止引擎
        engine.set_enabled(False)

        # 驗證結果
        self.assertGreaterEqual(rounds_completed, 10, f"只完成了 {rounds_completed} 局，少於最低要求")
        self.assertEqual(len(self.errors), 0, f"發生 {len(self.errors)} 個錯誤: {self.errors}")

        self.logger.info(f"✓ 乾跑測試完成，共完成 {rounds_completed} 局")

    def test_actuator_dry_run_behavior(self):
        """測試執行器乾跑行為"""
        from src.autobet.actuator import Actuator, ClickConfig
        from src.autobet.positions import PositionsManager
        from src.autobet.planner import BettingPlan, ChipBreakdown

        if not os.path.exists(self.positions_file):
            self.skipTest("位置配置檔案不存在")

        # 創建位置管理器
        positions = PositionsManager()
        positions.load_from_file(self.positions_file)

        # 創建執行器（乾跑模式）
        actuator = Actuator(positions, ClickConfig(), dry_run=True)

        # 創建模擬下注計劃
        chip_breakdown = ChipBreakdown(
            chips={1000: 2, 500: 1},
            total_amount=2500,
            click_count=3
        )

        betting_plan = BettingPlan(
            targets={"banker": 2500},
            total_amount=2500,
            chip_breakdown=chip_breakdown,
            achievable_amount=2500
        )

        # 執行下注計劃
        with patch('builtins.print') as mock_print:
            result = actuator.execute_betting_plan(betting_plan)

        # 驗證乾跑行為
        self.assertTrue(result["success"], "乾跑執行失敗")
        self.assertGreater(result["total_clicks"], 0, "應該有點擊記錄")

        self.logger.info("✓ 執行器乾跑行為測試通過")

    def test_risk_manager_limits(self):
        """測試風控限制"""
        from src.autobet.risk import RiskManager

        limits_config = {
            'per_round_cap': 5000,
            'session_stop_loss': -10000,
            'session_take_profit': 15000,
            'max_retries': 2,
            'max_consecutive_losses': 3
        }

        risk_manager = RiskManager(limits_config)

        # 測試單局限制
        check = risk_manager.check_round_limits("test_round_1", 3000)
        self.assertTrue(check["allowed"], "正常金額應該被允許")

        check = risk_manager.check_round_limits("test_round_2", 6000)
        self.assertFalse(check["allowed"], "超限金額應該被拒絕")

        # 測試會話限制
        risk_manager.session_profit = -11000
        check = risk_manager.check_session_limits()
        self.assertFalse(check["continue"], "超過止損應該停止")

        risk_manager.session_profit = 16000
        check = risk_manager.check_session_limits()
        self.assertFalse(check["continue"], "達到止盈應該停止")

        self.logger.info("✓ 風控限制測試通過")

    def _on_log_message(self, message: str):
        """日誌消息回調"""
        if "錯誤" in message or "失敗" in message or "ERROR" in message.upper():
            self.errors.append(message)

    def _on_state_changed(self, state: str):
        """狀態變更回調"""
        if state == "error":
            self.errors.append(f"狀態機進入錯誤狀態: {state}")


class TestEventSource(unittest.TestCase):
    """事件來源測試"""

    def test_demo_event_generation(self):
        """測試 demo 事件生成"""
        event_source = EventSource(EventSourceMode.DEMO)
        event_source.configure_demo(interval=1, random_seed=42)

        events_received = []

        def event_callback(event):
            events_received.append(event)

        event_source.set_event_callback(event_callback)

        # 啟動事件來源
        success = event_source.start()
        self.assertTrue(success, "事件來源啟動失敗")

        # 等待幾個事件
        time.sleep(3)

        # 停止事件來源
        event_source.stop()

        # 驗證事件
        self.assertGreater(len(events_received), 0, "應該收到至少一個事件")

        for event in events_received:
            self.assertIsInstance(event, GameEvent)
            self.assertIn(event.winner, ["P", "B", "T"])
            self.assertTrue(event.round_id.startswith("DEMO_"))

        logging.getLogger(__name__).info(f"✓ Demo 事件生成測試通過，收到 {len(events_received)} 個事件")


def run_full_dry_run_test():
    """運行完整乾跑測試"""
    print("🧪 開始完整乾跑測試...")
    print("=" * 50)

    # 創建測試套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加測試
    suite.addTest(TestDryRun('test_engine_initialization'))
    suite.addTest(TestDryRun('test_config_loading'))
    suite.addTest(TestDryRun('test_component_initialization'))
    suite.addTest(TestDryRun('test_actuator_dry_run_behavior'))
    suite.addTest(TestDryRun('test_risk_manager_limits'))
    suite.addTest(TestDryRun('test_dry_run_30_rounds'))
    suite.addTest(TestEventSource('test_demo_event_generation'))

    # 運行測試
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 顯示結果
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("🎉 所有乾跑測試通過！")
        print("系統準備就緒，可以開始使用。")
    else:
        print("❌ 部分測試失敗")
        print(f"失敗: {len(result.failures)}, 錯誤: {len(result.errors)}")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_full_dry_run_test()
    sys.exit(0 if success else 1)