"""Автопоиск компьютера преподавателя в локальной сети (UDP broadcast)."""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import Callable

from .constants import APP_NAME, DEFAULT_PORT, DEFAULT_TOKEN, DISCOVERY_PORT

DISCOVER_MESSAGE = "KIBERONE_DISCOVER"
RESPONSE_PREFIX = "KIBERONE_TEACHER"


def local_ipv4_list() -> list[str]:
    ips: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass

    return list(dict.fromkeys(ips))


def broadcast_targets() -> list[str]:
    targets = ["255.255.255.255"]
    for ip in local_ipv4_list():
        parts = ip.split(".")
        if len(parts) == 4:
            targets.append(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
    return list(dict.fromkeys(targets))


def local_ip_for(remote_ip: str) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((remote_ip, 1))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    ips = local_ipv4_list()
    return ips[0] if ips else "127.0.0.1"


def discover_teacher(timeout: float = 4.0, token: str = DEFAULT_TOKEN) -> str | None:
    """Ищет преподавателя в локальной сети. Возвращает IP или None."""
    payload = json.dumps({"type": DISCOVER_MESSAGE, "token": token}).encode("utf-8")
    found: dict[str, int] = {}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Один сокет на send+recv — ответ приходит на тот же порт
        sock.bind(("", 0))
        sock.settimeout(0.4)

        targets = broadcast_targets()
        deadline = time.time() + timeout
        next_send = 0.0

        while time.time() < deadline:
            now = time.time()
            if now >= next_send:
                for target in targets:
                    try:
                        sock.sendto(payload, (target, DISCOVERY_PORT))
                    except OSError:
                        continue
                next_send = now + 0.8

            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                message = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if message.get("type") != RESPONSE_PREFIX:
                continue
            if message.get("token") != token:
                continue

            host = str(message.get("host") or addr[0]).strip()
            port = int(message.get("port") or DEFAULT_PORT)
            if host and not host.startswith("127."):
                found[host] = port
                return host
            if addr[0] and not str(addr[0]).startswith("127."):
                found[addr[0]] = port
                return addr[0]
    finally:
        sock.close()

    return next(iter(found), None)


class DiscoveryAnnouncer:
    """Отвечает на broadcast-запросы учеников."""

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        token: str = DEFAULT_TOKEN,
        get_host: Callable[[], str] | None = None,
        on_log: Callable[[str], None] | None = None,
    ):
        self.port = port
        self.token = token
        self.get_host = get_host or (lambda: "127.0.0.1")
        self.on_log = on_log or (lambda _msg: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.on_log(f"Автопоиск включён (UDP {DISCOVERY_PORT})")

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", DISCOVERY_PORT))
            sock.settimeout(0.5)
            while not self._stop.is_set():
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    message = json.loads(data.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if message.get("type") != DISCOVER_MESSAGE:
                    continue
                if message.get("token") != self.token:
                    continue

                # Отвечаем IP того интерфейса, через который виден ученик
                host = local_ip_for(addr[0])
                response = json.dumps(
                    {
                        "type": RESPONSE_PREFIX,
                        "token": self.token,
                        "host": host,
                        "port": self.port,
                        "name": APP_NAME,
                    }
                ).encode("utf-8")
                try:
                    sock.sendto(response, addr)
                    self.on_log(f"Ученик {addr[0]} — отправлен IP {host}")
                except OSError as exc:
                    self.on_log(f"Не удалось ответить {addr[0]}: {exc}")
        finally:
            sock.close()
