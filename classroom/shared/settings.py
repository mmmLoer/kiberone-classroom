"""Настройки тьютора (синхронизация и пр.)."""

from __future__ import annotations

import json

from .constants import config_path

DEFAULT_SYNC_SECONDS = 300  # 5 минут
MIN_SYNC_SECONDS = 30
MAX_SYNC_SECONDS = 3600


def _defaults() -> dict:
    return {"sync_seconds": DEFAULT_SYNC_SECONDS}


def load_teacher_settings() -> dict:
    path = config_path("teacher_settings.json")
    data = dict(_defaults())
    if not path.exists():
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return data
    if not isinstance(raw, dict):
        return data
    data.update(raw)
    data["sync_seconds"] = clamp_sync_seconds(data.get("sync_seconds", DEFAULT_SYNC_SECONDS))
    return data


def save_teacher_settings(settings: dict) -> dict:
    cleaned = dict(_defaults())
    cleaned.update(settings or {})
    cleaned["sync_seconds"] = clamp_sync_seconds(cleaned.get("sync_seconds", DEFAULT_SYNC_SECONDS))
    path = config_path("teacher_settings.json")
    path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def clamp_sync_seconds(value) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = DEFAULT_SYNC_SECONDS
    return max(MIN_SYNC_SECONDS, min(MAX_SYNC_SECONDS, seconds))
