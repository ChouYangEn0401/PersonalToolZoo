"""Advanced Excel Tool — GUI entry point.

一個分頁式 Excel 工具（整理單檔 / 比對雙檔 / 合併 / AB 比對 / 條件清理 / 集合運算），
以 infinity_treeview.InfinityTable 為表格核心、core/gui 分層（MVC）。

    python GUI_AdvancedExcelTool.py

Phase 1：僅骨架 + 空殼分頁，供審視架構。
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
