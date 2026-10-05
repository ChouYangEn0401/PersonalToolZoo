import tkinter as tk
from tkinter import ttk

import sv_ttk

from gui.tabs.quick_tab import QuickTab
from gui.tabs.image_tab import ImageTab
from gui.tabs.video_tab import VideoTab
from gui.tabs.extractor_tab import ExtractorTab
from gui.tabs.pdf_maker_tab import PdfMakerTab
from gui.tabs.pdf_extract_tab import PdfExtractTab
from gui.tabs.table_tab import TableTab
from version import __version__

try:
    from tkinterdnd2 import TkinterDnD
except ImportError:          # 沒裝 tkinterdnd2：其他分頁照常，快速拖放分頁會顯示提示
    TkinterDnD = None

_TABS = [
    ("⚡  快速拖放", QuickTab),     # 原本獨立的 Quick Converter
    ("🖼  圖片", ImageTab),
    ("🎬  影片", VideoTab),
    ("✂  影片擷取", ExtractorTab),
    ("📄  圖片→PDF", PdfMakerTab),
    ("📋  PDF 轉換", PdfExtractTab),
    ("📊  表格轉換", TableTab),
]


class MainWindow:
    def __init__(self):
        # 拖放要用 TkinterDnD 的視窗（它會把 tkdnd 載入 Tcl）
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title(f"Super File Converter v{__version__}")
        self.root.geometry("960x700")
        self.root.minsize(820, 560)
        self._dark_mode = False
        sv_ttk.set_theme("light")
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Header bar
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=12, pady=(10, 0))

        ttk.Label(
            header,
            text=f"⚡  Super File Converter  v{__version__}",
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        self._theme_btn = ttk.Button(
            header,
            text="🌙  深色模式",
            command=self._toggle_theme,
            width=12,
        )
        self._theme_btn.pack(side="right")

        ttk.Separator(self.root, orient="horizontal").pack(
            fill="x", padx=12, pady=(8, 0)
        )

        # Notebook
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=10)

        for label, cls in _TABS:
            tab = cls(notebook, self.root)
            notebook.add(tab, text=f"  {label}  ")

    # ── Theme toggle ─────────────────────────────────────────────────────────

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        sv_ttk.set_theme("dark" if self._dark_mode else "light")
        self._theme_btn.config(
            text=("☀  淺色模式" if self._dark_mode else "🌙  深色模式")
        )

    def run(self):
        self.root.mainloop()
