# src/autobet/lines/performance.py
"""
性能追蹤模組

追蹤關鍵操作的延遲和性能指標：
1. 決策生成延遲（從階段變化到產生決策）
2. 執行延遲（從決策產生到執行完成）
3. 端到端延遲（從結果檢測到下注完成）
4. 統計報告（平均延遲、最大延遲、性能瓶頸）
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from statistics import mean, median, stdev


@dataclass
class PerformanceSample:
    """性能樣本"""
    timestamp: float
    operation: str  # 操作名稱（例如 "decision_generation"）
    duration_ms: float  # 持續時間（毫秒）
    success: bool = True
    metadata: Dict[str, any] = field(default_factory=dict)


@dataclass
class OperationStats:
    """操作統計"""
    operation: str
    total_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    # 延遲統計（毫秒）
    total_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    median_duration_ms: float = 0.0
    std_duration_ms: float = 0.0

    # 百分位數
    p50_ms: float = 0.0  # 中位數
    p95_ms: float = 0.0  # 95 百分位
    p99_ms: float = 0.0  # 99 百分位

    # 最近樣本（用於計算百分位數）
    recent_samples: deque = field(default_factory=lambda: deque(maxlen=1000))

    def update(self, duration_ms: float, success: bool = True) -> None:
        """更新統計"""
        self.total_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.avg_duration_ms = self.total_duration_ms / self.total_count

        # 保存樣本用於計算百分位數
        self.recent_samples.append(duration_ms)

        # 重新計算統計值
        self._recalculate_stats()

    def _recalculate_stats(self) -> None:
        """重新計算統計值"""
        if len(self.recent_samples) < 2:
            return

        samples = list(self.recent_samples)
        samples.sort()

        # 中位數
        self.median_duration_ms = median(samples)
        self.p50_ms = self.median_duration_ms

        # 95 百分位
        p95_idx = int(len(samples) * 0.95)
        self.p95_ms = samples[min(p95_idx, len(samples) - 1)]

        # 99 百分位
        p99_idx = int(len(samples) * 0.99)
        self.p99_ms = samples[min(p99_idx, len(samples) - 1)]

        # 標準差
        if len(samples) >= 2:
            self.std_duration_ms = stdev(samples)

    def get_success_rate(self) -> float:
        """獲取成功率"""
        if self.total_count == 0:
            return 0.0
        return self.success_count / self.total_count

    def to_dict(self) -> Dict:
        """轉換為字典"""
        return {
            "operation": self.operation,
            "total_count": self.total_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.get_success_rate(),
            "min_duration_ms": self.min_duration_ms if self.min_duration_ms != float('inf') else 0,
            "max_duration_ms": self.max_duration_ms,
            "avg_duration_ms": self.avg_duration_ms,
            "median_duration_ms": self.median_duration_ms,
            "std_duration_ms": self.std_duration_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
        }


class PerformanceTracker:
    """
    性能追蹤器

    追蹤系統中關鍵操作的延遲和性能
    """

    # 操作名稱常量
    OP_DECISION_GENERATION = "decision_generation"  # 決策生成
    OP_DECISION_EXECUTION = "decision_execution"  # 決策執行
    OP_END_TO_END = "end_to_end"  # 端到端（結果→下注完成）
    OP_PHASE_TRANSITION = "phase_transition"  # 階段轉換
    OP_CONFLICT_RESOLUTION = "conflict_resolution"  # 衝突解決
    OP_CAPITAL_ALLOCATION = "capital_allocation"  # 資金分配

    def __init__(self, max_history: int = 10000) -> None:
        """
        初始化性能追蹤器

        Args:
            max_history: 最大歷史樣本數量
        """
        self.stats: Dict[str, OperationStats] = {}
        self.samples: deque = deque(maxlen=max_history)

        # 當前進行中的操作（用於計算端到端延遲）
        self.pending_operations: Dict[str, float] = {}  # operation_id -> start_time

    def start_operation(self, operation_id: str) -> None:
        """
        開始一個操作（用於計算延遲）

        Args:
            operation_id: 操作唯一標識（例如 "decision_main_001"）
        """
        self.pending_operations[operation_id] = time.time()

    def end_operation(
        self,
        operation_id: str,
        operation_type: str,
        success: bool = True,
        metadata: Optional[Dict[str, any]] = None
    ) -> Optional[float]:
        """
        結束一個操作並記錄延遲

        Args:
            operation_id: 操作唯一標識
            operation_type: 操作類型（例如 OP_DECISION_GENERATION）
            success: 是否成功
            metadata: 附加元數據

        Returns:
            延遲時間（毫秒），如果操作未開始則返回 None
        """
        if operation_id not in self.pending_operations:
            return None

        start_time = self.pending_operations.pop(operation_id)
        duration_ms = (time.time() - start_time) * 1000.0

        # 記錄樣本
        sample = PerformanceSample(
            timestamp=time.time(),
            operation=operation_type,
            duration_ms=duration_ms,
            success=success,
            metadata=metadata or {}
        )
        self.samples.append(sample)

        # 更新統計
        if operation_type not in self.stats:
            self.stats[operation_type] = OperationStats(operation=operation_type)

        self.stats[operation_type].update(duration_ms, success)

        return duration_ms

    def record_instant(
        self,
        operation_type: str,
        duration_ms: float,
        success: bool = True,
        metadata: Optional[Dict[str, any]] = None
    ) -> None:
        """
        直接記錄一個瞬時操作（不需要 start/end）

        Args:
            operation_type: 操作類型
            duration_ms: 持續時間（毫秒）
            success: 是否成功
            metadata: 附加元數據
        """
        # 記錄樣本
        sample = PerformanceSample(
            timestamp=time.time(),
            operation=operation_type,
            duration_ms=duration_ms,
            success=success,
            metadata=metadata or {}
        )
        self.samples.append(sample)

        # 更新統計
        if operation_type not in self.stats:
            self.stats[operation_type] = OperationStats(operation=operation_type)

        self.stats[operation_type].update(duration_ms, success)

    def get_stats(self, operation_type: str) -> Optional[OperationStats]:
        """
        獲取操作統計

        Args:
            operation_type: 操作類型

        Returns:
            操作統計，如果不存在則返回 None
        """
        return self.stats.get(operation_type)

    def get_all_stats(self) -> Dict[str, OperationStats]:
        """獲取所有操作統計"""
        return self.stats.copy()

    def get_recent_samples(self, operation_type: Optional[str] = None, limit: int = 100) -> List[PerformanceSample]:
        """
        獲取最近的樣本

        Args:
            operation_type: 操作類型（None 表示所有類型）
            limit: 最大返回數量

        Returns:
            樣本列表
        """
        if operation_type is None:
            return list(self.samples)[-limit:]

        filtered = [s for s in self.samples if s.operation == operation_type]
        return filtered[-limit:]

    def get_summary(self) -> Dict:
        """
        獲取性能摘要

        Returns:
            包含所有操作統計的字典
        """
        return {
            "total_operations": sum(s.total_count for s in self.stats.values()),
            "total_samples": len(self.samples),
            "operations": {
                op_type: stats.to_dict()
                for op_type, stats in self.stats.items()
            }
        }

    def get_bottlenecks(self, threshold_ms: float = 100.0) -> List[Tuple[str, OperationStats]]:
        """
        獲取性能瓶頸（平均延遲超過閾值的操作）

        Args:
            threshold_ms: 閾值（毫秒）

        Returns:
            [(操作類型, 統計)] 列表，按平均延遲降序排列
        """
        bottlenecks = [
            (op_type, stats)
            for op_type, stats in self.stats.items()
            if stats.avg_duration_ms > threshold_ms
        ]

        # 按平均延遲降序排列
        bottlenecks.sort(key=lambda x: x[1].avg_duration_ms, reverse=True)

        return bottlenecks

    def get_slowest_operations(self, limit: int = 10) -> List[PerformanceSample]:
        """
        獲取最慢的操作樣本

        Args:
            limit: 最大返回數量

        Returns:
            樣本列表，按持續時間降序排列
        """
        sorted_samples = sorted(self.samples, key=lambda s: s.duration_ms, reverse=True)
        return sorted_samples[:limit]

    def clear(self) -> None:
        """清空所有統計和樣本"""
        self.stats.clear()
        self.samples.clear()
        self.pending_operations.clear()

    def reset_stats(self) -> None:
        """重置統計（保留最近的樣本）"""
        self.stats.clear()

        # 從樣本重新計算統計
        for sample in self.samples:
            if sample.operation not in self.stats:
                self.stats[sample.operation] = OperationStats(operation=sample.operation)
            self.stats[sample.operation].update(sample.duration_ms, sample.success)

    def print_report(self) -> None:
        """打印性能報告（用於調試）"""
        print("=" * 80)
        print("性能報告")
        print("=" * 80)
        print()

        summary = self.get_summary()
        print(f"總操作數: {summary['total_operations']}")
        print(f"總樣本數: {summary['total_samples']}")
        print()

        if not self.stats:
            print("暫無性能數據")
            return

        print(f"{'操作':<25} {'次數':>8} {'成功率':>8} {'平均':>10} {'中位數':>10} {'P95':>10} {'P99':>10} {'最大':>10}")
        print("-" * 80)

        for op_type, stats in sorted(self.stats.items()):
            print(
                f"{op_type:<25} "
                f"{stats.total_count:>8} "
                f"{stats.get_success_rate():>7.1%} "
                f"{stats.avg_duration_ms:>9.2f}ms "
                f"{stats.median_duration_ms:>9.2f}ms "
                f"{stats.p95_ms:>9.2f}ms "
                f"{stats.p99_ms:>9.2f}ms "
                f"{stats.max_duration_ms:>9.2f}ms"
            )

        print()

        # 顯示性能瓶頸
        bottlenecks = self.get_bottlenecks(threshold_ms=50.0)
        if bottlenecks:
            print("⚠️ 性能瓶頸（平均延遲 > 50ms）:")
            for op_type, stats in bottlenecks:
                print(f"  - {op_type}: 平均 {stats.avg_duration_ms:.2f}ms")
            print()

        print("=" * 80)
