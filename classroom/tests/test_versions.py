"""Тесты истории версий."""

from __future__ import annotations

from pathlib import Path

from classroom.shared.versions import (
    HISTORY_DIR,
    archive_if_changed,
    force_snapshot,
    list_all_versioned_files,
    list_client_files,
    list_commits,
    list_file_versions,
    restore_commit,
    restore_version,
    snapshot_all,
)


def test_archive_creates_history_on_change(tmp_path: Path):
    relative = "lesson_1.py"
    target = tmp_path / relative
    target.write_text("version-1", encoding="utf-8")

    archived = archive_if_changed(tmp_path, relative, b"version-2")
    assert archived is not None
    assert archived["file"] == relative
    assert (tmp_path / HISTORY_DIR).exists()
    versions = list_file_versions(tmp_path, relative)
    assert len(versions) == 1
    assert versions[0]["size"] == len(b"version-1")


def test_archive_skips_identical_content(tmp_path: Path):
    relative = "main.py"
    target = tmp_path / relative
    data = b"same"
    target.write_bytes(data)
    assert archive_if_changed(tmp_path, relative, data) is None
    assert list_file_versions(tmp_path, relative) == []


def test_restore_version_rolls_back(tmp_path: Path):
    relative = "notes.txt"
    target = tmp_path / relative
    target.write_text("old", encoding="utf-8")
    entry = archive_if_changed(tmp_path, relative, b"new")
    target.write_text("new", encoding="utf-8")

    restore_version(tmp_path, relative, entry["id"])
    assert target.read_text(encoding="utf-8") == "old"


def test_force_snapshot_and_list_client_files(tmp_path: Path):
    relative = "code.py"
    (tmp_path / relative).write_text("hello", encoding="utf-8")
    entry = force_snapshot(tmp_path, relative, label="ручной")
    assert entry is not None
    assert entry["label"] == "ручной"
    rows = list_client_files(tmp_path)
    assert len(rows) == 1
    assert rows[0]["path"] == relative
    assert rows[0]["versions"] == 1


def test_snapshot_all(tmp_path: Path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    assert snapshot_all(tmp_path) == 2
    assert snapshot_all(tmp_path) == 0  # без изменений повторно 0


def test_list_all_versioned_files(tmp_path: Path):
    a = tmp_path / "a.py"
    b = tmp_path / "subdir"
    b.mkdir()
    file_b = b / "b.py"
    a.write_text("1", encoding="utf-8")
    file_b.write_text("1", encoding="utf-8")
    archive_if_changed(tmp_path, "a.py", b"2")
    archive_if_changed(tmp_path, "subdir/b.py", b"2")

    rows = list_all_versioned_files(tmp_path)
    paths = {row["path"] for row in rows}
    assert "a.py" in paths
    assert "subdir/b.py" in paths


def test_snapshot_creates_commit_and_restore_all(tmp_path: Path):
    (tmp_path / "a.txt").write_text("a1", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b1", encoding="utf-8")
    assert snapshot_all(tmp_path, label="урок") == 2
    commits = list_commits(tmp_path)
    assert len(commits) == 1
    assert commits[0]["label"] == "урок"
    assert commits[0]["file_count"] == 2

    (tmp_path / "a.txt").write_text("a2", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b2", encoding="utf-8")
    restored = restore_commit(tmp_path, commits[0]["id"])
    assert set(restored) == {"a.txt", "b.txt"}
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "a1"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "b1"
