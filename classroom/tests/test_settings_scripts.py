"""Тесты настроек и скриптов."""

from __future__ import annotations

from pathlib import Path

from classroom.shared.scripts import SHB_SCRIPT, add_preset_from_file, get_preset, load_scripts, remove_preset
from classroom.shared.settings import clamp_sync_seconds, load_teacher_settings, save_teacher_settings


def test_clamp_sync_seconds():
    assert clamp_sync_seconds(10) == 30
    assert clamp_sync_seconds(300) == 300
    assert clamp_sync_seconds(99999) == 3600
    assert clamp_sync_seconds("abc") == 300


def test_teacher_settings_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TEMP", str(tmp_path))
    # config_path uses app_dir — подменим через monkeypatch config folder
    from classroom.shared import settings as settings_mod

    monkeypatch.setattr(settings_mod, "config_path", lambda name: tmp_path / name)
    saved = save_teacher_settings({"sync_seconds": 600})
    assert saved["sync_seconds"] == 600
    loaded = load_teacher_settings()
    assert loaded["sync_seconds"] == 600


def test_shb_preset_exists():
    data = load_scripts()
    assert any(p["id"] == "shb" and p["name"] == "ШБ" for p in data["presets"])
    preset = get_preset("shb")
    assert preset is not None
    assert "ProxyEnable" in (preset.get("content") or SHB_SCRIPT)


def test_add_and_remove_custom_script(tmp_path: Path, monkeypatch):
    from classroom.shared import scripts as scripts_mod

    monkeypatch.setattr(scripts_mod, "config_path", lambda name: tmp_path / name)
    bat = tmp_path / "mine.bat"
    bat.write_text("@echo off\necho hi\n", encoding="utf-8")
    data = add_preset_from_file(bat, name="Мой")
    assert any(p["name"] == "Мой" for p in data["presets"])
    custom_id = next(p["id"] for p in data["presets"] if p["name"] == "Мой")
    data = remove_preset(custom_id)
    assert all(p["name"] != "Мой" for p in data["presets"])
    # ШБ нельзя удалить
    data = remove_preset("shb")
    assert any(p["id"] == "shb" for p in data["presets"])
