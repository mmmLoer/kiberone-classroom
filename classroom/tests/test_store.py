"""Тесты серверного хранилища."""

from __future__ import annotations

from pathlib import Path

from classroom.server.hub import ClassroomStore, HISTORY_DIR
from classroom.shared.constants import DEFAULT_TOKEN


def test_save_upload_keeps_version_and_hides_history(tmp_path: Path):
    store = ClassroomStore(tmp_path, token=DEFAULT_TOKEN)
    store.save_upload("PC1", "lesson_1.py", b"first")
    # первая загрузка уже делает снимок
    root = store.client_root("PC1")
    assert (root / HISTORY_DIR).exists()

    store.save_upload("PC1", "lesson_1.py", b"second")
    assert (root / "lesson_1.py").read_bytes() == b"second"

    files = store.list_files("PC1")
    paths = [item["path"] for item in files]
    assert "lesson_1.py" in paths
    assert all(HISTORY_DIR not in path.split("/") for path in paths)


def test_heartbeat_and_commands(tmp_path: Path):
    store = ClassroomStore(tmp_path, token=DEFAULT_TOKEN)
    store.register_heartbeat(
        "AABBCCDDEEFF",
        {"pc_number": "3", "hostname": "VM1", "watch_folder": "C:/Desktop"},
        "192.168.56.10",
    )
    clients = store.list_clients()
    assert len(clients) == 1
    assert clients[0]["pc_number"] == "3"
    assert clients[0]["status"] == "online"

    store.enqueue(["AABBCCDDEEFF"], "open_url", {"url": "https://example.com"})
    commands = store.pull_commands("AABBCCDDEEFF")
    assert len(commands) == 1
    assert commands[0]["kind"] == "open_url"
    assert store.pull_commands("AABBCCDDEEFF") == []

    assert store.set_client_pc_number("AABBCCDDEEFF", "12")
    assert store.list_clients()[0]["pc_number"] == "12"
    assert not store.set_client_pc_number("MISSING", "1")


def test_safe_client_paths(tmp_path: Path):
    store = ClassroomStore(tmp_path, token=DEFAULT_TOKEN)
    store.register_heartbeat("PC-1", {"pc_number": "5"}, "127.0.0.1")
    store.save_upload("PC-1", "folder/file.txt", b"ok")
    assert store.read_download("PC-1", "folder/file.txt") == b"ok"
    assert (tmp_path / "ПК-5" / "folder" / "file.txt").is_file()


def test_pc_folder_migrates_on_renumber(tmp_path: Path):
    from classroom.server.hub import safe_pc_folder

    assert safe_pc_folder("3") == "ПК-3"
    store = ClassroomStore(tmp_path, token=DEFAULT_TOKEN)
    store.register_heartbeat("AABB", {"pc_number": "1"}, "10.0.0.2")
    store.save_upload("AABB", "a.txt", b"one")
    assert (tmp_path / "ПК-1" / "a.txt").read_bytes() == b"one"
    store.set_client_pc_number("AABB", "2")
    assert (tmp_path / "ПК-2" / "a.txt").is_file()
    assert store.client_root("AABB").name == "ПК-2"
