# tests/test_signal_tracker.py
import time

from src.autobet.lines.config import DedupMode, EntryConfig
from src.autobet.lines.signal import SignalTracker


def test_signal_tracker_overlapping_dedup():
    cfg = EntryConfig(pattern="BB then bet P", dedup=DedupMode.OVERLAP)
    tracker = SignalTracker(cfg)

    now = time.time()
    tracker.record("WG7", "1", "B", now - 5)
    tracker.record("WG7", "2", "B", now - 3)

    assert tracker.should_trigger("WG7", "3", now)
    # same hand should not trigger twice
    assert tracker.should_trigger("WG7", "3", now) is False


def test_signal_tracker_valid_window():
    cfg = EntryConfig(pattern="PP then bet B", valid_window_sec=2.0)
    tracker = SignalTracker(cfg)

    now = time.time()
    tracker.record("WG8", "1", "P", now - 5)
    tracker.record("WG8", "2", "P", now - 4)
    assert tracker.should_trigger("WG8", "3", now) is False

    tracker.record("WG8", "3", "P", now - 1)
    tracker.record("WG8", "4", "P", now - 0.5)
    assert tracker.should_trigger("WG8", "5", now) is True
