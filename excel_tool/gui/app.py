"""AdvancedExcelApp — the ttk.Notebook shell.

Phase 1: every tab is an empty shell (:class:`PlaceholderTab`) describing what
will live there, so the architecture can be reviewed before controls are wired.
Later phases replace each placeholder with a real tab whose buttons call
controller callbacks that dispatch to ``excel_tool.core`` operations.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

FONT = ("Microsoft JhengHei", 10)

# (title, planned-contents blurb). Order = tab order.
TABS = [
    ("🧹 整理單檔", "FastEditor 全 17 項 + 教學系統：載入/匯出、刪/留/重命名/重排欄、"
                   "去重、刪空列欄、per-欄 NaN 刪列、比對/查重複值、aggregate、pivot。"),
    ("🔍 比對雙檔", "兩檔主鍵對齊差異，三模式（Single / Neighbor / Two-Side），"
                   "完整還原 Two-Side 高級樣式 + 表頭 popup 互動（轉換選單 + ⚙ 顯示設定）。"),
    ("📂 合併", "多檔多 Sheet 合併輸出（整理自舊 Merger）。"),
    ("🔎 AB 比對", "主鍵分組人工審核、勾選接受/拒絕（整理自舊 ABComparer）。"),
    ("🔧 條件清理", "規則引擎清理（整理自舊 ConditionCleaner / legacy.lib）。"),
    ("📊 集合運算", "多表交集 / 差集 / 聯集（整理自舊 TableComparator）。"),
]


class PlaceholderTab(ttk.Frame):
    def __init__(self, parent, title, blurb):
        super().__init__(parent)
        box = tk.Frame(self)
        box.place(relx=0.5, rely=0.4, anchor="center")
        tk.Label(box, text=title, font=("Microsoft JhengHei", 20, "bold")).pack(pady=(0, 10))
        tk.Label(box, text="（施工中 — Phase 1 骨架）", font=FONT, fg="#c07000").pack()
        tk.Label(box, text=blurb, font=FONT, fg="#555", wraplength=520,
                 justify="center").pack(pady=12)


class AdvancedExcelApp:
    """Builds the notebook shell into *root*. Holds no data yet in Phase 1."""

    def __init__(self, root):
        self.root = root
        root.title("Advanced Excel Tool")
        try:
            root.geometry("1280x760")
            root.minsize(960, 600)
        except Exception:
            pass
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=6)
        self.tabs = {}
        for title, blurb in TABS:
            frame = PlaceholderTab(self.notebook, title, blurb)
            self.notebook.add(frame, text=title)
            self.tabs[title] = frame
