"""Клиент ученика: синхронизация, heartbeat, выполнение команд."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable

from ..shared.constants import DEFAULT_TOKEN, POLL_SECONDS, SYNC_SECONDS, expand_path
from ..shared.identity import get_mac_id, get_pc_number, get_watch_folder


class StudentAgent:
    def __init__(
        self,
        teacher_host: str,
        port: int = 8765,
        token: str = DEFAULT_TOKEN,
        watch_folder: str | None = None,
        fresh_saves_dir: Path | None = None,
        on_log: Callable[[str], None] | None = None,
    ):
        self.teacher_host = teacher_host.strip()
        self.port = port
        self.token = token
        self.client_id = get_mac_id()
        self.watch_folder = expand_path(watch_folder or get_watch_folder(str(Path.home() / "Desktop")))
        self.fresh_saves_dir = fresh_saves_dir
        self.on_log = on_log or (lambda msg: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state_path = Path(os.environ.get("TEMP", ".")) / f"classroom_sync_{self.client_id}.json"
        self.exclude_dirs = {".venv", "__pycache__", ".git", "node_modules", "$RECYCLE.BIN", ".history"}
        self.exclude_files = {"Thumbs.db", "desktop.ini", ".DS_Store"}

    @property
    def base_url(self) -> str:
        return f"http://{self.teacher_host}:{self.port}"

    def log(self, message: str) -> None:
        self.on_log(message)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.watch_folder.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.log("Агент запущен")

    def stop(self) -> None:
        self._stop.set()
        self.log("Агент остановлен")

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"X-Sync-Token": self.token, "X-Client-Id": self.client_id}
        if extra:
            headers.update(extra)
        return headers

    def _request(self, method: str, path: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 15):
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
            if "application/json" in content_type:
                return json.loads(body.decode("utf-8"))
            return body

    def ping(self) -> bool:
        try:
            self._request("GET", "/health", headers=self._headers())
            return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _loop(self) -> None:
        last_sync = 0.0
        while not self._stop.is_set():
            try:
                self._heartbeat()
                self._poll_commands()
                if time.time() - last_sync >= SYNC_SECONDS:
                    self.sync_once()
                    last_sync = time.time()
            except Exception as exc:
                self.log(f"Ошибка: {exc}")
            self._stop.wait(POLL_SECONDS)

    def _heartbeat(self) -> None:
        payload = json.dumps(
            {
                "client_id": self.client_id,
                "pc_number": get_pc_number(),
                "hostname": socket.gethostname(),
                "watch_folder": str(self.watch_folder),
            }
        ).encode("utf-8")
        self._request(
            "POST",
            "/heartbeat",
            data=payload,
            headers={**self._headers(), "Content-Type": "application/json"},
        )

    def _poll_commands(self) -> None:
        result = self._request("GET", f"/commands?client_id={self.client_id}", headers=self._headers())
        for command in result.get("commands", []):
            self._execute(command)

    def _execute(self, command: dict) -> None:
        kind = command.get("kind", "")
        payload = command.get("payload") or {}
        self.log(f"Команда: {kind}")

        if kind == "open_url":
            url = payload.get("url", "")
            if url:
                webbrowser.open(url)
        elif kind == "set_wallpaper":
            self._apply_wallpaper(payload)
        elif kind == "run_file":
            self._run_file(payload)
        elif kind == "restore_saves":
            self.restore_from_teacher()
        elif kind == "use_fresh_saves":
            self.apply_fresh_saves(payload.get("target", "сохры"))
        elif kind == "sync_now":
            self.sync_once()
        elif kind == "message":
            self.log(f"Сообщение: {payload.get('text', '')}")
        elif kind == "install_starter_pack":
            names = payload.get("names")
            self.install_starter_pack(names=names)

    def fetch_starter_pack(self) -> list[dict]:
        result = self._request("GET", "/starter-pack", headers=self._headers(), timeout=20)
        return list(result.get("items") or [])

    def download_starter_item(self, name: str) -> Path:
        encoded = urllib.parse.quote(name)
        data = self._request(
            "GET",
            f"/starter-pack/file?name={encoded}",
            headers=self._headers(),
            timeout=300,
        )
        if isinstance(data, dict):
            raise RuntimeError(data.get("error") or "download failed")
        temp_dir = Path(os.environ.get("TEMP", ".")) / "classroom_starter"
        temp_dir.mkdir(parents=True, exist_ok=True)
        local = temp_dir / Path(name).name
        local.write_bytes(data)
        return local

    def install_starter_pack(self, names: list[str] | None = None) -> int:
        items = self.fetch_starter_pack()
        if names:
            wanted = set(names)
            items = [item for item in items if item.get("name") in wanted]
        if not items:
            self.log("Стартовый пак пуст")
            return 0

        installed = 0
        for item in items:
            name = item["name"]
            title = item.get("title") or name
            try:
                self.log(f"Скачиваю: {title}")
                local = self.download_starter_item(name)
                self.log(f"Запускаю установщик: {title}")
                suffix = local.suffix.lower()
                if suffix == ".msi":
                    subprocess.Popen(["msiexec", "/i", str(local)], shell=False)
                elif suffix == ".ps1":
                    subprocess.Popen(
                        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(local)],
                        shell=False,
                    )
                else:
                    subprocess.Popen([str(local)], shell=True)
                installed += 1
            except Exception as exc:
                self.log(f"Не удалось установить {title}: {exc}")
        self.log(f"Стартовый пак: запущено установщиков {installed}/{len(items)}")
        return installed

    def _apply_wallpaper(self, payload: dict) -> None:
        rel = payload.get("relative_path")
        if rel:
            data = self._request("GET", f"/download?client_id={self.client_id}&path={urllib.parse.quote(rel)}", headers=self._headers())
            temp = Path(os.environ.get("TEMP", ".")) / "classroom_wallpaper.png"
            temp.write_bytes(data)
            image_path = str(temp)
        else:
            image_path = payload.get("path", "")

        if not image_path:
            return

        ps = (
            f'$p="{image_path}";'
            'Set-ItemProperty -Path "HKCU:\\Control Panel\\Desktop" -Name WallpaperStyle -Value 10;'
            'Set-ItemProperty -Path "HKCU:\\Control Panel\\Desktop" -Name TileWallpaper -Value 0;'
            'Add-Type @\"'
            "using System; using System.Runtime.InteropServices;"
            "public class W { [DllImport(\"user32.dll\", SetLastError=true)] public static extern bool SystemParametersInfo(int a,int b,string c,int d); }"
            '\"@;'
            '[W]::SystemParametersInfo(20,0,$p,3)'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
        self.log("Обои установлены")

    def _run_file(self, payload: dict) -> None:
        rel = payload.get("relative_path")
        if rel:
            data = self._request("GET", f"/download?client_id={self.client_id}&path={urllib.parse.quote(rel)}", headers=self._headers())
            temp_dir = Path(os.environ.get("TEMP", ".")) / "classroom_install"
            temp_dir.mkdir(parents=True, exist_ok=True)
            local = temp_dir / Path(rel).name
            local.write_bytes(data)
            path = str(local)
        else:
            path = payload.get("path", "")

        if not path:
            return
        subprocess.Popen(path, shell=True)
        self.log(f"Запущен файл: {path}")

    def apply_fresh_saves(self, target_name: str = "сохры") -> None:
        if not self.fresh_saves_dir or not self.fresh_saves_dir.exists():
            self.log("Папка чистых сохранений не найдена")
            return
        target = self.watch_folder / target_name
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run(["robocopy", str(self.fresh_saves_dir), str(target), "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np"], check=False)
        self.log("Чистые сохранения применены")

    def restore_from_teacher(self) -> None:
        result = self._request("GET", f"/list?client_id={self.client_id}", headers=self._headers())
        files = result.get("files", [])
        if not files:
            self.log("На сервере нет сохранений для этого ПК")
            return
        for item in files:
            rel = item["path"]
            data = self._request("GET", f"/download?client_id={self.client_id}&path={urllib.parse.quote(rel)}", headers=self._headers())
            local = self.watch_folder / rel
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
        self.log(f"Загружено файлов: {len(files)}")

    def _load_state(self) -> dict:
        if not self._state_path.exists():
            return {}
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save_state(self, state: dict) -> None:
        self._state_path.write_text(json.dumps(state), encoding="utf-8")

    def _should_sync(self, file_path: Path, root: Path) -> bool:
        if file_path.name in self.exclude_files:
            return False
        rel = file_path.relative_to(root)
        for part in rel.parts:
            if part in self.exclude_dirs:
                return False
        return True

    def sync_once(self) -> None:
        root = self.watch_folder.resolve()
        state = self._load_state()
        new_state = {}
        uploaded = 0
        for file_path in root.rglob("*"):
            if not file_path.is_file() or not self._should_sync(file_path, root):
                continue
            rel = file_path.relative_to(root).as_posix()
            signature = f"{file_path.stat().st_mtime_ns}|{file_path.stat().st_size}"
            new_state[rel] = signature
            if state.get(rel) == signature:
                continue
            data = file_path.read_bytes()
            self._request(
                "POST",
                "/upload",
                data=data,
                headers={
                    **self._headers(),
                    "X-Relative-Path": urllib.parse.quote(rel),
                    "Content-Type": "application/octet-stream",
                },
            )
            uploaded += 1
        self._save_state(new_state)
        if uploaded:
            self.log(f"Отправлено файлов: {uploaded}")
        else:
            self.log("Изменений нет")
