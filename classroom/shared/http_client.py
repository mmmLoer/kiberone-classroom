"""HTTP без системного прокси — на школьных ПК иначе LAN-запросы часто уходят в прокси."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(
    method: str,
    url: str,
    data: bytes | None = None,
    headers: dict | None = None,
    timeout: float = 15,
    raw: bool = False,
):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with _NO_PROXY_OPENER.open(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
            if not raw and "application/json" in content_type:
                return json.loads(body.decode("utf-8"))
            return body
    except urllib.error.HTTPError as exc:
        # 401 и др. — пробрасываем с телом, чтобы ping мог объяснить причину
        raise exc


def tcp_reachable(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    host = (host or "").strip()
    if not host:
        return False, "IP тьютора не указан"
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except socket.timeout:
        return (
            False,
            "Порт не отвечает (таймаут). На ПК тьютора разреши KIBERoneTutor в брандмауэре Windows "
            f"и проверь порт {port}.",
        )
    except OSError as exc:
        text = str(exc).lower()
        if "refused" in text or "unreachable" in text or "10061" in text:
            return (
                False,
                f"Порт {port} закрыт на {host}. На тьюторе запусти KIBERoneTutor и разреши доступ к сети.",
            )
        return False, f"Нет TCP-связи с {host}:{port} ({exc})"
