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
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

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
    """

    def __init__(self):
        # 訂閱者: {EventType: [callback, ...]}
        self._subscribers: Dict[EventType, List[Callable]] = {}

        # 事件歷史（用於調試）
        self._event_history: List[Event] = []
        self._max_history = 1000

        logger.info("✅ EventBus 初始化完成")

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """
        訂閱事件

        Args:
            event_type: 事件類型
            callback: 回調函數，接收 Event 參數
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        self._subscribers[event_type].append(callback)
        logger.debug(f"📌 訂閱: {callback.__name__} → {event_type.value}")

    def publish(self, event: Event) -> None:
        """
        發布事件

        Args:
            event: 事件對象
        """
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

        # 分發給訂閱者
        subscribers = self._subscribers.get(event.type, [])
        for callback in subscribers:
            try:
                callback(event)
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


# 全局單例（可選）
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """獲取全局事件總線"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus
