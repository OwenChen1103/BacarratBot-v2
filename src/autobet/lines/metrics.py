# src/autobet/lines/metrics.py
"""
度量與事件記錄模組

根據規範 §K 實現：
- 完整的事件追蹤
- 延遲度量
- PnL 分層統計
- 觸發/凍結事件記錄
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class EventType(str, Enum):
    """事件類型"""
    SIGNAL_TRIGGERED = "signal_triggered"  # 信號觸發
    LINE_ARMED = "line_armed"  # Line 進入 ARMED 狀態
    LINE_ENTERED = "line_entered"  # Line 進入 ENTERED 狀態（已下注）
    LINE_PROGRESSED = "line_progressed"  # Layer 前進
    LINE_RESET = "line_reset"  # Layer 重置
    LINE_FROZEN = "line_frozen"  # Line 凍結
    LINE_UNFROZEN = "line_unfrozen"  # Line 解凍
    RISK_TRIGGERED = "risk_triggered"  # 風控觸發
    CONFLICT_RESOLVED = "conflict_resolved"  # 衝突解決
    CAPITAL_RESERVED = "capital_reserved"  # 資金預留
    CAPITAL_RELEASED = "capital_released"  # 資金釋放
    OUTCOME_RECORDED = "outcome_recorded"  # 結果記錄


@dataclass
class LatencyMetrics:
    """延遲度量（§K）"""
    detect_bettable_ms: Optional[float] = None  # 偵測可下注 < 200ms
    panel_green_ms: Optional[float] = None  # 面板變綠 < 100ms
    detect_to_action_ms: Optional[float] = None  # 偵測→首個滑鼠動作 < 150ms


@dataclass
class LayerMetrics:
    """層級度量"""
    layer_index: int
    stake: int  # 含正負號，表示方向
    pnl: float = 0.0  # 該層級的盈虧
    win_count: int = 0
    loss_count: int = 0
    skip_count: int = 0  # Tie 跳過次數
    total_wagered: float = 0.0  # 累計下注額


@dataclass
class LineMetrics:
    """Line 度量統計"""
    strategy_key: str
    table_id: str

    # 層級統計
    current_layer: int = 0
    max_layer_reached: int = 0
    layer_stats: Dict[int, LayerMetrics] = field(default_factory=dict)

    # PnL 統計
    total_pnl: float = 0.0
    session_pnl: float = 0.0
    peak_pnl: float = 0.0
    trough_pnl: float = 0.0

    # 計數統計
    total_bets: int = 0
    total_wins: int = 0
    total_losses: int = 0
    total_skips: int = 0

    # 連勝/連輸
    current_win_streak: int = 0
    current_loss_streak: int = 0
    max_win_streak: int = 0
    max_loss_streak: int = 0

    # 觸發統計
    trigger_count: int = 0
    armed_count: int = 0
    entered_count: int = 0

    # 凍結統計
    frozen_count: int = 0
    total_frozen_time_sec: float = 0.0

    # 配置記錄（§K）
    first_trigger_layer: int = 1
    cross_table_mode: str = "reset"

    # 時間戳
    created_at: float = field(default_factory=time.time)
    last_updated_at: float = field(default_factory=time.time)

    def update_layer_stats(self, layer_index: int, stake: int, outcome: str, pnl_delta: float) -> None:
        """更新層級統計"""
        if layer_index not in self.layer_stats:
            self.layer_stats[layer_index] = LayerMetrics(layer_index=layer_index, stake=stake)

        layer = self.layer_stats[layer_index]
        layer.pnl += pnl_delta
        layer.total_wagered += abs(stake)

        if outcome == "win":
            layer.win_count += 1
            self.total_wins += 1
            self.current_win_streak += 1
            self.current_loss_streak = 0
            self.max_win_streak = max(self.max_win_streak, self.current_win_streak)
        elif outcome == "loss":
            layer.loss_count += 1
            self.total_losses += 1
            self.current_loss_streak += 1
            self.current_win_streak = 0
            self.max_loss_streak = max(self.max_loss_streak, self.current_loss_streak)
        elif outcome == "skip":
            layer.skip_count += 1
            self.total_skips += 1

        self.total_pnl += pnl_delta
        self.session_pnl += pnl_delta
        self.peak_pnl = max(self.peak_pnl, self.total_pnl)
        self.trough_pnl = min(self.trough_pnl, self.total_pnl)
        self.max_layer_reached = max(self.max_layer_reached, layer_index)
        self.last_updated_at = time.time()

    def record_trigger(self) -> None:
        """記錄觸發事件"""
        self.trigger_count += 1
        self.last_updated_at = time.time()

    def record_armed(self) -> None:
        """記錄 ARMED 事件"""
        self.armed_count += 1
        self.last_updated_at = time.time()

    def record_entered(self, layer_index: int) -> None:
        """記錄 ENTERED 事件"""
        self.entered_count += 1
        self.total_bets += 1
        self.current_layer = layer_index
        self.last_updated_at = time.time()

    def record_frozen(self, duration_sec: Optional[float] = None) -> None:
        """記錄凍結事件"""
        self.frozen_count += 1
        if duration_sec:
            self.total_frozen_time_sec += duration_sec
        self.last_updated_at = time.time()

    def get_win_rate(self) -> float:
        """獲取勝率"""
        total = self.total_wins + self.total_losses
        if total == 0:
            return 0.0
        return self.total_wins / total

    def get_avg_bet_size(self) -> float:
        """獲取平均下注額"""
        if self.total_bets == 0:
            return 0.0
        total_wagered = sum(layer.total_wagered for layer in self.layer_stats.values())
        return total_wagered / self.total_bets

    def to_dict(self) -> Dict:
        """轉換為字典（用於序列化）"""
        return {
            "strategy_key": self.strategy_key,
            "table_id": self.table_id,
            "current_layer": self.current_layer,
            "max_layer_reached": self.max_layer_reached,
            "total_pnl": self.total_pnl,
            "session_pnl": self.session_pnl,
            "peak_pnl": self.peak_pnl,
            "trough_pnl": self.trough_pnl,
            "total_bets": self.total_bets,
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "total_skips": self.total_skips,
            "win_rate": self.get_win_rate(),
            "avg_bet_size": self.get_avg_bet_size(),
            "current_win_streak": self.current_win_streak,
            "current_loss_streak": self.current_loss_streak,
            "max_win_streak": self.max_win_streak,
            "max_loss_streak": self.max_loss_streak,
            "trigger_count": self.trigger_count,
            "armed_count": self.armed_count,
            "entered_count": self.entered_count,
            "frozen_count": self.frozen_count,
            "total_frozen_time_sec": self.total_frozen_time_sec,
            "first_trigger_layer": self.first_trigger_layer,
            "cross_table_mode": self.cross_table_mode,
            "created_at": self.created_at,
            "last_updated_at": self.last_updated_at,
            "layer_stats": {
                idx: {
                    "stake": layer.stake,
                    "pnl": layer.pnl,
                    "win_count": layer.win_count,
                    "loss_count": layer.loss_count,
                    "skip_count": layer.skip_count,
                    "total_wagered": layer.total_wagered,
                }
                for idx, layer in self.layer_stats.items()
            },
        }


@dataclass
class EventRecord:
    """事件記錄"""
    event_type: EventType
    timestamp: float
    table_id: str
    round_id: Optional[str] = None
    strategy_key: Optional[str] = None
    layer_index: Optional[int] = None
    stake: Optional[int] = None
    direction: Optional[str] = None
    amount: Optional[float] = None
    pnl_delta: Optional[float] = None
    outcome: Optional[str] = None
    reason: Optional[str] = None
    metadata: Dict[str, any] = field(default_factory=dict)
    latency: Optional[LatencyMetrics] = None

    def to_dict(self) -> Dict:
        """轉換為字典（用於日誌）"""
        data = {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "table_id": self.table_id,
        }

        if self.round_id:
            data["round_id"] = self.round_id
        if self.strategy_key:
            data["strategy_key"] = self.strategy_key
        if self.layer_index is not None:
            data["layer_index"] = self.layer_index
        if self.stake is not None:
            data["stake"] = self.stake
        if self.direction:
            data["direction"] = self.direction
        if self.amount is not None:
            data["amount"] = self.amount
        if self.pnl_delta is not None:
            data["pnl_delta"] = self.pnl_delta
        if self.outcome:
            data["outcome"] = self.outcome
        if self.reason:
            data["reason"] = self.reason
        if self.metadata:
            data["metadata"] = self.metadata
        if self.latency:
            data["latency"] = {
                "detect_bettable_ms": self.latency.detect_bettable_ms,
                "panel_green_ms": self.latency.panel_green_ms,
                "detect_to_action_ms": self.latency.detect_to_action_ms,
            }

        return data


class MetricsTracker:
    """度量追蹤器"""

    def __init__(self) -> None:
        self.line_metrics: Dict[Tuple[str, str], LineMetrics] = {}  # (table_id, strategy_key) -> metrics
        self.event_history: List[EventRecord] = []
        self.max_history_size: int = 10000  # 最多保留 10000 條事件

    def get_or_create_line_metrics(
        self,
        table_id: str,
        strategy_key: str,
        first_trigger_layer: int = 1,
        cross_table_mode: str = "reset",
    ) -> LineMetrics:
        """獲取或創建 Line 度量"""
        key = (table_id, strategy_key)
        if key not in self.line_metrics:
            self.line_metrics[key] = LineMetrics(
                strategy_key=strategy_key,
                table_id=table_id,
                first_trigger_layer=first_trigger_layer,
                cross_table_mode=cross_table_mode,
            )
        return self.line_metrics[key]

    def record_event(self, event: EventRecord) -> None:
        """記錄事件"""
        self.event_history.append(event)

        # 限制歷史大小
        if len(self.event_history) > self.max_history_size:
            self.event_history = self.event_history[-self.max_history_size:]

    def get_line_metrics(self, table_id: str, strategy_key: str) -> Optional[LineMetrics]:
        """獲取 Line 度量"""
        return self.line_metrics.get((table_id, strategy_key))

    def get_all_line_metrics(self) -> List[LineMetrics]:
        """獲取所有 Line 度量"""
        return list(self.line_metrics.values())

    def get_recent_events(self, limit: int = 100) -> List[EventRecord]:
        """獲取最近的事件"""
        return self.event_history[-limit:]

    def get_events_by_type(self, event_type: EventType, limit: Optional[int] = None) -> List[EventRecord]:
        """按類型獲取事件"""
        events = [e for e in self.event_history if e.event_type == event_type]
        if limit:
            return events[-limit:]
        return events

    def get_global_stats(self) -> Dict:
        """獲取全局統計"""
        all_metrics = self.get_all_line_metrics()

        if not all_metrics:
            return {
                "total_lines": 0,
                "total_bets": 0,
                "total_pnl": 0.0,
                "global_win_rate": 0.0,
            }

        total_bets = sum(m.total_bets for m in all_metrics)
        total_wins = sum(m.total_wins for m in all_metrics)
        total_losses = sum(m.total_losses for m in all_metrics)
        total_pnl = sum(m.total_pnl for m in all_metrics)

        win_rate = 0.0
        if total_wins + total_losses > 0:
            win_rate = total_wins / (total_wins + total_losses)

        return {
            "total_lines": len(all_metrics),
            "total_bets": total_bets,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "total_pnl": total_pnl,
            "global_win_rate": win_rate,
            "active_lines": len([m for m in all_metrics if m.current_layer > 0]),
        }

    def clear_events(self) -> None:
        """清空事件歷史"""
        self.event_history.clear()

    def reset_session_metrics(self) -> None:
        """重置會話度量（保留歷史）"""
        for metrics in self.line_metrics.values():
            metrics.session_pnl = 0.0
