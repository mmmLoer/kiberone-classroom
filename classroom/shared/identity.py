"""Идентификация ПК ученика."""

from __future__ import annotations

import json
import socket
import uuid
from pathlib import Path

from .constants import app_dir, config_path


def get_mac_id() -> str:
    # Без PowerShell: uuid.getnode() или hostname
    try:
        node = uuid.getnode()
        if node and (node >> 40) % 2 == 0:  # не случайный (локально сгенерированный) MAC
            return f"{node:012X}"
        if node:
            return f"{node:012X}"
    except Exception:
        pass

    try:
        return socket.gethostname().upper().replace(" ", "")[:32]
    except OSError:
        return "UNKNOWN"


def _student_state_path() -> Path:
    """Локальные настройки ученика — рядом с программой, не в config/."""
    return app_dir() / "student.json"


def _load_local() -> dict:
    path = _student_state_path()
    # миграция со старого config/student_local.json
    if not path.exists():
        legacy = config_path("student_local.json")
        if legacy.exists():
            try:
                data = json.loads(legacy.read_text(encoding="utf-8"))
                _save_local(data if isinstance(data, dict) else {})
                return _load_local()
            except json.JSONDecodeError:
                pass
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_local(data: dict) -> None:
    path = _student_state_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_pc_number(default: str = "") -> str:
    return str(_load_local().get("pc_number", default))


def set_pc_number(number: str) -> None:
    data = _load_local()
    data["pc_number"] = str(number).strip()
    _save_local(data)


def get_teacher_host(default: str = "") -> str:
    return str(_load_local().get("teacher_host", default))


def set_teacher_host(host: str) -> None:
    data = _load_local()
    data["teacher_host"] = host.strip()
    _save_local(data)


def get_watch_folder(default: str) -> str:
    return str(_load_local().get("watch_folder", default))


def set_watch_folder(folder: str) -> None:
    data = _load_local()
    data["watch_folder"] = folder.strip()
    _save_local(data)


def client_label(mac_id: str) -> str:
    number = get_pc_number()
    if number:
        return f"ПК {number}"
    return mac_id
