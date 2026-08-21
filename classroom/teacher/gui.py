"""GUI тьютора."""

from __future__ import annotations

import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..server.hub import ClassroomServer
from ..shared.branding import place_header_logo
from ..shared.constants import APP_NAME, APP_VERSION, DEFAULT_PORT, DEFAULT_TOKEN, default_backup_dir
from ..shared.osutil import file_type_filters, open_in_os
from ..shared.scripts import get_preset, load_scripts, script_extension, set_selected
from ..shared.scrollable import ScrollableFrame
from ..shared.starter_pack import deploy_dir
from ..shared.theme import COLORS, append_log, apply_theme, make_log
from ..shared.updates import get_update_info
from ..shared.versions import list_commits, restore_commit, snapshot_all
from .roster_tab import RosterTab
from .settings_window import SettingsWindow


class TeacherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — Тьютор")
        self.geometry("1100x760")
        self.minsize(760, 520)
        self.resizable(True, True)
        apply_theme(self)

        self.server = ClassroomServer(port=DEFAULT_PORT, token=DEFAULT_TOKEN, backup_dir=default_backup_dir())
        self.server.on_event = lambda msg: self.after(0, self.log, msg)
        self.clients: list[dict] = []
        self._script_map: dict[str, str] = {}
        self._settings_win: SettingsWindow | None = None

        self._build()
        self.server.start()
        self.log(f"IP этого компьютера: {self.server.local_ip()}")
        self.log(f"Папка учеников: {default_backup_dir()}")
        sync = self.server.store.get_settings().get("sync_seconds", 300)
        self.log(f"Интервал синхронизации: {sync} с")
        info = get_update_info()
        if info:
            self.log(f"Пакет ученика для раздачи: v{info.get('version')}")
        self.refresh_script_combo()
        self.after(1500, self.refresh_clients)

    def _build(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 12))
        header.pack(fill="x")
        self._logo = place_header_logo(header, max_height=42)
        left_h = ttk.Frame(header, style="Header.TFrame")
        left_h.pack(side="left", fill="x", expand=True)
        ttk.Label(left_h, text="Панель тьютора", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(
            left_h,
            text=f"Управление классом по локальной сети · v{APP_VERSION}",
            style="Header.TLabel",
        ).pack(anchor="w")
        ttk.Button(header, text="Настройки", command=self.open_settings, style="Ghost.TButton").pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(header, text="Обновить список", command=self.refresh_clients, style="Ghost.TButton").pack(side="right")

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        # Главный notebook: Класс + Ученики
        nb = ttk.Notebook(body)
        nb.pack(fill="both", expand=True)

        class_tab = ttk.Frame(nb)
        nb.add(class_tab, text="  🖴  Класс  ")

        roster_frame = RosterTab(
            nb,
            on_api=self._tutor_api,
            get_backup_root=lambda: self.server.store.backup_root,
            on_log=self.log,
        )
        nb.add(roster_frame, text="  👤  Ученики  ")

        hpaned = ttk.Panedwindow(class_tab, orient="horizontal")
        hpaned.pack(fill="both", expand=True)

        left = ttk.Frame(hpaned, padding=(0, 0, 8, 0))
        right_wrap = ttk.Frame(hpaned)
        hpaned.add(left, weight=2)
        hpaned.add(right_wrap, weight=3)

        # Заголовок + Выбор группы
        hdr_frame = ttk.Frame(left)
        hdr_frame.pack(fill="x", anchor="w")
        ttk.Label(hdr_frame, text="Компьютеры", style="Title.TLabel").pack(side="left")

        self._class_groups: list[dict] = []
        self._class_group_var = tk.StringVar()
        self._class_group_combo = ttk.Combobox(
            hdr_frame, textvariable=self._class_group_var, state="readonly", width=18
        )
        self._class_group_combo.pack(side="right", padx=(10, 0))
        self._class_group_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_clients())

        list_card = ttk.Frame(left, style="Surface.TFrame", padding=8)
        list_card.pack(fill="both", expand=True, pady=(8, 0))

        self.tree = ttk.Treeview(list_card, columns=("pc", "ip", "status", "student", "extra"), show="headings")
        for col, title, width in [("pc", "ПК", 55), ("ip", "IP", 110), ("status", "Статус", 80), ("student", "Ученик / ID", 140), ("extra", "Режимы", 70)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="w", stretch=True)
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("online", foreground=COLORS["online"])
        self.tree.tag_configure("offline", foreground=COLORS["offline"])
        ttk.Button(left, text="Выбрать все online", command=self.select_online).pack(anchor="w", pady=(8, 0))

        vpaned = ttk.Panedwindow(right_wrap, orient="vertical")
        vpaned.pack(fill="both", expand=True)

        actions_host = ttk.Frame(vpaned)
        log_host = ttk.Frame(vpaned)
        vpaned.add(actions_host, weight=3)
        vpaned.add(log_host, weight=2)

        scroll = ScrollableFrame(actions_host)
        scroll.pack(fill="both", expand=True)
        right = scroll.inner

        actions = ttk.LabelFrame(right, text="Действия", padding=12)
        actions.pack(fill="x", padx=4, pady=(0, 8))

        ttk.Label(actions, text="Ссылка", style="Surface.TLabel").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar(value="https://www.python.org")
        ttk.Entry(actions, textvariable=self.url_var).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        ttk.Button(actions, text="Открыть на выбранных", command=self.open_url, style="Accent.TButton").grid(
            row=1, column=2, sticky="ew", padx=(8, 0), pady=(4, 8)
        )

        ttk.Button(actions, text="Чистые сохранения", command=self.push_fresh).grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Button(actions, text="Восстановить с сервера", command=self.push_restore).grid(
            row=2, column=1, sticky="ew", pady=4, padx=6
        )
        ttk.Button(actions, text="Синхронизировать сейчас", command=self.push_sync).grid(row=2, column=2, sticky="ew", pady=4)

        ttk.Button(actions, text="Установить обои…", command=self.push_wallpaper).grid(row=3, column=0, sticky="ew", pady=4)
        ttk.Button(actions, text="Запустить установщик…", command=self.push_installer).grid(
            row=3, column=1, sticky="ew", pady=4, padx=6
        )
        ttk.Button(actions, text="Отправить сообщение", command=self.push_message).grid(row=3, column=2, sticky="ew", pady=4)

        ttk.Button(actions, text="Заблокировать экран", command=self.lock_screens).grid(
            row=4, column=0, sticky="ew", pady=4
        )
        ttk.Button(actions, text="Разблокировать", command=self.unlock_screens, style="Accent.TButton").grid(
            row=4, column=1, sticky="ew", pady=4, padx=6
        )
        ttk.Label(
            actions,
            text="Блокировка через приложение (без пароля Windows)",
            style="Muted.TLabel",
        ).grid(row=4, column=2, sticky="w", padx=(8, 0))

        control_lf = ttk.LabelFrame(right, text="Контроль и Безопасность (Windows)", padding=12)
        control_lf.pack(fill="x", padx=4, pady=(0, 8))

        ttk.Button(control_lf, text="🎯 Режим Фокуса (Убить игры)", command=self.enable_focus).grid(row=0, column=0, sticky="ew", pady=4, padx=(0, 6))
        ttk.Button(control_lf, text="Выключить Фокус", command=self.disable_focus, style="Accent.TButton").grid(row=0, column=1, sticky="ew", pady=4)
        
        ttk.Button(control_lf, text="🛡️ Включить Сторожа", command=self.enable_watchdog).grid(row=1, column=0, sticky="ew", pady=4, padx=(0, 6))
        ttk.Button(control_lf, text="Выключить Сторожа", command=self.disable_watchdog, style="Accent.TButton").grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(
            actions_host,
            text="Используй Ctrl+Клик или Shift+Клик в таблице для выбора нескольких ПК",
            style="Muted.TLabel",
            anchor="center",
        ).pack(fill="x", pady=6)

        ttk.Label(actions, text="Скрипт запуска", style="Surface.TLabel").grid(row=5, column=0, sticky="w", pady=(10, 0))
        self.script_var = tk.StringVar()
        self.script_combo = ttk.Combobox(actions, textvariable=self.script_var, state="readonly")
        self.script_combo.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        self.script_combo.bind("<<ComboboxSelected>>", self._on_script_selected)
        script_btns = ttk.Frame(actions, style="Surface.TFrame")
        script_btns.grid(row=6, column=2, sticky="ew", padx=(8, 0), pady=(4, 8))
        ttk.Button(script_btns, text="На выбранных", command=self.push_script, style="Accent.TButton").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(script_btns, text="У себя", command=self.run_selected_script_local).pack(side="left", padx=(6, 0))

        ttk.Button(actions, text="История и откат…", command=self.open_history).grid(
            row=7, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Button(actions, text="Обновить учеников…", command=self.offer_student_update).grid(
            row=7, column=1, sticky="ew", pady=(8, 0), padx=6
        )
        ttk.Button(actions, text="Открыть папку ученика", command=self.open_student_folder).grid(
            row=7, column=2, sticky="ew", pady=(8, 0)
        )
        ttk.Button(actions, text="Изменить номер ПК…", command=self.rename_pc).grid(
            row=8, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Label(
            actions,
            text="Папка ученика = номер ПК (например ПК-3)",
            style="Muted.TLabel",
        ).grid(row=8, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        actions.columnconfigure(2, weight=1)

        ttk.Label(log_host, text="Журнал", style="Title.TLabel").pack(anchor="w", pady=(0, 6))
        self.log_box = make_log(log_host, height=8)
        self.log_box.pack(fill="both", expand=True)

        deploy_dir().mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        append_log(self.log_box, message)

    def _tutor_api(self, method: str, path: str, body: dict | None) -> dict | None:
        """Вспомогательный вызов локального сервера с правами тьютора."""
        import json as _json
        from ..shared.http_client import request as _req
        try:
            data = _json.dumps(body).encode("utf-8") if body is not None else None
            headers = {
                "X-Sync-Token": DEFAULT_TOKEN,
                "X-Tutor": "1",
            }
            if data is not None:
                headers["Content-Type"] = "application/json"
            result = _req(
                method,
                f"http://127.0.0.1:{DEFAULT_PORT}{path}",
                data=data,
                headers=headers,
                timeout=10,
            )
            return result if isinstance(result, dict) else None
        except Exception as exc:
            self.after(0, self.log, f"API ошибка: {exc}")
            return None

    def open_settings(self) -> None:
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return
        self._settings_win = SettingsWindow(self)

    def refresh_script_combo(self) -> None:
        data = load_scripts()
        names = []
        self._script_map = {}
        for preset in data["presets"]:
            names.append(preset["name"])
            self._script_map[preset["name"]] = preset["id"]
        self.script_combo["values"] = names
        selected = get_preset(data.get("selected"))
        if selected:
            self.script_var.set(selected["name"])
        elif names:
            self.script_var.set(names[0])

    def _on_script_selected(self, _event=None) -> None:
        name = self.script_var.get()
        preset_id = self._script_map.get(name)
        if preset_id:
            set_selected(preset_id)

    def _current_script(self) -> dict | None:
        name = self.script_var.get()
        preset_id = self._script_map.get(name)
        return get_preset(preset_id)

    def push_script(self) -> None:
        preset = self._current_script()
        if not preset:
            messagebox.showinfo("Нет скрипта", "Выбери пресет или добавь свой в Настройках.")
            return
        self._send_command(
            "run_script",
            {"name": preset["name"], "content": preset.get("content", ""), "kind": preset.get("kind", "bat")},
        )

    def run_selected_script_local(self) -> None:
        preset = self._current_script()
        if not preset:
            messagebox.showinfo("Нет скрипта", "Выбери пресет.")
            return
        self.run_script_on_teacher(preset)

    def run_script_on_teacher(self, preset: dict) -> None:
        content = str(preset.get("content") or "")
        if not content.strip():
            messagebox.showinfo("Пусто", "В пресете нет содержимого.")
            return
        temp = Path(os.environ.get("TEMP", ".")) / "classroom_scripts"
        temp.mkdir(parents=True, exist_ok=True)
        kind = str(preset.get("kind") or "bat")
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in preset.get("name", "script"))[:40]
        path = temp / f"{safe}{script_extension(kind)}"
        path.write_text(content, encoding="utf-8", errors="replace")
        self.log(f"Запуск скрипта у себя: {preset.get('name')}")
        if kind == "ps1":
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)],
                shell=False,
            )
        else:
            subprocess.Popen(["cmd", "/c", str(path)], shell=False)

    def refresh_clients(self) -> None:
        # Обновляем список групп
        self._class_groups = self.server.store.db.list_groups()
        group_names = ["Все группы"] + [g["name"] for g in self._class_groups]
        current_sel = self._class_group_var.get()
        self._class_group_combo.config(values=group_names)
        if current_sel not in group_names:
            self._class_group_var.set("Все группы")
            current_sel = "Все группы"

        active_group = next((g for g in self._class_groups if g["name"] == current_sel), None)
        group_students = []
        if active_group:
            group_students = self.server.store.db.list_students(active_group["id"])

        self.clients = self.server.store.list_clients()
        selected = set(self.tree.selection())
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        seen_student_ids = set()

        # 1. Показываем все подключенные клиенты
        for client in self.clients:
            status = client.get("status") or "offline"
            student_display = client.get("client_id") or "—"
            student_id = client.get("student_id")
            
            # Если выбрана группа, фильтруем: 
            # показываем клиента, если он принадлежит этой группе,
            # либо если он вообще без ученика (чтобы тьютор видел неопознанные ПК)
            if active_group and student_id:
                if not any(s["id"] == student_id for s in group_students):
                    continue

            if student_id:
                student_record = self.server.store.db.get_student(student_id)
                if student_record:
                    student_display = f"{student_record['last_name']} {student_record['first_name']}"
                    seen_student_ids.add(student_id)

            extra_data = client.get("extra") or {}
            extra_str = ""
            if extra_data.get("watchdog_active"):
                extra_str += "🛡️ "
            if extra_data.get("focus_mode_active"):
                extra_str += "🎯 "

            self.tree.insert(
                "", "end", iid=client["client_id"],
                values=(
                    client.get("pc_number") or "—",
                    client.get("ip") or "—",
                    "online" if status == "online" else "offline",
                    student_display,
                    extra_str.strip(),
                ),
                tags=(status,),
            )

        # 2. Показываем оффлайн учеников выбранной группы
        if active_group:
            for s in group_students:
                if s["id"] not in seen_student_ids:
                    student_display = f"{s['last_name']} {s['first_name']}"
                    iid = f"offline_student_{s['id']}"
                    self.tree.insert(
                        "", "end", iid=iid,
                        values=("—", "—", "offline", student_display),
                        tags=("offline",)
                    )

        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)
        self.after(3000, self.refresh_clients)


    def selected_client_ids(self) -> list[str]:
        ids = list(self.tree.selection())
        valid_ids = [iid for iid in ids if not iid.startswith("offline_student_")]
        if valid_ids:
            return valid_ids
        return [c["client_id"] for c in self.clients if c.get("status") == "online"]

    def _send_command(self, kind: str, payload: dict | None = None) -> None:
        client_ids = self.selected_client_ids()
        if not client_ids:
            messagebox.showinfo("Нет получателей", "Выбери компьютеры или дождись online.")
            return
        count = self.server.store.enqueue(client_ids, kind, payload or {})
        self.log(f"Команда «{kind}» → {count} ПК")

    def select_online(self) -> None:
        self.tree.selection_set([])
        for client in self.clients:
            if client.get("status") == "online":
                if self.tree.exists(client["client_id"]):
                    self.tree.selection_add(client["client_id"])

    def open_url(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            return
        self._send_command("open_url", {"url": url})

    def push_fresh(self) -> None:
        self._send_command("use_fresh_saves", {"target": "сохры"})

    def push_restore(self) -> None:
        self._send_command("restore_saves")

    def push_sync(self) -> None:
        self._send_command("sync_now")

    def push_message(self) -> None:
        text = simpledialog.askstring("Сообщение", "Текст для учеников:")
        if text:
            self._send_command("message", {"text": text})

    def lock_screens(self) -> None:
        self._send_command("lock_screen")

    def unlock_screens(self) -> None:
        self._send_command("unlock_screen")

    def enable_focus(self) -> None:
        self._send_command("focus_on")

    def disable_focus(self) -> None:
        self._send_command("focus_off")

    def enable_watchdog(self) -> None:
        self._send_command("watchdog_on")

    def disable_watchdog(self) -> None:
        self._send_command("watchdog_off")

    def rename_pc(self) -> None:
        ids = list(self.tree.selection())
        if not ids:
            messagebox.showinfo("Выбери ПК", "Сначала выбери один или несколько компьютеров в списке.")
            return
        if len(ids) == 1:
            current = ""
            for client in self.clients:
                if client["client_id"] == ids[0]:
                    current = str(client.get("pc_number") or "")
                    break
            number = simpledialog.askstring(
                "Номер ПК",
                f"Новый номер для выбранного ПК:\n{ids[0]}",
                initialvalue=current or "1",
            )
            if not number or not number.strip():
                return
            self._send_command("set_pc_number", {"pc_number": number.strip()})
            self.server.store.set_client_pc_number(ids[0], number.strip())
            self._patch_tree_pc_number(ids[0], number.strip())
            return

        start = simpledialog.askstring(
            "Номера ПК",
            f"Выбрано ПК: {len(ids)}\nС какого номера начать? (дальше по порядку)",
            initialvalue="1",
        )
        if not start or not start.strip():
            return
        try:
            n = int(start.strip())
        except ValueError:
            messagebox.showinfo("Неверный номер", "Введи целое число, например 1.")
            return
        for client_id in ids:
            self.server.store.enqueue([client_id], "set_pc_number", {"pc_number": str(n)})
            self.server.store.set_client_pc_number(client_id, str(n))
            self._patch_tree_pc_number(client_id, str(n))
            n += 1
        self.log(f"Команда «set_pc_number» → {len(ids)} ПК")

    def _patch_tree_pc_number(self, client_id: str, pc_number: str) -> None:
        if not self.tree.exists(client_id):
            return
        values = list(self.tree.item(client_id, "values"))
        if values:
            values[0] = pc_number
            self.tree.item(client_id, values=values)
        for client in self.clients:
            if client["client_id"] == client_id:
                client["pc_number"] = pc_number
                break

    def _upload_deploy_file(self, local_path: Path) -> str:
        target = deploy_dir() / local_path.name
        target.write_bytes(local_path.read_bytes())
        return local_path.name

    def push_wallpaper(self) -> None:
        path = filedialog.askopenfilename(
            title="Выбери обои",
            filetypes=file_type_filters("Images", "*.png", "*.jpg", "*.jpeg", "*.bmp"),
        )
        if not path:
            return
        src = Path(path)
        name = self._upload_deploy_file(src)
        data = src.read_bytes()
        for client_id in self.selected_client_ids():
            self.server.store.save_upload(client_id, f"deploy/{name}", data)
            self.server.store.enqueue(
                [client_id],
                "set_wallpaper",
                {"deploy_name": name, "relative_path": f"deploy/{name}"},
            )
        self.log(f"Обои отправлены: {name}")

    def push_installer(self) -> None:
        path = filedialog.askopenfilename(
            title="Выбери exe/msi/bat",
            filetypes=file_type_filters("Programs", "*.exe", "*.msi", "*.bat"),
        )
        if not path:
            return
        name = self._upload_deploy_file(Path(path))
        rel = f"deploy/{name}"
        for client_id in self.selected_client_ids():
            self.server.store.save_upload(client_id, rel, Path(path).read_bytes())
            self.server.store.enqueue([client_id], "run_file", {"relative_path": rel})
        self.log(f"Установщик отправлен: {name}")

    def open_student_folder(self) -> None:
        ids = list(self.tree.selection())
        if not ids:
            messagebox.showinfo("Выбери ПК", "Сначала выбери компьютер в списке.")
            return
        folder = self.server.store.client_root(ids[0])
        folder.mkdir(parents=True, exist_ok=True)
        open_in_os(folder)

    def open_history(self) -> None:
        ids = list(self.tree.selection())
        if not ids:
            messagebox.showinfo("Выбери ПК", "Сначала выбери компьютер в списке.")
            return
        client_id = ids[0]
        root = self.server.store.client_root(client_id)
        HistoryWindow(self, client_id, root, on_log=self.log)

    def offer_student_update(self) -> None:
        info = get_update_info()
        if not info:
            messagebox.showinfo(
                "Нет пакета",
                "Сначала опубликуй KIBERoneStudent.exe в Настройки → Обновления.",
            )
            self.open_settings()
            return
        if not messagebox.askyesno(
            "Обновить учеников?",
            f"Предложить ученикам обновиться до v{info.get('version')}?\n"
            f"Размер: {int(info.get('size') or 0) / (1024 * 1024):.1f} МБ",
        ):
            return
        self._send_command("offer_update", info)


class HistoryWindow(tk.Toplevel):
    def __init__(self, master, client_id: str, client_root: Path, on_log):
        super().__init__(master)
        self.client_id = client_id
        self.client_root = client_root
        self.on_log = on_log
        self.title(f"История — {client_id}")
        self.geometry("820x540")
        self.minsize(560, 360)
        self.resizable(True, True)
        apply_theme(self)

        top = ttk.Frame(self, padding=14)
        top.pack(fill="both", expand=True)

        ttk.Label(top, text=f"ПК {client_id}", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            top,
            text="Снимки как в Git: выбери версию и восстанови сразу все файлы.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        paned = ttk.Panedwindow(top, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=2)
        paned.add(right, weight=3)

        ttk.Label(left, text="Снимки (версии)").pack(anchor="w")
        self.commits = ttk.Treeview(left, columns=("when", "label", "n"), show="headings")
        self.commits.heading("when", text="Когда")
        self.commits.heading("label", text="Метка")
        self.commits.heading("n", text="Файлов")
        self.commits.column("when", width=160)
        self.commits.column("label", width=120)
        self.commits.column("n", width=70)
        self.commits.pack(fill="both", expand=True, pady=4)
        self.commits.bind("<<TreeviewSelect>>", self._on_commit_select)

        ttk.Label(right, text="Файлы в снимке").pack(anchor="w")
        self.files = ttk.Treeview(right, columns=("path", "ver"), show="headings")
        self.files.heading("path", text="Файл")
        self.files.heading("ver", text="ID версии")
        self.files.column("path", width=280, stretch=True)
        self.files.column("ver", width=180)
        self.files.pack(fill="both", expand=True, pady=4)

        self.empty_var = tk.StringVar()
        ttk.Label(top, textvariable=self.empty_var, style="StatusWarn.TLabel").pack(anchor="w", pady=(6, 0))

        btns = ttk.Frame(top)
        btns.pack(fill="x", pady=10)
        ttk.Button(btns, text="Обновить", command=self.reload_commits).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Сделать снимок сейчас", command=self.make_snapshot).pack(side="left", padx=6)
        ttk.Button(
            btns,
            text="Восстановить все файлы к этой версии",
            command=self.restore_all,
            style="Accent.TButton",
        ).pack(side="left", padx=6)
        ttk.Button(btns, text="Отправить ученику", command=self.push_to_student).pack(side="left", padx=6)
        ttk.Button(btns, text="Открыть папку", command=self.open_folder).pack(side="left", padx=6)

        self._current_commit = ""
        self.reload_commits()

    def reload_commits(self) -> None:
        for item in self.commits.get_children():
            self.commits.delete(item)
        for item in self.files.get_children():
            self.files.delete(item)
        self._current_commit = ""

        rows = list_commits(self.client_root)
        for row in rows:
            self.commits.insert(
                "",
                "end",
                iid=row["id"],
                values=(row.get("saved_at", ""), row.get("label", ""), row.get("file_count", 0)),
            )

        if not rows:
            self.empty_var.set(
                "Снимков ещё нет. Нажми «Сделать снимок сейчас» или дождись изменений от ученика."
            )
        else:
            self.empty_var.set("")

    def make_snapshot(self) -> None:
        count = snapshot_all(self.client_root, label="ручной снимок")
        self.on_log(f"Снимок {self.client_id}: сохранено версий {count}")
        if count == 0 and not list_commits(self.client_root):
            messagebox.showinfo(
                "Снимок",
                "Папка пустая — нечего снимать. Пусть ученик синхронизирует файлы.",
                parent=self,
            )
        else:
            messagebox.showinfo("Снимок готов", f"Сохранено файловых версий: {count}", parent=self)
        self.reload_commits()

    def open_folder(self) -> None:
        self.client_root.mkdir(parents=True, exist_ok=True)
        open_in_os(self.client_root)

    def _on_commit_select(self, _event=None) -> None:
        selection = self.commits.selection()
        if not selection:
            return
        self._current_commit = selection[0]
        for item in self.files.get_children():
            self.files.delete(item)
        rows = list_commits(self.client_root)
        commit = next((row for row in rows if row["id"] == self._current_commit), None)
        if not commit:
            return
        files = commit.get("files") or {}
        for path, meta in sorted(files.items()):
            version_id = meta.get("version_id") if isinstance(meta, dict) else meta
            self.files.insert("", "end", values=(path, version_id or "—"))
        self.empty_var.set("")

    def restore_all(self) -> None:
        if not self._current_commit:
            messagebox.showinfo("Выбери снимок", "Сначала выбери версию слева.", parent=self)
            return
        commit = next((row for row in list_commits(self.client_root) if row["id"] == self._current_commit), None)
        label = (commit or {}).get("label") or self._current_commit
        when = (commit or {}).get("saved_at") or ""
        n = (commit or {}).get("file_count") or 0
        if not messagebox.askyesno(
            "Восстановить все файлы?",
            f"Вернуть все файлы к снимку?\n\n{label}\n{when}\nФайлов: {n}",
            parent=self,
        ):
            return
        try:
            restored = restore_commit(self.client_root, self._current_commit)
            self.on_log(f"Откат всех файлов: {self.client_id} → {self._current_commit} ({len(restored)})")
            messagebox.showinfo(
                "Восстановлено",
                f"Восстановлено файлов: {len(restored)}\nМожно отправить ученику.",
                parent=self,
            )
            self.reload_commits()
        except Exception as exc:
            messagebox.showerror("Не удалось откатить", str(exc), parent=self)

    def push_to_student(self) -> None:
        master = self.master
        if hasattr(master, "server"):
            master.server.store.enqueue([self.client_id], "restore_saves", {})
            self.on_log(f"Ученику {self.client_id} отправлено восстановление с сервера")
            messagebox.showinfo("Отправлено", "Ученик получит текущие файлы с сервера.", parent=self)


def main() -> None:
    app = TeacherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
