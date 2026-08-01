"""История версий файлов учеников (простой откат как в GitHub)."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

HISTORY_DIR = ".history"
MAX_VERSIONS_PER_FILE = 30


def _safe_history_key(relative: str) -> str:
    """Ключ папки истории: хеш пути + короткое имя для читаемости."""
    rel = relative.replace("\\", "/").lstrip("/")
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]
    name = Path(rel).name
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:40]
    return f"{safe_name}__{digest}"


def history_root(client_root: Path) -> Path:
    return client_root / HISTORY_DIR


def file_history_dir(client_root: Path, relative: str) -> Path:
    return history_root(client_root) / _safe_history_key(relative)


def _index_path(hist_dir: Path) -> Path:
    return hist_dir / "index.json"


def _load_index(hist_dir: Path) -> list[dict]:
    path = _index_path(hist_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save_index(hist_dir: Path, items: list[dict]) -> None:
    hist_dir.mkdir(parents=True, exist_ok=True)
    _index_path(hist_dir).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def content_hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def archive_if_changed(client_root: Path, relative: str, new_data: bytes) -> dict | None:
    """
    Если текущий файл отличается от нового — сохраняет старую версию.
    Возвращает запись версии или None (нет изменений / файла не было).
    """
    target = (client_root / relative).resolve()
    root = client_root.resolve()
    if root not in target.parents and target != root:
        raise ValueError("bad path")

    if not target.is_file():
        return None

    old_data = target.read_bytes()
    if old_data == new_data:
        return None

    hist_dir = file_history_dir(client_root, relative)
    hist_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_id = f"{stamp}_{content_hash(old_data)}"
    blob_name = f"{version_id}.bin"
    blob_path = hist_dir / blob_name
    blob_path.write_bytes(old_data)

    entry = {
        "id": version_id,
        "file": relative.replace("\\", "/"),
        "blob": blob_name,
        "size": len(old_data),
        "hash": content_hash(old_data),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }

    items = _load_index(hist_dir)
    # не дублируем одинаковый хеш подряд
    if items and items[0].get("hash") == entry["hash"]:
        return None

    items.insert(0, entry)
    # лимит версий
    while len(items) > MAX_VERSIONS_PER_FILE:
        old = items.pop()
        old_blob = hist_dir / old.get("blob", "")
        if old_blob.is_file():
            old_blob.unlink(missing_ok=True)

    # храним путь в meta
    meta = hist_dir / "path.txt"
    meta.write_text(relative.replace("\\", "/"), encoding="utf-8")
    _save_index(hist_dir, items)
    return entry


def list_file_versions(client_root: Path, relative: str) -> list[dict]:
    hist_dir = file_history_dir(client_root, relative)
    return _load_index(hist_dir)


def force_snapshot(client_root: Path, relative: str, label: str = "") -> dict | None:
    """Принудительно сохраняет текущий файл в историю (даже без входящих изменений)."""
    relative = relative.replace("\\", "/").lstrip("/")
    target = (client_root / relative).resolve()
    root = client_root.resolve()
    if root not in target.parents and target != root:
        raise ValueError("bad path")
    if not target.is_file():
        return None

    data = target.read_bytes()
    hist_dir = file_history_dir(client_root, relative)
    hist_dir.mkdir(parents=True, exist_ok=True)

    digest = content_hash(data)
    items = _load_index(hist_dir)
    if items and items[0].get("hash") == digest:
        return None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_id = f"{stamp}_{digest}"
    blob_name = f"{version_id}.bin"
    (hist_dir / blob_name).write_bytes(data)

    entry = {
        "id": version_id,
        "file": relative,
        "blob": blob_name,
        "size": len(data),
        "hash": digest,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "label": label or "снимок",
    }
    items.insert(0, entry)
    while len(items) > MAX_VERSIONS_PER_FILE:
        old = items.pop()
        old_blob = hist_dir / old.get("blob", "")
        if old_blob.is_file():
            old_blob.unlink(missing_ok=True)

    (hist_dir / "path.txt").write_text(relative, encoding="utf-8")
    _save_index(hist_dir, items)
    return entry


def snapshot_all(client_root: Path, label: str = "ручной снимок") -> int:
    """Создаёт снимок всех текущих файлов ученика. Возвращает число новых версий."""
    count = 0
    if not client_root.exists():
        return 0
    for path in client_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(client_root)
        if HISTORY_DIR in rel.parts:
            continue
        if force_snapshot(client_root, rel.as_posix(), label=label):
            count += 1
    return count


def list_client_files(client_root: Path) -> list[dict]:
    """Все файлы ученика + число версий в истории."""
    if not client_root.exists():
        return []

    result = []
    for path in sorted(client_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(client_root)
        if HISTORY_DIR in rel.parts:
            continue
        relative = rel.as_posix()
        versions = list_file_versions(client_root, relative)
        stat = path.stat()
        result.append(
            {
                "path": relative,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "versions": len(versions),
                "last_saved": versions[0].get("saved_at", "") if versions else "",
            }
        )
    return result


def list_all_versioned_files(client_root: Path) -> list[dict]:
    """Список файлов, у которых есть история."""
    root = history_root(client_root)
    if not root.exists():
        return []

    result = []
    for hist_dir in sorted(root.iterdir()):
        if not hist_dir.is_dir():
            continue
        path_file = hist_dir / "path.txt"
        relative = path_file.read_text(encoding="utf-8").strip() if path_file.exists() else hist_dir.name
        versions = _load_index(hist_dir)
        if not versions:
            continue
        result.append(
            {
                "path": relative,
                "versions": len(versions),
                "last_saved": versions[0].get("saved_at", ""),
            }
        )
    result.sort(key=lambda item: item.get("last_saved", ""), reverse=True)
    return result


def restore_version(client_root: Path, relative: str, version_id: str) -> Path:
    """Восстанавливает выбранную версию в текущий файл. Текущее состояние тоже архивируется."""
    hist_dir = file_history_dir(client_root, relative)
    items = _load_index(hist_dir)
    entry = next((item for item in items if item.get("id") == version_id), None)
    if not entry:
        raise FileNotFoundError(f"Версия не найдена: {version_id}")

    blob = hist_dir / entry["blob"]
    if not blob.is_file():
        raise FileNotFoundError(f"Файл версии отсутствует: {entry['blob']}")

    data = blob.read_bytes()
    target = (client_root / relative).resolve()
    root = client_root.resolve()
    if root not in target.parents and target != root:
        raise ValueError("bad path")

    # архивируем текущее перед откатом
    if target.is_file():
        archive_if_changed(client_root, relative, data)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def open_history_folder(client_root: Path) -> Path:
    path = history_root(client_root)
    path.mkdir(parents=True, exist_ok=True)
    return path
