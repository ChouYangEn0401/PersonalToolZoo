"""合併 tab — N tables → 1 result. Concat / join-append and set operations
(交集 / 聯集 / 差集), ported from the old Merger + TableComparator, on
infinity_treeview. Load several files, tag each 主表 / 納入 / 略過, then combine.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd

from infinity_treeview import InfinityTable

from ..core import combine
from . import loaders

FONT = ("Microsoft JhengHei", 10)


class CombineTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.cards = []          # list of dicts: {frame, df, name, role}
        self.result_df = None
        self._build_ui()
        loaders.bind_drop(self, self._load_file)

    def _build_ui(self):
        bar = tk.Frame(self)
        bar.pack(side="top", fill="x", padx=6, pady=(6, 2))
        tk.Button(bar, text="📂 載入 Excel", command=self._load, font=FONT).pack(side="left", padx=3)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        for text, cmd in [("直接疊加", lambda: self._concat("append_direct")),
                          ("共同欄疊加", lambda: self._concat("append_inner")),
                          ("交集", self._intersection),
                          ("聯集", self._union),
                          ("差集(主表-其他)", self._difference)]:
            tk.Button(bar, text=text, command=cmd, font=FONT).pack(side="left", padx=2)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        tk.Button(bar, text="💾 匯出結果", command=self._export, font=FONT).pack(side="left", padx=2)
        self.status = tk.Label(bar, text="", font=FONT, fg="#555")
        self.status.pack(side="right", padx=6)

        # cards (loaded tables) on a horizontal scroll
        card_outer = tk.Frame(self)
        card_outer.pack(side="top", fill="x", padx=6)
        canvas = tk.Canvas(card_outer, height=120, highlightthickness=0)
        canvas.pack(side="top", fill="x")
        hbar = ttk.Scrollbar(card_outer, orient="horizontal", command=canvas.xview)
        hbar.pack(side="bottom", fill="x")
        canvas.configure(xscrollcommand=hbar.set)
        self.card_area = tk.Frame(canvas)
        canvas.create_window((0, 0), window=self.card_area, anchor="nw")
        self.card_area.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        tk.Label(self, text="結果：", font=("Microsoft JhengHei", 11, "bold")).pack(anchor="w", padx=6)
        holder = tk.Frame(self)
        holder.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 6))
        self.result_table = InfinityTable(holder, pd.DataFrame(), visible_rows=16,
                                          selection_mode="single", data_name="結果",
                                          entire_table_width=1100)
        self.result_table.pack(fill="both", expand=True)

    # ── loading ───────────────────────────────────────────────────────
    def _load(self):
        df, name = loaders.load_excel(self)
        if df is not None:
            self._add_card(df, name)

    def _load_file(self, path):
        df, name = loaders.read_path(self, path)
        if df is not None:
            self._add_card(df, name)

    def _add_card(self, df, name):
        frame = tk.Frame(self.card_area, bd=2, relief="groove", padx=6, pady=4)
        frame.pack(side="left", padx=4, pady=4, fill="y")
        role = tk.StringVar(value="納入" if self.cards else "主表")
        card = {"frame": frame, "df": df, "name": name, "role": role}
        head = tk.Frame(frame)
        head.pack(fill="x")
        tk.Label(head, text=name.split(" — ")[0][:20], font=FONT, wraplength=150,
                 justify="left").pack(side="left")
        tk.Button(head, text="✕", fg="red", font=FONT,
                  command=lambda: self._remove(card)).pack(side="right")
        tk.Label(frame, text=f"{df.shape[0]}×{df.shape[1]}", font=FONT, fg="#555").pack(anchor="w")
        ttk.Combobox(frame, textvariable=role, values=["主表", "納入", "略過"],
                     state="readonly", width=8, font=FONT).pack(anchor="w", pady=2)
        self.cards.append(card)
        self._update_status()

    def _remove(self, card):
        card["frame"].destroy()
        self.cards.remove(card)
        self._update_status()

    def _update_status(self):
        self.status.config(text=f"已載入 {len(self.cards)} 張表")

    # ── participants ──────────────────────────────────────────────────
    def _participants(self):
        return [c for c in self.cards if c["role"].get() != "略過"]

    def _main(self):
        mains = [c for c in self.cards if c["role"].get() == "主表"]
        if len(mains) != 1:
            messagebox.showerror("錯誤", "請指定恰好一張「主表」。", parent=self)
            return None
        return mains[0]

    # ── operations ────────────────────────────────────────────────────
    def _concat(self, mode):
        parts = self._participants()
        if not parts:
            messagebox.showinfo("提示", "請先載入表格。", parent=self)
            return
        self._show(combine.concat_all([c["df"] for c in parts], mode))

    def _union(self):
        parts = self._participants()
        if len(parts) < 2:
            messagebox.showinfo("提示", "聯集需要至少兩張參與的表。", parent=self)
            return
        self._show(combine.union([c["df"] for c in parts]))

    def _intersection(self):
        parts = self._participants()
        if len(parts) < 2:
            messagebox.showinfo("提示", "交集需要至少兩張參與的表。", parent=self)
            return
        self._show(combine.intersection([c["df"] for c in parts]))

    def _difference(self):
        main = self._main()
        if not main:
            return
        others = [c["df"] for c in self.cards if c["role"].get() == "納入"]
        if not others:
            messagebox.showinfo("提示", "差集需要至少一張「納入」的附表。", parent=self)
            return
        self._show(combine.difference(main["df"], others))

    def _show(self, df):
        self.result_df = df
        self.result_table.set_data(df, keep_widths=False)
        self.status.config(text=f"已載入 {len(self.cards)} 張表　|　結果 {df.shape[0]}×{df.shape[1]}")

    def _export(self):
        if self.result_df is None:
            messagebox.showinfo("提示", "尚無結果可匯出。", parent=self)
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            filetypes=[("Excel files", "*.xlsx")], parent=self)
        if path:
            self.result_df.to_excel(path, index=False)
            messagebox.showinfo("完成", f"已匯出至\n{path}", parent=self)
