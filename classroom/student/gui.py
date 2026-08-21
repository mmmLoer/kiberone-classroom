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
from .login_screen import StudentLoginScreen


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
        self._lock_win: tk.Toplevel | None = None
        self._lock_lift_job: str | None = None
        self._connecting = False
        # Ученическая идентичность — заполняется после login_screen
        self._student_id: str = ""
        self._session_id: str = ""
        self._student_name: str = ""
        self.host_var = tk.StringVar()
        self.pc_var = tk.StringVar()
        self.folder_var = tk.StringVar()

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
            # Показываем экран входа
            self.after(100, lambda: self._show_login_screen(host))
        else:
            self.log("Тьютор не найден. Запусти KIBERoneTutor на хосте.")
            self.status_var.set("Тьютор не найден")
            self.status_label.configure(style="StatusWarn.TLabel")

    def _show_login_screen(self, host: str) -> None:
        # Сначала пробуем тихий автовход (работает когда сторож перезапустил программу)
        self.log("Проверяю последний сеанс…")
        self.status_var.set("Автовход…")

        def _try_auto() -> None:
            from .login_screen import try_auto_login
            result = try_auto_login(host)
            self.after(0, self._on_auto_login_result, result, host)

        import threading
        threading.Thread(target=_try_auto, daemon=True).start()

    def _on_auto_login_result(self, result: tuple | None, host: str) -> None:
        if result:
            student_id, session_id, student_display = result
            self.log(f"✅ Автовход: {student_display}")
            self._on_student_login(student_id, session_id, student_display)
        else:
            # Нет сохранённого сеанса или тьютор ответил ошибкой — показываем экран входа
            self.log("Последний сеанс не найден, нужен вход.")
            self.status_var.set(f"Найден: {host}")
            StudentLoginScreen(
                self,
                teacher_host=host,
                on_login=self._on_student_login,
                on_skip=lambda: self.log("Отработка без учётной записи."),
            )

    def _on_student_login(self, student_id: str, session_id: str, student_name: str) -> None:
        self._student_id = student_id
        self._session_id = session_id
        self._student_name = student_name
        self._subtitle_var.set(f"{student_name} · {self.host_var.get()}")
        self.btn_profile.configure(state="normal", style="Accent.TButton")
        self.btn_change_student.configure(state="normal")
        self.log(f"Вход выполнен: {student_name}")
        
        # Меняем папку на рабочем столе на имя ученика
        from pathlib import Path
        new_folder = str(Path.home() / "Desktop" / student_name)
        self.folder_var.set(new_folder)
        set_watch_folder(new_folder)
        self.log(f"Папка синхронизации: {new_folder}")

        # Автоматически подключаемся
        self.log("Запуск автоматического подключения...")
        self.after(300, lambda: self.connect(blocking=False))
        self._refresh_progress_loop()

    def _refresh_progress_loop(self) -> None:
        if not self._student_id or not self.agent:
            self.after(5000, self._refresh_progress_loop)
            return

        def worker():
            import urllib.request, json
            try:
                req = urllib.request.Request(f"{self.agent.base_url}/roster/student/{self._student_id}")
                req.add_header("X-Sync-Token", self.agent.token)
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    self.after(0, self._update_progress_ui, data)
            except Exception:
                pass

        import threading
        threading.Thread(target=worker, daemon=True).start()
        self.after(15000, self._refresh_progress_loop)

    def _update_progress_ui(self, data: dict) -> None:
        st = data.get("student") or {}
        ach = data.get("achievements") or []
        
        self.lbl_kiberons.configure(text=f"{st.get('kiberons', 0)} ₭")
        self.lbl_level.configure(text=f" | Ур. {st.get('level', 1)}")
        self.lbl_xp.configure(text=f" ({st.get('xp', 0)} XP)")
        
        icons = " ".join(a.get("icon", "") for a in ach[:5])
        if len(ach) > 5:
            icons += " ..."
        self.lbl_achievements.configure(text=icons)

    def change_student(self) -> None:
        self._student_id = ""
        self._session_id = ""
        self._student_name = ""
        self._subtitle_var.set(f"Подключение к тьютору · v{APP_VERSION}")
        self.btn_profile.configure(state="disabled", style="TButton")
        self.btn_change_student.configure(state="disabled")
        # Очищаем сохранённый student_id чтобы автовход не восстанавливал старого ученика
        from .login_screen import _load_prefs, _save_prefs
        prefs = _load_prefs()
        prefs.pop("student_id", None)
        _save_prefs(prefs)
        host = self.host_var.get().strip() or get_teacher_host("")
        self._show_login_screen(host)

    def open_settings(self) -> None:
        from .settings_window import StudentSettings
        win = StudentSettings(self)
        win.transient(self)
        win.grab_set()

    def _build(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 12))
        header.pack(fill="x")
        self._logo = place_header_logo(header, max_height=42)
        text_box = ttk.Frame(header, style="Header.TFrame")
        text_box.pack(side="left", fill="x", expand=True)
        ttk.Label(text_box, text="KIBERone Classroom", style="Brand.TLabel").pack(anchor="w")
        self._subtitle_var = tk.StringVar(value=f"Подключение к тьютору · v{APP_VERSION}")
        ttk.Label(
            text_box,
            textvariable=self._subtitle_var,
            style="Header.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        self.btn_profile = ttk.Button(header, text="Мой Профиль", command=self.open_profile, state="disabled")
        self.btn_profile.pack(side="right", padx=8)
        
        self.btn_change_student = ttk.Button(header, text="Сменить ученика", command=self.change_student, state="disabled")
        self.btn_change_student.pack(side="right")
        
        ttk.Button(header, text="⚙", width=3, command=self.open_settings, style="Ghost.TButton").pack(side="right", padx=8)


        paned = ttk.Panedwindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=12, pady=12)

        top = ttk.Frame(paned)
        bottom = ttk.Frame(paned)
        paned.add(top, weight=3)
        paned.add(bottom, weight=2)

        scroll = ScrollableFrame(top)
        scroll.pack(fill="both", expand=True)
        root = scroll.inner



        self.status_var = tk.StringVar(value="Не подключено")
        self.status_label = ttk.Label(root, textvariable=self.status_var, style="StatusWarn.TLabel")
        self.status_label.pack(anchor="w", padx=4, pady=(4, 8))

        self.progress_frame = ttk.Frame(root, style="Surface.TFrame")
        self.progress_frame.pack(fill="x", padx=4, pady=(0, 12))
        self.lbl_kiberons = ttk.Label(self.progress_frame, text="0 ₭", font=("Segoe UI", 12, "bold"), foreground="#FBBF24")
        self.lbl_kiberons.pack(side="left")
        self.lbl_level = ttk.Label(self.progress_frame, text=" | Ур. 1", font=("Segoe UI", 12))
        self.lbl_level.pack(side="left")
        self.lbl_xp = ttk.Label(self.progress_frame, text=" (0 XP)", style="Muted.TLabel")
        self.lbl_xp.pack(side="left")
        self.lbl_achievements = ttk.Label(self.progress_frame, text="", font=("Segoe UI", 12))
        self.lbl_achievements.pack(side="left", padx=(12, 0))

        actions = ttk.Frame(root)
        actions.pack(fill="x", padx=4)

        ttk.Button(actions, text="Синхронизировать", command=self.sync_now).pack(side="left", padx=8)
        ttk.Button(actions, text="Проверить обновления", command=self.check_updates).pack(side="left")

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

    def open_profile(self) -> None:
        if not self._student_id or not self.agent:
            return
        # Запрашиваем актуальные данные профиля с сервера
        import urllib.request, json
        try:
            req = urllib.request.Request(f"{self.agent.base_url}/roster/student/{self._student_id}")
            req.add_header("X-Sync-Token", self.agent.token)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            self.log(f"Не удалось загрузить профиль: {e}")
            return
            
        if not data.get("ok"):
            self.log("Ошибка сервера при загрузке профиля")
            return
            
        student = data.get("student") or {}
        achievements = data.get("achievements") or []
        
        win = tk.Toplevel(self)
        win.title("Мой Профиль")
        win.configure(bg="#0F172A")
        win.geometry("500x600")
        win.minsize(400, 500)
        
        header = tk.Frame(win, bg="#1E293B", pady=20)
        header.pack(fill="x")
        
        name = f"{student.get('first_name', '')} {student.get('last_name', '')}"
        tk.Label(header, text=name, font=("Segoe UI", 24, "bold"), bg="#1E293B", fg="white").pack()
        tk.Label(header, text=f"Уровень {student.get('level', 1)}", font=("Segoe UI", 14), bg="#1E293B", fg="#38BDF8").pack(pady=(4, 0))
        
        # XP Bar
        xp = student.get('xp', 0)
        next_lvl_xp = student.get('level', 1) * 100
        xp_pct = min(100, int((xp % 100) / 100 * 100)) if xp else 0
        
        progress_frame = tk.Frame(header, bg="#1E293B")
        progress_frame.pack(fill="x", padx=40, pady=(12, 0))
        bar_bg = tk.Frame(progress_frame, bg="#334155", height=8)
        bar_bg.pack(fill="x", expand=True)
        bar_bg.pack_propagate(False)
        bar_fg = tk.Frame(bar_bg, bg="#38BDF8", width=(xp_pct * 4) or 1) # simple proportional width
        bar_fg.pack(side="left", fill="y")
        tk.Label(progress_frame, text=f"{xp} XP", font=("Segoe UI", 9), bg="#1E293B", fg="#94A3B8").pack(side="left", pady=(4,0))
        tk.Label(progress_frame, text=f"до след. уровня: {100 - (xp % 100)} XP", font=("Segoe UI", 9), bg="#1E293B", fg="#94A3B8").pack(side="right", pady=(4,0))
        
        tk.Label(header, text=f"Баланс: {student.get('kiberons', 0)} ₭", font=("Segoe UI", 16, "bold"), bg="#1E293B", fg="#FBBF24").pack(pady=(16, 0))
        
        body = tk.Frame(win, bg="#0F172A", padx=20, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Мои Достижения", font=("Segoe UI", 14, "bold"), bg="#0F172A", fg="white").pack(anchor="w", pady=(0, 12))
        
        if not achievements:
            tk.Label(body, text="Пока нет достижений. Старайся на занятиях!", font=("Segoe UI", 11), bg="#0F172A", fg="#94A3B8").pack(anchor="w")
        else:
            ach_frame = tk.Frame(body, bg="#0F172A")
            ach_frame.pack(fill="both", expand=True)
            row, col = 0, 0
            for a in achievements:
                card = tk.Frame(ach_frame, bg="#1E293B", bd=1, relief="solid", highlightbackground="#334155", padx=8, pady=8)
                card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
                tk.Label(card, text=a.get("icon", "🏆"), font=("Segoe UI", 24), bg="#1E293B", fg="white").pack()
                tk.Label(card, text=a.get("title", ""), font=("Segoe UI", 10, "bold"), bg="#1E293B", fg="white", wraplength=100).pack(pady=(4,0))
                
                col += 1
                if col > 2:
                    col = 0
                    row += 1

    def show_notification(self, info: dict) -> None:
        """Всплывашка в стиле Steam (снизу справа) с плавной анимацией."""
        title = info.get("title", "")
        xp = info.get("xp", 0)
        icon = info.get("icon", "🏆")
        
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.0) # Начальная прозрачность
        popup.configure(bg="#1E293B", highlightthickness=1, highlightbackground="#334155")
        popup.geometry("300x80")
        
        # Размещаем в правом нижнем углу экрана
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()
        target_x = sw - 320
        target_y = sh - 140
        start_y = sh # Начинаем за пределами экрана снизу
        
        popup.geometry(f"+{target_x}+{start_y}")
        
        # Внутренний контейнер
        frame = tk.Frame(popup, bg="#1E293B", padx=16, pady=16)
        frame.pack(fill="both", expand=True)
        
        # Левая часть - иконка
        tk.Label(frame, text=icon, font=("Segoe UI", 24), bg="#1E293B", fg="white").pack(side="left", padx=(0, 16))
        
        # Правая часть - текст
        right = tk.Frame(frame, bg="#1E293B")
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text="Получено достижение!", font=("Segoe UI", 9, "bold"), bg="#1E293B", fg="#94A3B8").pack(anchor="w")
        tk.Label(right, text=title, font=("Segoe UI", 11, "bold"), bg="#1E293B", fg="white").pack(anchor="w")
        if xp:
            tk.Label(right, text=f"+{xp} XP", font=("Segoe UI", 9), bg="#1E293B", fg="#38BDF8").pack(anchor="w")
            
        # Анимация появления
        def animate_in(step=0):
            if not popup.winfo_exists(): return
            steps = 20
            if step <= steps:
                # Easing: вычисляем прогресс
                progress = step / steps
                alpha = progress
                current_y = start_y - int((start_y - target_y) * progress)
                
                try:
                    popup.attributes("-alpha", alpha)
                    popup.geometry(f"+{target_x}+{current_y}")
                    popup.after(16, animate_in, step + 1)
                except tk.TclError:
                    pass
            else:
                popup.after(5000, start_animate_out)

        def start_animate_out():
            animate_out(0)

        # Анимация исчезновения
        def animate_out(step=0):
            if not popup.winfo_exists(): return
            steps = 20
            if step <= steps:
                progress = step / steps
                alpha = 1.0 - progress
                current_y = target_y + int((start_y - target_y) * progress)
                
                try:
                    popup.attributes("-alpha", alpha)
                    popup.geometry(f"+{target_x}+{current_y}")
                    popup.after(16, animate_out, step + 1)
                except tk.TclError:
                    pass
            else:
                try:
                    popup.destroy()
                except tk.TclError:
                    pass

        animate_in()


    def lock_screen(self) -> None:
        """Полноэкранная блокировка без Windows-пароля (снимается командой тьютора)."""
        if self._lock_win and self._lock_win.winfo_exists():
            try:
                self._lock_win.lift()
                self._lock_win.focus_force()
            except tk.TclError:
                pass
            return

        win = tk.Toplevel(self)
        win.configure(bg="#020617")
        win.attributes("-topmost", True)
        try:
            win.attributes("-fullscreen", True)
        except tk.TclError:
            win.state("zoomed")
        win.overrideredirect(True)
        win.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = tk.Frame(win, bg="#020617")
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text="Экран заблокирован",
            fg="#F8FAFC",
            bg="#020617",
            font=("Segoe UI Semibold", 36, "bold"),
        ).pack(expand=True, pady=(0, 8))
        tk.Label(
            frame,
            text="Дождись тьютора",
            fg="#94A3B8",
            bg="#020617",
            font=("Segoe UI", 16),
        ).pack()

        def _secret_unlock(_event=None):
            self.unlock_screen()
            self.log("Экран разблокирован тьютором (секретная комбинация клавиш)")
            return "break"

        def _block(event=None):
            # Секретная комбинация для тьютора при обрыве сети: Ctrl+Shift+F12 или Ctrl+Shift+K / Ctrl+Shift+U
            if event and hasattr(event, "keysym"):
                # Ctrl (0x4) + Shift (0x1)
                is_ctrl_shift = bool((event.state & 0x4) and (event.state & 0x1))
                if is_ctrl_shift:
                    if event.keysym in ("F12", "f12"):
                        return _secret_unlock(event)
                    if event.keysym.lower() in ("k", "u", "л", "г"):
                        return _secret_unlock(event)
            return "break"

        for seq in (
            "<Key>",
            "<Button>",
            "<ButtonRelease>",
            "<MouseWheel>",
            "<Alt-F4>",
            "<Control-w>",
            "<Escape>",
        ):
            win.bind(seq, _block)

        for secret_seq in (
            "<Control-Shift-F12>",
            "<Control-Shift-K>",
            "<Control-Shift-k>",
            "<Control-Shift-U>",
            "<Control-Shift-u>",
            "<Control-Alt-Shift-K>",
            "<Control-Alt-Shift-k>",
            "<Control-Alt-Shift-U>",
            "<Control-Alt-Shift-u>",
        ):
            try:
                win.bind(secret_seq, _secret_unlock)
            except tk.TclError:
                pass

        try:
            win.grab_set()
            win.focus_force()
        except tk.TclError:
            pass

        self._lock_win = win
        self._keep_lock_on_top()
        self.log("Экран заблокирован тьютором")

    def _keep_lock_on_top(self) -> None:
        win = self._lock_win
        if not win or not win.winfo_exists():
            self._lock_lift_job = None
            return
        try:
            win.lift()
            win.attributes("-topmost", True)
            win.focus_force()
        except tk.TclError:
            pass
        self._lock_lift_job = self.after(800, self._keep_lock_on_top)

    def unlock_screen(self) -> None:
        if self._lock_lift_job:
            try:
                self.after_cancel(self._lock_lift_job)
            except tk.TclError:
                pass
            self._lock_lift_job = None

        win = self._lock_win
        self._lock_win = None
        if win is not None:
            try:
                win.grab_release()
            except tk.TclError:
                pass
            try:
                win.destroy()
            except tk.TclError:
                pass
        self.log("Экран разблокирован")

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
        if self._connecting:
            messagebox.showinfo("Подождите", "Идёт подключение к тьютору…")
            return False
        self.connect(blocking=True)
        return self.agent is not None

    def connect(self, blocking: bool = False) -> None:
        if getattr(self, "_connecting", False):
            self.log("Подключение уже в процессе, пропускаем...")
            return
        self._save_fields()
        if blocking:
            self._connecting = True
            try:
                self._finish_connect(*self._connect_impl())
            finally:
                self._connecting = False
            return

        self._connecting = True
        self.status_var.set("Подключение…")
        self.status_label.configure(style="StatusWarn.TLabel")
        self.update_idletasks()

        def worker() -> None:
            try:
                result = self._connect_impl()
            except Exception as exc:
                result = (None, "", str(exc))
            self.after(0, self._finish_connect, *result)
            self.after(0, lambda: setattr(self, "_connecting", False))

        threading.Thread(target=worker, daemon=True).start()

    def _connect_impl(self) -> tuple[StudentAgent | None, str, str]:
        """Сеть в фоне: (agent, host, error)."""
        host = self.host_var.get().strip()
        if not host:
            host = discover_teacher(
                timeout=5.0,
                token=DEFAULT_TOKEN,
                hint_host=get_teacher_host("") or None,
            )
            if not host:
                return None, "", "Тьютор не найден в сети"

        if self.agent:
            self.agent.stop()

        agent = StudentAgent(
            teacher_host=host,
            port=DEFAULT_PORT,
            token=DEFAULT_TOKEN,
            watch_folder=self.folder_var.get().strip(),
            fresh_saves_dir=self.fresh_saves if self.fresh_saves.exists() else None,
            on_log=lambda msg: self.after(0, self.log, msg),
            on_message=lambda text: self.after(0, self.show_teacher_message, text),
            on_pc_number_changed=lambda number: self.after(0, self._on_pc_number_changed, number),
            on_update_available=lambda info: self.after(0, self.prompt_update, info),
            on_notification=lambda info: self.after(0, self.show_notification, info),
            on_lock_screen=lambda: self.after(0, self.lock_screen),
            on_unlock_screen=lambda: self.after(0, self.unlock_screen),
            student_id=self._student_id,
            session_id=self._session_id,
        )


        ok, detail = agent.ping_details()
        if not ok:
            return None, host, detail
        return agent, host, ""

    def _finish_connect(self, agent: StudentAgent | None, host: str, error: str) -> None:
        if not host and error:
            messagebox.showerror(
                "Тьютор не найден",
                "Запусти KIBERoneTutor на хосте и проверь, что этот ПК в той же сети.",
            )
            self.status_var.set("Тьютор не найден")
            self.status_label.configure(style="StatusWarn.TLabel")
            return

        if host:
            self.host_var.set(host)
            set_teacher_host(host)
            if not error:
                self.log(f"Найден тьютор: {host}")

        if error or agent is None:
            self.log(f"Нет связи: {error or 'неизвестная ошибка'}")
            messagebox.showerror(
                "Нет связи",
                f"Не удалось подключиться к тьютору.\n\n{error or 'Проверь IP и что сервер запущен.'}",
            )
            self.agent = None
            self.status_var.set("Нет связи")
            self.status_label.configure(style="StatusWarn.TLabel")
            return

        self.agent = agent
        self.agent.start()
        self.status_var.set(f"Подключено · {client_label(self.client_id)}")
        self.status_label.configure(style="StatusOk.TLabel")
        self.log("Подключение успешно")

        # Если ученик залогинился — проверяем расхождения сохранений
        if self._student_id:
            self.after(300, self._check_save_conflict)

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
                    lambda err=str(exc): messagebox.showerror("Обновление", f"Не удалось проверить:\n{err}"),
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
                    lambda err=str(exc): messagebox.showerror("Обновление", f"Не удалось скачать:\n{err}"),
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

    def _check_save_conflict(self) -> None:
        """Сравнивает локальные сохранения с сервером и при расхождениях показывает диалог."""
        if not self.agent:
            return
        self.log("Проверяю сохранения…")

        def worker() -> None:
            try:
                diff = self.agent.diff_with_server()
            except Exception as exc:
                self.after(0, self.log, f"Не удалось проверить сохранения: {exc}")
                return
            has_conflict = diff["conflict"] or diff["local_only"] or diff["server_only"]
            if has_conflict:
                self.after(0, self._show_conflict_dialog, diff)
            else:
                self.after(0, self.log, "Сохранения совпадают — всё в порядке")

        threading.Thread(target=worker, daemon=True).start()

    def _show_conflict_dialog(self, diff: dict) -> None:
        """Показывает модальный диалог выбора при расхождении сохранений."""
        local_only  = diff.get("local_only", [])
        server_only = diff.get("server_only", [])
        conflict    = diff.get("conflict", [])

        # Формируем читаемое описание различий
        lines = []
        if conflict:
            lines.append(f"• {len(conflict)} файл(ов) отличаются от версии тьютора")
        if local_only:
            lines.append(f"• {len(local_only)} файл(ов) есть только у тебя")
        if server_only:
            lines.append(f"• {len(server_only)} файл(ов) есть только у тьютора")
        detail = "\n".join(lines)

        win = tk.Toplevel(self)
        win.title("Расхождение сохранений")
        win.geometry("480x260")
        win.minsize(400, 220)
        win.resizable(True, True)
        win.grab_set()
        win.focus_force()
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        from ..shared.theme import apply_theme, COLORS
        apply_theme(win)

        ttk.Label(
            win,
            text="⚠  Найдены различия в сохранениях",
            style="Title.TLabel",
        ).pack(anchor="w", padx=18, pady=(16, 4))

        ttk.Label(win, text=detail, style="Muted.TLabel").pack(anchor="w", padx=18, pady=(0, 12))

        ttk.Label(
            win,
            text="Что сделать?",
            style="Surface.TLabel",
        ).pack(anchor="w", padx=18)

        btn_frame = ttk.Frame(win, padding=(14, 8))
        btn_frame.pack(fill="x")

        def _download() -> None:
            win.destroy()
            self.log("Загружаю сохранения с сервера тьютора…")
            def w():
                try:
                    self.agent.restore_from_teacher()
                    self.after(0, self.log, "Сохранения загружены с сервера")
                except Exception as exc:
                    self.after(0, self.log, f"Ошибка загрузки: {exc}")
            threading.Thread(target=w, daemon=True).start()

        def _upload_as_new() -> None:
            win.destroy()
            self.log("Отправляю локальные сохранения как новые…")
            def w():
                try:
                    self.agent.sync_once()
                    self.after(0, self.log, "Локальные сохранения отправлены тьютору")
                except Exception as exc:
                    self.after(0, self.log, f"Ошибка отправки: {exc}")
            threading.Thread(target=w, daemon=True).start()

        def _skip() -> None:
            win.destroy()
            self.log("Проверка сохранений пропущена — синхронизация будет идти как обычно")

        ttk.Button(
            btn_frame,
            text="⬇  Скачать с тьютора (заменить мои)",
            command=_download,
            style="Accent.TButton",
        ).pack(fill="x", pady=3)
        ttk.Button(
            btn_frame,
            text="⬆  Сохранить мои как новые (отправить тьютору)",
            command=_upload_as_new,
        ).pack(fill="x", pady=3)
        ttk.Button(
            btn_frame,
            text="Пропустить (не менять ничего)",
            command=_skip,
            style="Ghost.TButton",
        ).pack(fill="x", pady=3)

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
            kind = item.get("kind") or "installer"
            size_mb = item.get("size", 0) / (1024 * 1024)
            kind_label = "папка" if kind == "folder" else "установщик"
            var = tk.BooleanVar(value=True)
            self._pack_vars[name] = var
            row = ttk.Frame(self.pack_frame, style="Surface.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Checkbutton(
                row,
                text=f"{title}  ({size_mb:.1f} МБ, {kind_label})",
                variable=var,
            ).pack(side="left", anchor="w")
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
