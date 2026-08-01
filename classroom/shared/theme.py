"""Тема интерфейса KIBERone Classroom (tkinter)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# Светлая прохладная палитра: slate + teal (без purple / cream / terracotta)
COLORS = {
    "bg": "#EEF2F6",
    "surface": "#FFFFFF",
    "surface_muted": "#E8EEF4",
    "ink": "#152033",
    "ink_muted": "#5B6B7C",
    "border": "#C9D3DE",
    "accent": "#0F766E",
    "accent_hover": "#0D9488",
    "accent_soft": "#CCFBF1",
    "success": "#166534",
    "success_soft": "#DCFCE7",
    "warn": "#9A3412",
    "warn_soft": "#FFEDD5",
    "danger": "#991B1B",
    "online": "#15803D",
    "offline": "#94A3B8",
    "log_bg": "#0F172A",
    "log_fg": "#E2E8F0",
    "header": "#0F172A",
    "header_fg": "#F8FAFC",
}

FONTS = {
    "brand": ("Segoe UI Semibold", 18),
    "title": ("Segoe UI Semibold", 14),
    "body": ("Segoe UI", 10),
    "label": ("Segoe UI", 10),
    "mono": ("Cascadia Mono", 9),
    "button": ("Segoe UI Semibold", 10),
}


def apply_theme(root: tk.Misc) -> ttk.Style:
    root.configure(bg=COLORS["bg"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=COLORS["bg"], foreground=COLORS["ink"], font=FONTS["body"])
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure("Muted.TFrame", background=COLORS["surface_muted"])
    style.configure("Header.TFrame", background=COLORS["header"])

    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["ink"], font=FONTS["body"])
    style.configure("Surface.TLabel", background=COLORS["surface"], foreground=COLORS["ink"])
    style.configure("Muted.TLabel", background=COLORS["bg"], foreground=COLORS["ink_muted"], font=FONTS["label"])
    style.configure("Brand.TLabel", background=COLORS["header"], foreground=COLORS["header_fg"], font=FONTS["brand"])
    style.configure("Header.TLabel", background=COLORS["header"], foreground="#94A3B8", font=FONTS["body"])
    style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["ink"], font=FONTS["title"])
    style.configure("StatusOk.TLabel", background=COLORS["bg"], foreground=COLORS["success"], font=FONTS["body"])
    style.configure("StatusWarn.TLabel", background=COLORS["bg"], foreground=COLORS["warn"], font=FONTS["body"])
    style.configure("Mono.TLabel", background=COLORS["bg"], foreground=COLORS["ink_muted"], font=FONTS["mono"])

    style.configure(
        "TButton",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        font=FONTS["button"],
        padding=(12, 8),
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", COLORS["surface_muted"]), ("pressed", COLORS["border"])],
        foreground=[("disabled", COLORS["offline"])],
    )

    style.configure(
        "Accent.TButton",
        background=COLORS["accent"],
        foreground="#FFFFFF",
        font=FONTS["button"],
        padding=(14, 9),
        borderwidth=0,
    )
    style.map(
        "Accent.TButton",
        background=[("active", COLORS["accent_hover"]), ("pressed", "#115E59")],
        foreground=[("disabled", "#99F6E4")],
    )

    style.configure(
        "Ghost.TButton",
        background=COLORS["bg"],
        foreground=COLORS["ink_muted"],
        font=FONTS["button"],
        padding=(10, 7),
    )

    style.configure(
        "TEntry",
        fieldbackground=COLORS["surface"],
        foreground=COLORS["ink"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["accent"],
        darkcolor=COLORS["border"],
        padding=6,
        insertcolor=COLORS["ink"],
    )
    style.map("TEntry", bordercolor=[("focus", COLORS["accent"])])

    style.configure(
        "TLabelframe",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        bordercolor=COLORS["border"],
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "TLabelframe.Label",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        font=FONTS["title"],
    )

    style.configure(
        "Treeview",
        background=COLORS["surface"],
        fieldbackground=COLORS["surface"],
        foreground=COLORS["ink"],
        bordercolor=COLORS["border"],
        rowheight=28,
        font=FONTS["body"],
    )
    style.configure(
        "Treeview.Heading",
        background=COLORS["surface_muted"],
        foreground=COLORS["ink_muted"],
        font=FONTS["button"],
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", COLORS["accent_soft"])],
        foreground=[("selected", COLORS["ink"])],
    )

    style.configure("TPanedwindow", background=COLORS["bg"])
    style.configure("TSeparator", background=COLORS["border"])
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
    )
    return box


def append_log(box: tk.Text, message: str) -> None:
    box.configure(state="normal")
    box.insert("end", message + "\n")
    box.see("end")
    box.configure(state="disabled")
