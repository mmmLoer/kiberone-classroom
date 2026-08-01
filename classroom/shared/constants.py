"""Общие константы и пути."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "KIBERone Classroom"
DEFAULT_PORT = 8765
DISCOVERY_PORT = 8766
DEFAULT_TOKEN = "kiberone-sync-2026"
DEFAULT_FOLDER_NAME = "Ученики"
POLL_SECONDS = 3
SYNC_SECONDS = 60

COMMAND_TYPES = (
    "open_url",
    "set_wallpaper",
    "run_file",
    "run_shell",
    "restore_saves",
    "use_fresh_saves",
    "sync_now",
    "message",
    "install_starter_pack",
)


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # classroom/shared/constants.py -> корень репозитория
    return Path(__file__).resolve().parent.parent.parent


def config_path(name: str) -> Path:
    folder = app_dir() / "config"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


def desktop_dir() -> Path:
    home = Path.home()
    for name in ("Desktop", "Рабочий стол"):
        candidate = home / name
        if candidate.exists():
            return candidate
    return home / "Desktop"


def default_backup_dir() -> Path:
    return desktop_dir() / DEFAULT_FOLDER_NAME


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()
