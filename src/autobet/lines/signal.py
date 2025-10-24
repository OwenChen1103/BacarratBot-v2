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
        # ✅ Overlap Dedup: 記錄最後一次觸發時「模式結束位置」的時間戳
        # 只有當新模式的「起始時間」晚於上次「結束時間」，才算是全新模式
        self.last_trigger_pattern_end_time: Dict[str, float] = {}

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

        # ✅ Overlap Dedup: 基於「模式起始位置」去重
        # 概念：PP 模式由「第1個P」和「第2個P」組成
        # 只有當「第1個P的時間戳」晚於上次觸發的「第2個P的時間戳」時，才算全新模式
        if self.config.dedup == DedupMode.OVERLAP:
            pattern_len = len(required_seq)
            pattern_start_time = self._pattern_start_time(table_id, pattern_len)
            pattern_end_time = self._pattern_end_time(table_id, pattern_len)

            if pattern_start_time is None or pattern_end_time is None:
                return False

            last_pattern_end_time = self.last_trigger_pattern_end_time.get(table_id, -1)

            # 如果這次模式的「起始時間」<= 上次模式的「結束時間」
            # 說明這是「重疊」或「包含在同一組觀察序列中」的模式，不應重複觸發
            if pattern_start_time <= last_pattern_end_time:
                return False

            # 記錄這次觸發時「模式結束位置」的時間戳（即最後一筆的時間戳）
            self.last_trigger_pattern_end_time[table_id] = pattern_end_time

        # ✅ Strict Dedup: 基於 round_id 嚴格去重（保留原邏輯）
        dedup_key = f"{table_id}:{current_round_id}"
        if self.config.dedup == DedupMode.OVERLAP:
            # Overlap 模式已經在上面處理，這裡保留舊代碼以防萬一
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
        """取得模式「起始位置」的時間戳（第1筆的時間戳）"""
        dq = self.history.get(table_id)
        if not dq or len(dq) < length:
            return None
        return list(dq)[-length][1]

    def _pattern_end_time(self, table_id: str, length: int) -> Optional[float]:
        """取得模式「結束位置」的時間戳（最後1筆的時間戳）"""
        dq = self.history.get(table_id)
        if not dq or len(dq) < length:
            return None
        return list(dq)[-1][1]

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
