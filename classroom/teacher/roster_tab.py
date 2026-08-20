"""Вкладка «Ученики» в тьюторском GUI: группы, карточка ученика, оценки, история."""

from __future__ import annotations

import json
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from ..shared.osutil import open_in_os
from ..shared.theme import COLORS, FONTS


def _stars(value: int) -> str:
    return "★" * value + "☆" * (5 - value)


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return "—"
    try:
        import datetime
        return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(ts)


class RosterTab(ttk.Frame):
    """
    Содержимое вкладки «Ученики».

    ``on_api`` — функция-посредник для вызова сервера:
        on_api(method, path, body=None) -> dict | None
    ``get_backup_root`` — возвращает Path к корневой папке бэкапов.
    """

    def __init__(
        self,
        master: tk.Misc,
        on_api: Callable[[str, str, dict | None], dict | None],
        get_backup_root: Callable[[], object],
        on_log: Callable[[str], None],
    ):
        super().__init__(master)
        self._api = on_api
        self._get_root = get_backup_root
        self._log = on_log

        self._groups: list[dict] = []
        self._students: list[dict] = []
        self._sel_group: dict | None = None
        self._sel_student: dict | None = None

        self._build()
        self.after(300, self.reload_groups)

    # ── build ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # Левая колонка — группы
        left = ttk.Frame(paned, padding=(0, 0, 6, 0))
        paned.add(left, weight=1)

        ttk.Label(left, text="Группы", style="Title.TLabel").pack(anchor="w", pady=(0, 4))

        self._group_list = tk.Listbox(
            left,
            font=FONTS["body"],
            bg=COLORS["surface"],
            fg=COLORS["ink"],
            selectbackground=COLORS["accent_soft"],
            selectforeground=COLORS["ink"],
            activestyle="none",
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        self._group_list.pack(fill="both", expand=True)
        self._group_list.bind("<<ListboxSelect>>", self._on_group_select)

        grp_btns = ttk.Frame(left)
        grp_btns.pack(fill="x", pady=(6, 0))
        ttk.Button(grp_btns, text="+ Группа", command=self._add_group).pack(side="left")
        ttk.Button(grp_btns, text="✎", width=3, command=self._edit_group).pack(side="left", padx=4)
        ttk.Button(grp_btns, text="✕", width=3, command=self._del_group).pack(side="left")

        # Средняя колонка — ученики
        mid = ttk.Frame(paned, padding=(0, 0, 6, 0))
        paned.add(mid, weight=1)

        ttk.Label(mid, text="Ученики", style="Title.TLabel").pack(anchor="w", pady=(0, 4))

        cols = ("name", "age", "last_session")
        self._student_tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        self._student_tree.heading("name", text="Фамилия Имя")
        self._student_tree.heading("age", text="Возраст")
        self._student_tree.heading("last_session", text="Последнее занятие")
        self._student_tree.column("name", width=140, stretch=True)
        self._student_tree.column("age", width=60)
        self._student_tree.column("last_session", width=120)
        self._student_tree.pack(fill="both", expand=True)
        self._student_tree.bind("<<TreeviewSelect>>", self._on_student_select)

        stu_btns = ttk.Frame(mid)
        stu_btns.pack(fill="x", pady=(6, 0))
        ttk.Button(stu_btns, text="+ Ученик", command=self._add_student).pack(side="left")
        ttk.Button(stu_btns, text="✎", width=3, command=self._edit_student).pack(side="left", padx=4)
        ttk.Button(stu_btns, text="✕", width=3, command=self._del_student).pack(side="left")

        # Правая панель — карточка ученика
        right = ttk.Frame(paned, padding=(6, 0, 0, 0))
        paned.add(right, weight=2)

        self._card_name = ttk.Label(right, text="", style="Title.TLabel")
        self._card_name.pack(anchor="w")
        self._card_meta = ttk.Label(right, text="", style="Muted.TLabel")
        self._card_meta.pack(anchor="w", pady=(2, 10))

        # Комментарий
        comment_lf = ttk.LabelFrame(right, text="Комментарий тьютора", padding=8)
        comment_lf.pack(fill="x", pady=(0, 10))
        self._comment_box = tk.Text(
            comment_lf,
            height=3,
            wrap="word",
            font=FONTS["body"],
            bg=COLORS["surface"],
            fg=COLORS["ink"],
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            insertbackground=COLORS["ink"],
        )
        self._comment_box.pack(fill="x")
        ttk.Button(comment_lf, text="Сохранить", command=self._save_comment).pack(
            anchor="e", pady=(6, 0)
        )

        # История занятий
        hist_lf = ttk.LabelFrame(right, text="История занятий", padding=8)
        hist_lf.pack(fill="both", expand=True, pady=(0, 10))

        hist_cols = ("date", "topic", "grade")
        self._hist_tree = ttk.Treeview(
            hist_lf, columns=hist_cols, show="headings", selectmode="browse", height=6
        )
        self._hist_tree.heading("date", text="Дата")
        self._hist_tree.heading("topic", text="Тема")
        self._hist_tree.heading("grade", text="Оценка")
        self._hist_tree.column("date", width=130)
        self._hist_tree.column("topic", width=160, stretch=True)
        self._hist_tree.column("grade", width=80)
        self._hist_tree.pack(fill="both", expand=True)
        self._hist_tree.bind("<<TreeviewSelect>>", self._on_session_select)
        self._hist_session_ids: list[str] = []

        # Оценка
        grade_row = ttk.Frame(right)
        grade_row.pack(fill="x", pady=(0, 6))
        ttk.Label(grade_row, text="Оценка:").pack(side="left")
        self._grade_var = tk.IntVar(value=0)
        for v in range(1, 6):
            ttk.Radiobutton(
                grade_row, text=str(v), variable=self._grade_var, value=v
            ).pack(side="left", padx=2)
        ttk.Label(grade_row, text="Заметка:").pack(side="left", padx=(10, 2))
        self._grade_note = ttk.Entry(grade_row, width=16)
        self._grade_note.pack(side="left")
        ttk.Button(grade_row, text="Сохранить", command=self._save_grade, style="Accent.TButton").pack(
            side="left", padx=(8, 0)
        )

        # Кнопка открыть папку
        ttk.Button(
            right, text="📂  Открыть папку сохранений", command=self._open_folder
        ).pack(anchor="w")

    # ── groups ──────────────────────────────────────────────────────────────

    def reload_groups(self) -> None:
        def worker():
            data = self._api("GET", "/roster/groups", None)
            self.after(0, self._on_groups, data)

        threading.Thread(target=worker, daemon=True).start()

    def _on_groups(self, data: dict | None) -> None:
        self._groups = (data or {}).get("groups") or []
        self._group_list.delete(0, "end")
        for g in self._groups:
            self._group_list.insert("end", f"  {g['name']}")
            if g.get("module"):
                self._group_list.insert("end", f"    ({g['module']})")
        # Обновляем displayname с двух строк → один элемент через tags. Проще — перестроим:
        self._group_list.delete(0, "end")
        for g in self._groups:
            display = g["name"]
            if g.get("module"):
                display += f"  · {g['module']}"
            self._group_list.insert("end", display)

    def _selected_group_idx(self) -> int | None:
        sel = self._group_list.curselection()
        return sel[0] if sel else None

    def _on_group_select(self, _event=None) -> None:
        idx = self._selected_group_idx()
        if idx is None:
            return
        self._sel_group = self._groups[idx]
        self._load_students()

    def _add_group(self) -> None:
        name = simpledialog.askstring("Новая группа", "Название группы:", parent=self)
        if not name:
            return
        module = simpledialog.askstring("Новая группа", "Модуль (необязательно):", parent=self) or ""

        def worker():
            self._api("POST", "/roster/groups", {"name": name, "module": module})
            self.after(0, self.reload_groups)

        threading.Thread(target=worker, daemon=True).start()

    def _edit_group(self) -> None:
        if not self._sel_group:
            return
        name = simpledialog.askstring(
            "Редактировать группу", "Название:", initialvalue=self._sel_group["name"], parent=self
        )
        if not name:
            return
        module = simpledialog.askstring(
            "Редактировать группу", "Модуль:", initialvalue=self._sel_group.get("module", ""), parent=self
        ) or ""

        def worker(gid):
            self._api("POST", f"/roster/groups/{gid}", {"name": name, "module": module})
            self.after(0, self.reload_groups)

        threading.Thread(target=worker, args=(self._sel_group["id"],), daemon=True).start()

    def _del_group(self) -> None:
        if not self._sel_group:
            return
        if not messagebox.askyesno(
            "Удалить группу?",
            f"Удалить группу «{self._sel_group['name']}» и всех учеников в ней?",
            parent=self,
        ):
            return

        def worker(gid):
            self._api("POST", f"/roster/groups/{gid}", {"_delete": True})
            self.after(0, self.reload_groups)

        threading.Thread(target=worker, args=(self._sel_group["id"],), daemon=True).start()
        self._sel_group = None
        self._clear_student_list()
        self._clear_card()

    # ── students ───────────────────────────────────────────────────────────

    def _load_students(self) -> None:
        if not self._sel_group:
            return

        def worker(gid):
            data = self._api("GET", f"/roster/students?group_id={gid}", None)
            self.after(0, self._on_students, data)

        threading.Thread(target=worker, args=(self._sel_group["id"],), daemon=True).start()

    def _on_students(self, data: dict | None) -> None:
        self._students = (data or {}).get("students") or []
        self._clear_student_list()
        for s in self._students:
            name = f"{s['last_name']} {s['first_name']}"
            age = str(s["age"]) if s.get("age") else "—"
            self._student_tree.insert("", "end", iid=s["id"], values=(name, age, "—"))

    def _clear_student_list(self) -> None:
        for row in self._student_tree.get_children():
            self._student_tree.delete(row)

    def _on_student_select(self, _event=None) -> None:
        sel = self._student_tree.selection()
        if not sel:
            return
        sid = sel[0]
        self._sel_student = next((s for s in self._students if s["id"] == sid), None)
        if self._sel_student:
            self._load_student_card(sid)

    def _add_student(self) -> None:
        if not self._sel_group:
            messagebox.showinfo("Выбери группу", "Сначала выбери группу слева.", parent=self)
            return
        last = simpledialog.askstring("Новый ученик", "Фамилия:", parent=self)
        if not last:
            return
        first = simpledialog.askstring("Новый ученик", "Имя:", parent=self)
        if not first:
            return
        age_str = simpledialog.askstring("Новый ученик", "Возраст (или пропусти):", parent=self)
        age = int(age_str) if age_str and age_str.isdigit() else None

        def worker(gid):
            self._api("POST", "/roster/students", {
                "last_name": last, "first_name": first, "group_id": gid, "age": age
            })
            self.after(0, self._load_students)

        threading.Thread(target=worker, args=(self._sel_group["id"],), daemon=True).start()

    def _edit_student(self) -> None:
        if not self._sel_student:
            return
        s = self._sel_student
        last = simpledialog.askstring("Редактировать", "Фамилия:", initialvalue=s["last_name"], parent=self)
        if not last:
            return
        first = simpledialog.askstring("Редактировать", "Имя:", initialvalue=s["first_name"], parent=self)
        if not first:
            return
        age_str = simpledialog.askstring(
            "Редактировать", "Возраст:", initialvalue=str(s.get("age") or ""), parent=self
        )
        age = int(age_str) if age_str and age_str.isdigit() else None

        def worker(sid):
            self._api("POST", f"/roster/students/{sid}", {
                "last_name": last, "first_name": first, "age": age
            })
            self.after(0, self._load_students)

        threading.Thread(target=worker, args=(s["id"],), daemon=True).start()

    def _del_student(self) -> None:
        if not self._sel_student:
            return
        s = self._sel_student
        name = f"{s['last_name']} {s['first_name']}"
        if not messagebox.askyesno("Удалить ученика?", f"Удалить «{name}»?", parent=self):
            return

        def worker(sid):
            self._api("POST", f"/roster/students/{sid}", {"_delete": True})
            self.after(0, self._load_students)

        threading.Thread(target=worker, args=(s["id"],), daemon=True).start()
        self._sel_student = None
        self._clear_card()

    # ── student card ────────────────────────────────────────────────────────

    def _load_student_card(self, student_id: str) -> None:
        def worker(sid):
            data = self._api("GET", f"/roster/student/{sid}/history", None)
            self.after(0, self._on_card_loaded, data)

        threading.Thread(target=worker, args=(student_id,), daemon=True).start()

    def _on_card_loaded(self, data: dict | None) -> None:
        if not data or not data.get("ok"):
            return
        student = data["student"]
        sessions = data.get("sessions") or []
        grades_list = data.get("grades") or []
        grade_by_session: dict[str, dict] = {g["session_id"]: g for g in grades_list if g.get("session_id")}

        name = f"{student['last_name']} {student['first_name']}"
        self._card_name.configure(text=name)
        group = next((g for g in self._groups if g["id"] == student["group_id"]), None)
        group_name = group["name"] if group else "—"
        age_str = f", {student['age']} лет" if student.get("age") else ""
        self._card_meta.configure(text=f"Группа: {group_name}{age_str}")

        # Комментарий
        self._comment_box.configure(state="normal")
        self._comment_box.delete("1.0", "end")
        self._comment_box.insert("1.0", student.get("comment") or "")

        # История
        for row in self._hist_tree.get_children():
            self._hist_tree.delete(row)
        self._hist_session_ids = []
        for sess in sessions:
            grade = grade_by_session.get(sess["id"])
            grade_str = _stars(int(grade["value"])) if grade else "—"
            date_str = _fmt_ts(sess.get("created_at"))
            self._hist_tree.insert(
                "", "end",
                iid=sess["id"],
                values=(date_str, sess.get("topic") or "—", grade_str),
            )
            self._hist_session_ids.append(sess["id"])

        # Обновить последнее занятие в таблице учеников
        if sessions and self._sel_student:
            last_ts = sessions[0].get("created_at")
            last_str = _fmt_ts(last_ts)
            try:
                self._student_tree.set(self._sel_student["id"], "last_session", last_str)
            except tk.TclError:
                pass

    def _clear_card(self) -> None:
        self._card_name.configure(text="")
        self._card_meta.configure(text="")
        self._comment_box.configure(state="normal")
        self._comment_box.delete("1.0", "end")
        for row in self._hist_tree.get_children():
            self._hist_tree.delete(row)

    def _on_session_select(self, _event=None) -> None:
        sel = self._hist_tree.selection()
        if not sel:
            return
        # Прочитать существующую оценку для этого занятия
        row = self._hist_tree.item(sel[0])
        grade_str = (row["values"][2] if row["values"] else "") or ""
        count = grade_str.count("★")
        self._grade_var.set(count if count else 0)
        self._grade_note.delete(0, "end")

    def _save_comment(self) -> None:
        if not self._sel_student:
            return
        comment = self._comment_box.get("1.0", "end").strip()
        sid = self._sel_student["id"]

        def worker():
            self._api("POST", f"/roster/students/{sid}", {"comment": comment})
            self.after(0, lambda: self._log(f"Комментарий сохранён: {self._sel_student and self._sel_student.get('last_name')}"))

        threading.Thread(target=worker, daemon=True).start()

    def _save_grade(self) -> None:
        if not self._sel_student:
            return
        value = self._grade_var.get()
        if value not in range(1, 6):
            messagebox.showwarning("Оценка", "Выбери оценку от 1 до 5.", parent=self)
            return
        note = self._grade_note.get().strip()
        sid = self._sel_student["id"]
        sel = self._hist_tree.selection()
        session_id = sel[0] if sel else None

        def worker():
            self._api("POST", "/roster/grade", {
                "student_id": sid,
                "session_id": session_id,
                "value": value,
                "note": note,
            })
            # Перезагружаем карточку
            self.after(0, self._load_student_card, sid)

        threading.Thread(target=worker, daemon=True).start()

    def _open_folder(self) -> None:
        if not self._sel_student:
            return
        from pathlib import Path
        root = self._get_root()
        if root is None:
            return
        s = self._sel_student
        group = next((g for g in self._groups if g["id"] == s["group_id"]), None)

        def _safe(name: str) -> str:
            return "".join(ch if (ch.isalnum() or ch in "-_ ") else "_" for ch in name.strip()).replace(" ", "_")

        group_name = _safe(group["name"] if group else "группа")
        student_name = _safe(f"{s['last_name']}_{s['first_name']}")
        folder = Path(str(root)) / group_name / student_name
        folder.mkdir(parents=True, exist_ok=True)
        open_in_os(folder)
