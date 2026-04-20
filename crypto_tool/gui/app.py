"""CryptoTool Pro — main application window."""

from __future__ import annotations

import sys
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from .theme import FONT_TITLE, FONT_BODY, FONT_SMALL, PAD
from .tab_file import FileTab
from .tab_text import TextTab
from .tab_mixture import MixtureTab
from .tab_largefile import LargeFileTab


APP_TITLE = "CryptoTool Pro"
APP_SIZE = (1080, 780)
APP_MIN = (900, 650)
THEME = "darkly"


class CryptoToolApp:
    def __init__(self):
        self.root = ttk.Window(
            title=APP_TITLE,
            themename=THEME,
            size=APP_SIZE,
            minsize=APP_MIN,
        )
        self.root.place_window_center()
        self._status_var = tk.StringVar(value="Ready")
        self._build_ui()

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────
        hdr = ttk.Frame(self.root, padding=(PAD, 8))
        hdr.pack(fill=X)
        ttk.Label(
            hdr,
            text="🔐  CryptoTool Pro",
            font=("Segoe UI", 16, "bold"),
        ).pack(side=LEFT)
        ttk.Label(
            hdr,
            text="Encrypt · Decrypt · Protect",
            font=FONT_SMALL,
            bootstyle="secondary",
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
        nb.add(tab3, text="  🔗  Mixture  ")
        nb.add(tab4, text="  📦  Large File  ")

        # ── Status bar ────────────────────────────────────────────────
        status = ttk.Frame(self.root, padding=(PAD, 4))
        status.pack(fill=X, side=BOTTOM)
        ttk.Label(
            status, textvariable=self._status_var,
            font=FONT_SMALL, bootstyle="secondary",
        ).pack(side=LEFT)
        ttk.Label(
            status, text="v1.0.0",
            font=FONT_SMALL, bootstyle="secondary",
        ).pack(side=RIGHT)

    def run(self):
        self.root.mainloop()
