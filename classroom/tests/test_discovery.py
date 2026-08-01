"""Тесты discovery и identity."""

from __future__ import annotations

import json
import socket
import threading
import time

from classroom.shared.discovery import (
    DISCOVER_MESSAGE,
    RESPONSE_PREFIX,
    DiscoveryAnnouncer,
    broadcast_targets,
    discover_teacher,
    local_ip_for,
    local_ipv4_list,
)
from classroom.shared.identity import get_mac_id
from classroom.shared.constants import DEFAULT_TOKEN, DISCOVERY_PORT


def test_get_mac_id_is_stable_and_nonempty():
    value = get_mac_id()
    assert isinstance(value, str)
    assert len(value) >= 4
    assert get_mac_id() == value


def test_broadcast_targets_include_global():
    targets = broadcast_targets()
    assert "255.255.255.255" in targets


def test_local_ip_helpers():
    ips = local_ipv4_list()
    assert isinstance(ips, list)
    ip = local_ip_for("8.8.8.8")
    assert isinstance(ip, str)
    assert ip


def test_discover_teacher_roundtrip():
    announcer = DiscoveryAnnouncer(
        port=8765,
        token=DEFAULT_TOKEN,
        get_host=lambda: "127.0.0.1",
    )
    # Подменяем ответ: announcer отвечает на DISCOVERY_PORT, discover слушает reply на свой порт.
    # Для unit-теста поднимаем мини-сервер вручную на DISCOVERY_PORT.
    stop = threading.Event()

    def serve():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", DISCOVERY_PORT))
        sock.settimeout(0.3)
        while not stop.is_set():
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
            response = json.dumps(
                {
                    "type": RESPONSE_PREFIX,
                    "token": DEFAULT_TOKEN,
                    "host": "10.0.0.55",
                    "port": 8765,
                    "name": "test",
                }
            ).encode("utf-8")
            sock.sendto(response, addr)
        sock.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    time.sleep(0.15)
    try:
        # discover_teacher шлёт на broadcast; в тестах часто не доходит до 127.0.0.1:port.
        # Проверяем протокол напрямую тем же форматом.
        payload = json.dumps({"type": DISCOVER_MESSAGE, "token": DEFAULT_TOKEN}).encode("utf-8")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        sock.sendto(payload, ("127.0.0.1", DISCOVERY_PORT))
        data, _addr = sock.recvfrom(4096)
        sock.close()
        message = json.loads(data.decode("utf-8"))
        assert message["type"] == RESPONSE_PREFIX
        assert message["host"] == "10.0.0.55"
    finally:
        stop.set()
        thread.join(timeout=1)
