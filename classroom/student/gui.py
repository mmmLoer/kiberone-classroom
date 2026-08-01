"""GUI ученика."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..shared.branding import place_header_logo
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
from ..shared.scrollable import ScrollableFrame
from ..shared.theme import append_log, apply_theme, make_log
from .agent import StudentAgent


class StudentApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — Ученик")
        self.geometry("640x720")
        self.minsize(480, 420)
        self.resizable(True, True)
        apply_theme(self)

        self.agent: StudentAgent | None = None
        self.client_id = get_mac_id()
        self.fresh_saves = app_dir() / "сохры"
        self._pack_vars: dict[str, tk.BooleanVar] = {}

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
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 12))
        header.pack(fill="x")
        self._logo = place_header_logo(header, max_height=42)
        text_box = ttk.Frame(header, style="Header.TFrame")
        text_box.pack(side="left", fill="x", expand=True)
        ttk.Label(text_box, text="KIBERone Classroom", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(text_box, text="Подключение к преподавателю", style="Header.TLabel").pack(anchor="w", pady=(2, 0))

        paned = ttk.Panedwindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=12, pady=12)

        top = ttk.Frame(paned)
        bottom = ttk.Frame(paned)
        paned.add(top, weight=3)
        paned.add(bottom, weight=2)

        scroll = ScrollableFrame(top)
        scroll.pack(fill="both", expand=True)
        root = scroll.inner

        card = ttk.LabelFrame(root, text="Настройки", padding=12)
        card.pack(fill="x", padx=4, pady=(0, 8))

        ttk.Label(card, text="IP преподавателя", style="Surface.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        host_row = ttk.Frame(card, style="Surface.TFrame")
        host_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.host_var = tk.StringVar()
        ttk.Entry(host_row, textvariable=self.host_var).pack(side="left", fill="x", expand=True)
        ttk.Button(host_row, text="Найти в сети", command=self.find_teacher, style="Ghost.TButton").pack(
            side="left", padx=(8, 0)
        )

        ttk.Label(card, text="Номер ПК", style="Surface.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.pc_var = tk.StringVar()
        ttk.Entry(card, textvariable=self.pc_var).grid(row=3, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(card, text="Папка синхронизации", style="Surface.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 4))
        self.folder_var = tk.StringVar()
        ttk.Entry(card, textvariable=self.folder_var).grid(row=5, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(card, text="ID компьютера", style="Surface.TLabel").grid(row=6, column=0, sticky="w", pady=(0, 4))
        ttk.Label(card, text=self.client_id, style="Mono.TLabel").grid(row=7, column=0, sticky="w")
        card.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="Не подключено")
        self.status_label = ttk.Label(root, textvariable=self.status_var, style="StatusWarn.TLabel")
        self.status_label.pack(anchor="w", padx=4, pady=(4, 8))

        actions = ttk.Frame(root)
        actions.pack(fill="x", padx=4)
        ttk.Button(actions, text="Подключиться", command=self.connect, style="Accent.TButton").pack(side="left")
        ttk.Button(actions, text="Синхронизировать", command=self.sync_now).pack(side="left", padx=8)
        ttk.Button(actions, text="Отключиться", command=self.disconnect, style="Ghost.TButton").pack(side="left")

        setup = ttk.LabelFrame(root, text="Начальная настройка", padding=12)
        setup.pack(fill="x", padx=4, pady=(12, 0))
        ttk.Label(
            setup,
            text="После подключения загрузи стартовый пак программ от преподавателя",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        pack_btns = ttk.Frame(setup, style="Surface.TFrame")
        pack_btns.pack(fill="x", pady=(0, 8))
        ttk.Button(pack_btns, text="Обновить список", command=self.refresh_starter_pack).pack(side="left")
        ttk.Button(
            pack_btns,
            text="Скачать и установить выбранное",
            command=self.install_selected_pack,
            style="Accent.TButton",
        ).pack(side="left", padx=8)

        self.pack_frame = ttk.Frame(setup, style="Surface.TFrame")
        self.pack_frame.pack(fill="x")
        self.pack_empty = ttk.Label(
            self.pack_frame,
            text="Список пуст. Подключись к преподавателю и нажми «Обновить список».",
            style="Muted.TLabel",
        )
        self.pack_empty.pack(anchor="w")

        saves = ttk.LabelFrame(root, text="Сохранения", padding=12)
        saves.pack(fill="x", padx=4, pady=(12, 8))
        ttk.Label(saves, text="Выбери, с чего начать урок", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Button(saves, text="Начать с чистых сохранений", command=self.use_fresh).pack(fill="x", pady=3)
        ttk.Button(saves, text="Загрузить с компьютера преподавателя", command=self.use_restore).pack(fill="x", pady=3)

        ttk.Label(bottom, text="Журнал", style="Title.TLabel").pack(anchor="w", pady=(0, 6))
        self.log_box = make_log(bottom, height=8)
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

    def _ensure_agent(self) -> bool:
        if self.agent:
            return True
        self.connect()
        return self.agent is not None

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
            self.agent = None
            return

        self.agent.start()
        self.status_var.set(f"Подключено · {client_label(self.client_id)}")
        self.status_label.configure(style="StatusOk.TLabel")
        self.log("Подключение успешно")
        self.refresh_starter_pack()

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
        if not self._ensure_agent():
            return
        self.agent.apply_fresh_saves()

    def use_restore(self) -> None:
        if not self._ensure_agent():
            return
        self.agent.restore_from_teacher()

    def refresh_starter_pack(self) -> None:
        if not self.agent:
            messagebox.showinfo("Сначала подключись", "Подключись к преподавателю, чтобы увидеть стартовый пак.")
            return

        def worker() -> None:
            try:
                items = self.agent.fetch_starter_pack()
                self.after(0, self._render_starter_pack, items, None)
            except Exception as exc:
                self.after(0, self._render_starter_pack, [], str(exc))

        self.log("Загружаю стартовый пак…")
        threading.Thread(target=worker, daemon=True).start()

    def _render_starter_pack(self, items: list[dict], error: str | None) -> None:
        for child in self.pack_frame.winfo_children():
            child.destroy()
        self._pack_vars.clear()

        if error:
            ttk.Label(self.pack_frame, text=f"Не удалось загрузить: {error}", style="StatusWarn.TLabel").pack(anchor="w")
            return
        if not items:
            ttk.Label(
                self.pack_frame,
                text="Преподаватель пока не отметил программы в стартовом паке.",
                style="Muted.TLabel",
            ).pack(anchor="w")
            return

        for item in items:
            name = item["name"]
            title = item.get("title") or name
            size_mb = item.get("size", 0) / (1024 * 1024)
            var = tk.BooleanVar(value=True)
            self._pack_vars[name] = var
            row = ttk.Frame(self.pack_frame, style="Surface.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Checkbutton(row, text=f"{title}  ({size_mb:.1f} МБ)", variable=var).pack(side="left", anchor="w")
            ttk.Label(row, text=name, style="Mono.TLabel").pack(side="right")

        self.log(f"В стартовом паке программ: {len(items)}")

    def install_selected_pack(self) -> None:
        if not self._ensure_agent():
            return
        selected = [name for name, var in self._pack_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo("Ничего не выбрано", "Отметь хотя бы одну программу или обнови список.")
            return

        def worker() -> None:
            try:
                self.agent.install_starter_pack(names=selected)
            except Exception as exc:
                self.after(0, self.log, f"Ошибка установки пака: {exc}")

        self.log(f"Установка выбранных программ: {len(selected)}")
        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    app = StudentApp()
    app.mainloop()


if __name__ == "__main__":
    main()
