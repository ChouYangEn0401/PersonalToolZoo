"""Reusable custom widgets for CryptoTool Pro."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinterdnd2 import DND_FILES

from .theme import (
    FONT_BODY, FONT_SMALL, FONT_SUBTITLE, PAD,
    ACCENT_ENCRYPT, ACCENT_DECRYPT, FG_MUTED,
    GOLD_MID, GOLD_DARK, GOLD_BRIGHT, BG_CARD, DND_ACTIVE,
)


# ── Algorithm bar layout & short names ───────────────────────────────────

_ALGO_ROWS: list[list[str]] = [
    ["AES-256-CBC", "AES-256-GCM", "ChaCha20-Poly1305", "Blowfish-CBC"],
    ["3DES-CBC",    "XOR",          "Base64"],
]

_SHORT_NAMES: dict[str, str] = {
    "AES-256-CBC":       "AES · CBC",
    "AES-256-GCM":       "AES · GCM",
    "ChaCha20-Poly1305": "ChaCha20",
    "Blowfish-CBC":      "Blowfish",
    "3DES-CBC":          "3DES",
    "XOR":               "XOR",
    "Base64":            "Base64",
}


class AlgoBar(ttk.Frame):
    """Segmented algorithm selector — gold-highlighted active button, hover glow."""

    _BG_ACT = "#C9A84C"   # GOLD_MID — active selection
    _FG_ACT = "#141210"   # near-black text on gold
    _BG_OFF = "#252015"   # dark warm — inactive
    _FG_OFF = "#9A8866"   # FG_MUTED
    _BG_HOV = "#3D3519"   # DND_ACTIVE — hover glow

    def __init__(
        self,
        parent,
        variable: tk.StringVar,
        algorithms: list[str] | None = None,
        **kw,
    ):
        super().__init__(parent, **kw)
        self._var = variable
        _allowed = set(algorithms) if algorithms else set(_SHORT_NAMES.keys())
        self._btns: dict[str, tk.Button] = {}

        for row_algos in _ALGO_ROWS:
            row_items = [a for a in row_algos if a in _allowed]
            if not row_items:
                continue
            row_frame = ttk.Frame(self)
            row_frame.pack(fill=X, pady=1)
            for algo in row_items:
                short = _SHORT_NAMES.get(algo, algo)
                btn = tk.Button(
                    row_frame,
                    text=short,
                    bg=self._BG_OFF,
                    fg=self._FG_OFF,
                    activebackground=self._BG_HOV,
                    activeforeground=self._FG_OFF,
                    relief=FLAT,
                    bd=0,
                    font=FONT_SMALL,
                    padx=10,
                    pady=5,
                    cursor="hand2",
                    command=lambda a=algo: self._select(a),
                )
                btn.pack(side=LEFT, padx=(0, 2))
                btn.bind("<Enter>", lambda e, b=btn, a=algo: self._on_enter(b, a))
                btn.bind("<Leave>", lambda e, b=btn, a=algo: self._on_leave(b, a))
                self._btns[algo] = btn

        variable.trace_add("write", lambda *_: self._sync())
        self._sync()

    def _select(self, algo: str):
        self._var.set(algo)

    def _sync(self, *_):
        current = self._var.get()
        for algo, btn in self._btns.items():
            if algo == current:
                btn.config(bg=self._BG_ACT, fg=self._FG_ACT)
            else:
                btn.config(bg=self._BG_OFF, fg=self._FG_OFF)

    def _on_enter(self, btn: tk.Button, algo: str):
        if self._var.get() != algo:
            btn.config(bg=self._BG_HOV)

    def _on_leave(self, btn: tk.Button, algo: str):
        if self._var.get() != algo:
            btn.config(bg=self._BG_OFF)

    def set(self, algo: str):
        """Programmatically set the selected algorithm."""
        if algo in self._btns:
            self._var.set(algo)


# ── Drag-and-drop path cleaner ────────────────────────────────────────────

def _clean_dnd_path(raw: str) -> str:
    """Normalise a path string returned by tkinterdnd2 on Windows.

    Handles:
    - Curly-brace wrapping for paths with spaces: ``{C:/my path/file}``
    - Multiple-file drops (only the first path is returned)
    - Surrounding whitespace
    """
    raw = raw.strip()
    if raw.startswith("{"):
        # Extract first group
        end = raw.find("}")
        raw = raw[1:end] if end != -1 else raw[1:]
    elif " " in raw:
        # Multiple space-separated paths: take the first one
        raw = raw.split()[0]
    return raw


# ── File selector with browse button ─────────────────────────────────────

class FileSelector(ttk.Frame):
    """A labelled file-path entry with a Browse button and drag-and-drop support."""

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

        # ── Drag-and-drop ─────────────────────────────────────────────
        self._entry.drop_target_register(DND_FILES)
        self._entry.dnd_bind("<<Drop>>", self._on_drop)
        self._entry.dnd_bind("<<DragEnter>>", self._on_drag_enter)
        self._entry.dnd_bind("<<DragLeave>>", self._on_drag_leave)

    def _on_drop(self, event):
        path = _clean_dnd_path(event.data)
        if path:
            self.path_var.set(path)
        self._entry.config(foreground="")

    def _on_drag_enter(self, event):
        self._entry.config(foreground=GOLD_MID)

    def _on_drag_leave(self, event):
        self._entry.config(foreground="")

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
    """Directory selector with browse button and drag-and-drop support."""

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

        # ── Drag-and-drop ─────────────────────────────────────────────
        self._entry.drop_target_register(DND_FILES)
        self._entry.dnd_bind("<<Drop>>", self._on_drop)
        self._entry.dnd_bind("<<DragEnter>>", lambda e: self._entry.config(foreground=GOLD_MID))
        self._entry.dnd_bind("<<DragLeave>>", lambda e: self._entry.config(foreground=""))

    def _on_drop(self, event):
        path = _clean_dnd_path(event.data)
        if path:
            p = Path(path)
            # Accept both a folder drop and a file drop (use its parent dir)
            self.path_var.set(str(p if p.is_dir() else p.parent))
        self._entry.config(foreground="")

    def _browse(self):
        p = filedialog.askdirectory()
        if p:
            self.path_var.set(p)

    def get(self) -> str:
        return self.path_var.get().strip()


# ── Password frame (text entry OR file selector) ─────────────────────────

_FILE_FILTERS: dict[str, list[tuple[str, str]]] = {
    "file":     [("All files", "*.*")],
    "image":    [("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("All files", "*.*")],
    "video":    [("Videos", "*.mp4 *.mkv *.avi *.mov *.wmv *.flv"), ("All files", "*.*")],
    "bytefile": [("ByteFile", "*.bytefile"), ("All files", "*.*")],
}

# Accept plain text files as a key source (one line or full document)
KEY_TYPES = ["text", "file", "image", "video", "bytefile", "txtfile"]

_FILE_FILTERS.update({
    "txtfile": [("Text files", "*.txt *.md *.text"), ("All files", "*.*")],
})


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

        # ── Drag-and-drop for file key entry ──────────────────────────
        self._file_entry.drop_target_register(DND_FILES)
        self._file_entry.dnd_bind("<<Drop>>", self._on_file_drop)
        self._file_entry.dnd_bind(
            "<<DragEnter>>", lambda e: self._file_entry.config(state=NORMAL) or
            self._file_entry.config(foreground=GOLD_MID) or
            self._file_entry.config(state="readonly")
        )
        self._file_entry.dnd_bind(
            "<<DragLeave>>", lambda e: None
        )

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

    def _on_file_drop(self, event):
        path = _clean_dnd_path(event.data)
        if path:
            self.file_path_var.set(path)

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


# ── Tooltip ───────────────────────────────────────────────────────────────

class Tooltip:
    """Lightweight tooltip that pops up near a widget on hover.

    Usage::

        Tooltip(widget, "Helpful description here")
    """

    _DELAY = 500       # ms before appearing
    _BG    = "#2A2010"
    _FG    = "#FFD580"
    _BORDER = "#7A5C1E"

    def __init__(self, widget: tk.Widget, text: str):
        self._widget = widget
        self._text   = text
        self._win: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>",   self._schedule,  add="+")
        widget.bind("<Leave>",   self._cancel,    add="+")
        widget.bind("<Button>",  self._cancel,    add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self._widget.after(self._DELAY, self._show)

    def _cancel(self, _event=None):
        if self._after_id:
            self._widget.after_cancel(self._after_id)
            self._after_id = None
        if self._win:
            self._win.destroy()
            self._win = None

    def _show(self):
        if self._win:
            return
        w = self._widget
        x = w.winfo_rootx() + w.winfo_width() // 2
        y = w.winfo_rooty() + w.winfo_height() + 6
        self._win = tw = tk.Toplevel(w)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            tw,
            text=self._text,
            wraplength=340,
            justify=LEFT,
            background=self._BG,
            foreground=self._FG,
            relief="solid",
            borderwidth=1,
            highlightbackground=self._BORDER,
            highlightthickness=1,
            font=FONT_SMALL,
            padx=8,
            pady=5,
        )
        lbl.pack()


# ── Status bar ────────────────────────────────────────────────────────────────────

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
