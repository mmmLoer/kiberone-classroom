"""Окно настроек тьютора."""

from __future__ import annotations

import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..shared.constants import APP_VERSION, app_dir
from ..shared.scripts import (
    add_preset_from_file,
    get_preset,
    load_scripts,
    remove_preset,
    set_selected,
)
from ..shared.settings import DEFAULT_SYNC_SECONDS, clamp_sync_seconds
from ..shared.starter_pack import (
    deploy_dir,
    list_deploy_installers,
    load_starter_selection,
    save_starter_selection,
)
from ..shared.theme import apply_theme
from ..shared.updates import get_update_info, publish_student_exe, updates_dir


class SettingsWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("Настройки")
        self.geometry("720x640")
        self.minsize(560, 480)
        self.resizable(True, True)
        apply_theme(self)

        self._pack_vars: dict[str, tk.BooleanVar] = {}
        self._script_ids: list[str] = []

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        sync_tab = ttk.Frame(notebook, padding=12)
        scripts_tab = ttk.Frame(notebook, padding=12)
        updates_tab = ttk.Frame(notebook, padding=12)
        pack_tab = ttk.Frame(notebook, padding=12)
        advanced_tab = ttk.Frame(notebook, padding=12)
        notebook.add(sync_tab, text="Синхронизация")
        notebook.add(updates_tab, text="Обновления")
        notebook.add(scripts_tab, text="Скрипты")
        notebook.add(pack_tab, text="Стартовый пак")
        notebook.add(advanced_tab, text="Дополнительно")

        self._build_sync(sync_tab)
        self._build_updates(updates_tab)
        self._build_scripts(scripts_tab)
        self._build_pack(pack_tab)
        self._build_advanced(advanced_tab)

        bottom = ttk.Frame(self, padding=(12, 0, 12, 12))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Закрыть", command=self.destroy).pack(side="right")

    def _build_sync(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Опрос сохранений", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            parent,
            text="Как часто ученики отправляют файлы на компьютер тьютора. По умолчанию — раз в 5 минут.",
            style="Muted.TLabel",
            wraplength=640,
        ).pack(anchor="w", pady=(4, 12))

        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Label(row, text="Интервал (секунды)").pack(side="left")
        current = self.master_app.server.store.get_settings().get("sync_seconds", DEFAULT_SYNC_SECONDS)
        self.sync_var = tk.StringVar(value=str(current))
        ttk.Entry(row, textvariable=self.sync_var, width=10).pack(side="left", padx=8)
        ttk.Label(row, text="(от 30 до 3600)", style="Muted.TLabel").pack(side="left")

        presets = ttk.Frame(parent)
        presets.pack(fill="x", pady=(12, 0))
        for label, seconds in [("1 мин", 60), ("5 мин", 300), ("10 мин", 600), ("15 мин", 900)]:
            ttk.Button(
                presets,
                text=label,
                command=lambda s=seconds: self.sync_var.set(str(s)),
                style="Ghost.TButton",
            ).pack(side="left", padx=(0, 6))

        ttk.Button(parent, text="Сохранить и разослать ученикам", command=self.save_sync, style="Accent.TButton").pack(
            anchor="w", pady=(16, 0)
        )

    def save_sync(self) -> None:
        seconds = clamp_sync_seconds(self.sync_var.get())
        self.sync_var.set(str(seconds))
        updated = self.master_app.server.store.update_settings({"sync_seconds": seconds})
        online = [c["client_id"] for c in self.master_app.clients if c.get("status") == "online"]
        if online:
            self.master_app.server.store.enqueue(online, "configure", {"sync_seconds": seconds})
        self.master_app.log(f"Интервал синхронизации: {seconds} с → {len(online)} ПК")
        self.master_app.refresh_script_combo()
        messagebox.showinfo(
            "Сохранено",
            f"Ученики будут слать сохранения раз в {updated['sync_seconds']} с.\n"
            f"Команда отправлена online-ПК: {len(online)}",
            parent=self,
        )

    def _build_updates(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Обновление программы ученика", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            parent,
            text="Опубликуй KIBERoneStudent.exe — ученики увидят предложение обновиться, "
            "если их версия старше.",
            style="Muted.TLabel",
            wraplength=640,
        ).pack(anchor="w", pady=(4, 12))

        self.update_status_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.update_status_var, style="Surface.TLabel").pack(anchor="w")
        ttk.Label(parent, text=str(updates_dir()), style="Mono.TLabel").pack(anchor="w", pady=(4, 12))

        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Версия пакета").pack(side="left")
        self.update_version_var = tk.StringVar(value=APP_VERSION)
        ttk.Entry(row, textvariable=self.update_version_var, width=12).pack(side="left", padx=8)

        btns = ttk.Frame(parent)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Взять из dist…", command=self.publish_from_dist).pack(side="left")
        ttk.Button(btns, text="Выбрать EXE…", command=self.publish_browse).pack(side="left", padx=8)
        ttk.Button(
            btns,
            text="Предложить обновление ученикам",
            command=self.offer_update_now,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(btns, text="Открыть папку updates", command=self.open_updates_folder, style="Ghost.TButton").pack(
            side="left", padx=8
        )
        self.refresh_update_status()

    def refresh_update_status(self) -> None:
        info = get_update_info()
        if not info:
            self.update_status_var.set("Пакет не опубликован.")
            self.update_version_var.set(APP_VERSION)
            return
        size_mb = int(info.get("size") or 0) / (1024 * 1024)
        self.update_status_var.set(
            f"Опубликовано: v{info.get('version')} · {size_mb:.1f} МБ · {info.get('published_at') or '—'}"
        )
        self.update_version_var.set(str(info.get("version") or APP_VERSION))

    def publish_from_dist(self) -> None:
        candidates = [
            app_dir() / "dist" / "KIBERoneStudent.exe",
            app_dir() / "KIBERoneStudent.exe",
        ]
        src = next((p for p in candidates if p.is_file()), None)
        if not src:
            messagebox.showinfo(
                "Нет файла",
                "Не найден dist\\KIBERoneStudent.exe. Сначала собери Student или выбери EXE вручную.",
                parent=self,
            )
            return
        self._publish(src)

    def publish_browse(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="EXE ученика",
            filetypes=[("EXE", "*.exe"), ("All", "*.*")],
        )
        if path:
            self._publish(Path(path))

    def _publish(self, source: Path) -> None:
        version = self.update_version_var.get().strip() or APP_VERSION
        try:
            info = publish_student_exe(source, version=version)
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.master_app.log(f"Опубликовано обновление ученика: v{info.get('version')}")
        self.refresh_update_status()
        messagebox.showinfo(
            "Опубликовано",
            f"Версия {info.get('version')} готова к раздаче.\n"
            f"Можно нажать «Предложить обновление ученикам».",
            parent=self,
        )

    def offer_update_now(self) -> None:
        info = get_update_info()
        if not info:
            messagebox.showinfo("Нет пакета", "Сначала опубликуй EXE ученика.", parent=self)
            return
        self.master_app._send_command("offer_update", info)
        self.master_app.log(f"Предложение обновиться → v{info.get('version')}")

    def open_updates_folder(self) -> None:
        folder = updates_dir()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def _build_scripts(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Пресеты скриптов запуска", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            parent,
            text="ШБ — подключение к Wi‑Fi и отключение прокси. Можно добавить свои .bat / .cmd / .ps1.",
            style="Muted.TLabel",
            wraplength=640,
        ).pack(anchor="w", pady=(4, 12))

        self.scripts_list = ttk.Treeview(parent, columns=("name", "kind"), show="headings", height=10)
        self.scripts_list.heading("name", text="Название")
        self.scripts_list.heading("kind", text="Тип")
        self.scripts_list.column("name", width=360, stretch=True)
        self.scripts_list.column("kind", width=80)
        self.scripts_list.pack(fill="both", expand=True)

        btns = ttk.Frame(parent)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Добавить файл…", command=self.add_script).pack(side="left")
        ttk.Button(btns, text="Сделать выбранным", command=self.select_script).pack(side="left", padx=6)
        ttk.Button(btns, text="Удалить", command=self.delete_script).pack(side="left")
        ttk.Button(btns, text="Запустить у себя", command=self.run_script_local, style="Accent.TButton").pack(
            side="right"
        )
        self.reload_scripts()

    def reload_scripts(self) -> None:
        for item in self.scripts_list.get_children():
            self.scripts_list.delete(item)
        data = load_scripts()
        selected = data.get("selected")
        for preset in data["presets"]:
            mark = " ★" if preset["id"] == selected else ""
            self.scripts_list.insert(
                "",
                "end",
                iid=preset["id"],
                values=(f"{preset['name']}{mark}", preset["kind"]),
            )
        self.master_app.refresh_script_combo()

    def add_script(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Добавить скрипт",
            filetypes=[("Scripts", "*.bat;*.cmd;*.ps1"), ("All", "*.*")],
        )
        if not path:
            return
        name = simpledialog.askstring("Название", "Имя пресета:", initialvalue=Path(path).stem, parent=self)
        add_preset_from_file(Path(path), name=name)
        self.reload_scripts()
        self.master_app.log(f"Добавлен скрипт: {name or Path(path).stem}")

    def select_script(self) -> None:
        ids = self.scripts_list.selection()
        if not ids:
            messagebox.showinfo("Выбери скрипт", "Сначала выбери пресет в списке.", parent=self)
            return
        set_selected(ids[0])
        self.reload_scripts()

    def delete_script(self) -> None:
        ids = self.scripts_list.selection()
        if not ids:
            return
        if ids[0] == "shb":
            messagebox.showinfo("Нельзя удалить", "Пресет «ШБ» встроенный.", parent=self)
            return
        if messagebox.askyesno("Удалить?", "Удалить выбранный пресет?", parent=self):
            remove_preset(ids[0])
            self.reload_scripts()

    def run_script_local(self) -> None:
        ids = self.scripts_list.selection()
        preset = get_preset(ids[0] if ids else None)
        if not preset:
            messagebox.showinfo("Нет скрипта", "Нет доступных пресетов.", parent=self)
            return
        self.master_app.run_script_on_teacher(preset)

    def _build_pack(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Стартовый пак", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            parent,
            text="Отметь установщики и папки из deploy. Установщики запускаются у ученика, "
            "папки распаковываются на его рабочий стол.",
            style="Muted.TLabel",
            wraplength=640,
        ).pack(anchor="w", pady=(4, 8))
        ttk.Label(parent, text=str(deploy_dir()), style="Mono.TLabel").pack(anchor="w", pady=(0, 8))

        pack_btns = ttk.Frame(parent)
        pack_btns.pack(fill="x", pady=(0, 8))
        ttk.Button(pack_btns, text="Обновить список", command=self.refresh_pack).pack(side="left")
        ttk.Button(pack_btns, text="Сохранить выбор", command=self.save_pack, style="Accent.TButton").pack(
            side="left", padx=8
        )
        ttk.Button(pack_btns, text="Отправить пак ученикам", command=self.push_pack).pack(side="left")
        ttk.Button(pack_btns, text="Открыть deploy", command=self.open_deploy, style="Ghost.TButton").pack(
            side="left", padx=8
        )

        self.pack_list = ttk.Frame(parent)
        self.pack_list.pack(fill="both", expand=True)

        files_box = ttk.LabelFrame(parent, text="Добавить в deploy", padding=12)
        files_box.pack(fill="x", pady=(12, 0))
        ttk.Label(
            files_box,
            text="Можно .exe / .msi / .bat или целую папку с файлами.",
            style="Muted.TLabel",
        ).pack(anchor="w")
        add_btns = ttk.Frame(files_box)
        add_btns.pack(anchor="w", pady=(8, 0))
        ttk.Button(add_btns, text="Добавить установщик…", command=self.add_deploy).pack(side="left")
        ttk.Button(add_btns, text="Добавить папку…", command=self.add_deploy_folder).pack(side="left", padx=8)
        self.refresh_pack()

    def refresh_pack(self) -> None:
        for child in self.pack_list.winfo_children():
            child.destroy()
        self._pack_vars.clear()
        selection = load_starter_selection()
        enabled = set(selection.get("enabled") or [])
        installers = list_deploy_installers()
        if not installers:
            ttk.Label(
                self.pack_list,
                text="В deploy пока нет установщиков и папок.",
                style="Muted.TLabel",
            ).pack(anchor="w")
            return
        for item in installers:
            name = item["name"]
            kind = item.get("kind") or "installer"
            size_mb = item["size"] / (1024 * 1024)
            kind_label = "папка" if kind == "folder" else "установщик"
            var = tk.BooleanVar(value=name in enabled)
            self._pack_vars[name] = var
            row = ttk.Frame(self.pack_list)
            row.pack(fill="x", pady=2)
            ttk.Checkbutton(
                row,
                text=f"{name}  ({size_mb:.1f} МБ, {kind_label})",
                variable=var,
            ).pack(side="left", anchor="w")

    def save_pack(self) -> None:
        enabled = [name for name, var in self._pack_vars.items() if var.get()]
        save_starter_selection(enabled)
        self.master_app.log(f"Стартовый пак сохранён: {len(enabled)} пунктов")
        messagebox.showinfo("Сохранено", f"В стартовый пак добавлено: {len(enabled)}", parent=self)

    def push_pack(self) -> None:
        enabled = [name for name, var in self._pack_vars.items() if var.get()]
        if not enabled:
            messagebox.showinfo("Пак пуст", "Отметь хотя бы один пункт и сохрани выбор.", parent=self)
            return
        save_starter_selection(enabled)
        self.master_app._send_command("install_starter_pack", {"names": enabled})

    def open_deploy(self) -> None:
        folder = deploy_dir()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def add_deploy(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Добавить установщик",
            filetypes=[("Installers", "*.exe;*.msi;*.bat;*.cmd;*.ps1"), ("All", "*.*")],
        )
        if not path:
            return
        src = Path(path)
        target = deploy_dir() / src.name
        target.write_bytes(src.read_bytes())
        self.master_app.log(f"Добавлен в deploy: {src.name}")
        self.refresh_pack()

    def add_deploy_folder(self) -> None:
        path = filedialog.askdirectory(parent=self, title="Добавить папку в deploy")
        if not path:
            return
        src = Path(path)
        target = deploy_dir() / src.name
        if target.exists():
            if not messagebox.askyesno(
                "Уже есть",
                f"Папка «{src.name}» уже в deploy. Заменить?",
                parent=self,
            ):
                return
            shutil.rmtree(target)
        shutil.copytree(src, target)
        self.master_app.log(f"Добавлена папка в deploy: {src.name}")
        self.refresh_pack()

    def _build_advanced(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Консольная команда", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            parent,
            text="Выполнить произвольную команду на выбранных ПК учеников.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 8))
        self.shell_var = tk.StringVar(value="python --version")
        ttk.Entry(parent, textvariable=self.shell_var).pack(fill="x")
        ttk.Button(parent, text="Выполнить на выбранных", command=self.push_shell).pack(anchor="w", pady=(8, 0))

        ttk.Separator(parent).pack(fill="x", pady=16)
        ttk.Label(parent, text="Прочее", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            parent,
            text="Смена номера ПК — на главном экране (выбери ученика).",
            style="Muted.TLabel",
            wraplength=640,
        ).pack(anchor="w", pady=(8, 0))

    def push_shell(self) -> None:
        command = self.shell_var.get().strip()
        if not command:
            messagebox.showinfo("Команда пустая", "Введи команду.", parent=self)
            return
        if not messagebox.askyesno(
            "Выполнить команду?",
            f"Запустить на выбранных ПК?\n\n{command}",
            parent=self,
        ):
            return
        self.master_app._send_command("run_shell", {"command": command, "timeout": 120})
