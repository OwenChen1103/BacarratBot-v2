#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import Flask, Response, request
import json, queue, threading, time

class ReaderEventBroadcaster:
    def __init__(self, host="127.0.0.1", port=8888):
        self.host, self.port = host, port
        self.app = Flask(__name__)
        self.q = queue.Queue()
        self._thread = None

        @self.app.route("/events")
        def events():
            def gen():
                yield "retry: 1000\n\n"
                while True:
                    data = self.q.get()
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            return Response(gen(), mimetype="text/event-stream")

        @self.app.route("/health")
        def health(): return "ok", 200

    def broadcast_event(self, data: dict):
        self.q.put(data)

    def start_server(self):
        def run():
            self.app.run(self.host, self.port, debug=False, threaded=True)
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        time.sleep(0.2)

    def stop_server(self):
        # Flask dev server 沒有優雅停止；乾脆丟個標記即可
        try:
            self.broadcast_event({"type":"READER_STOPPING","ts":time.time()})
        except Exception:
            pass