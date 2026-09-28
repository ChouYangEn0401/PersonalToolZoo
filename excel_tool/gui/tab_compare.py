"""比較 tab — two tables → inspect.

Diff (three modes, key-aligned) with the original Two-Side styling restored
(bold/underline colours) plus the agreed premium interaction: click a column
header → a lightweight popup menu (one reused widget, not N persistent combos)
to apply a cleaning transform to that column. Also hosts AB 人工審核.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import pandas as pd

from infinity_treeview import InfinityTable, Events

from ..core import diff
from ..core.transforms import TRANSFORMS, apply_transform
from .colored_table import ColoredTable
from . import loaders
from .ab_review import ABReviewWindow

FONT = ("Microsoft JhengHei", 10)


# ── input side ────────────────────────────────────────────────────────
class InputSection(tk.Frame):
    def __init__(self, parent, title):
        super().__init__(parent, bd=2, relief="groove")
        self.df = None
        self.key_column = None

        head = tk.Frame(self)
        head.pack(fill="x", padx=4, pady=4)
        tk.Label(head, text=title, font=("Microsoft JhengHei", 11, "bold")).pack(side="left")
        tk.Button(head, text="載入 Excel", command=self._load, font=FONT).pack(side="left", padx=6)

        row = tk.Frame(self)
        row.pack(fill="x", padx=4)
        tk.Label(row, text="主鍵：", font=FONT).pack(side="left")
        self.key_combo = ttk.Combobox(row, state="readonly", width=18, font=FONT)
        self.key_combo.pack(side="left", padx=2)
        self.key_combo.bind("<<ComboboxSelected>>",
                            lambda _e: setattr(self, "key_column", self.key_combo.get()))
        self.info = tk.Label(self, text="尚未載入", font=FONT, anchor="w", fg="#666")
        self.info.pack(fill="x", padx=4)

        self.holder = tk.Frame(self)
        self.holder.pack(fill="both", expand=True, padx=4, pady=4)
        self.preview = None
        loaders.bind_drop(self, self._load_file)

    def _load(self):
        df, name = loaders.load_excel(self)
        if df is not None:
            self._set(df, name)

    def _load_file(self, path):
        df, name = loaders.read_path(self, path)
        if df is not None:
            self._set(df, name)

    def _set(self, df, name):
        # read as str for faithful diff ("1" vs "1.0") — re-read not needed; cast here
        self.df = df.astype(object)
        self.info.config(text=f"{name}　{df.shape[0]}×{df.shape[1]}")
        cols = list(df.columns)
        self.key_combo["values"] = cols
        if cols:
            self.key_combo.set(cols[0])
            self.key_column = cols[0]
        if self.preview is not None:
            self.preview.destroy()
        self.preview = InfinityTable(self.holder, df, visible_rows=7, selection_mode="single",
                                     data_name="預覽", entire_table_width=520)
        self.preview.pack(fill="both", expand=True)


# ── diff windows ──────────────────────────────────────────────────────
def open_single(parent, dfl, dfr, kl, kr):
    win = tk.Toplevel(parent)
    win.title("模式一 — Single Table Diff")
    win.geometry("1100x640")
    tk.Label(win, text="淡紅=刪除　淡綠=新增　淡黃=修改(old → new)", font=FONT, anchor="w").pack(fill="x", padx=6, pady=4)
    df, styles, header = diff.compute_single(dfl, dfr, kl, kr)
    ColoredTable(win, df, styles, header, width=1040, data_name="Single Diff").pack(
        fill="both", expand=True, padx=6, pady=6)


def open_neighbor(parent, dfl, dfr, kl, kr):
    win = tk.Toplevel(parent)
    win.title("模式二 — Neighbor Diff")
    win.geometry("1200x640")
    tk.Label(win, text="每欄 L/R 並排　淡黃=修改　淡紅=左有右無　淡綠=左無右有　灰=整列缺鍵",
             font=FONT, anchor="w").pack(fill="x", padx=6, pady=4)
    df, styles, header = diff.compute_neighbor(dfl, dfr, kl, kr)
    ColoredTable(win, df, styles, header, width=1140, data_name="Neighbor Diff").pack(
        fill="both", expand=True, padx=6, pady=6)


class TwoSideWindow(tk.Toplevel):
    def __init__(self, parent, dfl, dfr, kl, kr):
        super().__init__(parent)
        self.title("模式三 — Two-Side Diff")
        self.geometry("1480x680")
        self.L = diff.prep(dfl, kl)
        self.R = diff.prep(dfr, kr)
        self._syncing = False
        self.toggles = {"add_row": True, "del_row": True,
                        "na_added": True, "na_deleted": True, "changed": True}
        self._menu = tk.Menu(self, tearoff=0)   # one reused popup for header clicks

        self._build_toolbar()
        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=4, pady=4)
        ld, rd, ls, rs, header, _ = diff.compute_two_side(self.L, self.R, self.toggles)
        self.left = ColoredTable(body, ld, ls, header, width=680, data_name="左(原始)")
        self.right = ColoredTable(body, rd, rs, header, width=680, data_name="右(修改)")
        self.left.pack(side="left", fill="both", expand=True)
        self.right.pack(side="left", fill="both", expand=True)

        self.left.table.on(Events.AFTER_SCROLL, self._make_sync(self.left, self.right))
        self.right.table.on(Events.AFTER_SCROLL, self._make_sync(self.right, self.left))
        # rebind header-click popups after each (re)build
        self.left.table.on(Events.AFTER_REFRESH, lambda *_a: self._bind_headers(self.left, "左"))
        self.right.table.on(Events.AFTER_REFRESH, lambda *_a: self._bind_headers(self.right, "右"))
        self.after_idle(lambda: (self._bind_headers(self.left, "左"),
                                 self._bind_headers(self.right, "右")))

    def _build_toolbar(self):
        bar = tk.Frame(self)
        bar.pack(fill="x", padx=6, pady=(6, 0))
        tk.Label(bar, text="點欄位表頭 → 選清洗轉換　|　顯示：", font=FONT).pack(side="left")
        self._vars = {}
        for key, label in [("add_row", "新增列"), ("del_row", "刪除列"),
                           ("na_added", "改:補值"), ("na_deleted", "改:清空"), ("changed", "改:一般")]:
            var = tk.BooleanVar(value=True)
            self._vars[key] = var
            tk.Checkbutton(bar, text=label, variable=var, font=FONT,
                           command=self._on_toggle).pack(side="left")

    def _on_toggle(self):
        for k, v in self._vars.items():
            self.toggles[k] = v.get()
        self._recompute()

    def _recompute(self):
        ld, rd, ls, rs, header, _ = diff.compute_two_side(self.L, self.R, self.toggles)
        self.left.update_data(ld, ls, header)
        self.right.update_data(rd, rs, header)

    def _bind_headers(self, colored, side):
        table = getattr(colored, "table", None)
        view = getattr(table, "view", None)
        if view is None or not view.header_labels:
            return
        for ci, lbl in enumerate(view.header_labels):
            name = table.model.headers[ci] if ci < len(table.model.headers) else None
            if name is None or name == diff.KEY_COL:
                continue
            lbl.bind("<Button-1>", lambda e, s=side, c=name: self._header_menu(e, s, c))

    def _header_menu(self, event, side, col):
        self._menu.delete(0, "end")
        self._menu.add_command(label=f"[{side}] {col} — 套用轉換", state="disabled")
        self._menu.add_separator()
        for t in TRANSFORMS:
            if t == "default":
                continue
            self._menu.add_command(label=t, command=lambda tf=t: self._apply_transform(side, col, tf))
        self._menu.tk_popup(event.x_root, event.y_root)

    def _apply_transform(self, side, col, tf):
        df = self.L if side == "左" else self.R
        if col not in df.columns:
            return
        digits = None
        if tf == "Round":
            digits = simpledialog.askinteger("Round", "四捨五入到幾位？", minvalue=0, maxvalue=10, parent=self)
            if digits is None:
                return
        errors = 0
        for idx in df.index:
            try:
                df.at[idx, col] = apply_transform(df.at[idx, col], tf, digits)
            except Exception:
                errors += 1
        self._recompute()
        if errors:
            messagebox.showinfo("清洗完成", f"「{col}」有 {errors} 格無法轉換，已保留原值。", parent=self)

    def _make_sync(self, src, dst):
        def cb(*_a):
            if self._syncing:
                return
            self._syncing = True
            try:
                if dst.table.start_index != src.table.start_index:
                    dst.table.start_index = src.table.start_index
                    dst.table.view.refresh()
                    dst._recolor()
            finally:
                self._syncing = False
        return cb


# ── the tab ───────────────────────────────────────────────────────────
class CompareTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        top = tk.Frame(self)
        top.pack(fill="x", padx=6, pady=6)
        tk.Button(top, text="① Single Table", font=FONT,
                  command=lambda: self._diff("single")).pack(side="left", padx=3)
        tk.Button(top, text="② Neighbor", font=FONT,
                  command=lambda: self._diff("neighbor")).pack(side="left", padx=3)
        tk.Button(top, text="③ Two-Side", font=FONT,
                  command=lambda: self._diff("two_side")).pack(side="left", padx=3)
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        tk.Button(top, text="AB 人工審核（用左表）", font=FONT,
                  command=self._ab_review).pack(side="left", padx=3)

        mid = tk.Frame(self)
        mid.pack(fill="both", expand=True, padx=6, pady=6)
        self.left_in = InputSection(mid, "左表格（原始 / ori）")
        self.right_in = InputSection(mid, "右表格（修改 / new）")
        self.left_in.pack(side="left", fill="both", expand=True, padx=(0, 3))
        self.right_in.pack(side="left", fill="both", expand=True, padx=(3, 0))

    def _diff(self, mode):
        dfl, dfr = self.left_in.df, self.right_in.df
        kl, kr = self.left_in.key_column, self.right_in.key_column
        if dfl is None or dfr is None:
            messagebox.showinfo("提示", "請先在左右兩側各載入一份 Excel。", parent=self)
            return
        if not kl or not kr:
            messagebox.showinfo("提示", "請先在左右兩側各選一個主鍵。", parent=self)
            return
        try:
            if mode == "single":
                open_single(self, dfl, dfr, kl, kr)
            elif mode == "neighbor":
                open_neighbor(self, dfl, dfr, kl, kr)
            else:
                TwoSideWindow(self, dfl, dfr, kl, kr)
        except Exception as e:
            messagebox.showerror("比對失敗", f"比對失敗（常見原因：主鍵有重複值）：\n{e}", parent=self)

    def _ab_review(self):
        if self.left_in.df is None:
            messagebox.showinfo("提示", "請先在左表載入資料。", parent=self)
            return
        ABReviewWindow(self, self.left_in.df)
