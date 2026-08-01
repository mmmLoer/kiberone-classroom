"""HTTP-сервер класса: файлы, команды, статусы."""

from __future__ import annotations

import json
import mimetypes
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

from ..shared.constants import DEFAULT_TOKEN, default_backup_dir
from ..shared.deploy_files import resolve_deploy_any
from ..shared.discovery import DiscoveryAnnouncer
from ..shared.starter_pack import list_enabled_starter_pack, resolve_deploy_file
from ..shared.versions import HISTORY_DIR, archive_if_changed, force_snapshot


def safe_client_id(raw: str) -> str:
    cleaned = "".join(ch for ch in raw.strip() if ch.isalnum() or ch in "-_")
    return cleaned or "unknown"


def safe_relative_path(raw: str) -> str:
    relative = unquote(raw).replace("\\", "/").lstrip("/")
    if not relative or ".." in relative.split("/"):
        raise ValueError("bad path")
    return relative


@dataclass
class ClientInfo:
    client_id: str
    pc_number: str = ""
    hostname: str = ""
    ip: str = ""
    last_seen: float = 0.0
    status: str = "offline"
    watch_folder: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Command:
    command_id: str
    client_id: str
    kind: str
    payload: dict
    created_at: float


class ClassroomStore:
    def __init__(self, backup_root: Path, token: str = DEFAULT_TOKEN):
        self.backup_root = backup_root
        self.token = token
        self.clients: dict[str, ClientInfo] = {}
        self.pending: dict[str, list[Command]] = {}
        self.broadcast_pending: list[Command] = []
        self.lock = threading.RLock()
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def client_root(self, client_id: str) -> Path:
        return (self.backup_root / safe_client_id(client_id)).resolve()

    def register_heartbeat(self, client_id: str, payload: dict, ip: str) -> None:
        with self.lock:
            info = self.clients.get(client_id) or ClientInfo(client_id=client_id)
            info.pc_number = str(payload.get("pc_number", info.pc_number))
            info.hostname = str(payload.get("hostname", info.hostname))
            info.watch_folder = str(payload.get("watch_folder", info.watch_folder))
            info.ip = ip
            info.last_seen = time.time()
            info.status = "online"
            info.extra = payload.get("extra", {})
            self.clients[client_id] = info

    def list_clients(self) -> list[dict]:
        now = time.time()
        with self.lock:
            result = []
            for client in self.clients.values():
                online = (now - client.last_seen) <= 15
                result.append(
                    {
                        "client_id": client.client_id,
                        "pc_number": client.pc_number,
                        "hostname": client.hostname,
                        "ip": client.ip,
                        "status": "online" if online else "offline",
                        "last_seen": client.last_seen,
                        "watch_folder": client.watch_folder,
                    }
                )
            result.sort(key=lambda item: (item["pc_number"] or "999", item["client_id"]))
            return result

    def enqueue(self, client_ids: list[str], kind: str, payload: dict | None = None) -> int:
        payload = payload or {}
        created = 0
        with self.lock:
            for client_id in client_ids:
                cmd = Command(
                    command_id=str(uuid.uuid4()),
                    client_id=safe_client_id(client_id),
                    kind=kind,
                    payload=payload,
                    created_at=time.time(),
                )
                self.pending.setdefault(cmd.client_id, []).append(cmd)
                created += 1
            if "__all__" in client_ids:
                cmd = Command(
                    command_id=str(uuid.uuid4()),
                    client_id="__all__",
                    kind=kind,
                    payload=payload,
                    created_at=time.time(),
                )
                self.broadcast_pending.append(cmd)
                created += 1
        return created

    def pull_commands(self, client_id: str) -> list[dict]:
        client_id = safe_client_id(client_id)
        with self.lock:
            own = self.pending.pop(client_id, [])
            broadcast = list(self.broadcast_pending)
            self.broadcast_pending.clear()
            commands = own + [cmd for cmd in broadcast if cmd.client_id == "__all__"]
            return [
                {
                    "command_id": cmd.command_id,
                    "kind": cmd.kind,
                    "payload": cmd.payload,
                }
                for cmd in commands
            ]

    def list_files(self, client_id: str) -> list[dict]:
        root = self.client_root(client_id)
        files = []
        if root.exists():
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                # историю версий ученикам не отдаём
                if HISTORY_DIR in path.relative_to(root).parts:
                    continue
                stat = path.stat()
                files.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                )
        return files

    def save_upload(self, client_id: str, relative: str, data: bytes) -> Path:
        from ..shared.versions import force_snapshot

        root = self.client_root(client_id)
        relative = relative.replace("\\", "/")
        target = (root / relative).resolve()
        if root not in target.parents:
            raise ValueError("bad path")

        existed = target.is_file()
        if HISTORY_DIR not in Path(relative).parts:
            if existed:
                archived = archive_if_changed(root, relative, data)
                if archived:
                    self._note_version(client_id, relative, archived)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        # после первой загрузки — сразу снимок, чтобы история не была пустой
        if HISTORY_DIR not in Path(relative).parts and not existed:
            snap = force_snapshot(root, relative, label="первая загрузка")
            if snap:
                self._note_version(client_id, relative, snap)
        return target

    def _note_version(self, client_id: str, relative: str, archived: dict) -> None:
        # хук для логов; ClassroomServer подставит on_event через store.logger при желании
        note = getattr(self, "on_version", None)
        if callable(note):
            note(client_id, relative, archived)

    def read_download(self, client_id: str, relative: str) -> bytes:
        root = self.client_root(client_id)
        target = (root / relative).resolve()
        if root not in target.parents or not target.is_file():
            raise FileNotFoundError(relative)
        return target.read_bytes()


class ClassroomServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765, backup_dir: Path | None = None, token: str = DEFAULT_TOKEN):
        self.host = host
        self.port = port
        self.store = ClassroomStore(backup_dir or default_backup_dir(), token=token)
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.discovery: DiscoveryAnnouncer | None = None
        self.on_event: Callable[[str], None] | None = None

    def _log(self, message: str) -> None:
        if self.on_event:
            self.on_event(message)

    def start(self) -> None:
        if self.httpd:
            return
        handler = self._make_handler()
        self.httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.store.on_version = lambda client_id, relative, archived: self._log(
            f"Версия сохранена: {client_id} / {relative} ({archived.get('saved_at')})"
        )
        self.discovery = DiscoveryAnnouncer(
            port=self.port,
            token=self.store.token,
            get_host=self.local_ip,
            on_log=self._log,
        )
        self.discovery.start()
        self._log(f"Сервер запущен на порту {self.port}")

    def stop(self) -> None:
        if self.discovery:
            self.discovery.stop()
            self.discovery = None
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        self._log("Сервер остановлен")

    def local_ip(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    def _make_handler(self):
        store = self.store
        log = self._log

        class Handler(BaseHTTPRequestHandler):
            server_version = "KIBERoneClassroom/1.0"

            def log_message(self, fmt, *args):
                return

            def _auth_ok(self) -> bool:
                return self.headers.get("X-Sync-Token", "") == store.token

            def _json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _bytes(self, status: int, data: bytes, content_type: str = "application/octet-stream") -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _client_id(self) -> str:
                query = parse_qs(urlparse(self.path).query)
                if "client_id" in query and query["client_id"]:
                    return safe_client_id(query["client_id"][0])
                return safe_client_id(self.headers.get("X-Client-Id", "unknown"))

            def do_GET(self):
                if not self._auth_ok():
                    self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "bad token"})
                    return
                route = urlparse(self.path).path
                if route == "/health":
                    self._json(HTTPStatus.OK, {"ok": True})
                    return
                if route == "/clients":
                    self._json(HTTPStatus.OK, {"ok": True, "clients": store.list_clients()})
                    return
                if route == "/list":
                    files = store.list_files(self._client_id())
                    self._json(HTTPStatus.OK, {"ok": True, "files": files})
                    return
                if route == "/commands":
                    commands = store.pull_commands(self._client_id())
                    self._json(HTTPStatus.OK, {"ok": True, "commands": commands})
                    return
                if route == "/download":
                    query = parse_qs(urlparse(self.path).query)
                    try:
                        relative = safe_relative_path(query["path"][0])
                        data = store.read_download(self._client_id(), relative)
                    except (KeyError, ValueError, FileNotFoundError) as exc:
                        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc)})
                        return
                    mime, _ = mimetypes.guess_type(relative)
                    self._bytes(HTTPStatus.OK, data, mime or "application/octet-stream")
                    return
                if route == "/starter-pack":
                    items = list_enabled_starter_pack()
                    self._json(HTTPStatus.OK, {"ok": True, "items": items})
                    return
                if route == "/starter-pack/file":
                    query = parse_qs(urlparse(self.path).query)
                    try:
                        name = query["name"][0]
                        path = resolve_deploy_file(name)
                        data = path.read_bytes()
                    except (KeyError, ValueError, FileNotFoundError) as exc:
                        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc)})
                        return
                    mime, _ = mimetypes.guess_type(path.name)
                    self._bytes(HTTPStatus.OK, data, mime or "application/octet-stream")
                    return
                if route == "/deploy/file":
                    query = parse_qs(urlparse(self.path).query)
                    try:
                        name = query["name"][0]
                        path = resolve_deploy_any(name)
                        data = path.read_bytes()
                    except (KeyError, ValueError, FileNotFoundError) as exc:
                        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc)})
                        return
                    mime, _ = mimetypes.guess_type(path.name)
                    self._bytes(HTTPStatus.OK, data, mime or "application/octet-stream")
                    return
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

            def do_POST(self):
                if not self._auth_ok():
                    self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "bad token"})
                    return
                route = urlparse(self.path).path
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length) if length else b"{}"
                if route == "/heartbeat":
                    payload = json.loads(body.decode("utf-8") or "{}")
                    client_id = safe_client_id(payload.get("client_id", ""))
                    store.register_heartbeat(client_id, payload, self.client_address[0])
                    self._json(HTTPStatus.OK, {"ok": True})
                    return
                if route == "/upload":
                    try:
                        relative = safe_relative_path(self.headers.get("X-Relative-Path", "unknown.bin"))
                        target = store.save_upload(self._client_id(), relative, body)
                        log(f"Файл от {self._client_id()}: {relative}")
                        self._json(HTTPStatus.OK, {"ok": True, "saved_to": str(target)})
                    except ValueError as exc:
                        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                    return
                if route == "/command":
                    payload = json.loads(body.decode("utf-8") or "{}")
                    client_ids = payload.get("client_ids") or []
                    kind = payload.get("kind", "")
                    cmd_payload = payload.get("payload") or {}
                    count = store.enqueue(client_ids, kind, cmd_payload)
                    log(f"Команда {kind} -> {len(client_ids)} ПК")
                    self._json(HTTPStatus.OK, {"ok": True, "queued": count})
                    return
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

        return Handler
