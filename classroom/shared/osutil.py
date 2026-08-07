"""Кроссплатформенные мелочи для GUI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_in_os(path: Path | str) -> None:
    """Открыть файл/папку в проводнике / Finder."""
    target = str(Path(path))
    if sys.platform == "darwin":
        subprocess.Popen(["open", target])
    elif sys.platform.startswith("win"):
        os.startfile(target)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", target])


def file_type_filters(label: str, *patterns: str) -> list[tuple[str, str]]:
    """
    filetypes для filedialog.
    На macOS нельзя писать «*.exe;*.msi» — Cocoa Tk падает с nil UTI.
    Даём по одному паттерну на строку.
    """
    rows = [(label, pattern) for pattern in patterns]
    rows.append(("Все файлы", "*.*"))
    return rows
