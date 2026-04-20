"""Tab 1 — File Encryption / Decryption."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from core.bytefile import ByteFile, BYTEFILE_EXT, default_note
from core.engine import ALGORITHMS, EncryptionEngine
from core.utils import derive_key_bytes, human_size

from .theme import FONT_TITLE, FONT_BODY, FONT_SUBTITLE, PAD
from .widgets import FileSelector, PasswordFrame, CollapsiblePanel


class FileTab(ttk.Frame):
    def __init__(self, parent, status_var: tk.StringVar, **kw):
        super().__init__(parent, padding=PAD, **kw)
        self._status = status_var
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = ttk.Label(self, text="🔐  File Encryption", font=FONT_TITLE)
        hdr.pack(anchor=W, pady=(0, PAD))

        # Main — two‑column card
        cols = ttk.Frame(self)
        cols.pack(fill=BOTH, expand=True)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)

        self._build_encrypt_card(cols)
        self._build_decrypt_card(cols)

        # Advanced settings (collapsed)
        self._build_advanced()

    # ── Encrypt card (left) ───────────────────────────────────────────

    def _build_encrypt_card(self, parent):
        card = ttk.Labelframe(parent, text="🔒  Encrypt", padding=PAD)
        card.grid(row=0, column=0, sticky=NSEW, padx=(0, PAD // 2), pady=(0, PAD))

        self.enc_file = FileSelector(card, label="Select file to encrypt")
        self.enc_file.pack(fill=X, pady=(0, 8))

        self.enc_pw = PasswordFrame(card, title="Encryption password")
        self.enc_pw.pack(fill=X, pady=(0, 10))

        btn = ttk.Button(
            card, text="🔒  Encrypt & Save",
            bootstyle="primary", command=self._do_encrypt,
        )
        btn.pack(fill=X, ipady=6)

    # ── Decrypt card (right) ──────────────────────────────────────────

    def _build_decrypt_card(self, parent):
        card = ttk.Labelframe(parent, text="🔓  Decrypt", padding=PAD)
        card.grid(row=0, column=1, sticky=NSEW, padx=(PAD // 2, 0), pady=(0, PAD))

        self.dec_file = FileSelector(
            card, label="Select .bytefile",
            filetypes=[("ByteFile", f"*{BYTEFILE_EXT}"), ("All files", "*.*")],
        )
        self.dec_file.pack(fill=X, pady=(0, 8))

        self.dec_pw = PasswordFrame(card, title="Decryption password")
        self.dec_pw.pack(fill=X, pady=(0, 10))

        btn = ttk.Button(
            card, text="🔓  Decrypt & Save",
            bootstyle="success", command=self._do_decrypt,
        )
        btn.pack(fill=X, ipady=6)

    # ── Advanced settings panel ───────────────────────────────────────

    def _build_advanced(self):
        panel = CollapsiblePanel(self, title="Advanced Settings")
        panel.pack(fill=X, pady=(0, 4))
        c = panel.content

        # Algorithm
        r1 = ttk.Frame(c)
        r1.pack(fill=X, pady=2)
        ttk.Label(r1, text="Algorithm:", font=FONT_BODY, width=14).pack(side=LEFT)
        self.algo_var = tk.StringVar(value="AES-256-CBC")
        ttk.Combobox(
            r1, textvariable=self.algo_var, values=ALGORITHMS,
            state="readonly", width=20, font=FONT_BODY,
        ).pack(side=LEFT, padx=(4, 0))

        # Author
        r2 = ttk.Frame(c)
        r2.pack(fill=X, pady=2)
        ttk.Label(r2, text="Author:", font=FONT_BODY, width=14).pack(side=LEFT)
        self.author_var = tk.StringVar(value="@anonymous")
        ttk.Entry(r2, textvariable=self.author_var, font=FONT_BODY, width=22).pack(side=LEFT, padx=(4, 0))

        # Password hint
        r3 = ttk.Frame(c)
        r3.pack(fill=X, pady=2)
        ttk.Label(r3, text="Password hint:", font=FONT_BODY, width=14).pack(side=LEFT)
        self.hint_var = tk.StringVar()
        ttk.Entry(r3, textvariable=self.hint_var, font=FONT_BODY, width=22).pack(side=LEFT, padx=(4, 0))

        # Encryption mode
        r4 = ttk.Frame(c)
        r4.pack(fill=X, pady=2)
        ttk.Label(r4, text="Mode:", font=FONT_BODY, width=14).pack(side=LEFT)
        self.mode_var = tk.StringVar(value="simple")
        ttk.Radiobutton(r4, text="Simple", variable=self.mode_var, value="simple").pack(side=LEFT, padx=(4, 8))
        ttk.Radiobutton(r4, text="Node", variable=self.mode_var, value="node").pack(side=LEFT)

        # Iterations
        r5 = ttk.Frame(c)
        r5.pack(fill=X, pady=2)
        ttk.Label(r5, text="Iterations:", font=FONT_BODY, width=14).pack(side=LEFT)
        self.iter_var = tk.IntVar(value=1)
        ttk.Spinbox(r5, from_=1, to=20, textvariable=self.iter_var, width=5, font=FONT_BODY).pack(side=LEFT, padx=(4, 0))

    # ── Actions ───────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._status.set(msg)

    def _do_encrypt(self):
        src = self.enc_file.get()
        pw_source = self.enc_pw.get_source()
        key_type = self.enc_pw.get_key_type()

        if not src:
            messagebox.showwarning("Missing input", "Please select a file to encrypt.")
            return
        if not pw_source and self.algo_var.get() != "Base64":
            messagebox.showwarning("Missing password", "Please enter a password.")
            return

        # Ask where to save
        default_name = Path(src).name + BYTEFILE_EXT
        dest = filedialog.asksaveasfilename(
            defaultextension=BYTEFILE_EXT,
            initialfile=default_name,
            filetypes=[("ByteFile", f"*{BYTEFILE_EXT}")],
        )
        if not dest:
            return

        self._set_status("Encrypting...")
        threading.Thread(
            target=self._encrypt_worker,
            args=(src, pw_source, key_type, dest),
            daemon=True,
        ).start()

    def _encrypt_worker(self, src: str, pw_source: str, key_type: str, dest: str):
        try:
            data = Path(src).read_bytes()
            key_bytes = derive_key_bytes(pw_source, key_type)
            algo = self.algo_var.get()
            iterations = self.iter_var.get()
            mode = self.mode_var.get()

            if mode == "node":
                # Each iteration wraps into a full bytefile
                payload = data
                for i in range(iterations):
                    encrypted = EncryptionEngine.encrypt(payload, key_bytes, algo)
                    note = default_note(
                        algorithm=algo, key_type=key_type, mode="node",
                        iterations=iterations,
                        author=self.author_var.get(),
                        password_hint=self.hint_var.get() or None,
                        original_filename=Path(src).name if i == 0 else None,
                        original_size=len(data) if i == 0 else None,
                    )
                    note["layer"] = i + 1
                    note["total_layers"] = iterations
                    bf = ByteFile(encrypted, note)
                    payload = bf.pack().encode("utf-8")
                Path(dest).write_bytes(payload)
            else:
                # Simple: encrypt N times then wrap once
                encrypted = data
                for _ in range(iterations):
                    encrypted = EncryptionEngine.encrypt(encrypted, key_bytes, algo)
                note = default_note(
                    algorithm=algo, key_type=key_type, mode="simple",
                    iterations=iterations,
                    author=self.author_var.get(),
                    password_hint=self.hint_var.get() or None,
                    original_filename=Path(src).name,
                    original_size=len(data),
                )
                bf = ByteFile(encrypted, note)
                bf.save(dest)

            self.after(0, lambda: self._set_status(f"✅ Encrypted → {Path(dest).name}"))
            self.after(0, lambda: messagebox.showinfo("Done", f"File encrypted successfully.\n{dest}"))
        except Exception as exc:
            self.after(0, lambda: self._set_status(f"❌ Error: {exc}"))
            self.after(0, lambda: messagebox.showerror("Encryption Error", str(exc)))

    def _do_decrypt(self):
        src = self.dec_file.get()
        pw_source = self.dec_pw.get_source()
        key_type = self.dec_pw.get_key_type()

        if not src:
            messagebox.showwarning("Missing input", "Please select a .bytefile.")
            return
        if not pw_source:
            messagebox.showwarning("Missing password", "Please enter a password.")
            return

        self._set_status("Decrypting...")
        threading.Thread(
            target=self._decrypt_worker,
            args=(src, pw_source, key_type),
            daemon=True,
        ).start()

    def _decrypt_worker(self, src: str, pw_source: str, key_type: str):
        try:
            key_bytes = derive_key_bytes(pw_source, key_type)

            text = Path(src).read_text(encoding="utf-8")
            bf = ByteFile.parse(text)
            algo = bf.algorithm
            mode = bf.mode

            if mode == "node":
                # Peel layers until raw data
                payload = text
                while True:
                    bf = ByteFile.parse(payload)
                    decrypted = EncryptionEngine.decrypt(bf.content, key_bytes, bf.algorithm)
                    try:
                        payload = decrypted.decode("utf-8")
                        ByteFile.parse(payload)
                    except Exception:
                        # Not a valid bytefile → we reached the original data
                        break
                result = decrypted
                orig_name = bf.original_filename
            else:
                iterations = bf.note.get("iterations", 1)
                result = bf.content
                for _ in range(iterations):
                    result = EncryptionEngine.decrypt(result, key_bytes, algo)
                orig_name = bf.original_filename

            # Ask where to save
            default_name = orig_name or "decrypted_file"
            dest = filedialog.asksaveasfilename(
                initialfile=default_name,
                filetypes=[("All files", "*.*")],
            )
            if not dest:
                self.after(0, lambda: self._set_status("Decrypt cancelled."))
                return

            Path(dest).write_bytes(result)
            self.after(0, lambda: self._set_status(f"✅ Decrypted → {Path(dest).name}"))
            self.after(0, lambda: messagebox.showinfo("Done", f"File decrypted successfully.\n{dest}"))
        except Exception as exc:
            self.after(0, lambda: self._set_status(f"❌ Error: {exc}"))
            self.after(0, lambda: messagebox.showerror("Decryption Error", str(exc)))
