# tests/test_event_bus.py
"""
EventBus 單元測試

測試範圍：
- 基本訂閱和發布
- 一次性訂閱
- 取消訂閱
- 事件歷史
- 性能監控
- 循環檢測
"""

import pytest
import time
from src.autobet.core.event_bus import EventBus, Event, EventType


class TestBasicSubscription:
    """測試基本訂閱功能"""

    def test_subscribe_and_publish(self):
        """測試訂閱和發布事件"""
        bus = EventBus()
        received_events = []

        def handler(event: Event):
            received_events.append(event)

        bus.subscribe(EventType.RESULT_DETECTED, handler)

        event = Event(
            type=EventType.RESULT_DETECTED,
            timestamp=time.time(),
            source="test",
            data={"winner": "B"}
        )

        bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].type == EventType.RESULT_DETECTED
        assert received_events[0].data["winner"] == "B"

    def test_multiple_subscribers(self):
        """測試多個訂閱者"""
        bus = EventBus()
        received_1 = []
        received_2 = []

        def handler1(event: Event):
            received_1.append(event)

        def handler2(event: Event):
            received_2.append(event)

        bus.subscribe(EventType.PHASE_CHANGED, handler1)
        bus.subscribe(EventType.PHASE_CHANGED, handler2)

        event = Event(
            type=EventType.PHASE_CHANGED,
            timestamp=time.time(),
            source="test",
            data={"phase": "bettable"}
        )

        bus.publish(event)

        assert len(received_1) == 1
        assert len(received_2) == 1
        assert received_1[0] == received_2[0]

    def test_duplicate_subscription_warning(self):
        """測試重複訂閱會發出警告"""
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.RESULT_DETECTED, handler)
        bus.subscribe(EventType.RESULT_DETECTED, handler)  # 重複訂閱

        event = Event(
            type=EventType.RESULT_DETECTED,
            timestamp=time.time(),
            source="test",
            data={}
        )

        bus.publish(event)

        # 應該只接收一次
        assert len(received) == 1


class TestOnceSubscription:
    """測試一次性訂閱功能"""

    def test_subscribe_once(self):
        """測試一次性訂閱只觸發一次"""
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.subscribe_once(EventType.BET_EXECUTED, handler)

        event1 = Event(type=EventType.BET_EXECUTED, timestamp=time.time(), source="test", data={})
        event2 = Event(type=EventType.BET_EXECUTED, timestamp=time.time(), source="test", data={})

        bus.publish(event1)
        bus.publish(event2)

        # 只應接收第一個事件
        assert len(received) == 1

    def test_mixed_subscriptions(self):
        """測試混合普通訂閱和一次性訂閱"""
        bus = EventBus()
        normal_received = []
        once_received = []

        def normal_handler(event: Event):
            normal_received.append(event)

        def once_handler(event: Event):
            once_received.append(event)

        bus.subscribe(EventType.BET_EXECUTED, normal_handler)
        bus.subscribe_once(EventType.BET_EXECUTED, once_handler)

        event1 = Event(type=EventType.BET_EXECUTED, timestamp=time.time(), source="test", data={})
        event2 = Event(type=EventType.BET_EXECUTED, timestamp=time.time(), source="test", data={})

        bus.publish(event1)
        bus.publish(event2)

        assert len(normal_received) == 2
        assert len(once_received) == 1


class TestUnsubscribe:
    """測試取消訂閱功能"""

    def test_unsubscribe_normal(self):
        """測試取消普通訂閱"""
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.RESULT_DETECTED, handler)

        event1 = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test", data={})
        bus.publish(event1)

        # 取消訂閱
        result = bus.unsubscribe(EventType.RESULT_DETECTED, handler)
        assert result is True

        event2 = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test", data={})
        bus.publish(event2)

        # 只應接收第一個事件
        assert len(received) == 1

    def test_unsubscribe_nonexistent(self):
        """測試取消不存在的訂閱"""
        bus = EventBus()

        def handler(event: Event):
            pass

        result = bus.unsubscribe(EventType.RESULT_DETECTED, handler)
        assert result is False


class TestEventHistory:
    """測試事件歷史功能"""

    def test_event_history(self):
        """測試事件歷史記錄"""
        bus = EventBus()

        event1 = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test1", data={})
        event2 = Event(type=EventType.PHASE_CHANGED, timestamp=time.time(), source="test2", data={})

        bus.publish(event1)
        bus.publish(event2)

        history = bus.get_history()
        assert len(history) == 2
        # 最新的在前
        assert history[0].source == "test2"
        assert history[1].source == "test1"

    def test_event_history_filter(self):
        """測試事件歷史過濾"""
        bus = EventBus()

        event1 = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test1", data={})
        event2 = Event(type=EventType.PHASE_CHANGED, timestamp=time.time(), source="test2", data={})
        event3 = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test3", data={})

        bus.publish(event1)
        bus.publish(event2)
        bus.publish(event3)

        history = bus.get_history(event_type=EventType.RESULT_DETECTED)
        assert len(history) == 2
        assert history[0].source == "test3"
        assert history[1].source == "test1"

    def test_event_history_limit(self):
        """測試事件歷史數量限制"""
        bus = EventBus()

        for i in range(20):
            event = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source=f"test{i}", data={})
            bus.publish(event)

        history = bus.get_history(limit=5)
        assert len(history) == 5

    def test_clear_history(self):
        """測試清空事件歷史"""
        bus = EventBus()

        event = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test", data={})
        bus.publish(event)

        assert len(bus.get_history()) == 1

        bus.clear_history()
        assert len(bus.get_history()) == 0


class TestPerformanceTracking:
    """測試性能監控功能"""

    def test_performance_tracking_enabled(self):
        """測試啟用性能追蹤"""
        bus = EventBus(enable_performance_tracking=True)
        received = []

        def handler(event: Event):
            received.append(event)
            time.sleep(0.001)  # 模擬處理時間

        bus.subscribe(EventType.RESULT_DETECTED, handler)

        for _ in range(5):
            event = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test", data={})
            bus.publish(event)

        stats = bus.get_performance_stats()
        key = f"{EventType.RESULT_DETECTED.value}::handler"

        assert key in stats
        assert stats[key]["count"] == 5
        assert stats[key]["total_time"] > 0
        assert stats[key]["avg_time"] > 0
        assert stats[key]["max_time"] > 0
        assert stats[key]["min_time"] > 0

    def test_performance_tracking_disabled(self):
        """測試未啟用性能追蹤"""
        bus = EventBus(enable_performance_tracking=False)

        def handler(event: Event):
            pass

        bus.subscribe(EventType.RESULT_DETECTED, handler)

        event = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test", data={})
        bus.publish(event)

        stats = bus.get_performance_stats()
        assert len(stats) == 0

    def test_reset_performance_stats(self):
        """測試重置性能統計"""
        bus = EventBus(enable_performance_tracking=True)

        def handler(event: Event):
            pass

        bus.subscribe(EventType.RESULT_DETECTED, handler)

        event = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test", data={})
        bus.publish(event)

        stats_before = bus.get_performance_stats()
        assert len(stats_before) > 0

        bus.reset_performance_stats()
        stats_after = bus.get_performance_stats()
        assert len(stats_after) == 0


class TestLoopDetection:
    """測試循環檢測功能"""

    def test_event_loop_detection(self):
        """測試事件循環檢測"""
        bus = EventBus()
        publish_count = [0]

        def handler(event: Event):
            publish_count[0] += 1
            if publish_count[0] < 20:  # 嘗試觸發無限循環
                nested_event = Event(
                    type=EventType.RESULT_DETECTED,
                    timestamp=time.time(),
                    source="nested",
                    data={}
                )
                bus.publish(nested_event)

        bus.subscribe(EventType.RESULT_DETECTED, handler)

        event = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test", data={})
        bus.publish(event)

        # 應該在達到最大深度時停止
        assert publish_count[0] <= bus._max_depth + 1


class TestErrorHandling:
    """測試錯誤處理"""

    def test_callback_exception_does_not_break_bus(self):
        """測試回調函數拋出異常不會影響其他訂閱者"""
        bus = EventBus()
        received_1 = []
        received_2 = []

        def handler1(event: Event):
            raise Exception("Test error")

        def handler2(event: Event):
            received_2.append(event)

        bus.subscribe(EventType.RESULT_DETECTED, handler1)
        bus.subscribe(EventType.RESULT_DETECTED, handler2)

        event = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test", data={})
        bus.publish(event)

        # handler2 應該仍然收到事件
        assert len(received_2) == 1


class TestSubscriberCount:
    """測試訂閱者計數"""

    def test_get_subscriber_count_specific(self):
        """測試獲取特定事件的訂閱者數量"""
        bus = EventBus()

        def handler1(event: Event):
            pass

        def handler2(event: Event):
            pass

        bus.subscribe(EventType.RESULT_DETECTED, handler1)
        bus.subscribe(EventType.RESULT_DETECTED, handler2)
        bus.subscribe_once(EventType.RESULT_DETECTED, lambda e: None)

        count = bus.get_subscriber_count(EventType.RESULT_DETECTED)
        assert count == 3

    def test_get_subscriber_count_total(self):
        """測試獲取總訂閱者數量"""
        bus = EventBus()

        def handler(event: Event):
            pass

        bus.subscribe(EventType.RESULT_DETECTED, handler)
        bus.subscribe(EventType.PHASE_CHANGED, handler)
        bus.subscribe_once(EventType.BET_EXECUTED, handler)

        total = bus.get_subscriber_count()
        assert total == 3


class TestEventID:
    """測試事件 ID 生成"""

    def test_event_id_auto_generation(self):
        """測試事件 ID 自動生成"""
        bus = EventBus()

        event = Event(type=EventType.RESULT_DETECTED, timestamp=time.time(), source="test", data={})
        assert event.event_id is None

        bus.publish(event)
        assert event.event_id is not None
        assert event.event_id.startswith("result_detected-")

    def test_event_id_preserved(self):
        """測試手動設置的事件 ID 會被保留"""
        bus = EventBus()

        event = Event(
            type=EventType.RESULT_DETECTED,
            timestamp=time.time(),
            source="test",
            data={},
            event_id="custom-id-123"
        )

        bus.publish(event)
        assert event.event_id == "custom-id-123"
