"""Брендинг: логотип школы."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

from .constants import app_dir


def logo_candidates() -> list[Path]:
    paths: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        paths.append(meipass / "assets" / "logo.png")
        paths.append(meipass / "assets" / "logo.jpg")

    root = app_dir()
    paths.extend(
        [
            root / "assets" / "logo.png",
            root / "assets" / "logo.jpg",
            root / "deploy" / "images.jpg",
            root / "dist" / "deploy" / "images.jpg",
        ]
    )
    return paths


def logo_path() -> Path | None:
    for path in logo_candidates():
        if path.is_file():
            return path
    return None


def load_logo_photo(master: tk.Misc, max_height: int = 40) -> tk.PhotoImage | None:
    path = logo_path()
    if not path:
        return None
    # tk PhotoImage надёжнее с PNG
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        png = path.with_suffix(".png")
        if png.is_file():
            path = png
        else:
            # jpg часто не открывается в чистом tk — пробуем png рядом в assets
            alt = app_dir() / "assets" / "logo.png"
            if alt.is_file():
                path = alt
    try:
        image = tk.PhotoImage(file=str(path))
    except tk.TclError:
        return None

    h = int(image.height())
    if h > max_height and h > 0:
        factor = max(1, round(h / max_height))
        image = image.subsample(factor, factor)
    return image


def place_header_logo(header: tk.Misc, max_height: int = 40) -> tk.PhotoImage | None:
    """Ставит логотип слева в header. Возвращает PhotoImage, чтобы не GC-снуло."""
    photo = load_logo_photo(header, max_height=max_height)
    if not photo:
        return None
    label = tk.Label(header, image=photo, bg="#0F172A", borderwidth=0, highlightthickness=0)
    label.pack(side="left", padx=(0, 12))
    label.image = photo  # type: ignore[attr-defined]
    return photo
