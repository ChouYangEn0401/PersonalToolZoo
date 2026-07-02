"""ColoredTable — InfinityTable + a diff-colouring layer.

InfinityTable.refresh() hard-codes each cell's background (selection only) and a
scroll (_goto) doesn't even emit AFTER_REFRESH, so we recolour the *visible*
label pool from both AFTER_REFRESH and AFTER_SCROLL, and veto selection via
ON_ROW_SELECT -> CANCEL so clicks don't repaint over the diff colours.

Styles are ``{(row_position, col_name): {"bg","fg","font"}}`` and header styles
``{col_name: {"bg"}}``; fonts are honoured so the restored Two-Side styling can
use bold / underline exactly like the original tool.
"""
from __future__ import annotations

import tkinter as tk

from infinity_treeview import InfinityTable, Events, CANCEL

from ..core.diff import WHITE, DEFAULT_HEADER

_DEFAULT_FONT = ("TkDefaultFont", 11)


class ColoredTable(tk.Frame):
    def __init__(self, parent, df, cell_styles=None, header_styles=None,
                 *, visible_rows=18, width=760, data_name="table"):
        super().__init__(parent)
        self.cell_styles = cell_styles or {}
        self.header_styles = header_styles or {}
        self.table = InfinityTable(
            self, df,
            visible_rows=visible_rows,
            selection_mode="single",
            data_name=data_name,
            entire_table_width=width,
            hooks={
                Events.AFTER_REFRESH: self._recolor,
                Events.AFTER_SCROLL: self._recolor,
                Events.ON_ROW_SELECT: lambda *_a: CANCEL,
            },
        )
        self.table.pack(fill="both", expand=True)
        self.after_idle(self._recolor)

    def update_data(self, df, cell_styles=None, header_styles=None):
        if cell_styles is not None:
            self.cell_styles = cell_styles
        if header_styles is not None:
            self.header_styles = header_styles
        self.table.set_data(df, keep_widths=False)  # triggers AFTER_REFRESH -> recolour

    def recolor(self, cell_styles=None, header_styles=None):
        if cell_styles is not None:
            self.cell_styles = cell_styles
        if header_styles is not None:
            self.header_styles = header_styles
        self.table.refresh()

    def _recolor(self, *_args):
        # AFTER_REFRESH can fire during InfinityTable.__init__ before self.table
        # is bound — tolerate that.
        table = getattr(self, "table", None)
        view = getattr(table, "view", None)
        if view is None or not view.rows:
            return
        headers = table.model.headers
        nrows = table.model.nrows
        start = table.start_index

        for ci, name in enumerate(headers):
            if ci < len(view.header_labels):
                st = self.header_styles.get(name)
                view.header_labels[ci].config(bg=(st["bg"] if st else DEFAULT_HEADER))

        for vi, row_labels in enumerate(view.rows):
            raw = start + vi
            for ci, lbl in enumerate(row_labels):
                if raw >= nrows or ci >= len(headers):
                    continue
                st = self.cell_styles.get((raw, headers[ci]))
                if st:
                    lbl.config(bg=st.get("bg", WHITE), fg=st.get("fg", "black"),
                               font=st.get("font", _DEFAULT_FONT))
                else:
                    lbl.config(bg=WHITE, fg="black", font=_DEFAULT_FONT)
