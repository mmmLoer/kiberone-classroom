"""Автопоиск компьютера тьютора в локальной сети (UDP broadcast + beacon)."""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import Callable

from .constants import APP_NAME, DEFAULT_PORT, DEFAULT_TOKEN, DISCOVERY_PORT

DISCOVER_MESSAGE = "KIBERONE_DISCOVER"
RESPONSE_PREFIX = "KIBERONE_TEACHER"
BEACON_PORT = DISCOVERY_PORT + 1  # 8767 — объявления от тьютора


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


def _is_usable_host(host: str) -> bool:
    host = (host or "").strip()
    if not host:
        return False
    if host.startswith("127."):
        return False
    if host.lower() in {"localhost", "::1"}:
        return False
    return True


def _parse_teacher_message(data: bytes, addr: tuple, token: str | None = None) -> str | None:
    try:
        message = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if message.get("type") != RESPONSE_PREFIX:
        return None
    if token is not None and message.get("token") != token:
        return None
    host = str(message.get("host") or "").strip()
    if _is_usable_host(host):
        return host
    fallback = str(addr[0] if addr else "").strip()
    if _is_usable_host(fallback):
        return fallback
    return None


def discover_teacher(
    timeout: float = 5.0,
    token: str = DEFAULT_TOKEN,
    hint_host: str | None = None,
) -> str | None:
    """
    Ищет тьютора в локальной сети.
    1) Слушает beacon на BEACON_PORT
    2) Шлёт discover на DISCOVERY_PORT (broadcast + unicast на hint)
    """
    payload = json.dumps({"type": DISCOVER_MESSAGE, "token": token}).encode("utf-8")

    query_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    beacon_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        query_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        query_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        query_sock.bind(("", 0))
        query_sock.settimeout(0.35)

        beacon_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        beacon_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            beacon_sock.bind(("", BEACON_PORT))
        except OSError:
            # порт занят — работаем только через query/response
            beacon_sock.close()
            beacon_sock = None  # type: ignore[assignment]
        else:
            beacon_sock.settimeout(0.35)

        targets = broadcast_targets()
        if hint_host and _is_usable_host(hint_host):
            targets.insert(0, hint_host.strip())

        deadline = time.time() + timeout
        next_send = 0.0

        while time.time() < deadline:
            now = time.time()
            if now >= next_send:
                for target in targets:
                    try:
                        query_sock.sendto(payload, (target, DISCOVERY_PORT))
                    except OSError:
                        continue
                next_send = now + 0.6

            # ответы на запрос
            try:
                data, addr = query_sock.recvfrom(4096)
                host = _parse_teacher_message(data, addr, token=token)
                if host:
                    return host
            except socket.timeout:
                pass
            except OSError:
                break

            # beacon от тьютора
            if beacon_sock is not None:
                try:
                    data, addr = beacon_sock.recvfrom(4096)
                    host = _parse_teacher_message(data, addr, token=token)
                    if host:
                        return host
                except socket.timeout:
                    pass
                except OSError:
                    pass
    finally:
        query_sock.close()
        if beacon_sock is not None:
            beacon_sock.close()

    return None


def ensure_firewall_rules(on_log: Callable[[str], None] | None = None) -> None:
    """Пытается открыть порты в Windows Firewall (тихо, если нет прав)."""
    log = on_log or (lambda _m: None)
    try:
        import subprocess

        exe = ""
        try:
            import sys

            if getattr(sys, "frozen", False):
                exe = str(sys.executable)
        except Exception:
            exe = ""

        commands = [
            [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                "name=KIBERone Classroom TCP 8765",
                "dir=in",
                "action=allow",
                "protocol=TCP",
                "localport=8765",
                "profile=any",
            ],
            [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                "name=KIBERone Classroom UDP 8766",
                "dir=in",
                "action=allow",
                "protocol=UDP",
                "localport=8766",
                "profile=any",
            ],
            [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                "name=KIBERone Classroom UDP 8767",
                "dir=in",
                "action=allow",
                "protocol=UDP",
                "localport=8767",
                "profile=any",
            ],
        ]
        if exe:
            commands.append(
                [
                    "netsh",
                    "advfirewall",
                    "firewall",
                    "add",
                    "rule",
                    "name=KIBERone Classroom App",
                    "dir=in",
                    "action=allow",
                    "program=" + exe,
                    "enable=yes",
                    "profile=any",
                ]
            )

        for cmd in commands:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        log("Правила firewall проверены (если есть права администратора)")
    except Exception as exc:
        log(f"Firewall: пропуск ({exc})")


class DiscoveryAnnouncer:
    """Отвечает на broadcast-запросы учеников и шлёт beacon."""

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
        self._beacon_thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="discovery-listen")
        self._thread.start()
        self._beacon_thread = threading.Thread(target=self._beacon_loop, daemon=True, name="discovery-beacon")
        self._beacon_thread.start()
        self.on_log(f"Автопоиск включён (UDP {DISCOVERY_PORT}/{BEACON_PORT})")

    def stop(self) -> None:
        self._stop.set()

    def _teacher_payload(self, host: str) -> bytes:
        return json.dumps(
            {
                "type": RESPONSE_PREFIX,
                "token": self.token,
                "host": host,
                "port": self.port,
                "name": APP_NAME,
            }
        ).encode("utf-8")

    def _loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                sock.bind(("", DISCOVERY_PORT))
            except OSError as exc:
                self.on_log(f"Автопоиск НЕ запущен: порт {DISCOVERY_PORT} занят ({exc})")
                return
            sock.settimeout(0.5)
            self.on_log(f"Слушаю поиск учеников на UDP {DISCOVERY_PORT}")
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

                host = local_ip_for(addr[0])
                if not _is_usable_host(host):
                    host = self.get_host()
                try:
                    sock.sendto(self._teacher_payload(host), addr)
                    self.on_log(f"Ученик {addr[0]} — отправлен IP {host}")
                except OSError as exc:
                    self.on_log(f"Не удалось ответить {addr[0]}: {exc}")
        finally:
            sock.close()

    def _beacon_loop(self) -> None:
        """Периодически объявляет себя в сеть — помогает, если входящий UDP к тьютору режется."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", 0))
            while not self._stop.is_set():
                host = self.get_host()
                if not _is_usable_host(host):
                    ips = local_ipv4_list()
                    host = ips[0] if ips else host
                payload = self._teacher_payload(host)
                for target in broadcast_targets():
                    try:
                        sock.sendto(payload, (target, BEACON_PORT))
                    except OSError:
                        continue
                self._stop.wait(1.5)
        finally:
            sock.close()
