"""Экран входа ученика: выбор группы, имени, темы занятия."""

from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from ..shared.branding import place_header_logo
from ..shared.constants import APP_NAME, DEFAULT_PORT, DEFAULT_TOKEN, app_dir
from ..shared.http_client import request as http_request
from ..shared.identity import get_mac_id, get_pc_number
from ..shared.theme import COLORS, FONTS, apply_theme

_PREFS_FILE = app_dir() / "login_prefs.json"

# Предустановленные темы занятий (тьютор может дополнить их через настройки)
_DEFAULT_TOPICS = [
    "Знакомство с программой",
    "Основы интерфейса",
    "Переменные и данные",
    "Условия и ветвления",
    "Циклы",
    "Функции",
    "Платформер",
    "Игра со спрайтами",
    "Проект",
    "Свободная тема",
]


def _load_prefs() -> dict:
    try:
        return json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_prefs(prefs: dict) -> None:
    try:
        _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PREFS_FILE.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


class StudentLoginScreen(tk.Toplevel):
    """
    Окно выбора ученика перед началом занятия.

    После успешного входа вызывает ``on_login(student_id, session_id, student_name)``.
    При нажатии «Пропустить» или закрытии — вызывает ``on_skip()``.
    """

    def __init__(
        self,
        master: tk.Misc,
        teacher_host: str,
        port: int = DEFAULT_PORT,
        token: str = DEFAULT_TOKEN,
        on_login: Callable[[str, str, str], None] | None = None,
        on_skip: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self.teacher_host = teacher_host
        self.port = port
        self.token = token
        self.on_login = on_login or (lambda *_: None)
        self.on_skip = on_skip or (lambda: None)

        self._groups: list[dict] = []
        self._students: list[dict] = []
        self._student_map: dict[str, str] = {}  # display name → id
        self._prefs = _load_prefs()
        self._done = False

        apply_theme(self)
        self.title(f"{APP_NAME} — Начало занятия")
        self.geometry("460x460")
        self.minsize(380, 380)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._skip)

        self._build()
        self.after(200, self._fetch_groups)

    # ── build ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header
        hdr = ttk.Frame(self, style="Header.TFrame", padding=(18, 12))
        hdr.pack(fill="x")
        place_header_logo(hdr, max_height=36)
        left_h = ttk.Frame(hdr, style="Header.TFrame")
        left_h.pack(side="left", fill="x", expand=True)
        ttk.Label(left_h, text="Начало занятия", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(left_h, text="Выбери себя перед стартом", style="Header.TLabel").pack(anchor="w")

        body = ttk.Frame(self, padding=(24, 18))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        # Статус загрузки
        self._status_var = tk.StringVar(value="Подключаюсь к тьютору…")
        self._status_lbl = ttk.Label(body, textvariable=self._status_var, style="Muted.TLabel")
        self._status_lbl.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        # Группа
        ttk.Label(body, text="Группа", style="Title.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 4))
        self._group_var = tk.StringVar()
        self._group_combo = ttk.Combobox(body, textvariable=self._group_var, state="readonly", font=FONTS["body"])
        self._group_combo.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        self._group_combo.bind("<<ComboboxSelected>>", self._on_group_selected)

        # Ученик
        ttk.Label(body, text="Ученик", style="Title.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 4))
        self._student_var = tk.StringVar()
        self._student_combo = ttk.Combobox(body, textvariable=self._student_var, state="readonly", font=FONTS["body"])
        self._student_combo.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 14))

        # Тема
        ttk.Label(body, text="Тема занятия", style="Title.TLabel").grid(row=5, column=0, sticky="w", pady=(0, 4))
        self._topic_var = tk.StringVar()
        self._topic_combo = ttk.Combobox(body, textvariable=self._topic_var, font=FONTS["body"])
        self._topic_combo["values"] = _DEFAULT_TOPICS
        self._topic_combo.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 24))

        # Кнопки
        btn_frame = ttk.Frame(body)
        btn_frame.grid(row=7, column=0, columnspan=2, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self._login_btn = ttk.Button(
            btn_frame, text="Войти", command=self._login, style="Accent.TButton"
        )
        self._login_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._login_btn.configure(state="disabled")

        ttk.Button(btn_frame, text="Пропустить", command=self._skip).grid(
            row=0, column=1, sticky="ew"
        )

        body.rowconfigure(7, weight=1)

        # Восстанавливаем тему
        saved_topic = self._prefs.get("topic", "")
        if saved_topic:
            self._topic_var.set(saved_topic)

    # ── network ────────────────────────────────────────────────────────────

    def _base_url(self) -> str:
        return f"http://{self.teacher_host}:{self.port}"

    def _request(self, path: str) -> dict | None:
        try:
            result = http_request(
                "GET",
                f"{self._base_url()}{path}",
                headers={"X-Sync-Token": self.token},
                timeout=8,
            )
            return result if isinstance(result, dict) else None
        except Exception:
            return None

    def _post(self, path: str, body: dict) -> dict | None:
        try:
            result = http_request(
                "POST",
                f"{self._base_url()}{path}",
                data=json.dumps(body).encode("utf-8"),
                headers={"X-Sync-Token": self.token, "Content-Type": "application/json"},
                timeout=10,
            )
            return result if isinstance(result, dict) else None
        except Exception:
            return None

    def _fetch_groups(self) -> None:
        def worker() -> None:
            data = self._request("/roster/groups")
            self.after(0, self._on_groups_loaded, data)

        threading.Thread(target=worker, daemon=True).start()

    def _on_groups_loaded(self, data: dict | None) -> None:
        if not data or not data.get("ok"):
            self._status_var.set("Тьютор недоступен — нажми «Пропустить»")
            return
        self._groups = data.get("groups") or []
        if not self._groups:
            self._status_var.set("Групп нет — тьютор ещё не добавил их")
            return
        names = [g["name"] for g in self._groups]
        self._group_combo["values"] = names
        self._status_var.set("Выбери группу и своё имя")

        # Восстанавливаем сохранённую группу
        saved_group = self._prefs.get("group_name", "")
        if saved_group and saved_group in names:
            self._group_var.set(saved_group)
            self._fetch_students()
        else:
            self._group_var.set(names[0])
            self._fetch_students()

    def _on_group_selected(self, _event=None) -> None:
        self._student_combo.set("")
        self._login_btn.configure(state="disabled")
        self._fetch_students()

    def _fetch_students(self) -> None:
        group_name = self._group_var.get()
        group = next((g for g in self._groups if g["name"] == group_name), None)
        if not group:
            return

        def worker(gid: str) -> None:
            data = self._request(f"/roster/students?group_id={gid}")
            self.after(0, self._on_students_loaded, data)

        threading.Thread(target=worker, args=(group["id"],), daemon=True).start()

    def _on_students_loaded(self, data: dict | None) -> None:
        self._students = (data or {}).get("students") or []
        self._student_map = {}
        names = []
        for s in self._students:
            display = f"{s['last_name']} {s['first_name']}"
            names.append(display)
            self._student_map[display] = s["id"]
        self._student_combo["values"] = names

        saved = self._prefs.get("student_display", "")
        if saved and saved in names:
            self._student_var.set(saved)
        elif names:
            self._student_var.set(names[0])

        self._login_btn.configure(state="normal" if names else "disabled")

    # ── actions ────────────────────────────────────────────────────────────

    def _login(self) -> None:
        student_display = self._student_var.get().strip()
        student_id = self._student_map.get(student_display, "")
        topic = self._topic_var.get().strip()
        group_name = self._group_var.get().strip()

        if not student_id:
            messagebox.showwarning("Выбери ученика", "Сначала выбери своё имя в списке.", parent=self)
            return

        self._login_btn.configure(state="disabled")
        self._status_var.set("Регистрирую занятие…")

        def worker() -> None:
            result = self._post("/roster/checkin", {
                "student_id": student_id,
                "topic": topic,
                "pc_number": get_pc_number(),
            })
            self.after(0, self._on_checkin_done, result, student_id, student_display, topic, group_name)

        threading.Thread(target=worker, daemon=True).start()

    def _on_checkin_done(
        self,
        result: dict | None,
        student_id: str,
        student_display: str,
        topic: str,
        group_name: str,
    ) -> None:
        if not result or not result.get("ok"):
            self._status_var.set("Ошибка регистрации — попробуй ещё раз")
            self._login_btn.configure(state="normal")
            return

        session = result.get("session") or {}
        session_id = session.get("id", "")

        _save_prefs({
            "group_name": group_name,
            "student_display": student_display,
            "topic": topic,
        })

        self._done = True
        self.destroy()
        self.on_login(student_id, session_id, student_display)

    def _skip(self) -> None:
        if not self._done:
            self._done = True
            self.destroy()
            self.on_skip()
