"""GUI ученика."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..shared.branding import place_header_logo
from ..shared.constants import APP_NAME, APP_VERSION, DEFAULT_PORT, DEFAULT_TOKEN, app_dir
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
from ..shared.scripts import get_preset, load_scripts
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
        self._script_map: dict[str, dict] = {}
        self._update_prompt_open = False

        self._build()
        self._load_fields()
        self.refresh_script_combo()
        self.after(500, self.find_teacher)

    def find_teacher(self) -> None:
        self.log("Ищу тьютора в сети…")
        self.status_var.set("Поиск тьютора…")
        self.status_label.configure(style="StatusWarn.TLabel")
        hint = self.host_var.get().strip() or get_teacher_host("")

        def worker() -> None:
            host = discover_teacher(timeout=5.0, token=DEFAULT_TOKEN, hint_host=hint or None)
            self.after(0, self._on_teacher_found, host)

        threading.Thread(target=worker, daemon=True).start()

    def _on_teacher_found(self, host: str | None) -> None:
        if host:
            self.host_var.set(host)
            set_teacher_host(host)
            self.log(f"Найден тьютор: {host}")
            self.status_var.set(f"Найден: {host}")
            self.status_label.configure(style="StatusOk.TLabel")
        else:
            self.log("Тьютор не найден. Запусти KIBERoneTutor на хосте.")
            self.status_var.set("Тьютор не найден")
            self.status_label.configure(style="StatusWarn.TLabel")

    def _build(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 12))
        header.pack(fill="x")
        self._logo = place_header_logo(header, max_height=42)
        text_box = ttk.Frame(header, style="Header.TFrame")
        text_box.pack(side="left", fill="x", expand=True)
        ttk.Label(text_box, text="KIBERone Classroom", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(
            text_box,
            text=f"Подключение к тьютору · v{APP_VERSION}",
            style="Header.TLabel",
        ).pack(anchor="w", pady=(2, 0))

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

        ttk.Label(card, text="IP тьютора", style="Surface.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
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
        ttk.Button(actions, text="Проверить обновления", command=self.check_updates).pack(side="left")
        ttk.Button(actions, text="Отключиться", command=self.disconnect, style="Ghost.TButton").pack(side="left", padx=8)

        scripts = ttk.LabelFrame(root, text="Скрипт запуска", padding=12)
        scripts.pack(fill="x", padx=4, pady=(12, 0))
        ttk.Label(
            scripts,
            text="ШБ — Wi‑Fi и отключение прокси. Можно выбрать пресет тьютора.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        script_row = ttk.Frame(scripts, style="Surface.TFrame")
        script_row.pack(fill="x")
        self.script_var = tk.StringVar()
        self.script_combo = ttk.Combobox(script_row, textvariable=self.script_var, state="readonly")
        self.script_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(script_row, text="Запустить", command=self.run_selected_script, style="Accent.TButton").pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(script_row, text="Обновить", command=self.refresh_script_combo, style="Ghost.TButton").pack(
            side="left", padx=(6, 0)
        )

        setup = ttk.LabelFrame(root, text="Начальная настройка", padding=12)
        setup.pack(fill="x", padx=4, pady=(12, 0))
        ttk.Label(
            setup,
            text="После подключения загрузи стартовый пак программ от тьютора",
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
            text="Список пуст. Подключись к тьютору и нажми «Обновить список».",
            style="Muted.TLabel",
        )
        self.pack_empty.pack(anchor="w")

        saves = ttk.LabelFrame(root, text="Сохранения", padding=12)
        saves.pack(fill="x", padx=4, pady=(12, 8))
        ttk.Label(saves, text="Выбери, с чего начать урок", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Button(saves, text="Начать с чистых сохранений", command=self.use_fresh).pack(fill="x", pady=3)
        ttk.Button(saves, text="Загрузить с компьютера тьютора", command=self.use_restore).pack(fill="x", pady=3)

        ttk.Label(bottom, text="Журнал", style="Title.TLabel").pack(anchor="w", pady=(0, 6))
        self.log_box = make_log(bottom, height=8)
        self.log_box.pack(fill="both", expand=True)

    def _load_fields(self) -> None:
        self.host_var.set(get_teacher_host(""))
        self.pc_var.set(get_pc_number("1"))
        self.folder_var.set(get_watch_folder(str(Path.home() / "Desktop")))

    def log(self, message: str) -> None:
        append_log(self.log_box, message)

    def show_teacher_message(self, text: str) -> None:
        """Отдельное окно с жирным текстом от тьютора."""
        win = tk.Toplevel(self)
        win.title("Сообщение от тьютора")
        win.configure(bg="#0F172A")
        win.attributes("-topmost", True)
        win.geometry("560x280")
        win.minsize(420, 200)
        win.resizable(True, True)

        # по центру относительно главного окна
        try:
            self.update_idletasks()
            x = self.winfo_rootx() + max(20, (self.winfo_width() - 560) // 2)
            y = self.winfo_rooty() + max(20, (self.winfo_height() - 280) // 2)
            win.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

        header = tk.Label(
            win,
            text="Сообщение от тьютора",
            fg="#94A3B8",
            bg="#0F172A",
            font=("Segoe UI", 11),
            anchor="w",
        )
        header.pack(anchor="w", padx=24, pady=(20, 8))

        body = tk.Label(
            win,
            text=text,
            fg="#F8FAFC",
            bg="#0F172A",
            font=("Segoe UI Semibold", 22, "bold"),
            wraplength=500,
            justify="left",
            anchor="nw",
        )
        body.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        btn = ttk.Button(win, text="Понятно", command=win.destroy, style="Accent.TButton")
        btn.pack(pady=(0, 20))
        win.bind("<Return>", lambda _e: win.destroy())
        win.bind("<Escape>", lambda _e: win.destroy())
        try:
            win.focus_force()
            win.bell()
        except tk.TclError:
            pass

    def _on_pc_number_changed(self, number: str) -> None:
        self.pc_var.set(number)
        self.title(f"{APP_NAME} — Ученик · ПК {number}")
        self.log(f"Тьютор сменил номер ПК: {number}")

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
            self.log("IP не указан — ищу тьютора…")
            self.status_var.set("Поиск тьютора…")
            self.status_label.configure(style="StatusWarn.TLabel")
            self.update_idletasks()
            host = discover_teacher(
                timeout=5.0,
                token=DEFAULT_TOKEN,
                hint_host=get_teacher_host("") or None,
            )
            if not host:
                messagebox.showerror(
                    "Тьютор не найден",
                    "Запусти KIBERoneTutor на хосте и проверь, что этот ПК в той же сети.",
                )
                self.status_var.set("Тьютор не найден")
                self.status_label.configure(style="StatusWarn.TLabel")
                return
            self.host_var.set(host)
            set_teacher_host(host)
            self.log(f"Найден тьютор: {host}")

        if self.agent:
            self.agent.stop()

        self.agent = StudentAgent(
            teacher_host=host,
            port=DEFAULT_PORT,
            token=DEFAULT_TOKEN,
            watch_folder=self.folder_var.get().strip(),
            fresh_saves_dir=self.fresh_saves if self.fresh_saves.exists() else None,
            on_log=lambda msg: self.after(0, self.log, msg),
            on_message=lambda text: self.after(0, self.show_teacher_message, text),
            on_pc_number_changed=lambda number: self.after(0, self._on_pc_number_changed, number),
            on_update_available=lambda info: self.after(0, self.prompt_update, info),
        )

        if not self.agent.ping():
            messagebox.showerror(
                "Нет связи",
                "Не удалось связаться с тьютором.\nПроверь IP и что сервер запущен.",
            )
            self.agent = None
            return

        self.agent.start()
        self.status_var.set(f"Подключено · {client_label(self.client_id)}")
        self.status_label.configure(style="StatusOk.TLabel")
        self.log("Подключение успешно")
        self.refresh_starter_pack()
        self.refresh_script_combo()

    def refresh_script_combo(self) -> None:
        presets: list[dict] = []
        if self.agent:
            try:
                data = self.agent.fetch_scripts()
                presets = list(data.get("presets") or [])
                selected_id = data.get("selected")
            except Exception:
                presets = []
                selected_id = None
        else:
            data = load_scripts()
            presets = data.get("presets") or []
            selected_id = data.get("selected")

        if not presets:
            local = get_preset("shb")
            presets = [local] if local else []
            selected_id = "shb"

        names = []
        self._script_map = {}
        for preset in presets:
            name = preset.get("name") or preset.get("id")
            names.append(name)
            self._script_map[name] = preset
        self.script_combo["values"] = names
        preferred = None
        for preset in presets:
            if preset.get("id") == selected_id:
                preferred = preset.get("name")
                break
        if preferred:
            self.script_var.set(preferred)
        elif names:
            self.script_var.set(names[0])

    def check_updates(self) -> None:
        if not self._ensure_agent():
            return

        def worker() -> None:
            try:
                info = self.agent.check_for_update() if self.agent else None
            except Exception as exc:
                self.after(0, self.log, f"Проверка обновлений: {exc}")
                self.after(
                    0,
                    lambda: messagebox.showerror("Обновление", f"Не удалось проверить:\n{exc}"),
                )
                return
            if info:
                self.after(0, self.prompt_update, info)
            else:
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Обновлений нет",
                        f"У тебя актуальная версия: {APP_VERSION}",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def prompt_update(self, info: dict) -> None:
        if self._update_prompt_open:
            return
        remote = str(info.get("version") or "?")
        size = int(info.get("size") or 0)
        size_mb = size / (1024 * 1024) if size else 0
        self._update_prompt_open = True
        try:
            ok = messagebox.askyesno(
                "Доступно обновление",
                f"Тьютор предлагает новую версию программы ученика.\n\n"
                f"Сейчас: {APP_VERSION}\n"
                f"Новая: {remote}"
                + (f" ({size_mb:.1f} МБ)" if size_mb else "")
                + "\n\nСкачать и установить? Программа перезапустится.",
            )
        finally:
            self._update_prompt_open = False
        if not ok:
            self.log(f"Обновление {remote} отложено")
            return
        self._start_update_download(info)

    def _start_update_download(self, info: dict) -> None:
        if not self.agent:
            return
        self.log("Скачиваю обновление…")
        self.status_var.set("Скачивание обновления…")

        def worker() -> None:
            try:
                path = self.agent.download_student_update(str(info.get("sha256") or ""))
                self.after(0, self._finish_update_install, path, info)
            except Exception as exc:
                self.after(0, self.log, f"Ошибка обновления: {exc}")
                self.after(
                    0,
                    lambda: messagebox.showerror("Обновление", f"Не удалось скачать:\n{exc}"),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_install(self, path: Path, info: dict) -> None:
        import sys

        remote = str(info.get("version") or "")
        if not getattr(sys, "frozen", False):
            messagebox.showinfo(
                "Обновление",
                f"Файл скачан:\n{path}\n\n"
                f"Сейчас запущена Python-версия. Положи новый EXE вместо старого вручную "
                f"(v{remote}).",
            )
            self.log(f"Обновление скачано: {path}")
            return
        try:
            if self.agent:
                self.agent.apply_downloaded_update(path)
            messagebox.showinfo(
                "Обновление",
                "Файл готов. Сейчас программа закроется и откроется уже новая версия.",
            )
            self.log(f"Устанавливаю обновление {remote}…")
            if self.agent:
                self.agent.stop()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Обновление", f"Не удалось установить:\n{exc}")
            self.log(f"Ошибка установки: {exc}")

    def run_selected_script(self) -> None:
        name = self.script_var.get()
        preset = self._script_map.get(name)
        if not preset:
            messagebox.showinfo("Нет скрипта", "Выбери скрипт из списка.")
            return
        content = str(preset.get("content") or "")
        kind = str(preset.get("kind") or "bat")
        if self.agent:
            self.agent.run_script_local(name, content, kind)
        else:
            # локальный запуск без сервера
            from ..shared.scripts import script_extension
            import os
            import subprocess

            temp = Path(os.environ.get("TEMP", ".")) / "classroom_scripts"
            temp.mkdir(parents=True, exist_ok=True)
            safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:40]
            path = temp / f"{safe}{script_extension(kind)}"
            path.write_text(content, encoding="utf-8", errors="replace")
            self.log(f"Запускаю скрипт: {name}")
            if kind == "ps1":
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)],
                    shell=False,
                )
            else:
                subprocess.Popen(["cmd", "/c", str(path)], shell=False)

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
            messagebox.showinfo("Сначала подключись", "Подключись к тьютору, чтобы увидеть стартовый пак.")
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
                text="Тьютор пока не отметил программы в стартовом паке.",
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
