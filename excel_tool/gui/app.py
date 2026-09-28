"""AdvancedExcelApp — the ttk.Notebook shell with the three workbenches:

    🧹 核心整理 — 1 表 → 1 表，連續疊加操作（可 undo/還原）
    🔗 合併     — N 表 → 1 表：concat / 交集 / 聯集 / 差集
    🔍 比較     — 2 表 → 檢視：diff 三模式 + AB 人工審核

Each tab is self-contained (owns its own data); there is no hidden global state.
"""
from __future__ import annotations

from tkinter import ttk

from .tab_wrangle import WrangleTab
from .tab_combine import CombineTab
from .tab_compare import CompareTab


class AdvancedExcelApp:
    def __init__(self, root):
        self.root = root
        root.title("Advanced Excel Tool")
        try:
            root.geometry("1360x820")
            root.minsize(1000, 640)
        except Exception:
            pass
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=6)

        self.wrangle = WrangleTab(self.notebook)
        self.combine = CombineTab(self.notebook)
        self.compare = CompareTab(self.notebook)
        self.notebook.add(self.wrangle, text="🧹 核心整理")
        self.notebook.add(self.combine, text="🔗 合併")
        self.notebook.add(self.compare, text="🔍 比較")
