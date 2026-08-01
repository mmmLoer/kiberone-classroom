"""GUI преподавателя."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..server.hub import ClassroomServer
from ..shared.constants import APP_NAME, DEFAULT_PORT, DEFAULT_TOKEN, app_dir, default_backup_dir
from ..shared.scrollable import ScrollableFrame
from ..shared.starter_pack import (
    deploy_dir,
    list_deploy_installers,
    load_starter_selection,
    save_starter_selection,
)
from ..shared.theme import COLORS, append_log, apply_theme, make_log
from ..shared.versions import list_client_files, list_file_versions, restore_version, snapshot_all


class TeacherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — Преподаватель")
        self.geometry("1100x760")
        self.minsize(760, 520)
        self.resizable(True, True)
        apply_theme(self)

        self.server = ClassroomServer(port=DEFAULT_PORT, token=DEFAULT_TOKEN, backup_dir=default_backup_dir())
        self.server.on_event = lambda msg: self.after(0, self.log, msg)
        self.clients: list[dict] = []
        self._pack_vars: dict[str, tk.BooleanVar] = {}

        self._build()
        self.server.start()
        self.log(f"IP этого компьютера: {self.server.local_ip()}")
        self.log(f"Папка учеников: {default_backup_dir()}")
        self.refresh_starter_pack_ui()
        self.after(1500, self.refresh_clients)

    def _build(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 12))
        header.pack(fill="x")
        left_h = ttk.Frame(header, style="Header.TFrame")
        left_h.pack(side="left", fill="x", expand=True)
        ttk.Label(left_h, text="Панель преподавателя", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(left_h, text="Управление классом по локальной сети", style="Header.TLabel").pack(anchor="w")
        ttk.Button(header, text="Обновить список", command=self.refresh_clients, style="Ghost.TButton").pack(side="right")

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        hpaned = ttk.Panedwindow(body, orient="horizontal")
        hpaned.pack(fill="both", expand=True)

        left = ttk.Frame(hpaned, padding=(0, 0, 8, 0))
        right_wrap = ttk.Frame(hpaned)
        hpaned.add(left, weight=2)
        hpaned.add(right_wrap, weight=3)

        ttk.Label(left, text="Компьютеры", style="Title.TLabel").pack(anchor="w")
        list_card = ttk.Frame(left, style="Surface.TFrame", padding=8)
        list_card.pack(fill="both", expand=True, pady=(8, 0))

        self.tree = ttk.Treeview(list_card, columns=("pc", "ip", "status", "id"), show="headings")
        for col, title, width in [("pc", "ПК", 55), ("ip", "IP", 110), ("status", "Статус", 80), ("id", "ID", 140)]:
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

        ttk.Button(actions, text="История и откат…", command=self.open_history).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        ttk.Button(actions, text="Открыть папку ученика", command=self.open_student_folder).grid(
            row=4, column=2, sticky="ew", pady=(8, 0)
        )
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        actions.columnconfigure(2, weight=1)

        pack = ttk.LabelFrame(right, text="Стартовый пак программ", padding=12)
        pack.pack(fill="x", padx=4, pady=(0, 8))
        ttk.Label(
            pack,
            text="Отметь установщики из папки deploy — ученики скачают их при начальной настройке",
            style="Muted.TLabel",
        ).pack(anchor="w")
        ttk.Label(pack, text=str(deploy_dir()), style="Mono.TLabel").pack(anchor="w", pady=(4, 8))

        pack_btns = ttk.Frame(pack, style="Surface.TFrame")
        pack_btns.pack(fill="x", pady=(0, 8))
        ttk.Button(pack_btns, text="Обновить список", command=self.refresh_starter_pack_ui).pack(side="left")
        ttk.Button(pack_btns, text="Сохранить выбор", command=self.save_starter_pack, style="Accent.TButton").pack(
            side="left", padx=8
        )
        ttk.Button(pack_btns, text="Отправить пак ученикам", command=self.push_starter_pack).pack(side="left")
        ttk.Button(pack_btns, text="Открыть deploy", command=self.open_deploy, style="Ghost.TButton").pack(side="left", padx=8)

        self.pack_list = ttk.Frame(pack, style="Surface.TFrame")
        self.pack_list.pack(fill="x")

        files_box = ttk.LabelFrame(right, text="Раздача файлов", padding=12)
        files_box.pack(fill="x", padx=4, pady=(0, 8))
        ttk.Label(files_box, text="Сюда же можно добавить новые .exe / .msi / .bat", style="Muted.TLabel").pack(anchor="w")
        ttk.Button(files_box, text="Добавить установщик в deploy…", command=self.add_deploy_installer).pack(
            anchor="w", pady=(8, 0)
        )

        ttk.Label(log_host, text="Журнал", style="Title.TLabel").pack(anchor="w", pady=(0, 6))
        self.log_box = make_log(log_host, height=8)
        self.log_box.pack(fill="both", expand=True)

        deploy_dir().mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        append_log(self.log_box, message)

    def refresh_starter_pack_ui(self) -> None:
        for child in self.pack_list.winfo_children():
            child.destroy()
        self._pack_vars.clear()

        selection = load_starter_selection()
        enabled = set(selection.get("enabled") or [])
        installers = list_deploy_installers()

        if not installers:
            ttk.Label(
                self.pack_list,
                text="В deploy пока нет .exe / .msi / .bat. Добавь установщики и нажми «Обновить список».",
                style="Muted.TLabel",
            ).pack(anchor="w")
            return

        for item in installers:
            name = item["name"]
            size_mb = item["size"] / (1024 * 1024)
            var = tk.BooleanVar(value=name in enabled)
            self._pack_vars[name] = var
            row = ttk.Frame(self.pack_list, style="Surface.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Checkbutton(row, text=f"{name}  ({size_mb:.1f} МБ)", variable=var).pack(side="left", anchor="w")

    def save_starter_pack(self) -> None:
        enabled = [name for name, var in self._pack_vars.items() if var.get()]
        save_starter_selection(enabled)
        self.log(f"Стартовый пак сохранён: {len(enabled)} программ")
        messagebox.showinfo("Сохранено", f"В стартовый пак добавлено программ: {len(enabled)}")

    def push_starter_pack(self) -> None:
        enabled = [name for name, var in self._pack_vars.items() if var.get()]
        if not enabled:
            messagebox.showinfo("Пак пуст", "Отметь хотя бы одну программу и сохрани выбор.")
            return
        save_starter_selection(enabled)
        self._send_command("install_starter_pack", {"names": enabled})

    def add_deploy_installer(self) -> None:
        path = filedialog.askopenfilename(
            title="Добавить установщик",
            filetypes=[("Installers", "*.exe;*.msi;*.bat;*.cmd;*.ps1"), ("All", "*.*")],
        )
        if not path:
            return
        src = Path(path)
        target = deploy_dir() / src.name
        target.write_bytes(src.read_bytes())
        self.log(f"Добавлен в deploy: {src.name}")
        self.refresh_starter_pack_ui()

    def refresh_clients(self) -> None:
        self.clients = self.server.store.list_clients()
        selected = set(self.tree.selection())
        for item in self.tree.get_children():
            self.tree.delete(item)
        for client in self.clients:
            status = client.get("status") or "offline"
            self.tree.insert(
                "",
                "end",
                iid=client["client_id"],
                values=(
                    client.get("pc_number") or "—",
                    client.get("ip") or "—",
                    "online" if status == "online" else "offline",
                    client.get("client_id") or "—",
                ),
                tags=(status,),
            )
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)
        self.after(3000, self.refresh_clients)

    def selected_client_ids(self) -> list[str]:
        ids = list(self.tree.selection())
        if ids:
            return ids
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

    def _upload_deploy_file(self, local_path: Path) -> str:
        target = deploy_dir() / local_path.name
        target.write_bytes(local_path.read_bytes())
        return f"deploy/{local_path.name}"

    def push_wallpaper(self) -> None:
        path = filedialog.askopenfilename(title="Выбери обои", filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp")])
        if not path:
            return
        rel = self._upload_deploy_file(Path(path))
        data = Path(path).read_bytes()
        for client_id in self.selected_client_ids():
            self.server.store.save_upload(client_id, rel, data)
            self.server.store.enqueue([client_id], "set_wallpaper", {"relative_path": rel})
        self.log(f"Обои отправлены: {Path(path).name}")

    def push_installer(self) -> None:
        path = filedialog.askopenfilename(title="Выбери exe/msi/bat", filetypes=[("Programs", "*.exe;*.msi;*.bat")])
        if not path:
            return
        rel = self._upload_deploy_file(Path(path))
        for client_id in self.selected_client_ids():
            self.server.store.save_upload(client_id, rel, Path(path).read_bytes())
            self.server.store.enqueue([client_id], "run_file", {"relative_path": rel})
        self.log(f"Установщик отправлен: {Path(path).name}")
        self.refresh_starter_pack_ui()

    def open_deploy(self) -> None:
        path = deploy_dir()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_student_folder(self) -> None:
        ids = list(self.tree.selection())
        if not ids:
            messagebox.showinfo("Выбери ПК", "Сначала выбери компьютер в списке.")
            return
        folder = self.server.store.client_root(ids[0])
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def open_history(self) -> None:
        ids = list(self.tree.selection())
        if not ids:
            messagebox.showinfo("Выбери ПК", "Сначала выбери компьютер в списке.")
            return
        client_id = ids[0]
        root = self.server.store.client_root(client_id)
        HistoryWindow(self, client_id, root, on_log=self.log)


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
        self.hint_var = tk.StringVar(
            value="Слева все файлы ученика. Справа — сохранённые версии для отката."
        )
        ttk.Label(top, textvariable=self.hint_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 10))

        paned = ttk.Panedwindow(top, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=2)
        paned.add(right, weight=3)

        ttk.Label(left, text="Файлы ученика").pack(anchor="w")
        self.files = ttk.Treeview(left, columns=("path", "n", "when"), show="headings")
        self.files.heading("path", text="Файл")
        self.files.heading("n", text="Версий")
        self.files.heading("when", text="Последний снимок")
        self.files.column("path", width=260, stretch=True)
        self.files.column("n", width=70)
        self.files.column("when", width=150)
        self.files.pack(fill="both", expand=True, pady=4)
        self.files.bind("<<TreeviewSelect>>", self._on_file_select)

        ttk.Label(right, text="Версии выбранного файла").pack(anchor="w")
        self.versions = ttk.Treeview(right, columns=("when", "size", "label", "id"), show="headings")
        self.versions.heading("when", text="Когда")
        self.versions.heading("size", text="Размер")
        self.versions.heading("label", text="Метка")
        self.versions.heading("id", text="ID")
        self.versions.column("when", width=150)
        self.versions.column("size", width=70)
        self.versions.column("label", width=120)
        self.versions.column("id", width=160, stretch=True)
        self.versions.pack(fill="both", expand=True, pady=4)

        self.empty_var = tk.StringVar()
        ttk.Label(top, textvariable=self.empty_var, style="StatusWarn.TLabel").pack(anchor="w", pady=(6, 0))

        btns = ttk.Frame(top)
        btns.pack(fill="x", pady=10)
        ttk.Button(btns, text="Обновить", command=self.reload_files).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Сделать снимок сейчас", command=self.make_snapshot).pack(side="left", padx=6)
        ttk.Button(btns, text="Откатить версию", command=self.restore_selected, style="Accent.TButton").pack(
            side="left", padx=6
        )
        ttk.Button(btns, text="Отправить ученику", command=self.push_to_student).pack(side="left", padx=6)
        ttk.Button(btns, text="Открыть папку", command=self.open_folder).pack(side="left", padx=6)

        self._current_file = ""
        self.reload_files()

    def reload_files(self) -> None:
        for item in self.files.get_children():
            self.files.delete(item)
        rows = list_client_files(self.client_root)
        for row in rows:
            self.files.insert(
                "",
                "end",
                iid=row["path"],
                values=(row["path"], row["versions"], row["last_saved"] or "—"),
            )

        if not rows:
            self.empty_var.set(
                "Файлов ещё нет. Пусть ученик нажмёт «Синхронизировать» "
                "или положи файлы в папку ученика и сделай снимок."
            )
        elif not any(row["versions"] > 0 for row in rows):
            self.empty_var.set(
                "Файлы есть, но версий пока нет. Нажми «Сделать снимок сейчас» "
                "или дождись следующего изменения от ученика."
            )
        else:
            self.empty_var.set("")

        for item in self.versions.get_children():
            self.versions.delete(item)
        self._current_file = ""

    def make_snapshot(self) -> None:
        count = snapshot_all(self.client_root, label="ручной снимок")
        self.on_log(f"Снимок {self.client_id}: сохранено версий {count}")
        if count == 0:
            messagebox.showinfo(
                "Снимок",
                "Новых версий нет — либо папка пустая, либо файлы уже совпадают с последним снимком.",
            )
        else:
            messagebox.showinfo("Снимок готов", f"Сохранено версий: {count}")
        self.reload_files()

    def open_folder(self) -> None:
        self.client_root.mkdir(parents=True, exist_ok=True)
        os.startfile(self.client_root)

    def _on_file_select(self, _event=None) -> None:
        selection = self.files.selection()
        if not selection:
            return
        self._current_file = selection[0]
        for item in self.versions.get_children():
            self.versions.delete(item)
        versions = list_file_versions(self.client_root, self._current_file)
        if not versions:
            self.empty_var.set(f"У «{self._current_file}» ещё нет версий. Нажми «Сделать снимок сейчас».")
        else:
            self.empty_var.set("")
        for ver in versions:
            self.versions.insert(
                "",
                "end",
                iid=ver["id"],
                values=(
                    ver.get("saved_at", ""),
                    ver.get("size", 0),
                    ver.get("label", "авто"),
                    ver.get("id", ""),
                ),
            )

    def restore_selected(self) -> None:
        if not self._current_file:
            messagebox.showinfo("Выбери файл", "Сначала выбери файл слева.")
            return
        version_ids = self.versions.selection()
        if not version_ids:
            messagebox.showinfo("Выбери версию", "Сначала выбери версию справа.")
            return
        version_id = version_ids[0]
        if not messagebox.askyesno("Откатить файл?", f"Вернуть файл к версии?\n{self._current_file}\n→ {version_id}"):
            return
        try:
            path = restore_version(self.client_root, self._current_file, version_id)
            self.on_log(f"Откат: {self.client_id} / {self._current_file} → {version_id}")
            messagebox.showinfo("Файл восстановлен", str(path))
            self.reload_files()
            if self.files.exists(self._current_file):
                self.files.selection_set(self._current_file)
                self._on_file_select()
        except Exception as exc:
            messagebox.showerror("Не удалось откатить", str(exc))

    def push_to_student(self) -> None:
        master = self.master
        if hasattr(master, "server"):
            master.server.store.enqueue([self.client_id], "restore_saves", {})
            self.on_log(f"Ученику {self.client_id} отправлено восстановление с сервера")
            messagebox.showinfo("Отправлено", "Ученик получит текущие файлы с сервера.")


def main() -> None:
    app = TeacherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
