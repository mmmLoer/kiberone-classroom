"""Тесты стартового пака."""

from __future__ import annotations

from pathlib import Path

from classroom.shared import starter_pack as sp


def test_list_and_select_installers(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sp, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(sp, "config_path", lambda name: tmp_path / "config" / name)
    (tmp_path / "config").mkdir()
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "PythonSetup.exe").write_bytes(b"abc")
    (deploy / "notes.txt").write_text("skip")
    (deploy / "VSCode.msi").write_bytes(b"msi")
    pack = deploy / "Урок1"
    pack.mkdir()
    (pack / "readme.txt").write_text("hi", encoding="utf-8")
    (pack / "data.json").write_text("{}", encoding="utf-8")

    items = sp.list_deploy_installers()
    by_name = {item["name"]: item for item in items}
    assert set(by_name) == {"PythonSetup.exe", "VSCode.msi", "Урок1"}
    assert by_name["Урок1"]["kind"] == "folder"
    assert by_name["Урок1"]["size"] > 0
    assert by_name["PythonSetup.exe"]["kind"] == "installer"

    sp.save_starter_selection(["PythonSetup.exe", "Урок1"], titles={"Урок1": "Материалы"})
    enabled = sp.list_enabled_starter_pack()
    assert {item["name"] for item in enabled} == {"PythonSetup.exe", "Урок1"}
    folder_item = next(item for item in enabled if item["name"] == "Урок1")
    assert folder_item["kind"] == "folder"
    assert folder_item["title"] == "Материалы"

    path = sp.resolve_deploy_file("PythonSetup.exe")
    assert path.exists()

    folder, kind = sp.resolve_deploy_pack_item("Урок1")
    assert kind == "folder"
    assert folder.is_dir()
    data = sp.zip_folder_bytes(folder)
    assert data[:2] == b"PK"
