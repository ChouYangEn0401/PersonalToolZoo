"""Reusable custom widgets for CryptoTool Pro."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinterdnd2 import DND_FILES

from core.bytefile import BYTEFILE_EXT
from core.engine import NON_PGP_ALGORITHMS

from .theme import (
    FONT_BODY, FONT_SMALL, FONT_SUBTITLE, PAD,
    ACCENT_ENCRYPT, ACCENT_DECRYPT, FG_MUTED,
    GOLD_MID, GOLD_DARK, GOLD_BRIGHT, BG_CARD, DND_ACTIVE, AMBER,
)


# ── Algorithm bar layout & short names ───────────────────────────────────

_ALGO_ROWS: list[list[str]] = [
    ["AES-256-CBC", "AES-256-GCM", "ChaCha20-Poly1305", "Blowfish-CBC"],
    ["3DES-CBC",    "XOR",          "XOR-FOLD",    "Base64"],
    ["PGP",         "PGP-Multi",    "PGP-Escrow"],
]

_SHORT_NAMES: dict[str, str] = {
    "AES-256-CBC":       "AES · CBC",
    "AES-256-GCM":       "AES · GCM",
    "ChaCha20-Poly1305": "ChaCha20",
    "Blowfish-CBC":      "Blowfish",
    "3DES-CBC":          "3DES",
    "XOR":               "XOR",
    "XOR-FOLD":          "XOR · Fold",
    "Base64":            "Base64",
    "PGP":               "PGP",
    "PGP-Multi":         "PGP · Multi",
    "PGP-Escrow":        "PGP · Escrow",
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
    "bytefile": [("ByteFile", f"*{BYTEFILE_EXT}"), ("All files", "*.*")],
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


# ── PGP key selector row ─────────────────────────────────────────────────────────

class _PGPKeyRow(ttk.Frame):
    """Single PGP key file selector row (public or private key)."""

    def __init__(self, parent, label: str, on_remove=None, **kw):
        super().__init__(parent, **kw)
        self.path_var = tk.StringVar()
        ttk.Label(self, text=label, font=FONT_SMALL, width=11, anchor=W).pack(side=LEFT)
        e = ttk.Entry(self, textvariable=self.path_var, font=FONT_SMALL)
        e.pack(side=LEFT, fill=X, expand=True, padx=(0, 4))
        ttk.Button(
            self, text="Browse", bootstyle="outline", width=7,
            command=self._browse,
        ).pack(side=LEFT, padx=(0, 4))
        if on_remove is not None:
            ttk.Button(
                self, text="✕", width=3, bootstyle="outline-danger",
                command=on_remove,
            ).pack(side=LEFT)
        e.drop_target_register(DND_FILES)
        e.dnd_bind("<<Drop>>", lambda ev: self.path_var.set(_clean_dnd_path(ev.data)))

    def _browse(self):
        p = filedialog.askopenfilename(
            filetypes=[
                ("PEM / Key files", "*.pem *.key *.pub *.txt"),
                ("All files", "*.*"),
            ]
        )
        if p:
            self.path_var.set(p)

    def get_pem(self) -> bytes:
        """Read and return PEM file bytes. Raises ValueError if path is empty."""
        path = self.path_var.get().strip()
        if not path:
            raise ValueError("No PGP key file selected")
        return Path(path).read_bytes()


# ── PGP encrypt panel ─────────────────────────────────────────────────────────────

class PGPEncryptPanel(ttk.Labelframe):
    """Encryption-side PGP panel.

    Shows an inner-cipher selector plus a list of recipient public key entries.
    Supports single / multi / escrow modes via ``set_mode(algo)``.
    """

    def __init__(self, parent, **kw):
        super().__init__(parent, text="🔑  PGP — Asymmetric Wrap", padding=6, **kw)
        self._mode: str = "PGP"
        self._recip_rows: list[_PGPKeyRow] = []

        # ── Inner cipher ──────────────────────────────────────────────
        inner_row = ttk.Frame(self)
        inner_row.pack(fill=X, pady=(0, 6))
        ttk.Label(inner_row, text="Inner cipher:", font=FONT_BODY).pack(side=LEFT)
        # allow 'None' to indicate no inner symmetric encryption
        self.inner_algo_var = tk.StringVar(value="None")
        _ic = ttk.Combobox(
            inner_row, textvariable=self.inner_algo_var,
            values=["None"] + list(NON_PGP_ALGORITHMS), state="readonly", width=20, font=FONT_BODY,
        )
        _ic.pack(side=LEFT, padx=(8, 0))
        Tooltip(_ic, "\"None\" = 原始資料直接封入 PGP 信封（無對稱加密）；其他選項先用對稱加密再封入 PGP")

        # ── Recipient title ───────────────────────────────────────────
        self._recip_title = ttk.Label(self, text="Recipient public key:", font=FONT_BODY)
        self._recip_title.pack(anchor=W, pady=(0, 2))

        self._recip_frame = ttk.Frame(self)
        self._recip_frame.pack(fill=X)

        # ── Add-recipient button (multi / escrow only) ─────────────────
        self._add_btn = ttk.Button(
            self, text="＋ Add recipient",
            bootstyle="outline-primary",
            command=self._add_recip,
        )

        # ── Escrow section widgets (hidden until PGP-Escrow selected) ──
        self._escrow_sep = ttk.Separator(self)
        self._escrow_title = ttk.Label(
            self, text="⚠  Escrow key (third-party master key):",
            font=FONT_BODY, foreground=AMBER,
        )
        self._escrow_key_row: _PGPKeyRow | None = None
        self._escrow_desc = ttk.Label(
            self,
            text="The .isd will be tagged as third-party force-decryptable.",
            font=FONT_SMALL, foreground=FG_MUTED,
        )

        # Seed with 1 non-removable recipient row
        self._add_recip(removable=False)

    # ── Mode switching ────────────────────────────────────────────────

    def set_mode(self, algo: str) -> None:
        """Switch panel UI between 'PGP', 'PGP-Multi', 'PGP-Escrow'."""
        self._mode = algo
        is_multi = algo in ("PGP-Multi", "PGP-Escrow")
        is_escrow = algo == "PGP-Escrow"

        self._recip_title.config(
            text="Recipient public key:" if not is_multi else "Recipient public keys:"
        )

        if is_multi:
            self._add_btn.pack(anchor=W, pady=(4, 0))
        else:
            self._add_btn.pack_forget()
            while len(self._recip_rows) > 1:
                r = self._recip_rows.pop()
                r.destroy()

        if is_escrow:
            self._escrow_sep.pack(fill=X, pady=8)
            self._escrow_title.pack(anchor=W)
            if self._escrow_key_row is None:
                self._escrow_key_row = _PGPKeyRow(self, "Escrow key:", on_remove=None)
            self._escrow_key_row.pack(fill=X, pady=(4, 0))
            self._escrow_desc.pack(anchor=W, pady=(2, 0))
        else:
            self._escrow_sep.pack_forget()
            self._escrow_title.pack_forget()
            if self._escrow_key_row:
                self._escrow_key_row.pack_forget()
            self._escrow_desc.pack_forget()

    # ── Recipient management ──────────────────────────────────────────

    def _add_recip(self, removable: bool = True) -> None:
        placeholder: list[_PGPKeyRow | None] = [None]
        row = _PGPKeyRow(
            self._recip_frame,
            f"Recip #{len(self._recip_rows) + 1}:",
            on_remove=(lambda: self._do_remove(placeholder[0])) if removable else None,
        )
        placeholder[0] = row
        row.pack(fill=X, pady=(0, 2))
        self._recip_rows.append(row)

    def _do_remove(self, row: _PGPKeyRow) -> None:
        if len(self._recip_rows) <= 1:
            return
        row.destroy()
        self._recip_rows.remove(row)
        for i, r in enumerate(self._recip_rows):
            try:
                r.winfo_children()[0].config(text=f"Recip #{i + 1}:")
            except Exception:
                pass

    # ── Data accessors ────────────────────────────────────────────────

    def get_pub_pems(self) -> list[bytes]:
        return [r.get_pem() for r in self._recip_rows]

    def get_escrow_pem(self) -> bytes | None:
        if self._escrow_key_row:
            try:
                p = self._escrow_key_row.path_var.get().strip()
                return Path(p).read_bytes() if p else None
            except Exception:
                return None
        return None

    def get_inner_algo(self) -> str:
        return self.inner_algo_var.get()


# ── PGP decrypt panel ─────────────────────────────────────────────────────────────

class PGPDecryptPanel(ttk.Labelframe):
    """Decryption-side PGP panel: single private key file selector."""

    def __init__(self, parent, **kw):
        super().__init__(parent, text="🔑  PGP — Private Key", padding=6, **kw)
        self._row = _PGPKeyRow(self, "Private key:", on_remove=None)
        self._row.pack(fill=X)
        Tooltip(self._row, "提供您的 RSA 私鑰（.pem），用來解開 PGP 信封")

    def get_priv_pem(self) -> bytes:
        return self._row.get_pem()


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
