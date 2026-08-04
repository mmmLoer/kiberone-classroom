"""Тесты публикации обновлений ученика."""

from __future__ import annotations

from pathlib import Path

from classroom.shared.updates import (
    get_update_info,
    parse_version,
    publish_student_exe,
    update_available_for,
    version_newer,
)


def test_version_compare():
    assert parse_version("1.2.3") == (1, 2, 3)
    assert version_newer("1.1.0", "1.0.9")
    assert not version_newer("1.0.0", "1.0.0")
    assert not version_newer("1.0.0", "1.1.0")


def test_publish_and_detect(tmp_path: Path, monkeypatch):
    from classroom.shared import updates as updates_mod

    monkeypatch.setattr(updates_mod, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(updates_mod, "config_path", lambda name: tmp_path / name)

    src = tmp_path / "src" / "KIBERoneStudent.exe"
    src.parent.mkdir()
    src.write_bytes(b"fake-student-exe-content")

    info = publish_student_exe(src, version="1.2.0")
    assert info["version"] == "1.2.0"
    assert info["size"] == len(b"fake-student-exe-content")
    assert (tmp_path / "updates" / "KIBERoneStudent.exe").is_file()

    loaded = get_update_info()
    assert loaded is not None
    assert loaded["version"] == "1.2.0"

    assert update_available_for("1.0.0") is not None
    assert update_available_for("1.2.0") is None
    assert update_available_for("9.0.0") is None
