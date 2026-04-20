"""Tab 2 — Text Encryption / Decryption."""

from __future__ import annotations

import base64
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from core.bytefile import ByteFile, BYTEFILE_EXT, default_note
from core.engine import ALGORITHMS, EncryptionEngine
from core.utils import derive_key_bytes

from .theme import FONT_TITLE, FONT_BODY, FONT_MONO, FONT_SUBTITLE, PAD
from .widgets import PasswordFrame, CollapsiblePanel


class TextTab(ttk.Frame):
    def __init__(self, parent, status_var: tk.StringVar, **kw):
        super().__init__(parent, padding=PAD, **kw)
        self._status = status_var
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────

    def _build_ui(self):
        ttk.Label(self, text="📝  Text Encryption", font=FONT_TITLE).pack(anchor=W, pady=(0, PAD))

        # --- Input area ---
        inp_frame = ttk.Labelframe(self, text="Input", padding=PAD)
        inp_frame.pack(fill=BOTH, expand=True, pady=(0, 8))

        btn_row = ttk.Frame(inp_frame)
        btn_row.pack(fill=X, pady=(0, 4))
        ttk.Button(btn_row, text="Load .bytefile", bootstyle="outline-info",
                   command=self._load_bytefile).pack(side=LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Load text file", bootstyle="outline-secondary",
                   command=self._load_textfile).pack(side=LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Clear", bootstyle="outline-danger",
                   command=self._clear_input).pack(side=RIGHT)

        self.input_text = tk.Text(inp_frame, height=6, font=FONT_MONO, wrap=WORD)
        inp_scroll = ttk.Scrollbar(inp_frame, command=self.input_text.yview)
        self.input_text.config(yscrollcommand=inp_scroll.set)
        inp_scroll.pack(side=RIGHT, fill=Y)
        self.input_text.pack(fill=BOTH, expand=True)

        # --- Password & settings row ---
        mid = ttk.Frame(self)
        mid.pack(fill=X, pady=6)
        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(1, weight=0)

        self.pw = PasswordFrame(mid, title="Password")
        self.pw.grid(row=0, column=0, sticky=EW, padx=(0, 8))

        settings = ttk.Frame(mid)
        settings.grid(row=0, column=1, sticky=NE)

        ttk.Label(settings, text="Algorithm:", font=FONT_BODY).pack(anchor=W)
        self.algo_var = tk.StringVar(value="AES-256-CBC")
        ttk.Combobox(
            settings, textvariable=self.algo_var, values=ALGORITHMS,
            state="readonly", width=18, font=FONT_BODY,
        ).pack(anchor=W, pady=(2, 6))

        self.b64_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            settings, text="Base64 output (display-safe)",
            variable=self.b64_var, bootstyle="round-toggle",
        ).pack(anchor=W)

        # --- Action buttons ---
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=X, pady=6)
        ttk.Button(
            btn_frame, text="🔒  Encrypt", bootstyle="primary",
            command=self._do_encrypt,
        ).pack(side=LEFT, expand=True, fill=X, padx=(0, 4), ipady=6)
        ttk.Button(
            btn_frame, text="🔓  Decrypt", bootstyle="success",
            command=self._do_decrypt,
        ).pack(side=LEFT, expand=True, fill=X, padx=(4, 0), ipady=6)

        # --- Output area ---
        out_frame = ttk.Labelframe(self, text="Output", padding=PAD)
        out_frame.pack(fill=BOTH, expand=True, pady=(0, 4))

        out_btn_row = ttk.Frame(out_frame)
        out_btn_row.pack(fill=X, pady=(0, 4))
        ttk.Button(out_btn_row, text="📋 Copy to clipboard",
                   bootstyle="info", command=self._copy_clipboard).pack(side=LEFT, padx=(0, 6))
        ttk.Button(out_btn_row, text="💾 Save as .txt",
                   bootstyle="outline-secondary", command=self._save_txt).pack(side=LEFT, padx=(0, 6))
        ttk.Button(out_btn_row, text="💾 Save as .bytefile",
                   bootstyle="outline-warning", command=self._save_bytefile).pack(side=LEFT)

        self.output_text = tk.Text(out_frame, height=6, font=FONT_MONO, wrap=WORD, state=DISABLED)
        out_scroll = ttk.Scrollbar(out_frame, command=self.output_text.yview)
        self.output_text.config(yscrollcommand=out_scroll.set)
        out_scroll.pack(side=RIGHT, fill=Y)
        self.output_text.pack(fill=BOTH, expand=True)

        # internal storage of last encrypted bytes (for .bytefile save)
        self._last_encrypted_bytes: bytes | None = None
        self._last_note: dict | None = None

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_output(self, text: str):
        self.output_text.config(state=NORMAL)
        self.output_text.delete("1.0", END)
        self.output_text.insert("1.0", text)
        self.output_text.config(state=DISABLED)

    def _get_input(self) -> str:
        return self.input_text.get("1.0", END).rstrip("\n")

    def _load_bytefile(self):
        p = filedialog.askopenfilename(
            filetypes=[("ByteFile", f"*{BYTEFILE_EXT}"), ("All files", "*.*")]
        )
        if not p:
            return
        try:
            bf = ByteFile.load(p)
            # Show the base64 encoded content in the input box
            b64 = base64.b64encode(bf.content).decode("ascii")
            self.input_text.delete("1.0", END)
            self.input_text.insert("1.0", b64)
            self._status.set(f"Loaded bytefile: {Path(p).name}")
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))

    def _load_textfile(self):
        p = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not p:
            return
        try:
            content = Path(p).read_text(encoding="utf-8")
            self.input_text.delete("1.0", END)
            self.input_text.insert("1.0", content)
            self._status.set(f"Loaded text: {Path(p).name}")
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))

    def _clear_input(self):
        self.input_text.delete("1.0", END)

    # ── Encrypt ───────────────────────────────────────────────────────

    def _do_encrypt(self):
        raw = self._get_input()
        if not raw:
            messagebox.showwarning("Empty", "Enter some text to encrypt.")
            return
        pw_source = self.pw.get_source()
        key_type = self.pw.get_key_type()
        algo = self.algo_var.get()
        if not pw_source and algo != "Base64":
            messagebox.showwarning("Password", "Enter a password.")
            return

        self._status.set("Encrypting text...")
        threading.Thread(
            target=self._encrypt_worker,
            args=(raw, pw_source, key_type, algo),
            daemon=True,
        ).start()

    def _encrypt_worker(self, raw: str, pw_source: str, key_type: str, algo: str):
        try:
            data = raw.encode("utf-8")
            key_bytes = derive_key_bytes(pw_source, key_type)
            encrypted = EncryptionEngine.encrypt(data, key_bytes, algo)

            self._last_encrypted_bytes = encrypted
            self._last_note = default_note(
                algorithm=algo, key_type=key_type, mode="simple",
                iterations=1, original_filename=None,
                original_size=len(data),
            )

            if self.b64_var.get():
                display = base64.b64encode(encrypted).decode("ascii")
            else:
                display = encrypted.hex()

            self.after(0, lambda: self._set_output(display))
            self.after(0, lambda: self._status.set("✅ Text encrypted"))
        except Exception as exc:
            self.after(0, lambda exc=exc: self._status.set(f"❌ {exc}"))
            self.after(0, lambda exc=exc: messagebox.showerror("Error", str(exc)))

    # ── Decrypt ───────────────────────────────────────────────────────

    def _do_decrypt(self):
        raw = self._get_input()
        if not raw:
            messagebox.showwarning("Empty", "Enter encrypted data to decrypt.")
            return
        pw_source = self.pw.get_source()
        key_type = self.pw.get_key_type()
        algo = self.algo_var.get()
        if not pw_source and algo != "Base64":
            messagebox.showwarning("Password", "Enter a password.")
            return

        self._status.set("Decrypting text...")
        threading.Thread(
            target=self._decrypt_worker,
            args=(raw, pw_source, key_type, algo),
            daemon=True,
        ).start()

    def _decrypt_worker(self, raw: str, pw_source: str, key_type: str, algo: str):
        try:
            # Try base64 decode first, then hex
            try:
                encrypted = base64.b64decode(raw)
            except Exception:
                encrypted = bytes.fromhex(raw)

            key_bytes = derive_key_bytes(pw_source, key_type)
            decrypted = EncryptionEngine.decrypt(encrypted, key_bytes, algo)
            text = decrypted.decode("utf-8")

            self.after(0, lambda: self._set_output(text))
            self.after(0, lambda: self._status.set("✅ Text decrypted"))
        except Exception as exc:
            # Bind exc into the callbacks to avoid referencing cleared
            # exception variables after the except block ends.
            self.after(0, lambda exc=exc: self._status.set(f"❌ {exc}"))
            # If the error looks like an authentication/tag/padding failure,
            # report it as a likely wrong password / corrupted data.
            if isinstance(exc, ValueError):
                self.after(0, lambda exc=exc: messagebox.showerror(
                    "Wrong password",
                    "Decryption failed — wrong password or corrupted data.",
                ))
            else:
                self.after(0, lambda exc=exc: messagebox.showerror("Error", str(exc)))

    # ── Output actions ────────────────────────────────────────────────

    def _copy_clipboard(self):
        txt = self.output_text.get("1.0", END).strip()
        if not txt:
            return
        self.clipboard_clear()
        self.clipboard_append(txt)
        self._status.set("📋 Copied to clipboard")

    def _save_txt(self):
        txt = self.output_text.get("1.0", END).strip()
        if not txt:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
        )
        if p:
            Path(p).write_text(txt, encoding="utf-8")
            self._status.set(f"Saved → {Path(p).name}")

    def _save_bytefile(self):
        if self._last_encrypted_bytes is None or self._last_note is None:
            messagebox.showinfo("No data", "Encrypt something first (the last encrypted result will be saved).")
            return
        p = filedialog.asksaveasfilename(
            defaultextension=BYTEFILE_EXT,
            filetypes=[("ByteFile", f"*{BYTEFILE_EXT}")],
        )
        if p:
            bf = ByteFile(self._last_encrypted_bytes, self._last_note)
            bf.save(p)
            self._status.set(f"Saved → {Path(p).name}")
