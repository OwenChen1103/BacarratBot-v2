# tests/test_position_manager.py
"""
PositionManager 單元測試

測試覆蓋：
1. 倉位創建和儲存
2. 倉位結算（所有結果類型：WIN/LOSS/SKIPPED/CANCELLED）
3. PnL 計算（不同方向和賠率）
4. 倉位查詢
5. 結算歷史
6. 統計信息
"""
import time
import pytest
from src.autobet.lines.position_manager import PositionManager, PendingPosition, SettlementResult
from src.autobet.lines.state import LayerOutcome
from src.autobet.payout_manager import PayoutManager


@pytest.fixture
def manager():
    """創建 PositionManager"""
    return PositionManager()


class TestPositionCreation:
    """測試倉位創建"""

    def test_create_position(self, manager):
        """測試創建單個倉位"""
        position = manager.create_position(
            table_id="table1",
            round_id="round1",
            strategy_key="PB_BET_P",
            direction="P",
            amount=100.0,
            layer_index=0,
        )

        assert position.table_id == "table1"
        assert position.round_id == "round1"
        assert position.strategy_key == "PB_BET_P"
        assert position.direction == "P"
        assert position.amount == 100.0
        assert position.layer_index == 0

        # 檢查已添加到 pending
        assert manager.count_pending() == 1
        assert manager.has_position("table1", "round1", "PB_BET_P")

        # 檢查已添加到 tracker
        assert manager.tracker.get_position_count() == 1
        assert manager.tracker.get_total_exposure() == 100.0

    def test_create_duplicate_position_raises_error(self, manager):
        """測試創建重複倉位會拋出異常"""
        manager.create_position(
            table_id="table1",
            round_id="round1",
            strategy_key="PB_BET_P",
            direction="P",
            amount=100.0,
            layer_index=0,
        )

        # 嘗試創建重複倉位
        with pytest.raises(ValueError, match="already exists"):
            manager.create_position(
                table_id="table1",
                round_id="round1",
                strategy_key="PB_BET_P",
                direction="B",
                amount=200.0,
                layer_index=1,
            )

    def test_create_multiple_positions(self, manager):
        """測試創建多個倉位"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.create_position("table1", "round1", "strategy2", "B", 200.0, 0)
        manager.create_position("table2", "round2", "strategy1", "P", 150.0, 1)

        assert manager.count_pending() == 3
        assert manager.tracker.get_total_exposure() == 450.0


class TestOutcomeDetermination:
    """測試結果判定"""

    def test_determine_outcome_win(self, manager):
        """測試判定 WIN"""
        # Player 下注，Player 贏
        outcome = manager._determine_outcome("P", "P")
        assert outcome == LayerOutcome.WIN

        # Banker 下注，Banker 贏
        outcome = manager._determine_outcome("B", "B")
        assert outcome == LayerOutcome.WIN

        # Tie 下注，Tie 贏
        outcome = manager._determine_outcome("T", "T")
        assert outcome == LayerOutcome.WIN

    def test_determine_outcome_loss(self, manager):
        """測試判定 LOSS"""
        # Player 下注，Banker 贏
        outcome = manager._determine_outcome("P", "B")
        assert outcome == LayerOutcome.LOSS

        # Banker 下注，Player 贏
        outcome = manager._determine_outcome("B", "P")
        assert outcome == LayerOutcome.LOSS

    def test_determine_outcome_skipped(self, manager):
        """測試判定 SKIPPED（和局但未下注 Tie）"""
        # Player 下注，Tie
        outcome = manager._determine_outcome("P", "T")
        assert outcome == LayerOutcome.SKIPPED

        # Banker 下注，Tie
        outcome = manager._determine_outcome("B", "T")
        assert outcome == LayerOutcome.SKIPPED

    def test_determine_outcome_cancelled(self, manager):
        """測試判定 CANCELLED（無結果）"""
        outcome = manager._determine_outcome("P", None)
        assert outcome == LayerOutcome.CANCELLED

        outcome = manager._determine_outcome("B", None)
        assert outcome == LayerOutcome.CANCELLED


class TestPnLCalculation:
    """測試 PnL 計算"""

    def test_pnl_player_win(self, manager):
        """測試 Player WIN 的 PnL"""
        # Player 贏 1:1
        pnl = manager._calculate_pnl(100.0, LayerOutcome.WIN, "P")
        assert pnl == 100.0  # +100

    def test_pnl_banker_win(self, manager):
        """測試 Banker WIN 的 PnL"""
        # Banker 贏 0.95:1 (扣 5% 佣金)
        pnl = manager._calculate_pnl(100.0, LayerOutcome.WIN, "B")
        assert pnl == 95.0  # +95

    def test_pnl_tie_win(self, manager):
        """測試 Tie WIN 的 PnL"""
        # Tie 贏 8:1
        pnl = manager._calculate_pnl(100.0, LayerOutcome.WIN, "T")
        assert pnl == 800.0  # +800

    def test_pnl_loss(self, manager):
        """測試 LOSS 的 PnL"""
        # 輸了扣本金
        pnl = manager._calculate_pnl(100.0, LayerOutcome.LOSS, "P")
        assert pnl == -100.0

        pnl = manager._calculate_pnl(100.0, LayerOutcome.LOSS, "B")
        assert pnl == -100.0

    def test_pnl_skipped(self, manager):
        """測試 SKIPPED 的 PnL（和局退款）"""
        pnl = manager._calculate_pnl(100.0, LayerOutcome.SKIPPED, "P")
        assert pnl == 0.0

        pnl = manager._calculate_pnl(100.0, LayerOutcome.SKIPPED, "B")
        assert pnl == 0.0

    def test_pnl_cancelled(self, manager):
        """測試 CANCELLED 的 PnL"""
        pnl = manager._calculate_pnl(100.0, LayerOutcome.CANCELLED, "P")
        assert pnl == 0.0


class TestPositionSettlement:
    """測試倉位結算"""

    def test_settle_position_win(self, manager):
        """測試結算 WIN 倉位"""
        # 創建倉位
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)

        # 結算（Player 贏）
        result = manager.settle_position("table1", "round1", "strategy1", "P")

        assert result is not None
        assert result.outcome == LayerOutcome.WIN
        assert result.pnl_delta == 100.0
        assert result.position.direction == "P"

        # 檢查已從 pending 移除
        assert manager.count_pending() == 0
        assert not manager.has_position("table1", "round1", "strategy1")

        # 檢查已從 tracker 移除
        assert manager.tracker.get_position_count() == 0

    def test_settle_position_loss(self, manager):
        """測試結算 LOSS 倉位"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)

        # 結算（Banker 贏，Player 輸）
        result = manager.settle_position("table1", "round1", "strategy1", "B")

        assert result.outcome == LayerOutcome.LOSS
        assert result.pnl_delta == -100.0

    def test_settle_position_skipped(self, manager):
        """測試結算 SKIPPED 倉位（和局退款）"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)

        # 結算（Tie，退款）
        result = manager.settle_position("table1", "round1", "strategy1", "T")

        assert result.outcome == LayerOutcome.SKIPPED
        assert result.pnl_delta == 0.0

    def test_settle_position_cancelled(self, manager):
        """測試結算 CANCELLED 倉位"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)

        # 結算（無結果）
        result = manager.settle_position("table1", "round1", "strategy1", None)

        assert result.outcome == LayerOutcome.CANCELLED
        assert result.pnl_delta == 0.0

    def test_settle_nonexistent_position_returns_none(self, manager):
        """測試結算不存在的倉位返回 None"""
        result = manager.settle_position("table1", "round1", "nonexistent", "P")
        assert result is None

    def test_settle_all_for_round(self, manager):
        """測試結算某局的所有倉位"""
        # 創建多個倉位
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.create_position("table1", "round1", "strategy2", "B", 200.0, 0)
        manager.create_position("table1", "round2", "strategy3", "P", 150.0, 0)  # 不同局

        # 結算 round1 的所有倉位
        results = manager.settle_all_for_round("table1", "round1", "P")

        assert len(results) == 2
        strategy_keys = {r.position.strategy_key for r in results}
        assert strategy_keys == {"strategy1", "strategy2"}

        # round2 的倉位應該還在
        assert manager.count_pending() == 1


class TestPositionQuery:
    """測試倉位查詢"""

    def test_get_position(self, manager):
        """測試獲取倉位"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)

        position = manager.get_position("table1", "round1", "strategy1")
        assert position is not None
        assert position.direction == "P"
        assert position.amount == 100.0

    def test_get_nonexistent_position_returns_none(self, manager):
        """測試獲取不存在的倉位返回 None"""
        position = manager.get_position("table1", "round1", "nonexistent")
        assert position is None

    def test_has_position(self, manager):
        """測試檢查倉位是否存在"""
        assert not manager.has_position("table1", "round1", "strategy1")

        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)

        assert manager.has_position("table1", "round1", "strategy1")

    def test_has_any_position_for_strategy(self, manager):
        """測試檢查策略是否有任何倉位"""
        assert not manager.has_any_position_for_strategy("table1", "strategy1")

        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)

        assert manager.has_any_position_for_strategy("table1", "strategy1")

        # 不同桌號
        assert not manager.has_any_position_for_strategy("table2", "strategy1")

    def test_get_positions_for_table(self, manager):
        """測試獲取某桌號的所有倉位"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.create_position("table1", "round2", "strategy2", "B", 200.0, 0)
        manager.create_position("table2", "round1", "strategy3", "P", 150.0, 0)

        positions = manager.get_positions_for_table("table1")
        assert len(positions) == 2

        strategy_keys = {p.strategy_key for p in positions}
        assert strategy_keys == {"strategy1", "strategy2"}

    def test_get_positions_for_round(self, manager):
        """測試獲取某局的所有倉位"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.create_position("table1", "round1", "strategy2", "B", 200.0, 0)
        manager.create_position("table1", "round2", "strategy3", "P", 150.0, 0)

        positions = manager.get_positions_for_round("table1", "round1")
        assert len(positions) == 2

    def test_get_all_positions(self, manager):
        """測試獲取所有倉位"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.create_position("table2", "round2", "strategy2", "B", 200.0, 0)

        positions = manager.get_all_positions()
        assert len(positions) == 2

    def test_count_pending(self, manager):
        """測試獲取倉位總數"""
        assert manager.count_pending() == 0

        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        assert manager.count_pending() == 1

        manager.create_position("table1", "round2", "strategy2", "B", 200.0, 0)
        assert manager.count_pending() == 2


class TestSettlementHistory:
    """測試結算歷史"""

    def test_settlement_added_to_history(self, manager):
        """測試結算記錄添加到歷史"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.settle_position("table1", "round1", "strategy1", "P")

        history = manager.get_settlement_history()
        assert len(history) == 1
        assert history[0].outcome == LayerOutcome.WIN

    def test_get_settlement_history_limit(self, manager):
        """測試獲取歷史限制"""
        # 創建並結算多個倉位
        for i in range(10):
            manager.create_position("table1", f"round{i}", "strategy1", "P", 100.0, 0)
            manager.settle_position("table1", f"round{i}", "strategy1", "P")

        history = manager.get_settlement_history(limit=5)
        assert len(history) == 5

    def test_get_recent_settlements_for_strategy(self, manager):
        """測試獲取某策略的結算記錄"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.create_position("table1", "round2", "strategy2", "B", 200.0, 0)
        manager.settle_position("table1", "round1", "strategy1", "P")
        manager.settle_position("table1", "round2", "strategy2", "B")

        history = manager.get_recent_settlements_for_strategy("strategy1")
        assert len(history) == 1
        assert history[0].position.strategy_key == "strategy1"

    def test_clear_settlement_history(self, manager):
        """測試清空結算歷史"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.settle_position("table1", "round1", "strategy1", "P")

        assert len(manager.get_settlement_history()) == 1

        manager.clear_settlement_history()

        assert len(manager.get_settlement_history()) == 0


class TestPositionRemoval:
    """測試倉位移除"""

    def test_remove_position(self, manager):
        """測試移除倉位（不結算）"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)

        result = manager.remove_position("table1", "round1", "strategy1")

        assert result is True
        assert manager.count_pending() == 0
        assert manager.tracker.get_position_count() == 0

        # 不應該添加到結算歷史
        assert len(manager.get_settlement_history()) == 0

    def test_remove_nonexistent_position_returns_false(self, manager):
        """測試移除不存在的倉位返回 False"""
        result = manager.remove_position("table1", "round1", "nonexistent")
        assert result is False

    def test_clear_all_positions(self, manager):
        """測試清空所有倉位"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.create_position("table1", "round2", "strategy2", "B", 200.0, 0)

        count = manager.clear_all_positions()

        assert count == 2
        assert manager.count_pending() == 0
        assert manager.tracker.get_position_count() == 0


class TestStatistics:
    """測試統計信息"""

    def test_statistics_empty(self, manager):
        """測試空統計"""
        stats = manager.get_statistics()

        assert stats["total_settled"] == 0
        assert stats["total_pending"] == 0
        assert stats["win_count"] == 0
        assert stats["loss_count"] == 0
        assert stats["total_pnl"] == 0.0
        assert stats["win_rate"] == 0.0

    def test_statistics_with_settlements(self, manager):
        """測試有結算的統計"""
        # Win
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.settle_position("table1", "round1", "strategy1", "P")  # WIN +100

        # Loss
        manager.create_position("table1", "round2", "strategy1", "P", 100.0, 0)
        manager.settle_position("table1", "round2", "strategy1", "B")  # LOSS -100

        # Skip
        manager.create_position("table1", "round3", "strategy1", "P", 100.0, 0)
        manager.settle_position("table1", "round3", "strategy1", "T")  # SKIPPED 0

        stats = manager.get_statistics()

        assert stats["total_settled"] == 3
        assert stats["win_count"] == 1
        assert stats["loss_count"] == 1
        assert stats["skip_count"] == 1
        assert stats["total_pnl"] == 0.0  # +100 - 100 = 0
        assert stats["win_rate"] == 50.0  # 1 win / 2 decided

    def test_statistics_win_rate_excludes_skipped(self, manager):
        """測試勝率排除 SKIPPED"""
        # 2 wins, 1 loss, 1 skip
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.settle_position("table1", "round1", "strategy1", "P")  # WIN

        manager.create_position("table1", "round2", "strategy1", "P", 100.0, 0)
        manager.settle_position("table1", "round2", "strategy1", "P")  # WIN

        manager.create_position("table1", "round3", "strategy1", "P", 100.0, 0)
        manager.settle_position("table1", "round3", "strategy1", "B")  # LOSS

        manager.create_position("table1", "round4", "strategy1", "P", 100.0, 0)
        manager.settle_position("table1", "round4", "strategy1", "T")  # SKIPPED

        stats = manager.get_statistics()

        # 勝率 = 2 / (2+1) = 66.67%
        assert stats["win_rate"] == pytest.approx(66.67, rel=0.01)


class TestSnapshot:
    """測試快照功能"""

    def test_snapshot(self, manager):
        """測試快照包含所有狀態"""
        manager.create_position("table1", "round1", "strategy1", "P", 100.0, 0)
        manager.create_position("table1", "round2", "strategy2", "B", 200.0, 0)

        snapshot = manager.snapshot()

        assert snapshot["total_pending"] == 2
        assert snapshot["tracker_count"] == 2
        assert snapshot["total_exposure"] == 300.0
        assert len(snapshot["pending_positions"]) == 2
        assert "tracker_snapshot" in snapshot


class TestIntegration:
    """集成測試"""

    def test_complete_position_lifecycle(self, manager):
        """測試完整的倉位生命週期"""
        # 1. 創建倉位
        position = manager.create_position(
            table_id="table1",
            round_id="round1",
            strategy_key="PB_BET_P",
            direction="P",
            amount=100.0,
            layer_index=0,
        )

        assert manager.count_pending() == 1
        assert manager.tracker.get_position_count() == 1

        # 2. 查詢倉位
        found = manager.get_position("table1", "round1", "PB_BET_P")
        assert found is not None
        assert found.amount == 100.0

        # 3. 結算倉位
        result = manager.settle_position("table1", "round1", "PB_BET_P", "P")

        assert result.outcome == LayerOutcome.WIN
        assert result.pnl_delta == 100.0

        # 4. 驗證已清理
        assert manager.count_pending() == 0
        assert manager.tracker.get_position_count() == 0

        # 5. 檢查歷史
        history = manager.get_settlement_history()
        assert len(history) == 1

        # 6. 檢查統計
        stats = manager.get_statistics()
        assert stats["total_settled"] == 1
        assert stats["win_count"] == 1
        assert stats["total_pnl"] == 100.0

    def test_multiple_positions_different_outcomes(self, manager):
        """測試多個倉位不同結果"""
        # Player WIN
        manager.create_position("table1", "round1", "s1", "P", 100.0, 0)
        r1 = manager.settle_position("table1", "round1", "s1", "P")

        # Banker WIN (with commission)
        manager.create_position("table1", "round2", "s2", "B", 100.0, 0)
        r2 = manager.settle_position("table1", "round2", "s2", "B")

        # LOSS
        manager.create_position("table1", "round3", "s3", "P", 100.0, 0)
        r3 = manager.settle_position("table1", "round3", "s3", "B")

        # Tie WIN
        manager.create_position("table1", "round4", "s4", "T", 100.0, 0)
        r4 = manager.settle_position("table1", "round4", "s4", "T")

        # SKIPPED
        manager.create_position("table1", "round5", "s5", "P", 100.0, 0)
        r5 = manager.settle_position("table1", "round5", "s5", "T")

        # 驗證 PnL
        assert r1.pnl_delta == 100.0  # Player win
        assert r2.pnl_delta == 95.0   # Banker win (0.95x)
        assert r3.pnl_delta == -100.0  # Loss
        assert r4.pnl_delta == 800.0  # Tie win (8x)
        assert r5.pnl_delta == 0.0    # Skipped

        # 總 PnL
        stats = manager.get_statistics()
        total_pnl = 100 + 95 - 100 + 800 + 0
        assert stats["total_pnl"] == total_pnl
