import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Callable
from ..shared.theme import COLORS, FONTS

class AchievementsDialog(tk.Toplevel):
    def __init__(self, parent, api_func: Callable, groups: list[dict]):
        super().__init__(parent)
        self.title("Управление Достижениями (Ачивки)")
        self.geometry("600x400")
        self.api = api_func
        self.groups = groups
        
        self.configure(bg=COLORS["surface"])
        
        self._build()
        self._reload()
        
    def _build(self):
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="＋ Создать ачивку", command=self._add_ach).pack(side="left")
        ttk.Button(toolbar, text="✕ Удалить", command=self._del_ach, style="Danger.TButton").pack(side="right")
        
        cols = ("title", "xp", "groups")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("title", text="Название")
        self.tree.heading("xp", text="Награда (XP)")
        self.tree.heading("groups", text="Доступно группам")
        
        self.tree.column("title", width=200)
        self.tree.column("xp", width=80, anchor="center")
        self.tree.column("groups", width=250)
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        
        self.achievements = []
        
    def _reload(self):
        res = self.api("GET", "/roster/achievements", None)
        if res and res.get("ok"):
            self.achievements = res.get("achievements", [])
            for item in self.tree.get_children():
                self.tree.delete(item)
            for a in self.achievements:
                group_names = []
                for gid in a.get("group_ids", []):
                    for g in self.groups:
                        if g["id"] == gid:
                            group_names.append(g["name"])
                g_str = ", ".join(group_names) if group_names else "Всем"
                
                self.tree.insert("", "end", iid=a["id"], values=(
                    f"{a.get('icon', '')} {a['title']}", f"+{a['xp_reward']} XP", g_str
                ))

    def _add_ach(self):
        top = tk.Toplevel(self)
        top.title("Новая ачивка")
        top.geometry("400x450")
        top.configure(bg=COLORS["surface"])
        
        form = tk.Frame(top, bg=COLORS["surface"], padx=16, pady=16)
        form.pack(fill="both", expand=True)
        
        ttk.Label(form, text="Название:", style="TLabel").pack(anchor="w")
        e_title = ttk.Entry(form)
        e_title.pack(fill="x", pady=(0, 12))
        
        ttk.Label(form, text="Иконка (эмодзи):", style="TLabel").pack(anchor="w")
        e_icon = ttk.Entry(form)
        e_icon.insert(0, "🏆")
        e_icon.pack(fill="x", pady=(0, 12))
        
        ttk.Label(form, text="Награда (XP):", style="TLabel").pack(anchor="w")
        e_xp = ttk.Entry(form)
        e_xp.insert(0, "50")
        e_xp.pack(fill="x", pady=(0, 12))
        
        ttk.Label(form, text="Доступно группам (оставь пустым для всех):", style="TLabel").pack(anchor="w", pady=(8,4))
        
        group_vars = {}
        g_frame = tk.Frame(form, bg=COLORS["surface"])
        g_frame.pack(fill="x", pady=(0, 12))
        for g in self.groups:
            var = tk.BooleanVar(value=False)
            group_vars[g["id"]] = var
            ttk.Checkbutton(g_frame, text=g["name"], variable=var, style="TCheckbutton").pack(anchor="w")
            
        def _save():
            title = e_title.get().strip()
            icon = e_icon.get().strip()
            try:
                xp = int(e_xp.get().strip())
            except ValueError:
                messagebox.showerror("Ошибка", "XP должно быть числом", parent=top)
                return
            
            if not title:
                return
                
            selected_groups = [gid for gid, var in group_vars.items() if var.get()]
            
            payload = {
                "title": title,
                "description": "",
                "icon": icon,
                "xp_reward": xp,
                "group_ids": selected_groups
            }
            res = self.api("POST", "/roster/achievements", payload)
            if res and res.get("ok"):
                self._reload()
                top.destroy()
            else:
                messagebox.showerror("Ошибка", "Не удалось создать.", parent=top)
                
        ttk.Button(form, text="Создать", command=_save, style="Accent.TButton").pack(pady=8)

            
    def _del_ach(self):
        sel = self.tree.selection()
        if not sel: return
        if messagebox.askyesno("Удалить?", "Удалить это достижение навсегда?", parent=self):
            res = self.api("POST", "/roster/achievements", {"id": sel[0], "_delete": True})
            if res and res.get("ok"):
                self._reload()
