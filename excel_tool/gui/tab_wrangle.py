"""核心整理 tab — single-table wrangling with stacked (accumulating) operations.

Load one table, then keep applying operations; the table updates live and every
step is undoable / resettable (the ETL "疊加" workflow). Buttons are generated
from the operation registry (grouped), so GUI and CLI stay in lock-step. Two
bespoke controls — multi-criteria sort and multi-condition clean — plus a
right-click help window per operation.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd

from infinity_treeview import InfinityTable

from ..core import TableSession, REGISTRY
from ..core.operations import sort_values_multi, clean_by_conditions, _FILTER_OPS
from . import loaders, dialogs, help_content

FONT = ("Microsoft JhengHei", 10)
# operation groups shown as button clusters, in this order
GROUP_ORDER = ["欄位", "列", "清理", "分析", "重塑", "雙表"]


class WrangleTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.session = TableSession()
        self._build_toolbar()
        self._build_op_bar()
        self._build_table()
        self.session.on_change(self._on_data)
        loaders.bind_drop(self, self._load_file)
        self._update_status()

    # ── layout ────────────────────────────────────────────────────────
    def _build_toolbar(self):
        bar = tk.Frame(self)
        bar.pack(side="top", fill="x", padx=6, pady=(6, 2))
        tk.Button(bar, text="📂 載入 Excel", command=self._load, font=FONT).pack(side="left", padx=3)
        tk.Button(bar, text="💾 匯出", command=self._export, font=FONT).pack(side="left", padx=3)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        tk.Button(bar, text="⤺ 復原", command=self._undo, font=FONT).pack(side="left", padx=3)
        tk.Button(bar, text="↺ 還原原始", command=self._reset, font=FONT).pack(side="left", padx=3)
        self.status = tk.Label(bar, text="", font=FONT, fg="#555")
        self.status.pack(side="right", padx=6)

    def _build_op_bar(self):
        outer = tk.Frame(self)
        outer.pack(side="top", fill="x", padx=6)
        canvas = tk.Canvas(outer, height=92, highlightthickness=0)
        canvas.pack(side="top", fill="x")
        hbar = ttk.Scrollbar(outer, orient="horizontal", command=canvas.xview)
        hbar.pack(side="bottom", fill="x")
        canvas.configure(xscrollcommand=hbar.set)
        inner = tk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # registry ops grouped
        by_group = {}
        for op in REGISTRY.values():
            by_group.setdefault(op.group, []).append(op)

        for group in GROUP_ORDER:
            ops = by_group.get(group)
            if not ops:
                continue
            cluster = tk.LabelFrame(inner, text=group, font=FONT, padx=3, pady=2)
            cluster.pack(side="left", fill="y", padx=3, pady=3)
            for op in ops:
                b = tk.Button(cluster, text=op.label, font=FONT,
                              command=lambda o=op: self._run_op(o))
                b.pack(fill="x", pady=1)
                b.bind("<Button-3>", lambda e, o=op: help_content.show_help(self, o))

        # bespoke tools
        special = tk.LabelFrame(inner, text="專用", font=FONT, padx=3, pady=2)
        special.pack(side="left", fill="y", padx=3, pady=3)
        tk.Button(special, text="↕ 多欄排序", font=FONT, command=self._sort_dialog).pack(fill="x", pady=1)
        tk.Button(special, text="🔧 條件清理", font=FONT, command=self._condition_dialog).pack(fill="x", pady=1)

    def _build_table(self):
        holder = tk.Frame(self)
        holder.pack(side="top", fill="both", expand=True, padx=6, pady=6)
        self.table = InfinityTable(holder, pd.DataFrame(), visible_rows=20,
                                   selection_mode="single", data_name="核心整理",
                                   entire_table_width=1100)
        self.table.pack(fill="both", expand=True)

    # ── data plumbing ─────────────────────────────────────────────────
    def _on_data(self, df):
        self.table.set_data(df, keep_widths=False)
        self._update_status()

    def _update_status(self):
        df = self.session.df
        name = self.session.name or "(尚未載入)"
        undo = " | 可復原" if self.session.can_undo else ""
        self.status.config(text=f"{name}　{df.shape[0]} 列 × {df.shape[1]} 欄{undo}")

    def _require(self):
        if self.session.empty:
            messagebox.showinfo("提示", "請先載入 Excel。", parent=self)
            return False
        return True

    # ── toolbar actions ───────────────────────────────────────────────
    def _load(self):
        df, name = loaders.load_excel(self)
        if df is not None:
            self.session.load(df, name)

    def _load_file(self, path):
        df, name = loaders.read_path(self, path)
        if df is not None:
            self.session.load(df, name)

    def _export(self):
        if not self._require():
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            filetypes=[("Excel files", "*.xlsx")], parent=self)
        if path:
            self.session.df.to_excel(path, index=False)
            messagebox.showinfo("完成", f"已匯出至\n{path}", parent=self)

    def _undo(self):
        if not self.session.undo():
            messagebox.showinfo("提示", "沒有可復原的步驟。", parent=self)

    def _reset(self):
        if self._require():
            self.session.reset()

    # ── registry operation ────────────────────────────────────────────
    def _run_op(self, op):
        if not self._require():
            return
        params = dialogs.collect_params(self, op, self.session.columns)
        if params is None:
            return
        try:
            result = op.fn(self.session.df, **params)
        except Exception as e:
            messagebox.showerror("操作失敗", f"{op.label} 失敗：\n{e}", parent=self)
            return
        if op.result == "query":
            self._show_result(result, op.label)
        else:
            self.session.apply(result)

    def _show_result(self, df, title):
        win = tk.Toplevel(self)
        win.title(f"結果 — {title}")
        win.geometry("900x500")
        InfinityTable(win, df, visible_rows=18, selection_mode="single",
                      data_name=title, entire_table_width=860).pack(fill="both", expand=True)

    # ── bespoke: multi-criteria sort ──────────────────────────────────
    def _sort_dialog(self):
        if not self._require():
            return
        dlg = _SortDialog(self, self.session.columns)
        if dlg.result:
            self.session.apply(sort_values_multi(self.session.df, dlg.result))

    # ── bespoke: multi-condition clean ────────────────────────────────
    def _condition_dialog(self):
        if not self._require():
            return
        dlg = _ConditionDialog(self, self.session.columns)
        if dlg.result:
            conds, combine, action = dlg.result
            self.session.apply(clean_by_conditions(self.session.df, conds, combine, action))


# ══════════════════════════════════════════════════════════════════════
#  bespoke dialogs
# ══════════════════════════════════════════════════════════════════════

class _SortDialog(tk.Toplevel):
    def __init__(self, parent, columns):
        super().__init__(parent)
        self.title("多欄排序")
        self.transient(parent)
        self.grab_set()
        self.columns = list(columns)
        self.result = None
        self.rows = []

        self.body = tk.Frame(self, padx=10, pady=8)
        self.body.pack(fill="both", expand=True)
        tk.Button(self, text="＋ 新增排序條件", command=self._add_row, font=FONT).pack(pady=2)
        bar = tk.Frame(self)
        bar.pack(pady=8)
        tk.Button(bar, text="排序", width=10, command=self._ok, font=FONT).pack(side="left", padx=5)
        tk.Button(bar, text="取消", width=10, command=self.destroy, font=FONT).pack(side="left", padx=5)
        self._add_row()
        self.wait_window()

    def _add_row(self):
        row = tk.Frame(self.body)
        row.pack(fill="x", pady=2)
        col = tk.StringVar(value=self.columns[0] if self.columns else "")
        ttk.Combobox(row, textvariable=col, values=self.columns, state="readonly",
                     width=16, font=FONT).pack(side="left", padx=2)
        mode = tk.StringVar(value="文字排序")
        asc_cb = ttk.Combobox(row, values=["升冪", "降冪"], state="readonly", width=5, font=FONT)
        asc_cb.set("升冪")
        asc_cb.pack(side="left", padx=2)
        mode_cb = ttk.Combobox(row, textvariable=mode, values=["文字排序", "數值排序"],
                               state="readonly", width=8, font=FONT)
        mode_cb.pack(side="left", padx=2)
        tk.Button(row, text="✕", command=lambda: (row.destroy(), self.rows.remove(entry)),
                  font=FONT).pack(side="left")
        entry = (col, asc_cb, mode)
        self.rows.append(entry)

    def _ok(self):
        crits = []
        for col, asc_cb, mode in self.rows:
            if not col.get():
                continue
            crits.append({"column": col.get(),
                          "ascending": asc_cb.get() == "升冪",
                          "mode": mode.get()})
        self.result = crits or None
        self.destroy()


class _ConditionDialog(tk.Toplevel):
    def __init__(self, parent, columns):
        super().__init__(parent)
        self.title("條件清理")
        self.transient(parent)
        self.grab_set()
        self.columns = list(columns)
        self.result = None
        self.rows = []

        top = tk.Frame(self, padx=10, pady=6)
        top.pack(fill="x")
        self.combine = tk.StringVar(value="AND")
        tk.Label(top, text="條件組合：", font=FONT).pack(side="left")
        ttk.Combobox(top, textvariable=self.combine, values=["AND", "OR"], state="readonly",
                     width=5, font=FONT).pack(side="left")
        tk.Label(top, text="　動作：", font=FONT).pack(side="left")
        self.action = tk.StringVar(value="keep")
        ttk.Combobox(top, textvariable=self.action, values=["keep", "drop"], state="readonly",
                     width=6, font=FONT).pack(side="left")
        tk.Label(top, text="（符合條件的列）", font=FONT, fg="#888").pack(side="left")

        self.body = tk.Frame(self, padx=10)
        self.body.pack(fill="both", expand=True)
        tk.Button(self, text="＋ 新增條件", command=self._add_row, font=FONT).pack(pady=2)
        bar = tk.Frame(self)
        bar.pack(pady=8)
        tk.Button(bar, text="套用", width=10, command=self._ok, font=FONT).pack(side="left", padx=5)
        tk.Button(bar, text="取消", width=10, command=self.destroy, font=FONT).pack(side="left", padx=5)
        self._add_row()
        self.wait_window()

    def _add_row(self):
        row = tk.Frame(self.body)
        row.pack(fill="x", pady=2)
        col = tk.StringVar(value=self.columns[0] if self.columns else "")
        ttk.Combobox(row, textvariable=col, values=self.columns, state="readonly",
                     width=16, font=FONT).pack(side="left", padx=2)
        op = tk.StringVar(value="包含")
        ttk.Combobox(row, textvariable=op, values=list(_FILTER_OPS), state="readonly",
                     width=8, font=FONT).pack(side="left", padx=2)
        val = tk.Entry(row, width=16, font=FONT)
        val.pack(side="left", padx=2)
        entry = (col, op, val)
        tk.Button(row, text="✕", command=lambda: (row.destroy(), self.rows.remove(entry)),
                  font=FONT).pack(side="left")
        self.rows.append(entry)

    def _ok(self):
        conds = [{"column": c.get(), "op": o.get(), "value": v.get()}
                 for c, o, v in self.rows if c.get()]
        self.result = (conds, self.combine.get(), self.action.get()) if conds else None
        self.destroy()
