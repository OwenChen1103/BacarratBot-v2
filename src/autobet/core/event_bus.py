# src/autobet/core/event_bus.py
"""
事件總線 - 統一的事件分發機制

解決問題：
1. 信號在組件間來回跳轉
2. 事件流不清晰
3. 難以追蹤和調試

設計原則：
- 單向數據流
- 事件溯源
- 組件解耦

版本：P1 Task 3 - 完善版
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """事件類型"""
    # 結果檢測
    RESULT_DETECTED = "result_detected"

    # 階段轉換
    PHASE_CHANGED = "phase_changed"

    # 策略決策
    STRATEGY_TRIGGERED = "strategy_triggered"
    STRATEGY_DECISION = "strategy_decision"

    # 下注執行
    BET_PLACED = "bet_placed"
    BET_EXECUTED = "bet_executed"
    BET_FAILED = "bet_failed"

    # 結果結算
    POSITION_SETTLED = "position_settled"
    PNL_UPDATED = "pnl_updated"


@dataclass
class Event:
    """事件基類"""
    type: EventType
    timestamp: float
    source: str  # 事件來源組件
    data: Dict[str, Any] = field(default_factory=dict)

    # 元數據
    event_id: Optional[str] = None
    correlation_id: Optional[str] = None  # 用於追蹤相關事件


class EventBus:
    """
    事件總線 - 中央事件分發系統

    優點：
    1. 組件解耦：組件只需發布/訂閱事件，不需要知道其他組件
    2. 事件歷史：保留事件記錄，方便調試和回溯
    3. 可觀測性：統一的日誌和監控點

    新功能（P1 Task 3）:
    - subscribe_once: 一次性訂閱
    - unsubscribe: 取消訂閱
    - 性能監控: 追蹤事件處理時間
    - 循環檢測: 防止事件循環發布
    """

    def __init__(self, enable_performance_tracking: bool = False):
        # 訂閱者: {EventType: [callback, ...]}
        self._subscribers: Dict[EventType, List[Callable]] = {}

        # 一次性訂閱者: {EventType: [callback, ...]}
        self._once_subscribers: Dict[EventType, List[Callable]] = {}

        # 事件歷史（用於調試）
        self._event_history: List[Event] = []
        self._max_history = 1000

        # 性能監控
        self._enable_performance_tracking = enable_performance_tracking
        self._performance_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "count": 0,
            "total_time": 0.0,
            "max_time": 0.0,
            "min_time": float('inf'),
        })

        # 循環檢測：追蹤當前正在處理的事件類型
        self._processing_stack: List[EventType] = []
        self._max_depth = 10  # 最大嵌套深度

        logger.info("✅ EventBus 初始化完成 (performance_tracking=%s)", enable_performance_tracking)

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """
        訂閱事件

        Args:
            event_type: 事件類型
            callback: 回調函數，接收 Event 參數
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        # 避免重複訂閱
        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)
            logger.debug(f"📌 訂閱: {callback.__name__} → {event_type.value}")
        else:
            logger.warning(f"⚠️ 重複訂閱: {callback.__name__} → {event_type.value}")

    def subscribe_once(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """
        訂閱一次性事件（回調執行一次後自動取消訂閱）

        Args:
            event_type: 事件類型
            callback: 回調函數，接收 Event 參數
        """
        if event_type not in self._once_subscribers:
            self._once_subscribers[event_type] = []

        if callback not in self._once_subscribers[event_type]:
            self._once_subscribers[event_type].append(callback)
            logger.debug(f"📌 一次性訂閱: {callback.__name__} → {event_type.value}")

    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> bool:
        """
        取消訂閱事件

        Args:
            event_type: 事件類型
            callback: 回調函數

        Returns:
            是否成功取消訂閱
        """
        removed = False

        # 從普通訂閱者中移除
        if event_type in self._subscribers and callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
            logger.debug(f"✂️ 取消訂閱: {callback.__name__} → {event_type.value}")
            removed = True

        # 從一次性訂閱者中移除
        if event_type in self._once_subscribers and callback in self._once_subscribers[event_type]:
            self._once_subscribers[event_type].remove(callback)
            removed = True

        if not removed:
            logger.warning(f"⚠️ 未找到訂閱: {callback.__name__} → {event_type.value}")

        return removed

    def publish(self, event: Event) -> None:
        """
        發布事件

        Args:
            event: 事件對象
        """
        # 循環檢測
        if len(self._processing_stack) >= self._max_depth:
            logger.error(
                f"❌ 事件循環檢測: 嵌套深度超過 {self._max_depth} | "
                f"stack={[e.value for e in self._processing_stack]}"
            )
            return

        # 生成事件 ID
        if not event.event_id:
            event.event_id = f"{event.type.value}-{int(event.timestamp * 1000)}"

        # 記錄到歷史
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        logger.debug(
            f"📤 發布事件: {event.type.value} | source={event.source} | "
            f"data={list(event.data.keys())}"
        )

        # 進入處理棧（用於循環檢測）
        self._processing_stack.append(event.type)

        try:
            # 分發給普通訂閱者
            subscribers = self._subscribers.get(event.type, [])
            for callback in subscribers:
                self._dispatch_to_callback(event, callback)

            # 分發給一次性訂閱者
            once_subscribers = self._once_subscribers.get(event.type, [])
            if once_subscribers:
                # 複製列表，因為回調執行後會修改原列表
                once_subscribers_copy = once_subscribers.copy()
                for callback in once_subscribers_copy:
                    self._dispatch_to_callback(event, callback)
                    # 執行後移除
                    if callback in self._once_subscribers.get(event.type, []):
                        self._once_subscribers[event.type].remove(callback)
        finally:
            # 離開處理棧
            self._processing_stack.pop()

    def _dispatch_to_callback(self, event: Event, callback: Callable) -> None:
        """
        分發事件到單個回調函數

        Args:
            event: 事件對象
            callback: 回調函數
        """
        start_time = time.time() if self._enable_performance_tracking else None

        try:
            callback(event)

            # 性能統計
            if self._enable_performance_tracking and start_time:
                elapsed = time.time() - start_time
                key = f"{event.type.value}::{callback.__name__}"
                stats = self._performance_stats[key]
                stats["count"] += 1
                stats["total_time"] += elapsed
                stats["max_time"] = max(stats["max_time"], elapsed)
                stats["min_time"] = min(stats["min_time"], elapsed)

        except Exception as e:
            logger.error(
                f"❌ 事件處理錯誤: {callback.__name__} | "
                f"event={event.type.value} | error={e}",
                exc_info=True
            )

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100
    ) -> List[Event]:
        """
        獲取事件歷史

        Args:
            event_type: 過濾事件類型（可選）
            limit: 返回數量限制

        Returns:
            事件列表（最新的在前）
        """
        history = self._event_history[::-1]  # 反轉，最新的在前

        if event_type:
            history = [e for e in history if e.type == event_type]

        return history[:limit]

    def clear_history(self) -> None:
        """清空事件歷史"""
        self._event_history.clear()
        logger.info("🗑️ 事件歷史已清空")

    def get_performance_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        獲取性能統計

        Returns:
            性能統計字典: {
                "event_type::callback_name": {
                    "count": int,
                    "total_time": float,
                    "avg_time": float,
                    "max_time": float,
                    "min_time": float,
                }
            }
        """
        if not self._enable_performance_tracking:
            logger.warning("⚠️ 性能追蹤未啟用")
            return {}

        result = {}
        for key, stats in self._performance_stats.items():
            result[key] = {
                "count": stats["count"],
                "total_time": stats["total_time"],
                "avg_time": stats["total_time"] / stats["count"] if stats["count"] > 0 else 0.0,
                "max_time": stats["max_time"],
                "min_time": stats["min_time"] if stats["min_time"] != float('inf') else 0.0,
            }
        return result

    def reset_performance_stats(self) -> None:
        """重置性能統計"""
        self._performance_stats.clear()
        logger.info("🗑️ 性能統計已重置")

    def get_subscriber_count(self, event_type: Optional[EventType] = None) -> int:
        """
        獲取訂閱者數量

        Args:
            event_type: 事件類型（可選，不指定則返回總數）

        Returns:
            訂閱者數量
        """
        if event_type:
            count = len(self._subscribers.get(event_type, []))
            count += len(self._once_subscribers.get(event_type, []))
            return count
        else:
            total = sum(len(subs) for subs in self._subscribers.values())
            total += sum(len(subs) for subs in self._once_subscribers.values())
            return total


# 全局單例（可選）
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """獲取全局事件總線"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus
