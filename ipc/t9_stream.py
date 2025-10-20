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
        connection_refresh_interval: float = 60.0,  # 每60秒主動重連
    ) -> None:
        self.base_url = base_url
        self.event_types = event_types
        self.headers = headers or {"Accept": "text/event-stream"}
        self.retry_delay = max(1.0, retry_delay)
        self.request_timeout = max(5.0, request_timeout)
        self.connection_refresh_interval = connection_refresh_interval
        self.on_event = on_event
        self.on_status = on_status

        # 創建 session 並配置連接池
        if session:
            self._session = session
        else:
            self._session = requests.Session()
            # 配置連接池和 keep-alive
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=1,
                pool_maxsize=1,
                max_retries=0,
                pool_block=False
            )
            self._session.mount('http://', adapter)
            self._session.mount('https://', adapter)

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._current_response: Optional[requests.Response] = None
        self._response_lock = threading.Lock()

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
            connection_start_time = time.time()
            watchdog_thread = None

            try:
                self._emit_status("connecting", self.base_url)

                response = self._session.get(
                    self.base_url,
                    params=params,
                    headers=self.headers,
                    stream=True,
                    timeout=(5.0, self.request_timeout),
                )

                with self._response_lock:
                    self._current_response = response

                if response.status_code != requests.codes.ok:
                    detail = f"HTTP {response.status_code}"
                    logger.warning("T9 stream HTTP error: %s", detail)
                    self._emit_status("error", detail)
                    response.close()
                    self._wait_before_retry()
                    continue

                self._emit_status("connected", None)
                logger.info("T9 stream connected: %s (will refresh in %.1fs)",
                           response.url, self.connection_refresh_interval)

                # 啟動看門狗線程，在 refresh_interval 後強制關閉連接
                watchdog_stop = threading.Event()
                watchdog_thread = threading.Thread(
                    target=self._watchdog,
                    args=(response, connection_start_time, watchdog_stop),
                    daemon=True
                )
                watchdog_thread.start()

                event_count = 0

                for payload in self._iter_sse(response):
                    if payload is None:
                        continue
                    event_name, data = payload
                    if not data:
                        continue
                    event_count += 1

                    if self.on_event:
                        try:
                            self.on_event(event_name, data)
                        except Exception:
                            logger.exception("T9 stream on_event callback failed")

                # 停止看門狗
                if watchdog_thread:
                    watchdog_stop.set()

                logger.info(f"T9 stream iteration ended after {event_count} events")
                response.close()

                with self._response_lock:
                    self._current_response = None

            except requests.RequestException as exc:
                if watchdog_thread:
                    watchdog_stop.set()
                if self._stop.is_set():
                    break
                logger.warning("T9 stream connection error: %s", exc)
                self._emit_status("error", str(exc))
                self._wait_before_retry()
            except Exception as exc:
                if watchdog_thread:
                    watchdog_stop.set()
                if self._stop.is_set():
                    break
                logger.exception("Unexpected T9 stream error: %s", exc)
                self._emit_status("error", str(exc))
                self._wait_before_retry()
            else:
                # Normal exit (e.g., server closed or refresh timeout). If stop not set, retry immediately.
                self._emit_status("reconnecting", None)
                if not self._stop.is_set():
                    logger.info("T9 stream reconnecting...")
                    # 不等待直接重連
                    continue

        self._emit_status("stopped", None)
        logger.info("T9 stream client stopped")

    # ------------------------------------------------------------------
    def _watchdog(self, response: requests.Response, start_time: float, stop_event: threading.Event) -> None:
        """監控連接時間，超時後強制關閉響應以觸發重連"""
        while not stop_event.is_set() and not self._stop.is_set():
            elapsed = time.time() - start_time
            remaining = self.connection_refresh_interval - elapsed

            if remaining <= 0:
                logger.info(f"T9 stream watchdog: Force closing connection after {elapsed:.1f}s")
                try:
                    response.close()
                except Exception as e:
                    logger.debug(f"T9 stream watchdog: Error closing response: {e}")
                break

            # 每秒檢查一次
            stop_event.wait(min(1.0, remaining))

    # ------------------------------------------------------------------
    def _iter_sse(self, response: requests.Response):
        event_name: Optional[str] = None
        event_id: Optional[str] = None
        data_lines = []

        line_count = 0
        for raw_line in response.iter_lines(decode_unicode=True):
            line_count += 1
            if self._stop.is_set():
                logger.info(f"T9 stream _iter_sse stopped by flag after {line_count} lines")
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
        logger.info(f"T9 stream _iter_sse exited naturally after {line_count} lines")
        return

    # ------------------------------------------------------------------
    def _wait_before_retry(self) -> None:
        if self._stop.wait(timeout=self.retry_delay):
            return

