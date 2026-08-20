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

from ..shared.constants import APP_VERSION, DEFAULT_TOKEN, POLL_SECONDS, SYNC_SECONDS, desktop_dir, expand_path
from ..shared.http_client import request as http_request, tcp_reachable
from ..shared.identity import get_mac_id, get_pc_number, get_watch_folder, set_pc_number
from ..shared.settings import clamp_sync_seconds
from ..shared.scripts import script_extension
from ..shared.updates import file_sha256, schedule_exe_replace, version_newer

import zipfile


class StudentAgent:
    def __init__(
        self,
        teacher_host: str,
        port: int = 8765,
        token: str = DEFAULT_TOKEN,
        watch_folder: str | None = None,
        fresh_saves_dir: Path | None = None,
        on_log: Callable[[str], None] | None = None,
        on_message: Callable[[str], None] | None = None,
        on_pc_number_changed: Callable[[str], None] | None = None,
        on_update_available: Callable[[dict], None] | None = None,
        on_lock_screen: Callable[[], None] | None = None,
        on_unlock_screen: Callable[[], None] | None = None,
        student_id: str = "",
        session_id: str = "",
    ):
        self.teacher_host = teacher_host.strip()
        self.port = port
        self.token = token
        self.client_id = get_mac_id()
        self.watch_folder = expand_path(watch_folder or get_watch_folder(str(Path.home() / "Desktop")))
        self.fresh_saves_dir = fresh_saves_dir
        self.on_log = on_log or (lambda msg: None)
        self.on_message = on_message or (lambda text: self.on_log(f"Сообщение: {text}"))
        self.on_pc_number_changed = on_pc_number_changed or (lambda _n: None)
        self.on_update_available = on_update_available or (lambda _info: None)
        self.on_lock_screen = on_lock_screen or (lambda: None)
        self.on_unlock_screen = on_unlock_screen or (lambda: None)
        self.student_id = student_id
        self.session_id = session_id
        self.sync_seconds = SYNC_SECONDS
        self.app_version = APP_VERSION
        self._notified_update_version: str | None = None
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

    def _request(
        self,
        method: str,
        path: str,
        data: bytes | None = None,
        headers: dict | None = None,
        timeout: int = 15,
        raw: bool = False,
    ):
        if data is not None and not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError(f"request data must be bytes, got {type(data).__name__}")
        return http_request(
            method,
            f"{self.base_url}{path}",
            data=data,
            headers=headers or {},
            timeout=timeout,
            raw=raw,
        )

    def ping(self, retries: int = 3, timeout: float = 4.0) -> bool:
        ok, _ = self.ping_details(retries=retries, timeout=timeout)
        return ok

    def ping_details(self, retries: int = 3, timeout: float = 4.0) -> tuple[bool, str]:
        host = self.teacher_host
        ok, err = tcp_reachable(host, self.port, timeout=min(timeout, 3.0))
        if not ok:
            return False, err

        last_error = "Неизвестная ошибка"
        attempts = max(1, retries)
        for attempt in range(attempts):
            try:
                result = self._request("GET", "/health", headers=self._headers(), timeout=int(timeout))
                if isinstance(result, dict) and result.get("ok"):
                    return True, ""
                last_error = "Сервер ответил, но health-check не прошёл"
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    return False, "Неверный токен синхронизации (переустанови Student/Tutor с одного релиза)"
                last_error = f"HTTP {exc.code}"
            except urllib.error.URLError as exc:
                reason = str(getattr(exc, "reason", exc) or exc)
                low = reason.lower()
                if "proxy" in low or "tunnel" in low:
                    last_error = (
                        "Системный прокси блокирует связь с тьютором. "
                        "Обратись к админу сети или подключайся в той же подсети без прокси."
                    )
                elif "timed out" in low or "timeout" in low:
                    last_error = (
                        f"Таймаут HTTP к {host}:{self.port}. "
                        "Ping может проходить, а порт 8765 — быть закрыт брандмауэром на ПК тьютора."
                    )
                else:
                    last_error = reason
            except (TimeoutError, OSError) as exc:
                last_error = str(exc)
            if attempt + 1 < attempts:
                time.sleep(0.4)
        return False, last_error

    @staticmethod
    def _as_bytes(data) -> bytes:
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if isinstance(data, memoryview):
            return data.tobytes()
        if isinstance(data, dict):
            raise TypeError("ожидались байты файла, пришёл JSON (dict)")
        raise TypeError(f"ожидались байты файла, пришло {type(data).__name__}")

    def _loop(self) -> None:
        last_sync = 0.0
        while not self._stop.is_set():
            try:
                self._heartbeat()
                self._poll_commands()
                if time.time() - last_sync >= self.sync_seconds:
                    self.sync_once()
                    last_sync = time.time()
            except Exception as exc:
                self.log(f"Ошибка: {exc}")
            self._stop.wait(POLL_SECONDS)

    def _apply_settings(self, settings: dict | None) -> None:
        if not settings:
            return
        if "sync_seconds" in settings:
            new_value = clamp_sync_seconds(settings.get("sync_seconds"))
            if new_value != self.sync_seconds:
                self.sync_seconds = new_value
                self.log(f"Интервал синхронизации: {self.sync_seconds} с")

    def _heartbeat(self) -> None:
        payload = json.dumps(
            {
                "client_id": self.client_id,
                "pc_number": get_pc_number(),
                "hostname": socket.gethostname(),
                "watch_folder": str(self.watch_folder),
                "app_version": self.app_version,
                "student_id": self.student_id,
                "session_id": self.session_id,
            }
        ).encode("utf-8")
        result = self._request(
            "POST",
            "/heartbeat",
            data=payload,
            headers={**self._headers(), "Content-Type": "application/json"},
        )
        if isinstance(result, dict):
            self._apply_settings(result.get("settings"))
            self._maybe_notify_update(result.get("student_update"))

    def _maybe_notify_update(self, info: dict | None) -> None:
        if not info or not isinstance(info, dict):
            return
        remote = str(info.get("version") or "")
        if not remote or not version_newer(remote, self.app_version):
            return
        if self._notified_update_version == remote:
            return
        self._notified_update_version = remote
        self.log(f"Доступно обновление: {remote} (сейчас {self.app_version})")
        self.on_update_available(info)

    def check_for_update(self) -> dict | None:
        result = self._request("GET", "/update/student", headers=self._headers(), timeout=20)
        info = result.get("update") if isinstance(result, dict) else None
        if info and version_newer(str(info.get("version") or ""), self.app_version):
            return info
        return None

    def download_student_update(self, expected_sha256: str = "") -> Path:
        data = self._request(
            "GET",
            "/update/student/file",
            headers=self._headers(),
            timeout=600,
            raw=True,
        )
        if isinstance(data, dict):
            raise RuntimeError(data.get("error") or "download failed")
        data = self._as_bytes(data)
        temp_dir = Path(os.environ.get("TEMP", ".")) / "classroom_update"
        temp_dir.mkdir(parents=True, exist_ok=True)
        local = temp_dir / f"KIBERoneStudent_{self.client_id}.exe"
        local.write_bytes(data)
        if expected_sha256:
            digest = file_sha256(local)
            if digest.lower() != expected_sha256.lower():
                local.unlink(missing_ok=True)
                raise RuntimeError("Хеш скачанного файла не совпал")
        return local

    def apply_downloaded_update(self, local_exe: Path) -> None:
        schedule_exe_replace(local_exe)
        self.log("Обновление подготовлено — перезапуск…")

    def fetch_scripts(self) -> dict:
        return self._request("GET", "/scripts", headers=self._headers(), timeout=20)

    def run_script_local(self, name: str, content: str, kind: str = "bat") -> None:
        self._run_script({"name": name, "content": content, "kind": kind})

    def _run_script(self, payload: dict) -> None:
        name = str(payload.get("name") or "script").strip() or "script"
        content = str(payload.get("content") or "")
        kind = str(payload.get("kind") or "bat").lower()
        if not content.strip():
            self.log("Скрипт пустой")
            return
        temp_dir = Path(os.environ.get("TEMP", ".")) / "classroom_scripts"
        temp_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:40]
        script_path = temp_dir / f"{safe}{script_extension(kind)}"
        script_path.write_text(content, encoding="utf-8", errors="replace")
        self.log(f"Запускаю скрипт: {name}")
        if kind == "ps1":
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                shell=False,
            )
        else:
            subprocess.Popen(["cmd", "/c", str(script_path)], shell=False)

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
        elif kind == "run_shell":
            self._run_shell(payload)
        elif kind == "run_script":
            self._run_script(payload)
        elif kind == "configure":
            self._apply_settings(payload)
        elif kind == "offer_update":
            info = payload if payload.get("version") else self.check_for_update()
            if info:
                self._notified_update_version = None
                self._maybe_notify_update(info)
            else:
                self.log("Обновлений нет")
        elif kind == "restore_saves":
            self.restore_from_teacher()
        elif kind == "use_fresh_saves":
            self.apply_fresh_saves(payload.get("target", "сохры"))
        elif kind == "sync_now":
            self.sync_once()
        elif kind == "message":
            text = str(payload.get("text") or "").strip()
            if text:
                self.log(f"Сообщение: {text}")
                self.on_message(text)
        elif kind == "set_pc_number":
            number = str(payload.get("pc_number") or "").strip()
            if number:
                set_pc_number(number)
                self.log(f"Номер ПК изменён: {number}")
                self.on_pc_number_changed(number)
                # сразу сообщим тьютору новый номер
                try:
                    self._heartbeat()
                except Exception:
                    pass
        elif kind == "install_starter_pack":
            names = payload.get("names")
            self.install_starter_pack(names=names)
        elif kind == "lock_screen":
            self.on_lock_screen()
        elif kind == "unlock_screen":
            self.on_unlock_screen()

    def fetch_starter_pack(self) -> list[dict]:
        result = self._request("GET", "/starter-pack", headers=self._headers(), timeout=20)
        return list(result.get("items") or [])

    def download_starter_item(self, name: str, kind: str = "installer") -> Path:
        encoded = urllib.parse.quote(name)
        data = self._request(
            "GET",
            f"/starter-pack/file?name={encoded}",
            headers=self._headers(),
            timeout=300,
            raw=True,
        )
        if isinstance(data, dict):
            raise RuntimeError(data.get("error") or "download failed")
        temp_dir = Path(os.environ.get("TEMP", ".")) / "classroom_starter"
        temp_dir.mkdir(parents=True, exist_ok=True)
        if kind == "folder":
            local = temp_dir / f"{Path(name).name}.zip"
        else:
            local = temp_dir / Path(name).name
        local.write_bytes(self._as_bytes(data))
        return local

    def _deploy_folder_target(self, folder_name: str) -> Path:
        """Папка ресурсов на рабочем столе ученика."""
        safe = Path(folder_name).name
        target = desktop_dir() / safe
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _extract_starter_folder(self, archive: Path, folder_name: str) -> Path:
        target = self._deploy_folder_target(folder_name)
        root = target.resolve()
        with zipfile.ZipFile(archive, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                dest = (target / info.filename).resolve()
                if root not in dest.parents and dest != root:
                    raise RuntimeError(f"bad path in archive: {info.filename}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, dest.open("wb") as out:
                    out.write(src.read())
        return target

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
            kind = item.get("kind") or "installer"
            try:
                if kind == "folder":
                    self.log(f"Скачиваю папку: {title}")
                    local = self.download_starter_item(name, kind="folder")
                    target = self._extract_starter_folder(local, name)
                    self.log(f"Папка развёрнута: {target}")
                    installed += 1
                    continue

                self.log(f"Скачиваю: {title}")
                local = self.download_starter_item(name, kind="installer")
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
        self.log(f"Стартовый пак: обработано {installed}/{len(items)}")
        return installed

    def _apply_wallpaper(self, payload: dict) -> None:
        deploy_name = payload.get("deploy_name") or ""
        rel = payload.get("relative_path") or ""
        data: bytes | None = None
        suffix = ".jpg"

        try:
            if deploy_name:
                encoded = urllib.parse.quote(Path(deploy_name).name)
                raw = self._request(
                    "GET",
                    f"/deploy/file?name={encoded}",
                    headers=self._headers(),
                    timeout=120,
                    raw=True,
                )
                if isinstance(raw, dict):
                    raise RuntimeError(raw.get("error") or "download failed")
                data = self._as_bytes(raw)
                suffix = Path(deploy_name).suffix.lower() or ".jpg"
            elif rel:
                raw = self._request(
                    "GET",
                    f"/download?client_id={self.client_id}&path={urllib.parse.quote(rel)}",
                    headers=self._headers(),
                    timeout=120,
                    raw=True,
                )
                if isinstance(raw, dict):
                    raise RuntimeError(raw.get("error") or "download failed")
                data = self._as_bytes(raw)
                suffix = Path(rel).suffix.lower() or ".jpg"
            elif payload.get("path"):
                image_path = str(payload["path"])
                self._set_wallpaper_windows(image_path)
                self.log("Обои установлены")
                return
        except Exception as exc:
            self.log(f"Не удалось скачать обои: {exc}")
            return

        if not data:
            self.log("Обои: пустой файл")
            return

        if suffix not in {".jpg", ".jpeg", ".png", ".bmp"}:
            suffix = ".jpg"

        temp = Path(os.environ.get("TEMP", ".")) / f"classroom_wallpaper{suffix}"
        temp.write_bytes(data)
        try:
            self._set_wallpaper_windows(str(temp))
            self.log(f"Обои установлены ({temp.name})")
        except Exception as exc:
            self.log(f"Не удалось поставить обои: {exc}")

    def _set_wallpaper_windows(self, image_path: str) -> None:
        import ctypes
        import winreg

        path = str(Path(image_path).resolve())
        # Fill / stretch
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "10")
            winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "0")
            winreg.SetValueEx(key, "Wallpaper", 0, winreg.REG_SZ, path)

        SPI_SETDESKWALLPAPER = 20
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDWININICHANGE = 0x02
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            path,
            SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE,
        )
        if not ok:
            raise OSError(f"SystemParametersInfoW failed, code={ctypes.get_last_error()}")

    def _run_shell(self, payload: dict) -> None:
        command = str(payload.get("command") or "").strip()
        if not command:
            self.log("Пустая команда")
            return
        cwd = payload.get("cwd") or None
        timeout = int(payload.get("timeout") or 120)
        self.log(f"Команда: {command}")
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            out = (completed.stdout or "").strip()
            err = (completed.stderr or "").strip()
            self.log(f"Код выхода: {completed.returncode}")
            if out:
                self.log(out[:2000])
            if err:
                self.log(f"stderr: {err[:1000]}")
        except subprocess.TimeoutExpired:
            self.log(f"Команда превысила таймаут {timeout}с")
        except Exception as exc:
            self.log(f"Ошибка команды: {exc}")

    def _run_file(self, payload: dict) -> None:
        rel = payload.get("relative_path")
        if rel:
            data = self._request(
                "GET",
                f"/download?client_id={self.client_id}&path={urllib.parse.quote(rel)}",
                headers=self._headers(),
                raw=True,
            )
            temp_dir = Path(os.environ.get("TEMP", ".")) / "classroom_install"
            temp_dir.mkdir(parents=True, exist_ok=True)
            local = temp_dir / Path(rel).name
            local.write_bytes(self._as_bytes(data))
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
            data = self._request(
                "GET",
                f"/download?client_id={self.client_id}&path={urllib.parse.quote(rel)}",
                headers=self._headers(),
                raw=True,
            )
            local = self.watch_folder / rel
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(self._as_bytes(data))
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

    def diff_with_server(self) -> dict:
        """Сравнивает локальные файлы с тем, что есть на сервере.

        Возвращает dict:
          {
            "local_only":  [rel_path, ...],   # есть локально, нет на сервере
            "server_only": [rel_path, ...],   # есть на сервере, нет локально
            "conflict":    [rel_path, ...],   # есть с обеих сторон, но размер/mtime различаются
          }
        """
        root = self.watch_folder.resolve()

        # --- Локальные файлы ---
        local_files: dict[str, int] = {}
        if root.exists():
            for file_path in root.rglob("*"):
                if not file_path.is_file() or not self._should_sync(file_path, root):
                    continue
                rel = file_path.relative_to(root).as_posix()
                local_files[rel] = file_path.stat().st_size

        # --- Серверные файлы ---
        result = self._request("GET", f"/list?client_id={self.client_id}", headers=self._headers())
        server_list: list[dict] = (result or {}).get("files", []) if isinstance(result, dict) else []
        server_files: dict[str, int] = {item["path"]: item.get("size", 0) for item in server_list}

        local_set = set(local_files)
        server_set = set(server_files)

        return {
            "local_only":  sorted(local_set - server_set),
            "server_only": sorted(server_set - local_set),
            "conflict":    sorted(
                rel for rel in local_set & server_set
                if local_files[rel] != server_files[rel]
            ),
        }

