"""Работа с файлами deploy (обои, установщики и т.д.)."""

from __future__ import annotations

from pathlib import Path

from .constants import app_dir


def deploy_dir() -> Path:
    path = app_dir() / "deploy"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_deploy_any(name: str) -> Path:
    safe = Path(name).name
    if not safe or safe in {".", ".."}:
        raise ValueError("bad name")
    path = (deploy_dir() / safe).resolve()
    root = deploy_dir().resolve()
    if root not in path.parents and path != root:
        raise ValueError("bad path")
    if not path.is_file():
        raise FileNotFoundError(safe)
    return path
