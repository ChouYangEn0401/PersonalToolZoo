"""collect_params — build a modal parameter dialog straight from an Operation's
Param specs. This is the MVC payoff: the SAME registry spec drives both this GUI
dialog and the CLI, so no operation's inputs are described twice.

Supported Param kinds: columns / column / choice / text / int / bool / mapping /
table (loads another Excel via loaders).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from . import loaders

FONT = ("Microsoft JhengHei", 10)


def collect_params(parent, operation, columns):
    """Return {param_name: value} or None if cancelled. *columns* = current
    table's column names (for column/columns/mapping kinds)."""
    if not operation.params:
        return {}
    dlg = _ParamDialog(parent, operation, columns)
    return dlg.result


class _ParamDialog(tk.Toplevel):
    def __init__(self, parent, operation, columns):
        super().__init__(parent)
        self.title(operation.label)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self._op = operation
        self._columns = list(columns)
        self._widgets = {}   # name -> (kind, getter)

        body = tk.Frame(self, padx=12, pady=10)
        body.pack(fill="both", expand=True)
        for p in operation.params:
            self._build_row(body, p)

        bar = tk.Frame(self)
        bar.pack(pady=(0, 10))
        tk.Button(bar, text="確定", width=10, command=self._ok).pack(side="left", padx=5)
        tk.Button(bar, text="取消", width=10, command=self.destroy).pack(side="left", padx=5)
        self.wait_window()

    def _build_row(self, body, p):
        frame = tk.LabelFrame(body, text=p.label + ("" if p.required else "（可選）"),
                              font=FONT, padx=6, pady=4)
        frame.pack(fill="x", pady=4)

        if p.kind == "columns":
            lb = tk.Listbox(frame, selectmode=tk.MULTIPLE, exportselection=False,
                            height=min(8, max(3, len(self._columns))), font=FONT)
            for c in self._columns:
                lb.insert(tk.END, c)
            lb.pack(fill="x")
            self._widgets[p.name] = ("columns", lambda lb=lb: [lb.get(i) for i in lb.curselection()])

        elif p.kind == "column":
            var = tk.StringVar(value=self._columns[0] if self._columns else "")
            ttk.Combobox(frame, textvariable=var, values=self._columns,
                         state="readonly", font=FONT).pack(fill="x")
            self._widgets[p.name] = ("column", var.get)

        elif p.kind == "choice":
            var = tk.StringVar(value=p.default or (p.choices[0] if p.choices else ""))
            ttk.Combobox(frame, textvariable=var, values=p.choices,
                         state="readonly", font=FONT).pack(fill="x")
            self._widgets[p.name] = ("choice", var.get)

        elif p.kind == "bool":
            var = tk.BooleanVar(value=bool(p.default))
            tk.Checkbutton(frame, text="是", variable=var, font=FONT).pack(anchor="w")
            self._widgets[p.name] = ("bool", var.get)

        elif p.kind == "int":
            var = tk.StringVar(value=str(p.default) if p.default is not None else "")
            tk.Entry(frame, textvariable=var, font=FONT).pack(fill="x")
            self._widgets[p.name] = ("int", var.get)

        elif p.kind == "mapping":
            # one entry per column prefilled with its name; changed ones -> mapping
            inner = tk.Frame(frame)
            inner.pack(fill="x")
            entries = {}
            for c in self._columns:
                row = tk.Frame(inner)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=c, width=18, anchor="w", font=FONT).pack(side="left")
                tk.Label(row, text="→", font=FONT).pack(side="left")
                e = tk.Entry(row, font=FONT)
                e.insert(0, c)
                e.pack(side="left", fill="x", expand=True)
                entries[c] = e
            self._widgets[p.name] = ("mapping",
                                     lambda entries=entries: {old: e.get() for old, e in entries.items()
                                                              if e.get() and e.get() != old})

        elif p.kind == "table":
            state = {"df": None, "name": ""}
            lbl = tk.Label(frame, text="（尚未選擇檔案）", font=FONT, fg="#888")

            def pick(state=state, lbl=lbl):
                df, name = loaders.load_excel(self)
                if df is not None:
                    state["df"], state["name"] = df, name
                    lbl.config(text=name, fg="#080")
            tk.Button(frame, text="選擇 Excel…", command=pick, font=FONT).pack(anchor="w")
            lbl.pack(anchor="w")
            self._widgets[p.name] = ("table", lambda state=state: state["df"])

        else:  # text
            var = tk.StringVar(value=str(p.default) if p.default is not None else "")
            tk.Entry(frame, textvariable=var, font=FONT).pack(fill="x")
            self._widgets[p.name] = ("text", var.get)

    def _ok(self):
        values = {}
        for p in self._op.params:
            kind, getter = self._widgets[p.name]
            v = getter()
            if kind == "int":
                if str(v).strip() == "":
                    v = None
                else:
                    try:
                        v = int(v)
                    except ValueError:
                        messagebox.showerror("參數錯誤", f"「{p.label}」需為整數。", parent=self)
                        return
            if p.required and (v is None or v == "" or v == [] or v == {}):
                messagebox.showerror("參數錯誤", f"請填寫「{p.label}」。", parent=self)
                return
            # optional empty columns -> None (e.g. dedup subset)
            if kind == "columns" and not v:
                v = None
            values[p.name] = v
        self.result = values
        self.destroy()
