# tests/test_strategy_registry.py
"""
StrategyRegistry 單元測試

測試覆蓋：
1. 策略註冊和查詢
2. 桌號綁定管理
3. 批量操作
4. 邊界情況和錯誤處理
"""
import pytest
from src.autobet.lines.strategy_registry import StrategyRegistry
from src.autobet.lines.config import (
    StrategyDefinition,
    EntryConfig,
    StakingConfig,
    DedupMode,
)


@pytest.fixture
def registry():
    """創建空的 StrategyRegistry"""
    return StrategyRegistry()


@pytest.fixture
def sample_strategy():
    """創建範例策略定義"""
    return StrategyDefinition(
        strategy_key="PB_then_P",
        entry=EntryConfig(
            pattern="PB",
            dedup=DedupMode.STRICT,
        ),
        staking=StakingConfig(
            sequence=[100, 200, 400],
            reset_on_win=True,
        ),
    )


@pytest.fixture
def another_strategy():
    """創建另一個範例策略"""
    return StrategyDefinition(
        strategy_key="PP_then_B",
        entry=EntryConfig(
            pattern="PP",
            dedup=DedupMode.OVERLAP,
        ),
        staking=StakingConfig(
            sequence=[100, 200],
            reset_on_win=True,
        ),
    )


class TestStrategyRegistration:
    """測試策略註冊功能"""

    def test_register_single_strategy(self, registry, sample_strategy):
        """測試註冊單個策略"""
        registry.register(sample_strategy)

        assert registry.count() == 1
        assert registry.has_strategy("PB_then_P")
        assert registry.get_strategy("PB_then_P") == sample_strategy

    def test_register_with_tables(self, registry, sample_strategy):
        """測試註冊時同時綁定桌號"""
        registry.register(sample_strategy, tables=["table1", "table2"])

        assert registry.count() == 1
        assert registry.is_attached("table1", "PB_then_P")
        assert registry.is_attached("table2", "PB_then_P")

    def test_register_empty_key_raises_error(self, registry):
        """測試註冊空 key 會拋出異常"""
        invalid_strategy = StrategyDefinition(
            strategy_key="",
            entry=EntryConfig(pattern="PB"),
            staking=StakingConfig(sequence=[100]),
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            registry.register(invalid_strategy)

    def test_bulk_register(self, registry, sample_strategy, another_strategy):
        """測試批量註冊"""
        strategies = {
            "PB_then_P": sample_strategy,
            "PP_then_B": another_strategy,
        }

        registry.bulk_register(strategies)

        assert registry.count() == 2
        assert registry.has_strategy("PB_then_P")
        assert registry.has_strategy("PP_then_B")

    def test_bulk_register_key_mismatch_raises_error(self, registry, sample_strategy):
        """測試批量註冊時 key 不匹配會拋出異常"""
        strategies = {
            "wrong_key": sample_strategy,  # key 與 strategy_key 不匹配
        }

        with pytest.raises(ValueError, match="key mismatch"):
            registry.bulk_register(strategies)

    def test_unregister(self, registry, sample_strategy):
        """測試取消註冊"""
        registry.register(sample_strategy, tables=["table1"])

        # 取消註冊
        result = registry.unregister("PB_then_P")

        assert result is True
        assert registry.count() == 0
        assert not registry.has_strategy("PB_then_P")
        # 綁定關係也應該被移除
        assert not registry.is_attached("table1", "PB_then_P")

    def test_unregister_nonexistent_returns_false(self, registry):
        """測試取消不存在的策略返回 False"""
        result = registry.unregister("nonexistent")
        assert result is False


class TestStrategyQuery:
    """測試策略查詢功能"""

    def test_get_strategy(self, registry, sample_strategy):
        """測試獲取策略定義"""
        registry.register(sample_strategy)
        retrieved = registry.get_strategy("PB_then_P")
        assert retrieved == sample_strategy

    def test_get_nonexistent_strategy_returns_none(self, registry):
        """測試獲取不存在的策略返回 None"""
        assert registry.get_strategy("nonexistent") is None

    def test_has_strategy(self, registry, sample_strategy):
        """測試檢查策略是否存在"""
        assert not registry.has_strategy("PB_then_P")

        registry.register(sample_strategy)

        assert registry.has_strategy("PB_then_P")

    def test_list_all_strategies(self, registry, sample_strategy, another_strategy):
        """測試列出所有策略"""
        registry.register(sample_strategy)
        registry.register(another_strategy)

        all_strategies = registry.list_all_strategies()

        assert len(all_strategies) == 2
        assert "PB_then_P" in all_strategies
        assert "PP_then_B" in all_strategies
        assert all_strategies["PB_then_P"] == sample_strategy

    def test_get_strategy_keys(self, registry, sample_strategy, another_strategy):
        """測試獲取所有策略 key"""
        registry.register(sample_strategy)
        registry.register(another_strategy)

        keys = registry.get_strategy_keys()

        assert len(keys) == 2
        assert "PB_then_P" in keys
        assert "PP_then_B" in keys

    def test_count(self, registry, sample_strategy, another_strategy):
        """測試獲取策略總數"""
        assert registry.count() == 0

        registry.register(sample_strategy)
        assert registry.count() == 1

        registry.register(another_strategy)
        assert registry.count() == 2


class TestTableAttachment:
    """測試桌號綁定管理"""

    def test_attach_to_table(self, registry, sample_strategy):
        """測試綁定策略到桌號"""
        registry.register(sample_strategy)
        registry.attach_to_table("table1", "PB_then_P")

        assert registry.is_attached("table1", "PB_then_P")

    def test_attach_unregistered_strategy_raises_error(self, registry):
        """測試綁定未註冊的策略會拋出異常"""
        with pytest.raises(KeyError, match="not registered"):
            registry.attach_to_table("table1", "nonexistent")

    def test_attach_idempotent(self, registry, sample_strategy):
        """測試重複綁定是冪等的"""
        registry.register(sample_strategy)
        registry.attach_to_table("table1", "PB_then_P")
        registry.attach_to_table("table1", "PB_then_P")  # 重複綁定

        strategies = registry.get_strategies_for_table("table1")
        assert len(strategies) == 1  # 只有一個

    def test_detach_from_table(self, registry, sample_strategy):
        """測試解除綁定"""
        registry.register(sample_strategy, tables=["table1"])

        result = registry.detach_from_table("table1", "PB_then_P")

        assert result is True
        assert not registry.is_attached("table1", "PB_then_P")

    def test_detach_nonexistent_returns_false(self, registry, sample_strategy):
        """測試解除不存在的綁定返回 False"""
        registry.register(sample_strategy)

        result = registry.detach_from_table("table1", "PB_then_P")
        assert result is False

    def test_detach_all_from_table(self, registry, sample_strategy, another_strategy):
        """測試解除桌號的所有綁定"""
        registry.register(sample_strategy, tables=["table1"])
        registry.register(another_strategy, tables=["table1"])

        count = registry.detach_all_from_table("table1")

        assert count == 2
        assert not registry.is_attached("table1", "PB_then_P")
        assert not registry.is_attached("table1", "PP_then_B")

    def test_get_attached_tables(self, registry, sample_strategy):
        """測試獲取策略綁定的桌號"""
        registry.register(sample_strategy, tables=["table1", "table2", "table3"])

        tables = registry.get_attached_tables("PB_then_P")

        assert len(tables) == 3
        assert "table1" in tables
        assert "table2" in tables
        assert "table3" in tables

    def test_get_strategies_for_table(self, registry, sample_strategy, another_strategy):
        """測試獲取桌號的所有策略"""
        registry.register(sample_strategy, tables=["table1"])
        registry.register(another_strategy, tables=["table1"])

        strategies = registry.get_strategies_for_table("table1")

        assert len(strategies) == 2
        keys = [key for key, _ in strategies]
        assert "PB_then_P" in keys
        assert "PP_then_B" in keys

    def test_get_strategies_for_nonexistent_table_returns_empty(self, registry):
        """測試獲取不存在桌號的策略返回空列表"""
        strategies = registry.get_strategies_for_table("nonexistent")
        assert strategies == []

    def test_is_attached(self, registry, sample_strategy):
        """測試檢查綁定狀態"""
        registry.register(sample_strategy)

        assert not registry.is_attached("table1", "PB_then_P")

        registry.attach_to_table("table1", "PB_then_P")

        assert registry.is_attached("table1", "PB_then_P")


class TestSnapshotAndUtilities:
    """測試快照和工具方法"""

    def test_snapshot(self, registry, sample_strategy, another_strategy):
        """測試快照功能"""
        registry.register(sample_strategy, tables=["table1", "table2"])
        registry.register(another_strategy, tables=["table1"])

        snapshot = registry.snapshot()

        assert snapshot["total_strategies"] == 2
        assert snapshot["total_tables"] == 2
        assert "PB_then_P" in snapshot["strategies"]
        assert "PP_then_B" in snapshot["strategies"]

        # 檢查策略詳情
        pb_info = snapshot["strategies"]["PB_then_P"]
        assert pb_info["has_staking"] is True
        assert set(pb_info["attached_tables"]) == {"table1", "table2"}

    def test_clear(self, registry, sample_strategy, another_strategy):
        """測試清空功能"""
        registry.register(sample_strategy, tables=["table1"])
        registry.register(another_strategy, tables=["table2"])

        registry.clear()

        assert registry.count() == 0
        assert len(registry.get_strategy_keys()) == 0
        assert len(registry.get_strategies_for_table("table1")) == 0


class TestIntegration:
    """集成測試"""

    def test_complete_workflow(self, registry, sample_strategy, another_strategy):
        """測試完整工作流程"""
        # 1. 註冊策略
        registry.register(sample_strategy)
        registry.register(another_strategy)

        # 2. 綁定到桌號
        registry.attach_to_table("table1", "PB_then_P")
        registry.attach_to_table("table1", "PP_then_B")
        registry.attach_to_table("table2", "PB_then_P")

        # 3. 查詢桌號策略
        table1_strategies = registry.get_strategies_for_table("table1")
        assert len(table1_strategies) == 2

        table2_strategies = registry.get_strategies_for_table("table2")
        assert len(table2_strategies) == 1

        # 4. 解除部分綁定
        registry.detach_from_table("table1", "PP_then_B")
        table1_strategies = registry.get_strategies_for_table("table1")
        assert len(table1_strategies) == 1

        # 5. 取消註冊策略（會自動解除所有綁定）
        registry.unregister("PB_then_P")
        assert registry.count() == 1
        assert len(registry.get_strategies_for_table("table1")) == 0
        assert len(registry.get_strategies_for_table("table2")) == 0

    def test_multiple_tables_multiple_strategies(self, registry):
        """測試多桌多策略場景"""
        # 創建 5 個策略
        strategies = {}
        for i in range(5):
            key = f"strategy_{i}"
            strategies[key] = StrategyDefinition(
                strategy_key=key,
                entry=EntryConfig(
                    pattern="PB" if i % 2 == 0 else "BP",
                    dedup=DedupMode.STRICT if i % 2 == 0 else DedupMode.OVERLAP,
                ),
                staking=StakingConfig(
                    sequence=[100 * (i + 1)],
                    reset_on_win=True,
                ),
            )

        registry.bulk_register(strategies)

        # 綁定到 3 個桌號
        for table_idx in range(3):
            table_id = f"table{table_idx}"
            for strategy_idx in range(5):
                # 交錯綁定（不是所有策略都綁到所有桌）
                if (table_idx + strategy_idx) % 2 == 0:
                    registry.attach_to_table(table_id, f"strategy_{strategy_idx}")

        # 驗證綁定關係
        snapshot = registry.snapshot()
        assert snapshot["total_strategies"] == 5
        assert snapshot["total_tables"] == 3

        # 每個桌號應該有 2-3 個策略
        for table_idx in range(3):
            table_id = f"table{table_idx}"
            strategies = registry.get_strategies_for_table(table_id)
            assert 2 <= len(strategies) <= 3
