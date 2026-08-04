"""Тесты discovery и identity."""

from __future__ import annotations

import json
import socket
import threading
import time

from classroom.shared.discovery import (
    BEACON_PORT,
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
        get_host=lambda: "10.0.0.55",
        on_log=lambda _m: None,
    )
    announcer.start()
    time.sleep(0.4)
    try:
        # unicast на loopback + beacon
        host = discover_teacher(timeout=3.0, token=DEFAULT_TOKEN, hint_host="127.0.0.1")
        # на одной машине host может быть реальным LAN IP из local_ip_for
        assert host is not None
        assert not host.startswith("127.")
    finally:
        announcer.stop()
        time.sleep(0.3)


def test_beacon_port_constant():
    assert BEACON_PORT == DISCOVERY_PORT + 1
