"""Стартовый пак программ для начальной настройки учеников."""

from __future__ import annotations

import json
from pathlib import Path

from .constants import app_dir, config_path

INSTALLER_EXTENSIONS = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".msix"}


def deploy_dir() -> Path:
    path = app_dir() / "deploy"
    path.mkdir(parents=True, exist_ok=True)
    return path


def starter_pack_config_path() -> Path:
    return config_path("starter_pack.json")


def list_deploy_installers() -> list[dict]:
    """Все установщики в папке deploy."""
    root = deploy_dir()
    items = []
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in INSTALLER_EXTENSIONS:
            continue
        if path.name.lower() in {"readme.md", "desktop.ini"}:
            continue
        items.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "path": str(path),
            }
        )
    return items


def load_starter_selection() -> dict:
    path = starter_pack_config_path()
    if not path.exists():
        return {"enabled": [], "titles": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"enabled": [], "titles": {}}
    enabled = data.get("enabled") or []
    titles = data.get("titles") or {}
    return {"enabled": list(enabled), "titles": dict(titles)}


def save_starter_selection(enabled: list[str], titles: dict[str, str] | None = None) -> None:
    path = starter_pack_config_path()
    payload = {
        "enabled": enabled,
        "titles": titles or load_starter_selection().get("titles", {}),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def list_enabled_starter_pack() -> list[dict]:
    """Только отмеченные преподавателем установщики."""
    selection = load_starter_selection()
    enabled = set(selection.get("enabled") or [])
    titles = selection.get("titles") or {}
    result = []
    for item in list_deploy_installers():
        if item["name"] not in enabled:
            continue
        result.append(
            {
                "name": item["name"],
                "title": titles.get(item["name"]) or Path(item["name"]).stem,
                "size": item["size"],
            }
        )
    return result


def resolve_deploy_file(name: str) -> Path:
    safe = Path(name).name
    if ".." in safe or "/" in safe or "\\" in safe:
        raise ValueError("bad name")
    path = (deploy_dir() / safe).resolve()
    if deploy_dir().resolve() not in path.parents and path != deploy_dir().resolve():
        raise ValueError("bad path")
    if not path.is_file():
        raise FileNotFoundError(safe)
    if path.suffix.lower() not in INSTALLER_EXTENSIONS:
        raise ValueError("not an installer")
    return path
