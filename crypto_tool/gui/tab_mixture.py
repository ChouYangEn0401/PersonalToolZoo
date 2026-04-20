"""Tab 3 — Mixture (multi-stage) Encryption Mode."""

from __future__ import annotations

import base64
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinterdnd2 import DND_FILES

from core.bytefile import ByteFile, BYTEFILE_EXT, default_note
from core.engine import ALGORITHMS, PGP_ALGORITHMS, STAGE_ALGORITHMS, EncryptionEngine
from core.utils import derive_key_bytes

from .theme import FONT_TITLE, FONT_BODY, FONT_MONO, FONT_SUBTITLE, FONT_SMALL, PAD
from .widgets import PasswordFrame, FileSelector, Tooltip, _clean_dnd_path


class _StageRow(ttk.Frame):
    """One encryption-stage row: algorithm + password + delete button."""

    def __init__(self, parent, index: int, on_delete):
        super().__init__(parent)
        self.index = index
        self._on_delete = on_delete

        self.columnconfigure(1, weight=1)

        lbl = ttk.Label(self, text=f"#{index + 1}", font=FONT_BODY, width=3)
        lbl.grid(row=0, column=0, rowspan=2, padx=(0, 6))

        # Algorithm
        self.algo_var = tk.StringVar(value="AES-256-CBC")
        ttk.Combobox(
            self, textvariable=self.algo_var, values=STAGE_ALGORITHMS,
            state="readonly", width=18, font=FONT_BODY,
        ).grid(row=0, column=1, sticky=W, pady=(0, 2))

        # Password
        self._pw_row = ttk.Frame(self)
        pw_row = self._pw_row
        pw_row.grid(row=1, column=1, sticky=EW, pady=(0, 2))
        self.key_type_var = tk.StringVar(value="text")
        ttk.Combobox(
            pw_row, textvariable=self.key_type_var,
            values=["text", "file", "image", "video", "bytefile", "txtfile"],
            state="readonly", width=8, font=FONT_SMALL,
        ).pack(side=LEFT, padx=(0, 4))
        self.pw_var = tk.StringVar()
        self._pw_entry = ttk.Entry(pw_row, textvariable=self.pw_var, show="●", font=FONT_BODY)
        self._pw_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 4))
        ttk.Button(pw_row, text="👁", width=3, bootstyle="outline-secondary",
                   command=self._toggle).pack(side=LEFT, padx=(0, 4))

        # File browse (shown when key_type != text)
        self._browse_btn = ttk.Button(pw_row, text="📁", width=3, bootstyle="outline",
                                       command=self._browse_file)
        self._browse_btn.pack(side=LEFT, padx=(0, 4))
        self.key_type_var.trace_add("write", self._on_type_change)

        # ── DnD on password entry (for file-based key drops) ─────────
        self._pw_entry.drop_target_register(DND_FILES)
        self._pw_entry.dnd_bind("<<Drop>>", self._on_pw_drop)

        # ── PGP key rows (shown instead of password when PGP selected) ─
        self._pgp_row = ttk.Frame(self)
        # not gridded initially
        self._pgp_pub_var = tk.StringVar()
        self._pgp_priv_var = tk.StringVar()
        _pgp_inner = ttk.Frame(self._pgp_row)
        _pgp_inner.pack(fill=X)
        ttk.Label(_pgp_inner, text="Pub key:", font=FONT_SMALL, width=8).pack(side=LEFT)
        ttk.Entry(_pgp_inner, textvariable=self._pgp_pub_var, font=FONT_SMALL).pack(
            side=LEFT, fill=X, expand=True, padx=(0, 2))
        ttk.Button(_pgp_inner, text="📁", width=3, bootstyle="outline",
                   command=lambda: self._browse_pgp(self._pgp_pub_var)).pack(side=LEFT, padx=(0, 6))
        ttk.Label(_pgp_inner, text="Priv:", font=FONT_SMALL, width=5).pack(side=LEFT)
        ttk.Entry(_pgp_inner, textvariable=self._pgp_priv_var, font=FONT_SMALL).pack(
            side=LEFT, fill=X, expand=True, padx=(0, 2))
        ttk.Button(_pgp_inner, text="📁", width=3, bootstyle="outline",
                   command=lambda: self._browse_pgp(self._pgp_priv_var)).pack(side=LEFT)

        self.algo_var.trace_add("write", self._on_algo_change)

        # Delete
        ttk.Button(self, text="✕", width=3, bootstyle="outline-danger",
                   command=lambda: self._on_delete(self)).grid(row=0, column=2, rowspan=2, padx=(6, 0))

        self._show = False
        ttk.Separator(self, orient=HORIZONTAL).grid(row=2, column=0, columnspan=3, sticky=EW, pady=(6, 2))

    def _toggle(self):
        self._show = not self._show
        self._pw_entry.config(show="" if self._show else "●")

    def _on_algo_change(self, *_):
        if self.algo_var.get() == "PGP":
            self._pw_row.grid_remove()
            self._pgp_row.grid(row=1, column=1, sticky=EW, pady=(0, 2))
        else:
            self._pgp_row.grid_remove()
            self._pw_row.grid()

    def _browse_pgp(self, var: tk.StringVar):
        p = filedialog.askopenfilename(
            filetypes=[("PEM / Key files", "*.pem *.key *.pub *.txt"), ("All files", "*.*")]
        )
        if p:
            var.set(p)

    def _on_type_change(self, *_args):
        if self.key_type_var.get() == "text":
            self._browse_btn.pack_forget()
        else:
            self._browse_btn.pack(side=LEFT, padx=(0, 4))

    def _browse_file(self):
        p = filedialog.askopenfilename()
        if p:
            self.pw_var.set(p)

    def _on_pw_drop(self, event):
        """Accept a dropped file path as the key-file path."""
        path = _clean_dnd_path(event.data)
        if path:
            # Auto-switch key type to 'file' if text is currently selected
            if self.key_type_var.get() == "text":
                self.key_type_var.set("file")
            self.pw_var.set(path)

    def get_config(self) -> dict:
        algo = self.algo_var.get()
        if algo == "PGP":
            return {
                "algorithm": "PGP",
                "pub_pem_path": self._pgp_pub_var.get().strip(),
                "priv_pem_path": self._pgp_priv_var.get().strip(),
                "key_bytes": b"",
                "key_type": "pgp",
            }
        return {
            "algorithm": algo,
            "key_bytes": derive_key_bytes(self.pw_var.get(), self.key_type_var.get()),
            "key_type": self.key_type_var.get(),
        }


class MixtureTab(ttk.Frame):
    def __init__(self, parent, status_var: tk.StringVar, **kw):
        super().__init__(parent, padding=PAD, **kw)
        self._status = status_var
        self._stages: list[_StageRow] = []
        self._build_ui()
        self._add_stage()  # start with 1 stage

    def _build_ui(self):
        ttk.Label(self, text="🔗  Mixture Encryption", font=FONT_TITLE).pack(anchor=W, pady=(0, 4))
        ttk.Label(self, text="Build a multi-stage encryption pipeline with different algorithms & passwords per stage.",
                  font=FONT_SMALL, wraplength=700).pack(anchor=W, pady=(0, PAD))

        # ── Mode & input ──────────────────────────────────────────────
        top = ttk.Frame(self)
        top.pack(fill=X, pady=(0, 8))

        mode_frame = ttk.Labelframe(top, text="Mode", padding=8)
        mode_frame.pack(side=LEFT, padx=(0, 12))
        self.mode_var = tk.StringVar(value="layered")
        ttk.Radiobutton(mode_frame, text=f"Layered  (多階段融合 → 1 {BYTEFILE_EXT})",
                        variable=self.mode_var, value="layered").pack(anchor=W)
        ttk.Radiobutton(mode_frame, text=f"Nested  (每階段各自一個 {BYTEFILE_EXT})",
                        variable=self.mode_var, value="nested").pack(anchor=W)

        input_frame = ttk.Labelframe(top, text="Input type", padding=8)
        input_frame.pack(side=LEFT, fill=X, expand=True)
        self.input_type_var = tk.StringVar(value="file")
        ttk.Radiobutton(input_frame, text="File", variable=self.input_type_var,
                        value="file", command=self._switch_input).pack(side=LEFT, padx=(0, 12))
        ttk.Radiobutton(input_frame, text="Text", variable=self.input_type_var,
                        value="text", command=self._switch_input).pack(side=LEFT)

        # ── Input area (file / text) ──────────────────────────────────
        self._input_container = ttk.Frame(self)
        self._input_container.pack(fill=X, pady=(0, 8))

        self.file_sel = FileSelector(self._input_container, label="Select input file")
        self.file_sel.pack(fill=X)

        self._text_frame = ttk.Frame(self._input_container)
        self.input_text = tk.Text(self._text_frame, height=4, font=FONT_MONO, wrap=WORD)
        self.input_text.pack(fill=X)

        # ── Pipeline stages (scrollable) ──────────────────────────────
        stage_lf = ttk.Labelframe(self, text="Encryption Pipeline", padding=8)
        stage_lf.pack(fill=BOTH, expand=True, pady=(0, 8))

        stage_btn_row = ttk.Frame(stage_lf)
        stage_btn_row.pack(fill=X, pady=(0, 4))
        ttk.Button(stage_btn_row, text="＋ Add Stage", bootstyle="outline-primary",
                   command=self._add_stage).pack(side=LEFT, padx=(0, 6))
        ttk.Button(stage_btn_row, text="Clear All", bootstyle="outline-danger",
                   command=self._clear_stages).pack(side=LEFT)

        # Scrollable container
        canvas = tk.Canvas(stage_lf, highlightthickness=0)
        scrollbar = ttk.Scrollbar(stage_lf, orient=VERTICAL, command=canvas.yview)
        self._stage_frame = ttk.Frame(canvas)
        self._stage_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._stage_frame, anchor=NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        # mouse scroll
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        self._canvas = canvas

        # ── Action buttons ────────────────────────────────────────────
        act = ttk.Frame(self)
        act.pack(fill=X, pady=(0, 4))
        ttk.Button(act, text="🔒  Encrypt", bootstyle="warning",
                   command=self._do_encrypt).pack(side=LEFT, expand=True, fill=X, padx=(0, 4), ipady=6)
        ttk.Button(act, text="🔓  Decrypt", bootstyle="success",
                   command=self._do_decrypt).pack(side=LEFT, expand=True, fill=X, padx=(4, 0), ipady=6)

    # ── Input switching ───────────────────────────────────────────────

    def _switch_input(self):
        if self.input_type_var.get() == "file":
            self._text_frame.pack_forget()
            self.file_sel.pack(fill=X)
        else:
            self.file_sel.pack_forget()
            self._text_frame.pack(fill=X)

    # ── Stage management ──────────────────────────────────────────────

    def _add_stage(self):
        idx = len(self._stages)
        row = _StageRow(self._stage_frame, idx, self._remove_stage)
        row.pack(fill=X, padx=4, pady=2)
        self._stages.append(row)

    def _remove_stage(self, row: _StageRow):
        if len(self._stages) <= 1:
            return
        row.destroy()
        self._stages.remove(row)
        # re-index
        for i, s in enumerate(self._stages):
            s.index = i

    def _clear_stages(self):
        for s in self._stages:
            s.destroy()
        self._stages.clear()
        self._add_stage()

    def _get_chain(self) -> list[dict]:
        return [s.get_config() for s in self._stages]

    # ── Encrypt ───────────────────────────────────────────────────────

    def _do_encrypt(self):
        if self.input_type_var.get() == "file":
            src = self.file_sel.get()
            if not src:
                messagebox.showwarning("Input", "Select a file.")
                return
        else:
            raw = self.input_text.get("1.0", END).rstrip("\n")
            if not raw:
                messagebox.showwarning("Input", "Enter text.")
                return
            src = None

        try:
            chain = self._get_chain()
        except Exception as exc:
            messagebox.showerror("Config Error", str(exc))
            return

        # Ask output
        dest = filedialog.asksaveasfilename(
            defaultextension=BYTEFILE_EXT,
            filetypes=[("ByteFile", f"*{BYTEFILE_EXT}"), ("Text", "*.txt"), ("All", "*.*")],
        )
        if not dest:
            return

        self._status.set("Encrypting (mixture)...")
        threading.Thread(
            target=self._encrypt_worker,
            args=(src, chain, dest),
            daemon=True,
        ).start()

    def _encrypt_worker(self, src: str | None, chain: list[dict], dest: str):
        try:
            if src:
                data = Path(src).read_bytes()
                orig_name = Path(src).name
            else:
                data = self.input_text.get("1.0", END).rstrip("\n").encode("utf-8")
                orig_name = None

            mode = self.mode_var.get()
            chain_meta = [{"algorithm": s["algorithm"], "key_type": s["key_type"]} for s in chain]

            if mode == "nested":
                payload = data
                for i, step in enumerate(chain):
                    if step["algorithm"] == "PGP":
                        pub_pem = Path(step["pub_pem_path"]).read_bytes()
                        encrypted = EncryptionEngine.encrypt(payload, pub_pem, "PGP")
                    else:
                        encrypted = EncryptionEngine.encrypt(payload, step["key_bytes"], step["algorithm"])
                    note = default_note(
                        algorithm=step["algorithm"], key_type=step["key_type"],
                        mode="nested", iterations=len(chain),
                        original_filename=orig_name if i == 0 else None,
                        original_size=len(data) if i == 0 else None,
                    )
                    note["layer"] = i + 1
                    note["total_layers"] = len(chain)
                    bf = ByteFile(encrypted, note)
                    payload = bf.pack().encode("utf-8")
                Path(dest).write_bytes(payload)
            else:
                has_pgp = any(s["algorithm"] == "PGP" for s in chain)
                if has_pgp:
                    result = data
                    for step in chain:
                        if step["algorithm"] == "PGP":
                            pub_pem = Path(step["pub_pem_path"]).read_bytes()
                            result = EncryptionEngine.encrypt(result, pub_pem, "PGP")
                        else:
                            result = EncryptionEngine.encrypt(result, step["key_bytes"], step["algorithm"])
                    encrypted = result
                else:
                    encrypted = EncryptionEngine.encrypt_chain(data, chain)
                note = default_note(
                    algorithm=chain[0]["algorithm"], key_type=chain[0]["key_type"],
                    mode="layered", iterations=len(chain),
                    original_filename=orig_name,
                    original_size=len(data),
                    mixture_chain=chain_meta,
                )
                bf = ByteFile(encrypted, note)
                bf.save(dest)

            self.after(0, lambda: self._status.set(f"✅ Mixture encrypted → {Path(dest).name}"))
            self.after(0, lambda: messagebox.showinfo("Done", f"Encrypted!\n{dest}"))
        except Exception as exc:
            self.after(0, lambda: self._status.set(f"❌ {exc}"))
            self.after(0, lambda: messagebox.showerror("Error", str(exc)))

    # ── Decrypt ───────────────────────────────────────────────────────

    def _do_decrypt(self):
        # Use the input area as source (file selector or text box) instead of
        # opening a new file dialog. This makes MixtureTab decrypt inline with
        # the configured pipeline. Destination still requested for saving.
        if self.input_type_var.get() == "file":
            src = self.file_sel.get()
            if not src:
                messagebox.showwarning("Input", "Select a file in the Input area.")
                return
            src_is_path = True
        else:
            raw = self.input_text.get("1.0", END).rstrip("\n")
            if not raw:
                messagebox.showwarning("Input", "Enter text in the Input area.")
                return
            src = raw
            src_is_path = False

        try:
            chain = self._get_chain()
        except Exception as exc:
            messagebox.showerror("Config Error", str(exc))
            return

        dest = filedialog.asksaveasfilename(
            filetypes=[("All files", "*.*")],
        )
        if not dest:
            return

        self._status.set("Decrypting (mixture)...")
        threading.Thread(
            target=self._decrypt_worker,
            args=(src, src_is_path, chain, dest),
            daemon=True,
        ).start()

    def _decrypt_worker(self, src: str, src_is_path: bool, chain: list[dict], dest: str):
        try:
            # Load ByteFile from either a path or raw text
            if src_is_path:
                text = Path(src).read_text(encoding="utf-8")
            else:
                text = src

            bf = ByteFile.parse(text)
            mode = bf.mode

            # Nested: each layer is a packed .isd; peel layers using the provided chain
            if mode == "nested":
                payload = text
                decrypted = b""
                for step in reversed(chain):
                    bf = ByteFile.parse(payload)
                    if step["algorithm"] == "PGP":
                        priv_pem = Path(step["priv_pem_path"]).read_bytes()
                        decrypted = EncryptionEngine.decrypt(bf.content, priv_pem, "PGP")
                    else:
                        decrypted = EncryptionEngine.decrypt(bf.content, step["key_bytes"], step["algorithm"])
                    # If result is another packed .isd, continue peeling, otherwise stop
                    try:
                        payload = decrypted.decode("utf-8")
                        # If parse succeeds, continue loop to peel next
                        ByteFile.parse(payload)
                    except Exception:
                        break
                result = decrypted

            # Layered: the ByteFile contains a payload that was produced by encrypt_chain
            else:
                has_pgp = any(s["algorithm"] == "PGP" for s in chain)
                if has_pgp:
                    result = bf.content
                    for step in reversed(chain):
                        if step["algorithm"] == "PGP":
                            priv_pem = Path(step["priv_pem_path"]).read_bytes()
                            result = EncryptionEngine.decrypt(result, priv_pem, "PGP")
                        else:
                            result = EncryptionEngine.decrypt(result, step["key_bytes"], step["algorithm"])
                else:
                    result = EncryptionEngine.decrypt_chain(bf.content, chain)

            Path(dest).write_bytes(result)
            self.after(0, lambda: self._status.set(f"✅ Decrypted → {Path(dest).name}"))
            self.after(0, lambda: messagebox.showinfo("Done", f"Decrypted!\n{dest}"))
        except Exception as exc:
            # bubble up the error to the UI
            self.after(0, lambda: self._status.set(f"❌ {exc}"))
            self.after(0, lambda: messagebox.showerror("Error", str(exc)))
