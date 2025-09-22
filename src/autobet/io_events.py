# src/autobet/io_events.py
import json, time, threading, random, logging
from typing import Callable, Optional, Dict

logger = logging.getLogger(__name__)

class NDJSONPlayer:
    def __init__(self, path: str, callback: Callable[[Dict], None], interval_sec: float = 1.2):
        self.path = path
        self.callback = callback
        self.interval = interval_sec
        self._t: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False

    def start(self):
        if self._running: return
        self._stop.clear()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        self._running = True

    def _run(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    if self._stop.is_set(): break
                    line = line.strip()
                    if not line: continue
                    try:
                        evt = json.loads(line)
                        self.callback(evt)
                    except Exception as e:
                        logger.warning(f"NDJSON bad line: {line[:120]}... ({e})")
                    time.sleep(self.interval)
        finally:
            self._running = False

    def is_running(self) -> bool:
        return self._running

    def stop(self):
        self._stop.set()
        if self._t and self._t.is_alive():
            self._t.join(timeout=1.5)
        self._running = False


class DemoFeeder:
    def __init__(self, interval_sec: float, callback: Callable[[Dict], None], seed: Optional[str] = None):
        self.interval = interval_sec
        self.callback = callback
        self._t: Optional[threading.Thread] = None
        self._stop = threading.Event()
        if seed is not None:
            random.seed(seed)
        self._round = 0
        self._running = False

    def start(self):
        if self._running: return
        self._stop.clear()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        self._running = True

    def _run(self):
        winners = ["B", "P", "T"]
        try:
            while not self._stop.is_set():
                self._round += 1
                evt = {
                    "type": "RESULT",
                    "round_id": f"DEMO-{int(time.time())}-{self._round:03d}",
                    "winner": random.choice(winners),
                    "ts": int(time.time() * 1000),
                }
                self.callback(evt)
                time.sleep(self.interval)
        finally:
            self._running = False

    def is_running(self) -> bool:
        return self._running

    def stop(self):
        self._stop.set()
        if self._t and self._t.is_alive():
            self._t.join(timeout=1.5)
        self._running = False