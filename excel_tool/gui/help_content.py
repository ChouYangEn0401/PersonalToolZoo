"""Teaching/help content for operations (ported from FastEditor's help_data) +
a help window. Right-click an operation button to see: what it does, the steps,
and a before → after mini example.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

FONT = ("Microsoft JhengHei", 10)

HELP = {
    "pivot": {
        "title": "建立透視表",
        "summary": "把某一欄的類別轉成多個新欄位，並對值做聚合計算，快速產生摘要報告。",
        "steps": [
            "選擇「區域」作為索引 (index) 欄位。",
            "選擇「產品」作為欄位 (columns) 欄位。",
            "選擇「銷售額」作為值 (values) 欄位。",
            "選擇「sum」作為聚合函數。",
        ],
        "input": pd.DataFrame({"區域": ["東", "東", "西", "西"], "產品": ["A", "B", "A", "C"],
                               "銷售額": [100, 150, 200, 50]}),
        "output": pd.DataFrame({"區域": ["東", "西"], "A": [100, 200],
                                "B": [150, None], "C": [None, 50]}),
    },
    "aggregate": {
        "title": "合併濃縮資料",
        "summary": "依分組欄位把多列收合成一列，並把指定欄位的值用分隔符號串起來（一對多 → 一對一）。",
        "steps": [
            "選擇「訂單ID」「產品」作為分組欄位。",
            "選擇「顏色」作為要合併的欄位。",
            "輸入逗號「,」作為分隔符號。",
        ],
        "input": pd.DataFrame({"訂單ID": [101, 101, 102, 102, 102],
                               "產品": ["T-Shirt", "T-Shirt", "帽子", "帽子", "帽子"],
                               "顏色": ["紅色", "藍色", "黑色", "白色", "灰色"]}),
        "output": pd.DataFrame({"訂單ID": [101, 102], "產品": ["T-Shirt", "帽子"],
                                "顏色": ["紅色,藍色", "黑色,白色,灰色"]}),
    },
}


def _mini_table(parent, df, title):
    frame = tk.LabelFrame(parent, text=title, font=FONT, padx=4, pady=4)
    tv = ttk.Treeview(frame, columns=list(df.columns), show="headings", height=min(6, len(df)))
    for c in df.columns:
        tv.heading(c, text=str(c))
        tv.column(c, width=80, anchor="w")
    for _, row in df.iterrows():
        tv.insert("", "end", values=["" if pd.isna(v) else v for v in row])
    tv.pack()
    return frame


def show_help(parent, operation):
    data = HELP.get(operation.help)
    win = tk.Toplevel(parent)
    win.title(f"說明 — {operation.label}")
    win.transient(parent)
    tk.Label(win, text=operation.label, font=("Microsoft JhengHei", 14, "bold")).pack(pady=(10, 4))
    if not data:
        tk.Label(win, text="（此操作尚無詳細教學）", font=FONT, fg="#888").pack(padx=20, pady=20)
        return
    tk.Label(win, text=data["summary"], font=FONT, wraplength=460,
             justify="left").pack(padx=16, pady=4)
    steps = tk.LabelFrame(win, text="步驟", font=FONT, padx=8, pady=4)
    steps.pack(fill="x", padx=16, pady=6)
    for i, s in enumerate(data["steps"], 1):
        tk.Label(steps, text=f"{i}. {s}", font=FONT, anchor="w", justify="left",
                 wraplength=430).pack(anchor="w")
    ex = tk.Frame(win)
    ex.pack(padx=16, pady=8)
    _mini_table(ex, data["input"], "輸入").pack(side="left", padx=6)
    tk.Label(ex, text="→", font=("Microsoft JhengHei", 16)).pack(side="left")
    _mini_table(ex, data["output"], "輸出").pack(side="left", padx=6)
