# src/autobet/lines/strategy_registry.py
"""
StrategyRegistry - 策略定義管理器

職責：
1. 策略定義的註冊和儲存
2. 策略查詢（按 strategy_key, table_id）
3. 桌號-策略綁定關係管理

不負責：
- 策略觸發條件評估（由 EntryEvaluator 負責）
- 歷史記錄管理（由 SignalTracker 負責）
- 倉位管理（由 PositionManager 負責）
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from .config import StrategyDefinition


class StrategyRegistry:
    """策略定義註冊表

    管理策略定義和桌號綁定關係。

    使用範例:
        >>> registry = StrategyRegistry()
        >>> registry.register(my_strategy_def)
        >>> registry.attach_to_table("table1", "my_strategy")
        >>>
        >>> # 查詢單個策略
        >>> strategy = registry.get_strategy("my_strategy")
        >>>
        >>> # 查詢某桌號的所有策略
        >>> for key, definition in registry.get_strategies_for_table("table1"):
        ...     print(f"Strategy {key}: {definition.entry}")
    """

    def __init__(self) -> None:
        """初始化策略註冊表"""
        # 策略定義儲存 {strategy_key: StrategyDefinition}
        self._strategies: Dict[str, StrategyDefinition] = {}

        # 桌號-策略綁定關係 {table_id: [strategy_key1, strategy_key2, ...]}
        self._attachments: Dict[str, List[str]] = defaultdict(list)

    # ===== 策略註冊 =====

    def register(
        self,
        definition: StrategyDefinition,
        tables: Optional[Iterable[str]] = None
    ) -> None:
        """註冊策略定義

        Args:
            definition: 策略定義
            tables: 可選的初始綁定桌號列表

        Raises:
            ValueError: 如果 strategy_key 為空

        Example:
            >>> registry.register(
            ...     StrategyDefinition(strategy_key="PB_then_P", ...),
            ...     tables=["table1", "table2"]
            ... )
        """
        if not definition.strategy_key:
            raise ValueError("Strategy key cannot be empty")

        self._strategies[definition.strategy_key] = definition

        # 如果提供了桌號列表，自動綁定
        if tables:
            for table_id in tables:
                self.attach_to_table(table_id, definition.strategy_key)

    def bulk_register(
        self,
        definitions: Dict[str, StrategyDefinition]
    ) -> None:
        """批量註冊策略定義

        Args:
            definitions: {strategy_key: StrategyDefinition} 字典

        Example:
            >>> strategies = {
            ...     "PB_then_P": StrategyDefinition(...),
            ...     "PP_then_B": StrategyDefinition(...),
            ... }
            >>> registry.bulk_register(strategies)
        """
        for strategy_key, definition in definitions.items():
            # 確保 definition 的 strategy_key 與字典 key 一致
            if definition.strategy_key != strategy_key:
                raise ValueError(
                    f"Strategy key mismatch: dict key '{strategy_key}' != "
                    f"definition.strategy_key '{definition.strategy_key}'"
                )
            self._strategies[strategy_key] = definition

    def unregister(self, strategy_key: str) -> bool:
        """取消註冊策略

        Args:
            strategy_key: 策略 key

        Returns:
            是否成功移除（False 表示策略不存在）

        Note:
            同時會移除所有桌號的綁定關係
        """
        if strategy_key not in self._strategies:
            return False

        # 移除策略定義
        del self._strategies[strategy_key]

        # 移除所有桌號的綁定
        for table_id in list(self._attachments.keys()):
            if strategy_key in self._attachments[table_id]:
                self._attachments[table_id].remove(strategy_key)
                # 如果桌號沒有綁定任何策略，移除該桌號
                if not self._attachments[table_id]:
                    del self._attachments[table_id]

        return True

    # ===== 策略查詢 =====

    def get_strategy(self, strategy_key: str) -> Optional[StrategyDefinition]:
        """獲取策略定義

        Args:
            strategy_key: 策略 key

        Returns:
            策略定義，如果不存在則返回 None
        """
        return self._strategies.get(strategy_key)

    def has_strategy(self, strategy_key: str) -> bool:
        """檢查策略是否存在

        Args:
            strategy_key: 策略 key

        Returns:
            是否存在
        """
        return strategy_key in self._strategies

    def list_all_strategies(self) -> Dict[str, StrategyDefinition]:
        """列出所有策略定義

        Returns:
            {strategy_key: StrategyDefinition} 字典（淺拷貝）
        """
        return dict(self._strategies)

    def get_strategy_keys(self) -> List[str]:
        """獲取所有策略 key

        Returns:
            策略 key 列表
        """
        return list(self._strategies.keys())

    def count(self) -> int:
        """獲取策略總數

        Returns:
            策略數量
        """
        return len(self._strategies)

    # ===== 桌號綁定管理 =====

    def attach_to_table(self, table_id: str, strategy_key: str) -> None:
        """將策略綁定到桌號

        Args:
            table_id: 桌號
            strategy_key: 策略 key

        Raises:
            KeyError: 如果策略不存在

        Note:
            重複綁定會被忽略（冪等操作）
        """
        if strategy_key not in self._strategies:
            raise KeyError(f"Strategy '{strategy_key}' not registered")

        if strategy_key not in self._attachments[table_id]:
            self._attachments[table_id].append(strategy_key)

    def detach_from_table(self, table_id: str, strategy_key: str) -> bool:
        """解除策略與桌號的綁定

        Args:
            table_id: 桌號
            strategy_key: 策略 key

        Returns:
            是否成功解除（False 表示本來就沒綁定）
        """
        if table_id not in self._attachments:
            return False

        if strategy_key not in self._attachments[table_id]:
            return False

        self._attachments[table_id].remove(strategy_key)

        # 如果桌號沒有綁定任何策略，移除該桌號
        if not self._attachments[table_id]:
            del self._attachments[table_id]

        return True

    def detach_all_from_table(self, table_id: str) -> int:
        """解除某桌號的所有策略綁定

        Args:
            table_id: 桌號

        Returns:
            解除的策略數量
        """
        if table_id not in self._attachments:
            return 0

        count = len(self._attachments[table_id])
        del self._attachments[table_id]
        return count

    def get_attached_tables(self, strategy_key: str) -> List[str]:
        """獲取策略綁定的所有桌號

        Args:
            strategy_key: 策略 key

        Returns:
            桌號列表
        """
        return [
            table_id
            for table_id, keys in self._attachments.items()
            if strategy_key in keys
        ]

    def get_strategies_for_table(
        self,
        table_id: str
    ) -> List[Tuple[str, StrategyDefinition]]:
        """獲取某桌號綁定的所有策略

        Args:
            table_id: 桌號

        Returns:
            [(strategy_key, StrategyDefinition), ...] 列表

        Note:
            如果桌號沒有綁定任何策略，返回空列表

        Example:
            >>> for key, definition in registry.get_strategies_for_table("table1"):
            ...     print(f"{key}: {definition.entry.mode}")
        """
        if table_id not in self._attachments:
            return []

        result = []
        for strategy_key in self._attachments[table_id]:
            definition = self._strategies.get(strategy_key)
            if definition:  # 防禦性檢查（理論上不應該為 None）
                result.append((strategy_key, definition))

        return result

    def is_attached(self, table_id: str, strategy_key: str) -> bool:
        """檢查策略是否綁定到桌號

        Args:
            table_id: 桌號
            strategy_key: 策略 key

        Returns:
            是否已綁定
        """
        return (
            table_id in self._attachments and
            strategy_key in self._attachments[table_id]
        )

    # ===== 快照和統計 =====

    def snapshot(self) -> Dict[str, any]:
        """獲取註冊表快照（用於調試和 UI 顯示）

        Returns:
            包含完整狀態的字典
        """
        return {
            "total_strategies": len(self._strategies),
            "total_tables": len(self._attachments),
            "strategies": {
                key: {
                    "pattern": def_.entry.pattern,
                    "dedup_mode": def_.entry.dedup.value,
                    "has_staking": def_.staking is not None,
                    "attached_tables": self.get_attached_tables(key),
                }
                for key, def_ in self._strategies.items()
            },
            "attachments": dict(self._attachments),
        }

    def clear(self) -> None:
        """清空所有策略和綁定（慎用！）

        通常用於測試或重新初始化
        """
        self._strategies.clear()
        self._attachments.clear()
