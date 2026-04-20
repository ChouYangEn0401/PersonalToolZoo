"""CryptoTool Pro — main application window."""

from __future__ import annotations

import sys
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinterdnd2 import TkinterDnD

from .theme import (
    FONT_TITLE, FONT_BODY, FONT_SMALL, PAD,
    GOLD_MID, GOLD_DARK, GOLD_BRIGHT, FG_LIGHT, BG_DARK,
)
from .tab_file import FileTab
from .tab_text import TextTab
from .tab_mixture import MixtureTab
from .tab_largefile import LargeFileTab


APP_TITLE = "CryptoTool Pro"
APP_SIZE  = (1080, 780)
APP_MIN   = (900, 650)
THEME     = "darkly"


def _apply_gold_overrides(style: ttk.Style) -> None:
    """Overlay warm-gold colour tints onto the ttkbootstrap 'darkly' theme."""
    style.configure("TLabelframe.Label",
                    foreground=GOLD_MID, font=("Segoe UI", 10, "bold"))
    style.configure("TLabelframe",     bordercolor=GOLD_DARK)
    style.configure("TSeparator",      background=GOLD_DARK)
    style.configure("TNotebook",       tabmargins=[2, 4, 0, 0])
    style.configure("TNotebook.Tab",   padding=[14, 6],
                    font=("Segoe UI", 10, "bold"))
    style.map("TNotebook.Tab",
              foreground=[("selected", GOLD_BRIGHT), ("", FG_LIGHT)])


class CryptoToolApp:
    def __init__(self):
        # TkinterDnD.Tk() enables drag-and-drop across all child widgets.
        self.root = TkinterDnD.Tk()

        style = ttk.Style(theme=THEME)
        _apply_gold_overrides(style)

        self.root.title(APP_TITLE)
        self.root.geometry(f"{APP_SIZE[0]}x{APP_SIZE[1]}")
        self.root.minsize(*APP_MIN)

        # Centre on screen
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - APP_SIZE[0]) // 2
        y  = (sh - APP_SIZE[1]) // 2
        self.root.geometry(f"{APP_SIZE[0]}x{APP_SIZE[1]}+{x}+{y}")

        self._status_var = tk.StringVar(value="Ready")
        self._build_ui()

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────
        hdr = ttk.Frame(self.root, padding=(PAD, 8))
        hdr.pack(fill=X)
        tk.Label(
            hdr,
            text="🔐  CryptoTool Pro",
            font=("Segoe UI", 16, "bold"),
            foreground=GOLD_MID,
            background=style_bg(self.root),
        ).pack(side=LEFT)
        tk.Label(
            hdr,
            text="Encrypt · Decrypt · Protect",
            font=FONT_SMALL,
            foreground=GOLD_DARK,
            background=style_bg(self.root),
        ).pack(side=LEFT, padx=(12, 0))

        ttk.Separator(self.root).pack(fill=X)

        # ── Notebook (tabs) ───────────────────────────────────────────
        nb = ttk.Notebook(self.root, bootstyle="dark")
        nb.pack(fill=BOTH, expand=True, padx=PAD, pady=(PAD, 0))

        tab1 = FileTab(nb, self._status_var)
        tab2 = TextTab(nb, self._status_var)
        tab3 = MixtureTab(nb, self._status_var)
        tab4 = LargeFileTab(nb, self._status_var)

        nb.add(tab1, text="  📁  File  ")
        nb.add(tab2, text="  📝  Text  ")
        nb.add(tab3, text="  🔗  Mixture  --UNTESTED")
        nb.add(tab4, text="  📦  Large File  --UNTESTED")

        # ── Status bar ────────────────────────────────────────────────
        status = ttk.Frame(self.root, padding=(PAD, 4))
        status.pack(fill=X, side=BOTTOM)
        ttk.Separator(self.root).pack(fill=X, side=BOTTOM)
        ttk.Label(
            status, textvariable=self._status_var,
            font=FONT_SMALL, bootstyle="secondary",
        ).pack(side=LEFT)
        tk.Label(
            status, text="v1.1.0",
            font=FONT_SMALL,
            foreground=GOLD_DARK,
            background=style_bg(self.root),
        ).pack(side=RIGHT)

    def run(self):
        self.root.mainloop()


def style_bg(root) -> str:
    """Return the current theme's background colour for plain tk.Label."""
    try:
        return ttk.Style().colors.bg
    except Exception:
        return "#212529"
