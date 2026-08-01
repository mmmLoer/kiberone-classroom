"""Тесты HTTP API сервера."""

from __future__ import annotations

import json
import tempfile
import urllib.request
from pathlib import Path

from classroom.server.hub import ClassroomServer
from classroom.shared.constants import DEFAULT_TOKEN


def _request(method: str, url: str, data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        if "application/json" in ctype:
            return json.loads(body.decode("utf-8"))
        return body


def test_server_health_upload_list_download():
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp)
        server = ClassroomServer(host="127.0.0.1", port=18765, backup_dir=backup, token=DEFAULT_TOKEN)
        server.start()
        try:
            base = "http://127.0.0.1:18765"
            headers = {"X-Sync-Token": DEFAULT_TOKEN, "X-Client-Id": "TESTPC"}

            health = _request("GET", f"{base}/health", headers=headers)
            assert health["ok"] is True

            upload_headers = {
                **headers,
                "X-Relative-Path": "demo.txt",
                "Content-Type": "application/octet-stream",
            }
            result = _request("POST", f"{base}/upload", data=b"hello", headers=upload_headers)
            assert result["ok"] is True

            listed = _request("GET", f"{base}/list?client_id=TESTPC", headers=headers)
            assert any(item["path"] == "demo.txt" for item in listed["files"])

            content = _request("GET", f"{base}/download?client_id=TESTPC&path=demo.txt", headers=headers)
            assert content == b"hello"

            hb = json.dumps({"client_id": "TESTPC", "pc_number": "7", "hostname": "vm"}).encode()
            _request(
                "POST",
                f"{base}/heartbeat",
                data=hb,
                headers={**headers, "Content-Type": "application/json"},
            )
            clients = _request("GET", f"{base}/clients", headers=headers)
            assert any(c["client_id"] == "TESTPC" for c in clients["clients"])
        finally:
            server.stop()
