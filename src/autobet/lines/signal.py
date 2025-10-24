# src/autobet/lines/signal.py
import collections
import time
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

from .config import DedupMode, EntryConfig


@dataclass(frozen=True)
class SignalEvent:
    table_id: str
    round_id: str
    winner: Optional[str]
    timestamp: float


class SignalTracker:
    """Tracks recent outcomes and determines entry triggers."""

    def __init__(self, config: EntryConfig):
        self.config = config
        self.history: Dict[str, Deque[Tuple[str, float]]] = collections.defaultdict(collections.deque)
        self.last_trigger: Dict[str, str] = {}

    def record(self, table_id: str, round_id: str, winner: str, ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        deque = self.history[table_id]
        deque.append((winner, ts))
        while len(deque) > 20:
            deque.popleft()

    def should_trigger(self, table_id: str, current_round_id: str, state_timestamp: float) -> bool:
        pattern = self.config.pattern
        required_seq = self._pattern_sequence(pattern)
        winners = self._get_recent_winners(table_id, len(required_seq))
        if not winners:
            return False

        if not self._match_pattern(required_seq, winners):
            return False

        if self.config.valid_window_sec > 0:
            pattern_time = self._pattern_start_time(table_id, len(required_seq))
            if pattern_time is None or (state_timestamp - pattern_time) > self.config.valid_window_sec:
                return False

        dedup_key = f"{table_id}:{current_round_id}"
        if self.config.dedup == DedupMode.OVERLAP:
            last = self.last_trigger.get(table_id)
            if last == dedup_key:
                return False
            self.last_trigger[table_id] = dedup_key
        elif self.config.dedup == DedupMode.STRICT:
            if dedup_key in self.last_trigger:
                return False
            self.last_trigger[dedup_key] = dedup_key

            # ✅ 限制 STRICT 模式下的字典大小（避免長時間運行後內存膨脹）
            max_dedup_keys = 1000  # 最多保留 1000 筆去重記錄
            if len(self.last_trigger) > max_dedup_keys:
                # 移除最舊的 100 筆（批量刪除以提高效率）
                keys_to_remove = list(self.last_trigger.keys())[:100]
                for key in keys_to_remove:
                    self.last_trigger.pop(key, None)

        return True

    def _get_recent_winners(self, table_id: str, length: int) -> List[str]:
        dq = self.history.get(table_id)
        if not dq:
            return []
        # 返回最近 length 筆記錄，如果不足則返回全部
        return [winner for winner, _ in list(dq)[-length:]]

    def _pattern_start_time(self, table_id: str, length: int) -> Optional[float]:
        dq = self.history.get(table_id)
        if not dq or len(dq) < length:
            return None
        return list(dq)[-length][1]

    @staticmethod
    def _pattern_sequence(pattern: str) -> List[str]:
        upper = pattern.upper()
        if "THEN" in upper:
            prefix = upper.split("THEN", 1)[0]
        else:
            prefix = upper
        return [ch for ch in prefix if ch in {"B", "P", "T"}]

    @staticmethod
    def _match_pattern(required: List[str], winners: List[str]) -> bool:
        if not required or len(required) != len(winners):
            return False
        recent = [winner.upper()[0] for winner in winners]
        return recent == required
