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

    items = sp.list_deploy_installers()
    names = {item["name"] for item in items}
    assert names == {"PythonSetup.exe", "VSCode.msi"}

    sp.save_starter_selection(["PythonSetup.exe"], titles={"PythonSetup.exe": "Python"})
    enabled = sp.list_enabled_starter_pack()
    assert len(enabled) == 1
    assert enabled[0]["name"] == "PythonSetup.exe"
    assert enabled[0]["title"] == "Python"

    path = sp.resolve_deploy_file("PythonSetup.exe")
    assert path.exists()
