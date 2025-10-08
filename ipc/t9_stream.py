# ipc/t9_stream.py
# -*- coding: utf-8 -*-
"""Simple SSE client for consuming T9-Web-Api result streams."""

import json
import logging
import threading
import time
from typing import Callable, Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)


class T9StreamClient:
    """Background SSE client that pulls result events from T9-Web-Api."""

    def __init__(
        self,
        base_url: str,
        *,
        event_types: str = "result",
        headers: Optional[Dict[str, str]] = None,
        retry_delay: float = 5.0,
        on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_status: Optional[Callable[[str, Optional[str]], None]] = None,
        session: Optional[requests.Session] = None,
        request_timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url
        self.event_types = event_types
        self.headers = headers or {"Accept": "text/event-stream"}
        self.retry_delay = max(1.0, retry_delay)
        self.request_timeout = max(5.0, request_timeout)
        self.on_event = on_event
        self.on_status = on_status

        self._session = session or requests.Session()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="T9StreamClient", daemon=True)
            self._thread.start()

    # ------------------------------------------------------------------
    def stop(self) -> None:
        with self._lock:
            self._stop.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self._thread = None

    # ------------------------------------------------------------------
    def _emit_status(self, status: str, detail: Optional[str] = None) -> None:
        if self.on_status:
            try:
                self.on_status(status, detail)
            except Exception:
                logger.exception("T9StreamClient status callback failed")

    # ------------------------------------------------------------------
    def _run(self) -> None:
        params = {}
        if self.event_types:
            params["event_types"] = self.event_types

        while not self._stop.is_set():
            try:
                self._emit_status("connecting", self.base_url)

                response = self._session.get(
                    self.base_url,
                    params=params,
                    headers=self.headers,
                    stream=True,
                    timeout=(5.0, self.request_timeout),
                )

                if response.status_code != requests.codes.ok:
                    detail = f"HTTP {response.status_code}"
                    logger.warning("T9 stream HTTP error: %s", detail)
                    self._emit_status("error", detail)
                    response.close()
                    self._wait_before_retry()
                    continue

                self._emit_status("connected", None)
                logger.info("T9 stream connected: %s", response.url)

                for payload in self._iter_sse(response):
                    if payload is None:
                        continue
                    event_name, data = payload
                    if not data:
                        continue
                    if self.on_event:
                        try:
                            self.on_event(event_name, data)
                        except Exception:
                            logger.exception("T9 stream on_event callback failed")

                response.close()

            except requests.RequestException as exc:
                if self._stop.is_set():
                    break
                logger.warning("T9 stream connection error: %s", exc)
                self._emit_status("error", str(exc))
                self._wait_before_retry()
            except Exception as exc:
                if self._stop.is_set():
                    break
                logger.exception("Unexpected T9 stream error: %s", exc)
                self._emit_status("error", str(exc))
                self._wait_before_retry()
            else:
                # Normal exit (e.g., server closed). If stop not set, retry.
                self._emit_status("disconnected", None)
                if not self._stop.is_set():
                    logger.info("T9 stream disconnected, retrying in %.1fs", self.retry_delay)
                    self._wait_before_retry()

        self._emit_status("stopped", None)
        logger.info("T9 stream client stopped")

    # ------------------------------------------------------------------
    def _iter_sse(self, response: requests.Response):
        event_name: Optional[str] = None
        event_id: Optional[str] = None
        data_lines = []

        for raw_line in response.iter_lines(decode_unicode=True):
            if self._stop.is_set():
                break
            if raw_line is None:
                continue

            line = raw_line.strip("\r")

            if not line:
                if not data_lines:
                    event_name = None
                    event_id = None
                    continue

                data_str = "\n".join(data_lines)
                data_lines.clear()

                try:
                    parsed = json.loads(data_str) if data_str else None
                except json.JSONDecodeError:
                    logger.debug("T9 stream JSON decode failed: %s", data_str)
                    event_name = None
                    event_id = None
                    continue

                yield event_name or "message", parsed
                event_name = None
                event_id = None
                continue

            if line.startswith(":"):
                continue  # comment/heartbeat
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif line.startswith("event:"):
                event_name = line[6:].strip() or None
            elif line.startswith("id:"):
                event_id = line[3:].strip() or None

        # Signal termination with heartbeat to allow reconnect logic
        return

    # ------------------------------------------------------------------
    def _wait_before_retry(self) -> None:
        if self._stop.wait(timeout=self.retry_delay):
            return

