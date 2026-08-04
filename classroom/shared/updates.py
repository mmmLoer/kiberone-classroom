"""Публикация и проверка обновлений EXE ученика."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .constants import APP_VERSION, app_dir, config_path

STUDENT_EXE_NAME = "KIBERoneStudent.exe"
MANIFEST_NAME = "student_manifest.json"


def parse_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(value or "0").strip().split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def version_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def updates_dir() -> Path:
    path = app_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundled_updates_dir() -> Path | None:
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", "") or "")
        candidate = meipass / "updates"
        if candidate.is_dir():
            return candidate
    return None


def manifest_path() -> Path:
    return updates_dir() / MANIFEST_NAME


def student_exe_path() -> Path:
    return updates_dir() / STUDENT_EXE_NAME


def load_manifest() -> dict | None:
    path = manifest_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def save_manifest(data: dict) -> dict:
    updates_dir()
    path = manifest_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # дублируем в config для наглядности
    config_path("student_update.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def ensure_updates_seeded() -> None:
    """Если рядом с тьютором ещё нет пакета — скопировать из встроенного бандла или dist."""
    exe = student_exe_path()
    if exe.is_file() and load_manifest():
        return

    sources: list[Path] = []
    bundled = bundled_updates_dir()
    if bundled:
        sources.append(bundled / STUDENT_EXE_NAME)
    sources.append(app_dir() / "dist" / STUDENT_EXE_NAME)
    sources.append(app_dir() / STUDENT_EXE_NAME)

    for src in sources:
        if not src.is_file():
            continue
        # если манифест есть рядом с источником
        src_manifest = src.parent / MANIFEST_NAME
        version = APP_VERSION
        if src_manifest.is_file():
            try:
                raw = json.loads(src_manifest.read_text(encoding="utf-8"))
                version = str(raw.get("version") or version)
            except json.JSONDecodeError:
                pass
        publish_student_exe(src, version=version)
        return


def publish_student_exe(source: Path, version: str | None = None) -> dict:
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    ver = (version or APP_VERSION).strip() or APP_VERSION
    target = student_exe_path()
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    digest = file_sha256(target)
    manifest = {
        "version": ver,
        "filename": STUDENT_EXE_NAME,
        "size": target.stat().st_size,
        "sha256": digest,
        "published_at": datetime.now().isoformat(timespec="seconds"),
    }
    return save_manifest(manifest)


def get_update_info() -> dict | None:
    """Информация об опубликованном EXE ученика, если файл на месте."""
    ensure_updates_seeded()
    manifest = load_manifest()
    exe = student_exe_path()
    if not manifest or not exe.is_file():
        return None
    # если файл меняли вручную — обновим размер/хеш лениво
    size = exe.stat().st_size
    if int(manifest.get("size") or 0) != size:
        manifest["size"] = size
        manifest["sha256"] = file_sha256(exe)
        save_manifest(manifest)
    return {
        "version": str(manifest.get("version") or APP_VERSION),
        "filename": STUDENT_EXE_NAME,
        "size": int(manifest.get("size") or size),
        "sha256": str(manifest.get("sha256") or ""),
        "published_at": str(manifest.get("published_at") or ""),
    }


def update_available_for(local_version: str) -> dict | None:
    info = get_update_info()
    if not info:
        return None
    if version_newer(info["version"], local_version):
        return info
    return None


def read_student_exe_bytes() -> bytes:
    info = get_update_info()
    if not info:
        raise FileNotFoundError("Нет опубликованного EXE ученика")
    return student_exe_path().read_bytes()


def schedule_exe_replace(new_exe: Path, target_exe: Path | None = None) -> Path:
    """
    Запускает bat, который дождётся завершения текущего процесса,
    заменит EXE и перезапустит его. Возвращает путь к bat.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Обновление EXE доступно только в собранном приложении")

    current = Path(target_exe or sys.executable).resolve()
    new_exe = Path(new_exe).resolve()
    if not new_exe.is_file():
        raise FileNotFoundError(str(new_exe))

    pid = os.getpid()
    temp = Path(os.environ.get("TEMP", ".")) / "classroom_update"
    temp.mkdir(parents=True, exist_ok=True)
    staged = temp / f"KIBERoneStudent_new_{pid}.exe"
    shutil.copy2(new_exe, staged)

    bat = temp / f"apply_update_{pid}.bat"
    # пути в кавычках; escape не нужен для cmd copy
    bat.write_text(
        "\r\n".join(
            [
                "@echo off",
                "chcp 65001 > nul",
                f":wait_{pid}",
                f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
                "if not errorlevel 1 (",
                "  timeout /t 1 /nobreak >nul",
                f"  goto wait_{pid}",
                ")",
                f'copy /Y "{staged}" "{current}" >nul',
                f'start "" "{current}"',
                f'del /F /Q "{staged}" >nul 2>&1',
                'del /F /Q "%~f0" >nul 2>&1',
                "",
            ]
        ),
        encoding="utf-8",
        errors="replace",
    )
    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        cwd=str(temp),
        creationflags=creationflags,
        close_fds=True,
    )
    return bat
