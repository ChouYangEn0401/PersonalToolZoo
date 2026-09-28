"""Advanced Excel Tool — GUI entry point.

一個分頁式 Excel 工具，三個工作台：🧹 核心整理 / 🔗 合併 / 🔍 比較，
以 infinity_treeview.InfinityTable 為表格核心、core/gui 分層（MVC + 操作註冊表）。

    python GUI_AdvancedExcelTool.py
"""
from __future__ import annotations

import tkinter as tk

try:
    from tkinterdnd2 import TkinterDnD
    _HAS_DND = True
except ImportError:  # pragma: no cover
    _HAS_DND = False
    TkinterDnD = None

from excel_tool.gui import AdvancedExcelApp


def main():
    root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
    AdvancedExcelApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
