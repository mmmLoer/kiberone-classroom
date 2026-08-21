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
        title = simpledialog.askstring("Новая ачивка", "Название достижения (напр. 'Багхантер'):", parent=self)
        if not title: return
        xp = simpledialog.askinteger("Награда", "Сколько опыта (XP) давать за неё?", minvalue=0, initialvalue=50, parent=self)
        if xp is None: return
        icon = simpledialog.askstring("Иконка", "Эмодзи или URL иконки:", initialvalue="🏆", parent=self)
        if not icon: return
        
        payload = {
            "title": title,
            "description": "",
            "icon": icon,
            "xp_reward": xp,
            "group_ids": [] # Пока без фильтра, доступна всем
        }
        res = self.api("POST", "/roster/achievements", payload)
        if res and res.get("ok"):
            self._reload()
        else:
            messagebox.showerror("Ошибка", "Не удалось создать.")
            
    def _del_ach(self):
        sel = self.tree.selection()
        if not sel: return
        if messagebox.askyesno("Удалить?", "Удалить это достижение навсегда?", parent=self):
            res = self.api("POST", "/roster/achievements", {"id": sel[0], "_delete": True})
            if res and res.get("ok"):
                self._reload()
