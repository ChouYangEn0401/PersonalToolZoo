"""Shared load helpers: Excel loading with sheet pick, a modal choice dialog,
and optional drag-and-drop registration. Used by every tab.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd

try:
    from tkinterdnd2 import DND_FILES
    _HAS_DND = True
except ImportError:  # pragma: no cover
    _HAS_DND = False
    DND_FILES = None

FONT = ("Microsoft JhengHei", 10)


def ask_choice(parent, title, prompt, choices, initial=None):
    """Modal readonly combobox; returns the chosen string or None."""
    if not choices:
        return None
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    tk.Label(win, text=prompt, font=FONT).pack(padx=12, pady=(12, 4))
    var = tk.StringVar(value=initial or choices[0])
    cb = ttk.Combobox(win, textvariable=var, values=list(choices), state="readonly",
                      font=FONT, width=28)
    cb.pack(padx=12, pady=4)
    cb.current(list(choices).index(var.get()) if var.get() in choices else 0)
    out = {"v": None}
    tk.Button(win, text="確定", width=10,
              command=lambda: (out.__setitem__("v", var.get()), win.destroy())).pack(pady=8)
    cb.bind("<Return>", lambda _e: (out.__setitem__("v", var.get()), win.destroy()))
    win.wait_window()
    return out["v"]


def read_path(parent, path):
    """Read an Excel path; if multi-sheet, ask which. Returns (df, display_name)."""
    try:
        xls = pd.ExcelFile(path)
    except Exception as e:
        messagebox.showerror("讀取錯誤", f"無法開啟檔案：\n{e}", parent=parent)
        return None, None
    sheets = xls.sheet_names
    sheet = sheets[0] if len(sheets) == 1 else ask_choice(
        parent, "選擇 Sheet", "請選擇要載入的工作表：", sheets)
    if sheet is None:
        return None, None
    try:
        df = xls.parse(sheet)
    except Exception as e:
        messagebox.showerror("讀取錯誤", f"讀取工作表「{sheet}」失敗：\n{e}", parent=parent)
        return None, None
    return df, f"{os.path.basename(path)} — {sheet}"


def load_excel(parent):
    """File dialog + sheet pick. Returns (df, display_name) or (None, None)."""
    path = filedialog.askopenfilename(
        filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")], parent=parent)
    if not path:
        return None, None
    return read_path(parent, path)


def bind_drop(widget, on_file):
    """Register drag-and-drop of an Excel file onto *widget* (no-op without DnD)."""
    if not _HAS_DND:
        return
    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", lambda e: _dispatch_drop(widget, e, on_file))
    except Exception:
        pass


def _dispatch_drop(widget, event, on_file):
    for f in widget.tk.splitlist(event.data):
        if f.lower().endswith((".xls", ".xlsx")):
            on_file(f)
            break
