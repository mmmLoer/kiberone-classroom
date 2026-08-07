"""Стартовый пак: установщики и папки ресурсов для учеников."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from .constants import app_dir, config_path

INSTALLER_EXTENSIONS = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".msix"}
SKIP_NAMES = {"readme.md", "desktop.ini", "thumbs.db", ".ds_store"}
SKIP_DIR_NAMES = {".git", "__pycache__", ".venv", "node_modules"}


def deploy_dir() -> Path:
    path = app_dir() / "deploy"
    path.mkdir(parents=True, exist_ok=True)
    return path


def starter_pack_config_path() -> Path:
    return config_path("starter_pack.json")


def _folder_size(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


def list_deploy_installers() -> list[dict]:
    """Установщики и папки верхнего уровня в deploy."""
    root = deploy_dir()
    items: list[dict] = []
    for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        name = path.name
        if name.startswith("."):
            continue
        if name.lower() in SKIP_NAMES:
            continue
        if path.is_file():
            if path.suffix.lower() not in INSTALLER_EXTENSIONS:
                continue
            items.append(
                {
                    "name": name,
                    "kind": "installer",
                    "size": path.stat().st_size,
                    "path": str(path),
                }
            )
        elif path.is_dir():
            if name.lower() in SKIP_DIR_NAMES:
                continue
            items.append(
                {
                    "name": name,
                    "kind": "folder",
                    "size": _folder_size(path),
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
    """Только отмеченные тьютором пункты пака."""
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
                "kind": item.get("kind") or "installer",
                "title": titles.get(item["name"]) or Path(item["name"]).stem,
                "size": item["size"],
            }
        )
    return result


def resolve_deploy_file(name: str) -> Path:
    """Только файл-установщик (обратная совместимость)."""
    path, kind = resolve_deploy_pack_item(name)
    if kind != "installer":
        raise ValueError("not an installer")
    return path


def resolve_deploy_pack_item(name: str) -> tuple[Path, str]:
    safe = Path(name).name
    if not safe or safe in {".", ".."} or ".." in safe:
        raise ValueError("bad name")
    path = (deploy_dir() / safe).resolve()
    root = deploy_dir().resolve()
    if root not in path.parents and path != root:
        raise ValueError("bad path")
    if path.is_file():
        if path.suffix.lower() not in INSTALLER_EXTENSIONS:
            raise ValueError("not an installer")
        return path, "installer"
    if path.is_dir():
        if path.name.lower() in SKIP_DIR_NAMES:
            raise ValueError("bad folder")
        return path, "folder"
    raise FileNotFoundError(safe)


def zip_folder_bytes(folder: Path) -> bytes:
    """Упаковать папку в zip (пути относительно корня папки)."""
    buf = io.BytesIO()
    root = folder.resolve()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if any(part.lower() in SKIP_DIR_NAMES for part in path.relative_to(root).parts):
                continue
            zf.write(path, rel)
    return buf.getvalue()
