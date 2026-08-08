"""Тесты HTTP-клиента без прокси."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from classroom.shared import http_client as hc


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def test_request_local_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = hc.request("GET", f"http://127.0.0.1:{port}/", timeout=3)
        assert result["ok"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_tcp_reachable_refused():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(1)
    try:
        ok, err = hc.tcp_reachable("127.0.0.1", port, timeout=1.0)
        assert ok is True
        assert err == ""
    finally:
        sock.close()

    ok, err = hc.tcp_reachable("127.0.0.1", port, timeout=0.5)
    assert ok is False
    assert err
