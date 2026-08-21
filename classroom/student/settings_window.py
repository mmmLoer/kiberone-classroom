"""Окно настроек ученика."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..shared.theme import apply_theme

class StudentSettings(tk.Toplevel):
    def __init__(self, master_app):
        super().__init__(master_app)
        self.master_app = master_app
        self.title("Настройки")
        self.geometry("480x360")
        self.minsize(400, 300)
        self.resizable(True, True)
        apply_theme(self)

        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Настройки соединения и папок", style="Title.TLabel").pack(anchor="w", pady=(0, 16))

        # IP тьютора
        ttk.Label(body, text="IP тьютора").pack(anchor="w", pady=(0, 4))
        host_row = ttk.Frame(body)
        host_row.pack(fill="x", pady=(0, 12))
        ttk.Entry(host_row, textvariable=self.master_app.host_var).pack(side="left", fill="x", expand=True)
        ttk.Button(
            host_row,
            text="Найти в сети",
            command=self.master_app.find_teacher,
            style="Ghost.TButton"
        ).pack(side="left", padx=(8, 0))

        # Номер ПК
        ttk.Label(body, text="Номер ПК").pack(anchor="w", pady=(0, 4))
        ttk.Entry(body, textvariable=self.master_app.pc_var).pack(fill="x", pady=(0, 12))

        # Папка синхронизации
        ttk.Label(body, text="Папка синхронизации").pack(anchor="w", pady=(0, 4))
        ttk.Entry(body, textvariable=self.master_app.folder_var).pack(fill="x", pady=(0, 12))

        # ID компьютера
        ttk.Label(body, text="ID компьютера").pack(anchor="w", pady=(0, 4))
        ttk.Label(body, text=self.master_app.client_id, style="Mono.TLabel").pack(anchor="w", pady=(0, 12))

        # Кнопка закрытия
        bottom = ttk.Frame(self, padding=(12, 12))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Закрыть", command=self.destroy).pack(side="right")
