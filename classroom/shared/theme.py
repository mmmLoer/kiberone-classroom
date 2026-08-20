"""Тема интерфейса KIBERone Classroom (tkinter)."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

# ── Палитра ──────────────────────────────────────────────────────────────────
COLORS = {
    # Фоны
    "bg":            "#F0F4F8",   # Основной фон
    "surface":       "#FFFFFF",   # Карточки / поля
    "surface_muted": "#E4ECF4",   # Слегка затемнённые поверхности
    # Текст
    "ink":           "#0F1E2E",   # Основной текст (очень тёмный, читаемый везде)
    "ink_muted":     "#4A5F72",   # Вспомогательный текст
    "ink_subtle":    "#6B7E90",   # Placeholder, подписи к полям
    # Рамки
    "border":        "#C2CDD8",
    # Акцент
    "accent":        "#0F766E",
    "accent_hover":  "#0D9488",
    "accent_pressed":"#115E59",
    "accent_soft":   "#CCFBF1",
    # Статус
    "success":       "#15803D",
    "success_soft":  "#DCFCE7",
    "warn":          "#B45309",
    "warn_soft":     "#FEF3C7",
    "danger":        "#B91C1C",
    "danger_soft":   "#FEE2E2",
    "online":        "#15803D",
    "offline":       "#6B7E90",
    # Лог-панель
    "log_bg":        "#0C1524",
    "log_fg":        "#CBD5E1",
    # Хедер
    "header":        "#0C1524",
    "header_fg":     "#F1F5F9",
    "header_sub":    "#7E9BB5",   # Подзаголовок хедера
}

if sys.platform == "darwin":
    _FAMILY = "Helvetica Neue"
    _MONO   = "Menlo"
    FONTS = {
        "brand":  (_FAMILY, 17, "bold"),
        "title":  (_FAMILY, 13, "bold"),
        "body":   (_FAMILY, 12),
        "small":  (_FAMILY, 11),
        "label":  (_FAMILY, 12),
        "mono":   (_MONO,   11),
        "button": (_FAMILY, 12, "bold"),
    }
else:
    _FAMILY = "Segoe UI"
    _MONO   = "Cascadia Mono"
    FONTS = {
        "brand":  ("Segoe UI Semibold", 16),
        "title":  ("Segoe UI Semibold", 11),
        "body":   (_FAMILY, 10),
        "small":  (_FAMILY, 9),
        "label":  (_FAMILY, 10),
        "mono":   (_MONO,   9),
        "button": ("Segoe UI Semibold", 10),
    }


def apply_theme(root: tk.Misc) -> ttk.Style:
    root.configure(bg=COLORS["bg"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    # ── Global defaults ────────────────────────────────────────────────────
    style.configure(".",
        background=COLORS["bg"],
        foreground=COLORS["ink"],
        font=FONTS["body"],
    )

    # ── Frames ─────────────────────────────────────────────────────────────
    style.configure("TFrame",         background=COLORS["bg"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure("Muted.TFrame",   background=COLORS["surface_muted"])
    style.configure("Header.TFrame",  background=COLORS["header"])
    style.configure("Card.TFrame",    background=COLORS["surface"],
                    relief="solid", borderwidth=1)

    # ── Labels ─────────────────────────────────────────────────────────────
    style.configure("TLabel",
        background=COLORS["bg"],
        foreground=COLORS["ink"],
        font=FONTS["body"],
    )
    style.configure("Surface.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        font=FONTS["body"],
    )
    style.configure("Muted.TLabel",
        background=COLORS["bg"],
        foreground=COLORS["ink_muted"],
        font=FONTS["small"],
    )
    style.configure("Subtle.TLabel",
        background=COLORS["bg"],
        foreground=COLORS["ink_subtle"],
        font=FONTS["small"],
    )
    style.configure("SurfaceMuted.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["ink_muted"],
        font=FONTS["small"],
    )
    style.configure("Brand.TLabel",
        background=COLORS["header"],
        foreground=COLORS["header_fg"],
        font=FONTS["brand"],
    )
    style.configure("Header.TLabel",
        background=COLORS["header"],
        foreground=COLORS["header_sub"],
        font=FONTS["body"],
    )
    style.configure("Title.TLabel",
        background=COLORS["bg"],
        foreground=COLORS["ink"],
        font=FONTS["title"],
    )
    style.configure("SurfaceTitle.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        font=FONTS["title"],
    )
    style.configure("StatusOk.TLabel",
        background=COLORS["bg"],
        foreground=COLORS["success"],
        font=FONTS["body"],
    )
    style.configure("StatusWarn.TLabel",
        background=COLORS["bg"],
        foreground=COLORS["warn"],
        font=FONTS["body"],
    )
    style.configure("Danger.TLabel",
        background=COLORS["bg"],
        foreground=COLORS["danger"],
        font=FONTS["body"],
    )
    style.configure("Mono.TLabel",
        background=COLORS["bg"],
        foreground=COLORS["ink_muted"],
        font=FONTS["mono"],
    )

    # ── Buttons ────────────────────────────────────────────────────────────
    style.configure("TButton",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        font=FONTS["button"],
        padding=(10, 6),
        borderwidth=1,
        relief="flat",
    )
    style.map("TButton",
        background=[("active", COLORS["surface_muted"]), ("pressed", COLORS["border"])],
        foreground=[("disabled", COLORS["offline"])],
    )

    style.configure("Accent.TButton",
        background=COLORS["accent"],
        foreground="#FFFFFF",
        font=FONTS["button"],
        padding=(12, 7),
        borderwidth=0,
    )
    style.map("Accent.TButton",
        background=[("active", COLORS["accent_hover"]), ("pressed", COLORS["accent_pressed"])],
        foreground=[("disabled", "#99F6E4")],
    )

    style.configure("Ghost.TButton",
        background=COLORS["bg"],
        foreground=COLORS["ink_muted"],
        font=FONTS["button"],
        padding=(8, 5),
        borderwidth=0,
        relief="flat",
    )
    style.map("Ghost.TButton",
        background=[("active", COLORS["surface_muted"]), ("pressed", COLORS["border"])],
        foreground=[("active", COLORS["ink"])],
    )

    style.configure("Danger.TButton",
        background=COLORS["danger_soft"],
        foreground=COLORS["danger"],
        font=FONTS["button"],
        padding=(10, 6),
        borderwidth=0,
        relief="flat",
    )
    style.map("Danger.TButton",
        background=[("active", "#FECACA"), ("pressed", "#FCA5A5")],
        foreground=[("disabled", COLORS["offline"])],
    )

    # ── Entry ──────────────────────────────────────────────────────────────
    style.configure("TEntry",
        fieldbackground=COLORS["surface"],
        foreground=COLORS["ink"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        padding=(6, 5),
        insertcolor=COLORS["ink"],
        font=FONTS["body"],
    )
    style.map("TEntry",
        bordercolor=[("focus", COLORS["accent"])],
        lightcolor=[("focus", COLORS["accent"])],
    )

    # ── Combobox ───────────────────────────────────────────────────────────
    style.configure("TCombobox",
        fieldbackground=COLORS["surface"],
        foreground=COLORS["ink"],
        selectbackground=COLORS["accent_soft"],
        selectforeground=COLORS["ink"],
        font=FONTS["body"],
        padding=(6, 5),
        bordercolor=COLORS["border"],
    )
    style.map("TCombobox",
        bordercolor=[("focus", COLORS["accent"])],
        fieldbackground=[("readonly", COLORS["surface"])],
    )

    # ── LabelFrame ─────────────────────────────────────────────────────────
    style.configure("TLabelframe",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        bordercolor=COLORS["border"],
        relief="solid",
        borderwidth=1,
    )
    style.configure("TLabelframe.Label",
        background=COLORS["surface"],
        foreground=COLORS["ink_muted"],   # ← was ink (same as title, hard to distinguish)
        font=FONTS["small"],
    )

    # ── Notebook ────────────────────────────────────────────────────────────
    style.configure("TNotebook",
        background=COLORS["bg"],
        borderwidth=0,
    )
    style.configure("TNotebook.Tab",
        background=COLORS["surface_muted"],
        foreground=COLORS["ink_muted"],
        font=FONTS["button"],
        padding=(12, 6),
    )
    style.map("TNotebook.Tab",
        background=[("selected", COLORS["surface"])],
        foreground=[("selected", COLORS["ink"])],
    )

    # ── Treeview ────────────────────────────────────────────────────────────
    style.configure("Treeview",
        background=COLORS["surface"],
        fieldbackground=COLORS["surface"],
        foreground=COLORS["ink"],
        bordercolor=COLORS["border"],
        rowheight=26,
        font=FONTS["body"],
    )
    style.configure("Treeview.Heading",
        background=COLORS["surface_muted"],
        foreground=COLORS["ink_muted"],
        font=FONTS["small"],
        relief="flat",
        padding=(4, 4),
    )
    style.map("Treeview",
        background=[("selected", COLORS["accent_soft"])],
        foreground=[("selected", COLORS["ink"])],
    )
    style.map("Treeview.Heading",
        background=[("active", COLORS["border"])],
        foreground=[("active", COLORS["ink"])],
    )

    # ── Radiobutton / Checkbutton ───────────────────────────────────────────
    style.configure("TRadiobutton",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        font=FONTS["body"],
    )
    style.map("TRadiobutton",
        background=[("active", COLORS["surface_muted"])],
    )

    # ── Scrollbar ──────────────────────────────────────────────────────────
    style.configure("TScrollbar",
        background=COLORS["surface_muted"],
        troughcolor=COLORS["bg"],
        bordercolor=COLORS["bg"],
        arrowcolor=COLORS["ink_muted"],
    )

    # ── Separator / Paned ──────────────────────────────────────────────────
    style.configure("TPanedwindow", background=COLORS["bg"])
    style.configure("TSeparator",   background=COLORS["border"])

    return style


def make_log(parent: tk.Misc, height: int = 12) -> tk.Text:
    box = tk.Text(
        parent,
        height=height,
        wrap="word",
        state="disabled",
        bg=COLORS["log_bg"],
        fg=COLORS["log_fg"],
        insertbackground=COLORS["log_fg"],
        font=FONTS["mono"],
        relief="flat",
        borderwidth=0,
        padx=10,
        pady=8,
        highlightthickness=1,
        highlightbackground=COLORS["border"],
        highlightcolor=COLORS["accent"],
        selectbackground=COLORS["accent"],
        selectforeground="#FFFFFF",
    )
    return box


def append_log(box: tk.Text, message: str) -> None:
    box.configure(state="normal")
    box.insert("end", message + "\n")
    # Обрезаем старые строки — защита от утечки памяти при долгой работе
    line_count = int(box.index("end-1c").split(".")[0])
    if line_count > 500:
        box.delete("1.0", f"{line_count - 500}.0")
    box.see("end")
    box.configure(state="disabled")
