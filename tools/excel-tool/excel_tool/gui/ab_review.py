"""AB 人工審核 — group rows by a key column, eyeball each group and mark rows
✅ (accept) / ❌ (reject), then move processed groups out. Ported and streamlined
from the old ABComparer (keeps the core review + export; the per-cell value-edit
workflow is dropped for now).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd

FONT = ("Microsoft JhengHei", 10)
_COLORS = ['#f0f0ff', '#e0ffe0', '#ffe0e0', '#f0e0e0', '#e0e0ff', '#fff0e0']


class ABReviewWindow(tk.Toplevel):
    def __init__(self, parent, df):
        super().__init__(parent)
        self.title("AB 人工審核")
        self.geometry("1100x680")
        self.df = df.reset_index(drop=True).copy()
        self.a_col = None
        self.checks = {}                 # row idx -> "" / ✅ / ❌
        self.processed = pd.DataFrame()
        self.done_keys = set()           # keys already moved out
        self._colors = {}
        self._build_ui()

    def _build_ui(self):
        bar = tk.Frame(self)
        bar.pack(fill="x", padx=6, pady=6)
        tk.Label(bar, text="分組欄位(A)：", font=FONT).pack(side="left")
        self.a_combo = ttk.Combobox(bar, values=list(self.df.columns), state="readonly",
                                    width=18, font=FONT)
        self.a_combo.pack(side="left", padx=3)
        self.a_combo.bind("<<ComboboxSelected>>", self._on_a)
        tk.Button(bar, text="執行(移出已判定組)", command=self._run, font=FONT).pack(side="left", padx=6)
        tk.Button(bar, text="匯出已判定", command=lambda: self._export(self.processed), font=FONT).pack(side="left", padx=3)
        tk.Button(bar, text="匯出剩餘", command=lambda: self._export(self._remaining()), font=FONT).pack(side="left", padx=3)
        self.status = tk.Label(bar, text="", font=FONT, fg="#555")
        self.status.pack(side="right", padx=6)

        holder = tk.Frame(self)
        holder.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.tree = ttk.Treeview(holder, show="headings")
        vsb = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Button-1>", self._on_click)
        self._populate()

    def _on_a(self, _e=None):
        self.a_col = self.a_combo.get()
        uniq = self.df[self.a_col].astype(str).unique()
        self._colors = {v: _COLORS[i % len(_COLORS)] for i, v in enumerate(uniq)}
        self._populate()

    def _remaining(self):
        if self.a_col is None:
            return self.df
        return self.df[~self.df[self.a_col].astype(str).isin(self.done_keys)]

    def _populate(self):
        self.tree.delete(*self.tree.get_children())
        cols = list(self.df.columns) + ["人工檢查"]
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=110, anchor="w")
        rows = self._remaining()
        if self.a_col is not None:
            rows = rows.sort_values(by=self.a_col, kind="mergesort")
        for idx, row in rows.iterrows():
            tag = ()
            if self.a_col is not None:
                key = str(row[self.a_col])
                tagname = f"g{key}"
                self.tree.tag_configure(tagname, background=self._colors.get(key, "white"))
                tag = (tagname,)
            self.tree.insert("", "end", iid=str(idx),
                             values=list(row.values) + [self.checks.get(idx, "")], tags=tag)
        self._update_status()

    def _on_click(self, event):
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not item or col != f"#{len(self.df.columns) + 1}":
            return
        idx = int(item)
        cur = self.checks.get(idx, "")
        nxt = {"": "✅", "✅": "❌", "❌": ""}[cur]
        self.checks[idx] = nxt
        self.tree.set(item, "人工檢查", nxt)

    def _run(self):
        if self.a_col is None:
            messagebox.showinfo("提示", "請先選擇分組欄位(A)。", parent=self)
            return
        move_idx, accept, reject = [], set(), set()
        for key, grp in self.df.groupby(self.df[self.a_col].astype(str)):
            if key in self.done_keys:
                continue
            marks = {self.checks.get(i, "") for i in grp.index}
            if "✅" in marks:
                accept.add(key); move_idx += list(grp.index)
            elif "❌" in marks:
                reject.add(key); move_idx += list(grp.index)
        if not move_idx:
            messagebox.showinfo("提示", "沒有勾選(✅/❌)的組。", parent=self)
            return
        moved = self.df.loc[move_idx].copy()
        moved["處理方式"] = moved[self.a_col].astype(str).apply(
            lambda k: "接受" if k in accept else "拒絕")
        self.processed = pd.concat([self.processed, moved], ignore_index=True)
        self.done_keys |= accept | reject
        self._populate()

    def _export(self, df):
        if df is None or df.empty:
            messagebox.showinfo("提示", "沒有資料可匯出。", parent=self)
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            filetypes=[("Excel files", "*.xlsx")], parent=self)
        if path:
            df.to_excel(path, index=False)
            messagebox.showinfo("完成", f"已匯出至\n{path}", parent=self)

    def _update_status(self):
        total = self.df[self.a_col].astype(str).nunique() if self.a_col is not None else 0
        self.status.config(text=f"總組數 {total}　已判定 {len(self.done_keys)}　"
                                f"已判定列 {len(self.processed)}")
