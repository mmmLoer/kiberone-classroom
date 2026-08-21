"""Вкладка «Ученики» в тьюторском GUI: группы, карточка ученика, оценки, история."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from ..shared.osutil import open_in_os
from ..shared.theme import COLORS, FONTS
from .achievements_dialog import AchievementsDialog


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


def _chip(parent: tk.Widget, text: str, bg: str, fg: str) -> tk.Label:
    """Маленький цветной тег-чип."""
    lbl = tk.Label(
        parent, text=text,
        bg=bg, fg=fg,
        font=(FONTS["label"][0], FONTS["label"][1] - 1, "bold"),
        padx=6, pady=2, relief="flat", bd=0,
    )
    return lbl


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
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # ── Левая колонка: группы ──────────────────────────────────────────
        left = ttk.Frame(paned, padding=(0, 0, 6, 0))
        paned.add(left, weight=1)

        grp_hdr = ttk.Frame(left)
        grp_hdr.pack(fill="x", pady=(0, 6))
        ttk.Label(grp_hdr, text="Группы", style="Title.TLabel").pack(side="left")
        ttk.Button(grp_hdr, text="🏆 Ачивки", command=self._open_achievements, style="Ghost.TButton").pack(side="right", padx=2)
        ttk.Button(grp_hdr, text="＋", width=3, command=self._add_group, style="Ghost.TButton").pack(side="right")
        ttk.Button(grp_hdr, text="✎", width=3, command=self._edit_group, style="Ghost.TButton").pack(side="right", padx=2)
        ttk.Button(grp_hdr, text="✕", width=3, command=self._del_group, style="Ghost.TButton").pack(side="right")

        list_card = tk.Frame(left, bg=COLORS["surface"], relief="flat",
                             highlightthickness=1, highlightbackground=COLORS["border"])
        list_card.pack(fill="both", expand=True)

        self._group_list = tk.Listbox(
            list_card,
            font=FONTS["body"],
            bg=COLORS["surface"],
            fg=COLORS["ink"],
            selectbackground=COLORS["accent"],
            selectforeground="#FFFFFF",
            activestyle="none",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._group_list.pack(fill="both", expand=True, padx=4, pady=4)
        self._group_list.bind("<<ListboxSelect>>", self._on_group_select)

        # ── Средняя колонка: ученики ───────────────────────────────────────
        mid = ttk.Frame(paned, padding=(0, 0, 6, 0))
        paned.add(mid, weight=1)

        stu_hdr = ttk.Frame(mid)
        stu_hdr.pack(fill="x", pady=(0, 6))
        ttk.Label(stu_hdr, text="Ученики", style="Title.TLabel").pack(side="left")
        ttk.Button(stu_hdr, text="＋", width=3, command=self._add_student, style="Ghost.TButton").pack(side="right")
        ttk.Button(stu_hdr, text="✎", width=3, command=self._edit_student, style="Ghost.TButton").pack(side="right", padx=2)
        ttk.Button(stu_hdr, text="✕", width=3, command=self._del_student, style="Ghost.TButton").pack(side="right")

        cols = ("name", "age", "last_session")
        self._student_tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        self._student_tree.heading("name", text="Фамилия Имя")
        self._student_tree.heading("age", text="Возраст")
        self._student_tree.heading("last_session", text="Последнее занятие")
        self._student_tree.column("name", width=140, stretch=True)
        self._student_tree.column("age", width=55, anchor="center")
        self._student_tree.column("last_session", width=120)
        self._student_tree.pack(fill="both", expand=True)
        self._student_tree.bind("<<TreeviewSelect>>", self._on_student_select)

        # ── Правая панель: карточка ученика ───────────────────────────────
        right_outer = ttk.Frame(paned, padding=(6, 0, 0, 0))
        paned.add(right_outer, weight=3)

        # Шапка карточки
        card_header = tk.Frame(right_outer, bg=COLORS["header"], padx=14, pady=10)
        card_header.pack(fill="x", pady=(0, 8))

        self._card_name = tk.Label(
            card_header, text="Выбери ученика",
            bg=COLORS["header"], fg=COLORS["header_fg"],
            font=FONTS["title"], anchor="w",
        )
        self._card_name.pack(anchor="w")

        self._card_meta = tk.Label(
            card_header, text="",
            bg=COLORS["header"], fg="#94A3B8",
            font=FONTS["body"], anchor="w",
        )
        self._card_meta.pack(anchor="w", pady=(2, 0))

        # Кнопки шапки
        card_btn_row = tk.Frame(card_header, bg=COLORS["header"])
        card_btn_row.pack(anchor="w", pady=(8, 0))

        self._portfolio_btn = tk.Button(
            card_btn_row,
            text="🔗  Портфолио",
            bg=COLORS["accent"], fg="#FFFFFF",
            font=FONTS["body"],
            relief="flat", padx=8, pady=3, cursor="hand2",
            command=self._open_portfolio,
            state="disabled",
        )
        self._portfolio_btn.pack(side="left")

        tk.Button(
            card_btn_row,
            text="📂  Папка",
            bg="#1E293B", fg="#94A3B8",
            font=FONTS["body"],
            relief="flat", padx=8, pady=3, cursor="hand2",
            command=self._open_folder,
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            card_btn_row,
            text="🏆 Выдать ачивку",
            bg="#F59E0B", fg="#FFFFFF", # Оранжевый цвет для акцента
            font=FONTS["body"],
            relief="flat", padx=8, pady=3, cursor="hand2",
            command=self._grant_achievement_dialog,
        ).pack(side="left", padx=(8, 0))

        # Портфолио URL и CRM ID убраны в настройки ученика


        # Комментарий тьютора
        comment_lf = ttk.LabelFrame(right_outer, text="Комментарий тьютора", padding=8)
        comment_lf.pack(fill="x", pady=(0, 8))

        self._comment_box = tk.Text(
            comment_lf, height=3, wrap="word",
            font=FONTS["body"],
            bg=COLORS["surface"], fg=COLORS["ink"],
            relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground=COLORS["border"],
            insertbackground=COLORS["ink"],
        )
        self._comment_box.pack(fill="x")
        ttk.Button(comment_lf, text="Сохранить", command=self._save_comment).pack(anchor="e", pady=(6, 0))

        # История занятий
        hist_lf = ttk.LabelFrame(right_outer, text="История занятий", padding=8)
        hist_lf.pack(fill="both", expand=True, pady=(0, 8))

        hist_cols = ("date", "topic", "grade")
        self._hist_tree = ttk.Treeview(
            hist_lf, columns=hist_cols, show="headings", selectmode="browse", height=5
        )
        self._hist_tree.heading("date", text="Дата")
        self._hist_tree.heading("topic", text="Тема")
        self._hist_tree.heading("grade", text="Оценка")
        self._hist_tree.column("date", width=120)
        self._hist_tree.column("topic", width=160, stretch=True)
        self._hist_tree.column("grade", width=80, anchor="center")
        self._hist_tree.pack(fill="both", expand=True)
        self._hist_tree.bind("<<TreeviewSelect>>", self._on_session_select)
        self._hist_session_ids: list[str] = []

        hist_btn_row = ttk.Frame(hist_lf)
        hist_btn_row.pack(fill="x", pady=(6, 0))
        ttk.Label(hist_btn_row, text="", style="SurfaceMuted.TLabel").pack(side="left", fill="x", expand=True)
        ttk.Button(
            hist_btn_row,
            text="✕  Удалить занятие",
            command=self._del_session,
            style="Danger.TButton",
        ).pack(side="right")

        # Строка оценки
        grade_card = ttk.LabelFrame(right_outer, text="Оценить занятие", padding=8)
        grade_card.pack(fill="x")

        grade_inner = ttk.Frame(grade_card)
        grade_inner.pack(fill="x")

        self._grade_var = tk.IntVar(value=0)
        stars_row = ttk.Frame(grade_inner)
        stars_row.pack(side="left")
        ttk.Label(stars_row, text="Оценка:", style="TLabel").pack(side="left")
        for v in range(1, 6):
            ttk.Radiobutton(
                stars_row, text=str(v),
                variable=self._grade_var, value=v,
            ).pack(side="left", padx=2)

        ttk.Label(grade_inner, text="Заметка:", style="TLabel").pack(side="left", padx=(14, 4))
        self._grade_note = ttk.Entry(grade_inner, width=18)
        ttk.Button(
            grade_inner, text="Сохранить", command=self._save_grade, style="Accent.TButton"
        ).pack(side="left", padx=(8, 0))

        # Секция Геймификации
        gami_lf = ttk.LabelFrame(right_outer, text="Прогресс и Геймификация", padding=8)
        gami_lf.pack(fill="x", pady=(8, 0))

        top_gami = ttk.Frame(gami_lf)
        top_gami.pack(fill="x")
        
        self._lbl_level = ttk.Label(top_gami, text="Уровень: 1", font=FONTS["title"])
        self._lbl_level.pack(side="left")
        
        self._lbl_xp = ttk.Label(top_gami, text="(0 XP)", style="Muted.TLabel")
        self._lbl_xp.pack(side="left", padx=(4, 16))
        
        self._lbl_kib = ttk.Label(top_gami, text="Кибероны: 0 ₭", font=FONTS["title"])
        self._lbl_kib.pack(side="left")
        
        self._kib_entry = ttk.Entry(top_gami, width=5)
        self._kib_entry.pack(side="left", padx=(8, 2))
        ttk.Button(top_gami, text="± ₭", width=4, command=self._change_kiberons).pack(side="left")
        ttk.Button(top_gami, text="История", command=self._show_kiberon_history, style="Ghost.TButton").pack(side="left", padx=4)

        ach_row = ttk.Frame(gami_lf)
        ach_row.pack(fill="x", pady=(8, 0))
        ttk.Label(ach_row, text="Достижения:").pack(side="left")
        ttk.Button(ach_row, text="Выдать ачивку", command=self._grant_achievement_dialog).pack(side="right")
        
        self._ach_tree = ttk.Treeview(gami_lf, columns=("icon", "title", "xp"), show="headings", height=3)
        self._ach_tree.heading("icon", text="")
        self._ach_tree.heading("title", text="Название")
        self._ach_tree.heading("xp", text="Награда")
        self._ach_tree.column("icon", width=30, anchor="center")
        self._ach_tree.column("title", width=150, stretch=True)
        self._ach_tree.column("xp", width=60, anchor="center")
        self._ach_tree.pack(fill="x", pady=(4, 0))
        
        ttk.Button(gami_lf, text="✕ Отозвать выбранную ачивку", command=self._revoke_achievement, style="Danger.TButton").pack(anchor="e", pady=(4, 0))


    # ── GAMIFICATION ──────────────────────────────────────────────────────────

    def _open_achievements(self) -> None:
        AchievementsDialog(self, self._api, self._groups)

    def _change_kiberons(self) -> None:
        if not self._sel_student:
            return
            
        try:
            delta = int(self._kib_entry.get().strip())
        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректное число киберонов", parent=self)
            return
            
        reason = simpledialog.askstring("Причина", "За что?", parent=self)
        if reason is None:
            return
            
        sid = self._sel_student["id"]
        res = self._api("POST", f"/roster/student/{sid}/kiberons", {"delta": delta, "reason": reason})
        if res and res.get("ok"):
            self._kib_entry.delete(0, "end")
            self._load_student_card(sid)

    def _show_kiberon_history(self) -> None:
        if not self._sel_student:
            return
        sid = self._sel_student["id"]
        res = self._api("GET", f"/roster/student/{sid}/history")
        if not res or not res.get("ok"):
            return
            
        history = res.get("kiberon_history", [])
        
        top = tk.Toplevel(self)
        top.title(f"История киберонов: {self._sel_student['last_name']}")
        top.geometry("450x300")
        
        cols = ("date", "delta", "reason")
        tree = ttk.Treeview(top, columns=cols, show="headings", selectmode="none")
        tree.heading("date", text="Дата")
        tree.heading("delta", text="Изменение")
        tree.heading("reason", text="Причина")
        tree.column("date", width=120)
        tree.column("delta", width=80, anchor="center")
        tree.column("reason", width=200, stretch=True)
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        
        for h in history:
            import datetime
            dt = datetime.datetime.fromtimestamp(h["created_at"]).strftime("%d.%m.%Y %H:%M")
            delta_str = f"+{h['delta']} ₭" if h['delta'] > 0 else f"{h['delta']} ₭"
            tree.insert("", "end", values=(dt, delta_str, h["reason"]))

    def _grant_achievement_dialog(self) -> None:
        if not self._sel_student: return
        res = self._api("GET", "/roster/achievements")
        if not res or not res.get("ok"): return
        
        achs = res.get("achievements", [])
        if not achs:
            # Делаем отдельное модальное окно для предупреждения, чтобы 100% было поверх всего
            messagebox.showinfo("Нет ачивок", "Сначала создайте хотя бы одну ачивку в окне '🏆 Ачивки' (в заголовке группы).", parent=self)
            return
            
        top = tk.Toplevel(self)
        top.title("Выдать ачивку")
        top.geometry("400x300")
        top.transient(self)
        top.grab_set()
        top.focus_set()
        
        listbox = tk.Listbox(top, font=FONTS["body"])
        listbox.pack(fill="both", expand=True, padx=8, pady=8)
        
        for a in achs:
            listbox.insert("end", f"{a.get('icon', '')} {a.get('title', '')} (+{a.get('xp_reward', 0)} XP)")
            
        def _grant():
            sel = listbox.curselection()
            if not sel: return
            ach_id = achs[sel[0]]["id"]
            self._api("POST", f"/roster/student/{self._sel_student['id']}/achievements", {"achievement_id": ach_id})
            top.destroy()
            self._load_student_card(self._sel_student["id"])
            
        ttk.Button(top, text="Выдать", command=_grant, style="Accent.TButton").pack(pady=8)

    def _revoke_achievement(self) -> None:
        if not self._sel_student: return
        sel = self._ach_tree.selection()
        if not sel: return
        said = sel[0]
        if messagebox.askyesno("Отозвать?", "Точно отозвать это достижение?", parent=self):
            res = self._api("POST", f"/roster/student_achievement/{said}", {"_delete": True})
            if res and res.get("ok"):
                self._load_student_card(self._sel_student["id"])


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
        self._open_group_form()

    def _edit_group(self) -> None:
        if not self._sel_group:
            return
        self._open_group_form(self._sel_group)

    def _open_group_form(self, group: dict | None = None) -> None:
        is_edit = group is not None
        top = tk.Toplevel(self)
        top.title("Редактировать группу" if is_edit else "Новая группа")
        top.geometry("400x350")
        top.configure(bg=COLORS["surface"])
        
        form = tk.Frame(top, bg=COLORS["surface"], padx=16, pady=16)
        form.pack(fill="both", expand=True)
        
        ttk.Label(form, text="Название:", style="TLabel").pack(anchor="w")
        e_name = ttk.Entry(form)
        e_name.insert(0, group["name"] if group else "")
        e_name.pack(fill="x", pady=(0, 12))
        
        ttk.Label(form, text="Модуль:", style="TLabel").pack(anchor="w")
        e_module = ttk.Entry(form)
        e_module.insert(0, group.get("module", "") if group else "")
        e_module.pack(fill="x", pady=(0, 12))
        
        ttk.Label(form, text="Темы уроков (через запятую):", style="TLabel").pack(anchor="w")
        e_topics = tk.Text(
            form, height=4, wrap="word",
            font=FONTS["body"], bg=COLORS["surface"], fg=COLORS["ink"],
            highlightthickness=1, highlightbackground=COLORS["border"]
        )
        e_topics.insert("1.0", group.get("topics", "") if group else "")
        e_topics.pack(fill="x", pady=(0, 12))
        
        def _save():
            name = e_name.get().strip()
            if not name:
                messagebox.showerror("Ошибка", "Название обязательно", parent=top)
                return
                
            payload = {
                "name": name,
                "module": e_module.get().strip(),
                "topics": e_topics.get("1.0", "end").strip()
            }
            
            def worker():
                if is_edit:
                    self._api("POST", f"/roster/groups/{group['id']}", payload)
                else:
                    self._api("POST", "/roster/groups", payload)
                self.after(0, self.reload_groups)
                self.after(0, top.destroy)
                
            threading.Thread(target=worker, daemon=True).start()
            
        ttk.Button(form, text="Сохранить" if is_edit else "Создать", command=_save, style="Accent.TButton").pack(pady=8)

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
        self._open_student_form()

    def _edit_student(self) -> None:
        if not self._sel_student:
            return
        self._open_student_form(self._sel_student)

    def _open_student_form(self, student: dict | None = None) -> None:
        is_edit = student is not None
        top = tk.Toplevel(self)
        top.title("Редактировать ученика" if is_edit else "Новый ученик")
        top.geometry("400x400")
        top.configure(bg=COLORS["surface"])
        
        form = tk.Frame(top, bg=COLORS["surface"], padx=16, pady=16)
        form.pack(fill="both", expand=True)
        
        ttk.Label(form, text="Фамилия:", style="TLabel").pack(anchor="w")
        e_last = ttk.Entry(form)
        e_last.insert(0, student["last_name"] if student else "")
        e_last.pack(fill="x", pady=(0, 12))
        
        ttk.Label(form, text="Имя:", style="TLabel").pack(anchor="w")
        e_first = ttk.Entry(form)
        e_first.insert(0, student["first_name"] if student else "")
        e_first.pack(fill="x", pady=(0, 12))
        
        ttk.Label(form, text="Возраст:", style="TLabel").pack(anchor="w")
        e_age = ttk.Entry(form)
        e_age.insert(0, str(student.get("age") or "") if student else "")
        e_age.pack(fill="x", pady=(0, 12))
        
        ttk.Label(form, text="Портфолио (URL):", style="TLabel").pack(anchor="w")
        e_port = ttk.Entry(form)
        e_port.insert(0, student.get("portfolio_url", "") if student else "")
        e_port.pack(fill="x", pady=(0, 12))
        
        ttk.Label(form, text="CRM ID:", style="TLabel").pack(anchor="w")
        e_crm = ttk.Entry(form)
        e_crm.insert(0, student.get("crm_id", "") if student else "")
        e_crm.pack(fill="x", pady=(0, 12))
        
        def _save():
            last = e_last.get().strip()
            first = e_first.get().strip()
            if not last or not first:
                messagebox.showerror("Ошибка", "Фамилия и Имя обязательны", parent=top)
                return
                
            age_str = e_age.get().strip()
            age = int(age_str) if age_str.isdigit() else None
            
            payload = {
                "last_name": last,
                "first_name": first,
                "age": age,
                "portfolio_url": e_port.get().strip(),
                "crm_id": e_crm.get().strip()
            }
            if not is_edit:
                payload["group_id"] = self._sel_group["id"]
                
            def worker():
                if is_edit:
                    self._api("POST", f"/roster/students/{student['id']}", payload)
                else:
                    self._api("POST", "/roster/students", payload)
                self.after(0, self._load_students)
                self.after(0, top.destroy)
                
            threading.Thread(target=worker, daemon=True).start()
            
        ttk.Button(form, text="Сохранить" if is_edit else "Добавить", command=_save, style="Accent.TButton").pack(pady=8)

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
        achievements_list = data.get("achievements") or []
        grade_by_session: dict[str, dict] = {g["session_id"]: g for g in grades_list if g.get("session_id")}

        name = f"{student['last_name']} {student['first_name']}"
        self._card_name.configure(text=name)
        group = next((g for g in self._groups if g["id"] == student["group_id"]), None)
        group_name = group["name"] if group else "—"
        age_str = f" · {student['age']} лет" if student.get("age") else ""
        module_str = f" · {group['module']}" if group and group.get("module") else ""
        self._card_meta.configure(text=f"Группа: {group_name}{module_str}{age_str} | ID: {student['id'][:6]}")

        # Доп. инфа
        portfolio_url = student.get("portfolio_url") or ""
        if portfolio_url:
            self._portfolio_btn.configure(state="normal", cursor="hand2")
        else:
            self._portfolio_btn.configure(state="disabled")

        # Комментарий
        self._comment_box.configure(state="normal")
        self._comment_box.delete("1.0", "end")
        self._comment_box.insert("1.0", student.get("comment") or "")

        # Геймификация
        self._lbl_level.configure(text=f"Уровень: {student.get('level', 1)}")
        self._lbl_xp.configure(text=f"({student.get('xp', 0)} XP)")
        self._lbl_kib.configure(text=f"Кибероны: {student.get('kiberons', 0)} ₭")
        
        for item in self._ach_tree.get_children():
            self._ach_tree.delete(item)
        for a in achievements_list:
            self._ach_tree.insert("", "end", iid=a["student_achievement_id"], values=(
                a.get("icon", ""), a.get("title", ""), f"+{a.get('xp_reward', 0)} XP"
            ))

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
        self._card_name.configure(text="Выбери ученика")
        self._card_meta.configure(text="")
        self._portfolio_entry.delete(0, "end")
        self._portfolio_btn.configure(state="disabled")
        self._comment_box.configure(state="normal")
        self._comment_box.delete("1.0", "end")
        for row in self._hist_tree.get_children():
            self._hist_tree.delete(row)

    def _on_session_select(self, _event=None) -> None:
        sel = self._hist_tree.selection()
        if not sel:
            return
        row = self._hist_tree.item(sel[0])
        grade_str = (row["values"][2] if row["values"] else "") or ""
        count = grade_str.count("★")
        self._grade_var.set(count if count else 0)
        self._grade_note.delete(0, "end")

    # ── actions ────────────────────────────────────────────────────────────

    def _save_info(self) -> None:
        if not self._sel_student:
            return
        url = self._portfolio_entry.get().strip()
        crm = self._crm_entry.get().strip()
        res = self._api(
            "POST",
            f"/roster/students/{self._sel_student['id']}",
            {"portfolio_url": url, "crm_id": crm},
        )
        if res and res.get("ok"):
            self.reload_students()
            self._load_student_card(self._sel_student["id"])

    def _on_portfolio_saved(self, url: str) -> None:
        self._log(f"Портфолио сохранено: {url or '(очищено)'}")
        if url:
            self._portfolio_btn.configure(state="normal", cursor="hand2")
        else:
            self._portfolio_btn.configure(state="disabled")
        # Обновляем локальный кэш
        if self._sel_student:
            self._sel_student["portfolio_url"] = url

    def _open_portfolio(self) -> None:
        url = self._portfolio_entry.get().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось открыть ссылку:\n{exc}", parent=self)

    def _del_session(self) -> None:
        """Удаляет выбранное занятие из истории."""
        sel = self._hist_tree.selection()
        if not sel:
            messagebox.showinfo("Выбери занятие", "Сначала выбери занятие в истории.", parent=self)
            return
        session_id = sel[0]
        row = self._hist_tree.item(session_id)
        vals = row.get("values") or []
        date_str = vals[0] if vals else "?"
        topic_str = vals[1] if len(vals) > 1 else "?"
        if not messagebox.askyesno(
            "Удалить занятие?",
            f"Удалить занятие «{topic_str}» от {date_str}?\n\nВместе с ним удалятся все оценки за это занятие.",
            parent=self,
        ):
            return
        sid = self._sel_student["id"] if self._sel_student else None

        def worker():
            self._api("POST", "/roster/session/delete", {"session_id": session_id})
            if sid:
                self.after(0, self._load_student_card, sid)

        threading.Thread(target=worker, daemon=True).start()

    def _save_comment(self) -> None:
        if not self._sel_student:
            return
        comment = self._comment_box.get("1.0", "end").strip()
        sid = self._sel_student["id"]

        def worker():
            self._api("POST", f"/roster/students/{sid}", {"comment": comment})
            self.after(0, lambda: self._log(
                f"Комментарий сохранён: {self._sel_student and self._sel_student.get('last_name')}"
            ))

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
