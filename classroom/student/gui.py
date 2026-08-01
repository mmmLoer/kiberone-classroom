"""GUI ученика."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..shared.constants import APP_NAME, DEFAULT_PORT, DEFAULT_TOKEN, app_dir
from ..shared.discovery import discover_teacher
from ..shared.identity import (
    client_label,
    get_mac_id,
    get_pc_number,
    get_teacher_host,
    get_watch_folder,
    set_pc_number,
    set_teacher_host,
    set_watch_folder,
)
from ..shared.theme import COLORS, append_log, apply_theme, make_log
from .agent import StudentAgent


class StudentApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — Ученик")
        self.geometry("560x640")
        self.minsize(520, 580)
        apply_theme(self)

        self.agent: StudentAgent | None = None
        self.client_id = get_mac_id()
        self.fresh_saves = app_dir() / "сохры"

        self._build()
        self._load_fields()
        self.after(500, self.find_teacher)

    def find_teacher(self) -> None:
        self.log("Ищу преподавателя в сети…")
        self.status_var.set("Поиск преподавателя…")
        self.status_label.configure(style="StatusWarn.TLabel")

        def worker() -> None:
            host = discover_teacher(timeout=3.5, token=DEFAULT_TOKEN)
            self.after(0, self._on_teacher_found, host)

        threading.Thread(target=worker, daemon=True).start()

    def _on_teacher_found(self, host: str | None) -> None:
        if host:
            self.host_var.set(host)
            set_teacher_host(host)
            self.log(f"Найден преподаватель: {host}")
            self.status_var.set(f"Найден: {host}")
            self.status_label.configure(style="StatusOk.TLabel")
        else:
            self.log("Преподаватель не найден. Запусти Teacher на хосте.")
            self.status_var.set("Преподаватель не найден")
            self.status_label.configure(style="StatusWarn.TLabel")

    def _build(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 14))
        header.pack(fill="x")
        ttk.Label(header, text="KIBERone Classroom", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(header, text="Подключение к преподавателю", style="Header.TLabel").pack(anchor="w", pady=(2, 0))

        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        card = ttk.LabelFrame(root, text="Настройки", padding=14)
        card.pack(fill="x")

        ttk.Label(card, text="IP преподавателя", style="Surface.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        host_row = ttk.Frame(card, style="Surface.TFrame")
        host_row.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.host_var = tk.StringVar()
        ttk.Entry(host_row, textvariable=self.host_var).pack(side="left", fill="x", expand=True)
        ttk.Button(host_row, text="Найти в сети", command=self.find_teacher, style="Ghost.TButton").pack(side="left", padx=(8, 0))

        ttk.Label(card, text="Номер ПК", style="Surface.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.pc_var = tk.StringVar()
        ttk.Entry(card, textvariable=self.pc_var).grid(row=3, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(card, text="Папка синхронизации", style="Surface.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 4))
        self.folder_var = tk.StringVar()
        ttk.Entry(card, textvariable=self.folder_var).grid(row=5, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(card, text="ID компьютера", style="Surface.TLabel").grid(row=6, column=0, sticky="w", pady=(0, 4))
        ttk.Label(card, text=self.client_id, style="Mono.TLabel").grid(row=7, column=0, sticky="w")
        card.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="Не подключено")
        self.status_label = ttk.Label(root, textvariable=self.status_var, style="StatusWarn.TLabel")
        self.status_label.pack(anchor="w", pady=(12, 8))

        actions = ttk.Frame(root)
        actions.pack(fill="x")
        ttk.Button(actions, text="Подключиться", command=self.connect, style="Accent.TButton").pack(side="left")
        ttk.Button(actions, text="Синхронизировать", command=self.sync_now).pack(side="left", padx=8)
        ttk.Button(actions, text="Отключиться", command=self.disconnect, style="Ghost.TButton").pack(side="left")

        saves = ttk.LabelFrame(root, text="Сохранения", padding=12)
        saves.pack(fill="x", pady=(14, 0))
        ttk.Label(saves, text="Выбери, с чего начать урок", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Button(saves, text="Начать с чистых сохранений", command=self.use_fresh).pack(fill="x", pady=3)
        ttk.Button(saves, text="Загрузить с компьютера преподавателя", command=self.use_restore).pack(fill="x", pady=3)

        ttk.Label(root, text="Журнал", style="Title.TLabel").pack(anchor="w", pady=(14, 6))
        self.log_box = make_log(root, height=11)
        self.log_box.pack(fill="both", expand=True)

    def _load_fields(self) -> None:
        self.host_var.set(get_teacher_host(""))
        self.pc_var.set(get_pc_number("1"))
        self.folder_var.set(get_watch_folder(str(Path.home() / "Desktop")))

    def log(self, message: str) -> None:
        append_log(self.log_box, message)

    def _save_fields(self) -> None:
        set_teacher_host(self.host_var.get().strip())
        set_pc_number(self.pc_var.get().strip())
        set_watch_folder(self.folder_var.get().strip())

    def connect(self) -> None:
        self._save_fields()
        host = self.host_var.get().strip()
        if not host:
            self.log("IP не указан — ищу преподавателя…")
            self.status_var.set("Поиск преподавателя…")
            self.status_label.configure(style="StatusWarn.TLabel")
            self.update_idletasks()
            host = discover_teacher(timeout=4.0, token=DEFAULT_TOKEN)
            if not host:
                messagebox.showerror(
                    "Преподаватель не найден",
                    "Запусти KIBERoneTeacher на хосте и проверь, что этот ПК в той же сети.",
                )
                self.status_var.set("Преподаватель не найден")
                self.status_label.configure(style="StatusWarn.TLabel")
                return
            self.host_var.set(host)
            set_teacher_host(host)
            self.log(f"Найден преподаватель: {host}")

        if self.agent:
            self.agent.stop()

        self.agent = StudentAgent(
            teacher_host=host,
            port=DEFAULT_PORT,
            token=DEFAULT_TOKEN,
            watch_folder=self.folder_var.get().strip(),
            fresh_saves_dir=self.fresh_saves if self.fresh_saves.exists() else None,
            on_log=lambda msg: self.after(0, self.log, msg),
        )

        if not self.agent.ping():
            messagebox.showerror(
                "Нет связи",
                "Не удалось связаться с преподавателем.\nПроверь IP и что сервер запущен.",
            )
            return

        self.agent.start()
        self.status_var.set(f"Подключено · {client_label(self.client_id)}")
        self.status_label.configure(style="StatusOk.TLabel")
        self.log("Подключение успешно")

    def disconnect(self) -> None:
        if self.agent:
            self.agent.stop()
            self.agent = None
        self.status_var.set("Не подключено")
        self.status_label.configure(style="StatusWarn.TLabel")
        self.log("Отключено")

    def sync_now(self) -> None:
        if not self.agent:
            messagebox.showinfo("Сначала подключись", "Нажми «Подключиться», затем синхронизируй.")
            return
        self.agent.sync_once()

    def use_fresh(self) -> None:
        if not self.agent:
            self.connect()
        if self.agent:
            self.agent.apply_fresh_saves()

    def use_restore(self) -> None:
        if not self.agent:
            self.connect()
        if self.agent:
            self.agent.restore_from_teacher()


def main() -> None:
    app = StudentApp()
    app.mainloop()


if __name__ == "__main__":
    main()
