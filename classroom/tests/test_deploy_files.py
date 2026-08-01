"""Тесты deploy/wallpaper helpers."""

from __future__ import annotations

from pathlib import Path

from classroom.shared import deploy_files as df


def test_resolve_deploy_any(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(df, "app_dir", lambda: tmp_path)
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "wall.jpg").write_bytes(b"img")
    path = df.resolve_deploy_any("wall.jpg")
    assert path.read_bytes() == b"img"
