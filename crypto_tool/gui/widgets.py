"""Reusable custom widgets for CryptoTool Pro."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from .theme import (
    FONT_BODY, FONT_SMALL, FONT_SUBTITLE, PAD,
    ACCENT_ENCRYPT, ACCENT_DECRYPT, FG_MUTED,
)


# ── File selector with browse button ─────────────────────────────────────

class FileSelector(ttk.Frame):
    """A labelled file-path entry with a Browse button."""

    def __init__(
        self,
        parent,
        label: str = "File",
        filetypes: list[tuple[str, str]] | None = None,
        save: bool = False,
        **kw,
    ):
        super().__init__(parent, **kw)
        self._filetypes = filetypes or [("All files", "*.*")]
        self._save = save
        self.path_var = tk.StringVar()

        ttk.Label(self, text=label, font=FONT_BODY).pack(anchor=W)
        row = ttk.Frame(self)
        row.pack(fill=X, pady=(2, 0))
        self._entry = ttk.Entry(row, textvariable=self.path_var, font=FONT_BODY)
        self._entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        ttk.Button(
            row, text="Browse", bootstyle="outline",
            command=self._browse, width=8,
        ).pack(side=RIGHT)

    def _browse(self):
        if self._save:
            p = filedialog.asksaveasfilename(filetypes=self._filetypes)
        else:
            p = filedialog.askopenfilename(filetypes=self._filetypes)
        if p:
            self.path_var.set(p)

    def get(self) -> str:
        return self.path_var.get().strip()


class DirSelector(ttk.Frame):
    """Directory selector with browse button."""

    def __init__(self, parent, label: str = "Directory", **kw):
        super().__init__(parent, **kw)
        self.path_var = tk.StringVar()

        ttk.Label(self, text=label, font=FONT_BODY).pack(anchor=W)
        row = ttk.Frame(self)
        row.pack(fill=X, pady=(2, 0))
        self._entry = ttk.Entry(row, textvariable=self.path_var, font=FONT_BODY)
        self._entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        ttk.Button(
            row, text="Browse", bootstyle="outline",
            command=self._browse, width=8,
        ).pack(side=RIGHT)

    def _browse(self):
        p = filedialog.askdirectory()
        if p:
            self.path_var.set(p)

    def get(self) -> str:
        return self.path_var.get().strip()


# ── Password frame (text entry OR file selector) ─────────────────────────

KEY_TYPES = ["text", "file", "image", "video", "bytefile"]

_FILE_FILTERS: dict[str, list[tuple[str, str]]] = {
    "file":     [("All files", "*.*")],
    "image":    [("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("All files", "*.*")],
    "video":    [("Videos", "*.mp4 *.mkv *.avi *.mov *.wmv *.flv"), ("All files", "*.*")],
    "bytefile": [("ByteFile", "*.bytefile"), ("All files", "*.*")],
}


class PasswordFrame(ttk.Labelframe):
    """Password entry with key-type selector and show/hide toggle."""

    def __init__(self, parent, title: str = "Password", **kw):
        super().__init__(parent, text=title, padding=PAD, **kw)

        self.key_type_var = tk.StringVar(value="text")
        self.password_var = tk.StringVar()
        self.file_path_var = tk.StringVar()
        self._show = False

        # Row 1 — key type
        r1 = ttk.Frame(self)
        r1.pack(fill=X, pady=(0, 6))
        ttk.Label(r1, text="Key type:", font=FONT_BODY).pack(side=LEFT)
        combo = ttk.Combobox(
            r1, textvariable=self.key_type_var, values=KEY_TYPES,
            state="readonly", width=10, font=FONT_BODY,
        )
        combo.pack(side=LEFT, padx=(6, 0))
        combo.bind("<<ComboboxSelected>>", self._on_type_change)

        # Row 2 — text password
        self._text_frame = ttk.Frame(self)
        self._text_frame.pack(fill=X)
        self._pw_entry = ttk.Entry(
            self._text_frame, textvariable=self.password_var,
            show="●", font=FONT_BODY,
        )
        self._pw_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 4))
        self._toggle_btn = ttk.Button(
            self._text_frame, text="👁", width=3,
            bootstyle="outline-secondary", command=self._toggle_show,
        )
        self._toggle_btn.pack(side=RIGHT)

        # Row 2b — file password (hidden by default)
        self._file_frame = ttk.Frame(self)
        self._file_entry = ttk.Entry(
            self._file_frame, textvariable=self.file_path_var,
            font=FONT_BODY, state="readonly",
        )
        self._file_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 4))
        self._file_btn = ttk.Button(
            self._file_frame, text="Select key file",
            bootstyle="outline", command=self._browse_key_file,
        )
        self._file_btn.pack(side=RIGHT)

    def _on_type_change(self, _event=None):
        kt = self.key_type_var.get()
        if kt == "text":
            self._file_frame.pack_forget()
            self._text_frame.pack(fill=X)
        else:
            self._text_frame.pack_forget()
            self._file_frame.pack(fill=X)

    def _toggle_show(self):
        self._show = not self._show
        self._pw_entry.config(show="" if self._show else "●")
        self._toggle_btn.config(text="🔒" if self._show else "👁")

    def _browse_key_file(self):
        kt = self.key_type_var.get()
        ft = _FILE_FILTERS.get(kt, [("All files", "*.*")])
        p = filedialog.askopenfilename(filetypes=ft)
        if p:
            self.file_path_var.set(p)

    def get_source(self) -> str:
        """Return password text or file path."""
        if self.key_type_var.get() == "text":
            return self.password_var.get()
        return self.file_path_var.get()

    def get_key_type(self) -> str:
        return self.key_type_var.get()


# ── Collapsible panel ─────────────────────────────────────────────────────

class CollapsiblePanel(ttk.Frame):
    """Panel that can be toggled open/closed."""

    def __init__(self, parent, title: str = "Advanced Settings", **kw):
        super().__init__(parent, **kw)
        self._open = False

        self._toggle_btn = ttk.Button(
            self, text=f"▸  {title}", bootstyle="link",
            command=self.toggle,
        )
        self._toggle_btn.pack(fill=X, anchor=W)

        self.content = ttk.Frame(self, padding=(PAD, 4))
        self._title = title

    def toggle(self):
        self._open = not self._open
        if self._open:
            self.content.pack(fill=X, pady=(0, 4))
            self._toggle_btn.config(text=f"▾  {self._title}")
        else:
            self.content.pack_forget()
            self._toggle_btn.config(text=f"▸  {self._title}")


# ── Status bar ────────────────────────────────────────────────────────────

class StatusBar(ttk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.var = tk.StringVar(value="Ready")
        self._label = ttk.Label(
            self, textvariable=self.var, font=FONT_SMALL,
            bootstyle="inverse-dark", padding=(8, 4),
        )
        self._label.pack(fill=X)

    def set(self, msg: str):
        self.var.set(msg)
        self.update_idletasks()
