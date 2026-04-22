"""Tab — Mixture (multi-stage pipeline) Encryption Mode."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinterdnd2 import DND_FILES

from core.bytefile import ByteFile, BYTEFILE_EXT
from core.pipeline import (
    encrypt_multi, decrypt_multi,
    encrypt_layer_wrap, decrypt_layer_wrap,
    PartialDecryptError,
)
from core.engine import STAGE_ALGORITHMS

from .theme import FONT_TITLE, FONT_BODY, FONT_MONO, FONT_SMALL, PAD
from .widgets import FileSelector, _clean_dnd_path



class _StageRow(ttk.Frame):
    """
    One stage in the pipeline.

    Stores raw user input (pw_source + key_type OR PGP paths).
    Key derivation is deferred to the worker thread via core.pipeline so errors
    surface in the right place and the same config works for both encrypt/decrypt.
    """

    _KEY_TYPES = ["text", "file", "image", "video", "bytefile", "txtfile"]

    def __init__(self, parent, index: int, on_delete):
        super().__init__(parent)
        self.columnconfigure(1, weight=1)
        self._on_delete = on_delete

        # ── Index label ───────────────────────────────────────────────
        self._lbl = ttk.Label(self, font=FONT_BODY, width=3)
        self._lbl.grid(row=0, column=0, rowspan=2, padx=(0, 6))
        self.set_index(index)

        # ── Algorithm ─────────────────────────────────────────────────
        self.algo_var = tk.StringVar(value="AES-256-CBC")
        ttk.Combobox(
            self, textvariable=self.algo_var, values=STAGE_ALGORITHMS,
            state="readonly", width=18, font=FONT_BODY,
        ).grid(row=0, column=1, sticky=W, pady=(0, 2))

        # ── Symmetric password row ────────────────────────────────────
        self._pw_row = ttk.Frame(self)
        self._pw_row.grid(row=1, column=1, sticky=EW, pady=(0, 2))

        self.key_type_var = tk.StringVar(value="text")
        ttk.Combobox(
            self._pw_row, textvariable=self.key_type_var,
            values=self._KEY_TYPES, state="readonly", width=8, font=FONT_SMALL,
        ).pack(side=LEFT, padx=(0, 4))
        self.key_type_var.trace_add("write", self._on_key_type_change)

        self.pw_var = tk.StringVar()
        self._pw_entry = ttk.Entry(
            self._pw_row, textvariable=self.pw_var, show="●", font=FONT_BODY,
        )
        self._pw_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 4))
        self._show_pw = False
        ttk.Button(
            self._pw_row, text="👁", width=3, bootstyle="outline-secondary",
            command=self._toggle_pw,
        ).pack(side=LEFT, padx=(0, 4))

        self._file_browse_btn = ttk.Button(
            self._pw_row, text="📁", width=3, bootstyle="outline",
            command=self._browse_key_file,
        )
        # shown only for non-text key types

        # DnD on password entry
        self._pw_entry.drop_target_register(DND_FILES)
        self._pw_entry.dnd_bind("<<Drop>>", self._on_pw_drop)

        # ── PGP row (shown when algorithm == "PGP") ───────────────────
        self._pgp_row = ttk.Frame(self)
        # NOT gridded initially

        self._pgp_pub_var = tk.StringVar()
        self._pgp_priv_var = tk.StringVar()

        def _pgp_field(label: str, var: tk.StringVar, browse_cb):
            row = ttk.Frame(self._pgp_row)
            row.pack(fill=X, pady=(0, 2))
            ttk.Label(row, text=label, font=FONT_SMALL, width=18).pack(side=LEFT)
            ttk.Entry(row, textvariable=var, font=FONT_SMALL).pack(
                side=LEFT, fill=X, expand=True, padx=(0, 2))
            ttk.Button(row, text="📁", width=3, bootstyle="outline",
                       command=browse_cb).pack(side=LEFT)

        _pgp_field("Public key (encrypt):",
                   self._pgp_pub_var, lambda: self._browse_pem(self._pgp_pub_var))
        _pgp_field("Private key (decrypt):",
                   self._pgp_priv_var, lambda: self._browse_pem(self._pgp_priv_var))

        # ── Delete + separator ────────────────────────────────────────
        ttk.Button(
            self, text="✕", width=3, bootstyle="outline-danger",
            command=lambda: self._on_delete(self),
        ).grid(row=0, column=2, rowspan=2, padx=(6, 0))
        ttk.Separator(self, orient=HORIZONTAL).grid(
            row=2, column=0, columnspan=3, sticky=EW, pady=(6, 2),
        )

        self.algo_var.trace_add("write", self._on_algo_change)

    # ── Internal helpers ──────────────────────────────────────────────

    def set_index(self, idx: int):
        self._lbl.config(text=f"#{idx + 1}")

    def _toggle_pw(self):
        self._show_pw = not self._show_pw
        self._pw_entry.config(show="" if self._show_pw else "●")

    def _on_algo_change(self, *_):
        if self.algo_var.get() == "PGP":
            self._pw_row.grid_remove()
            self._pgp_row.grid(row=1, column=1, sticky=EW, pady=(0, 2))
        else:
            self._pgp_row.grid_remove()
            self._pw_row.grid()

    def _on_key_type_change(self, *_):
        if self.key_type_var.get() == "text":
            self._file_browse_btn.pack_forget()
        elif not self._file_browse_btn.winfo_ismapped():
            self._file_browse_btn.pack(side=LEFT, padx=(0, 4))

    def _browse_key_file(self):
        p = filedialog.askopenfilename()
        if p:
            self.pw_var.set(p)

    def _browse_pem(self, var: tk.StringVar):
        p = filedialog.askopenfilename(
            filetypes=[("PEM / Key files", "*.pem *.key *.pub *.txt"),
                       ("All files", "*.*")]
        )
        if p:
            var.set(p)

    def _on_pw_drop(self, event):
        path = _clean_dnd_path(event.data)
        if path:
            if self.key_type_var.get() == "text":
                self.key_type_var.set("file")
            self.pw_var.set(path)

    # ── Public API ────────────────────────────────────────────────────

    def get_config(self) -> dict:
        """
        Return raw stage config dict.
        Key derivation is NOT done here — pipeline module handles it in the worker.
        """
        algo = self.algo_var.get()
        if algo == "PGP":
            return {
                "algorithm": "PGP",
                "key_type": "pgp",
                "pw_source": "",
                "pub_pem_path": self._pgp_pub_var.get().strip(),
                "priv_pem_path": self._pgp_priv_var.get().strip(),
            }
        return {
            "algorithm": algo,
            "key_type": self.key_type_var.get(),
            "pw_source": self.pw_var.get(),
        }


# ── MixtureTab ────────────────────────────────────────────────────────────

class MixtureTab(ttk.Frame):
    """
    Multi-stage encryption/decryption using two modes:

    Multi-Encrypt  — all stages fused into ONE .isd.  Any wrong password = full fail.
    Layer-Wrap     — each stage wraps result in a new .isd.  Partial decrypt saves
                     the last valid .isd so the user can retry or use File tab.
    """

    _MODES = [
        ("Multi-Encrypt",
         "multi-encrypt",
         f"content → enc₁ → enc₂ → … → ONE {BYTEFILE_EXT}"),
        ("Layer-Wrap",
         "layer-wrap",
         f"content → enc₁ → isd₁ → enc₂ → isd₂ → … → outer {BYTEFILE_EXT}"),
    ]

    def __init__(self, parent, status_var: tk.StringVar, **kw):
        super().__init__(parent, padding=PAD, **kw)
        self._status = status_var
        self._stages: list[_StageRow] = []
        self._build_ui()
        self._add_stage()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self):
        ttk.Label(self, text="🔗  Mixture Pipeline", font=FONT_TITLE).pack(
            anchor=W, pady=(0, 4))
        ttk.Label(
            self,
            text=(
                "Build N stages, each with its own algorithm and password.  "
                "Encrypt runs stages 1→N; Decrypt runs stages N→1.  "
                "Mode controls whether stages share one .isd (Multi-Encrypt) or "
                "each stage produces its own .isd (Layer-Wrap)."
            ),
            font=FONT_SMALL, wraplength=700,
        ).pack(anchor=W, pady=(0, PAD))

        # ── Mode + input type ─────────────────────────────────────────
        top = ttk.Frame(self)
        top.pack(fill=X, pady=(0, 8))

        mode_lf = ttk.Labelframe(top, text="Mode", padding=8)
        mode_lf.pack(side=LEFT, padx=(0, 12))
        self.mode_var = tk.StringVar(value="multi-encrypt")
        for label, value, hint in self._MODES:
            ttk.Radiobutton(
                mode_lf, text=f"{label}  ({hint})",
                variable=self.mode_var, value=value,
            ).pack(anchor=W)

        input_lf = ttk.Labelframe(top, text="Input type", padding=8)
        input_lf.pack(side=LEFT, fill=X, expand=True)
        self.input_type_var = tk.StringVar(value="file")
        ttk.Radiobutton(
            input_lf, text="File", variable=self.input_type_var,
            value="file", command=self._switch_input,
        ).pack(side=LEFT, padx=(0, 12))
        ttk.Radiobutton(
            input_lf, text="Text", variable=self.input_type_var,
            value="text", command=self._switch_input,
        ).pack(side=LEFT)

        # ── Input area ────────────────────────────────────────────────
        self._input_container = ttk.Frame(self)
        self._input_container.pack(fill=X, pady=(0, 8))

        self.file_sel = FileSelector(self._input_container, label="Select input file")
        self.file_sel.pack(fill=X)

        self._text_frame = ttk.Frame(self._input_container)
        self.input_text = tk.Text(self._text_frame, height=4, font=FONT_MONO, wrap=WORD)
        self.input_text.pack(fill=X)

        # ── Pipeline stages (scrollable) ──────────────────────────────
        stage_lf = ttk.Labelframe(self, text="Pipeline Stages", padding=8)
        stage_lf.pack(fill=BOTH, expand=True, pady=(0, 8))

        btn_row = ttk.Frame(stage_lf)
        btn_row.pack(fill=X, pady=(0, 4))
        ttk.Button(
            btn_row, text="＋ Add Stage", bootstyle="outline-primary",
            command=self._add_stage,
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            btn_row, text="Clear All", bootstyle="outline-danger",
            command=self._clear_stages,
        ).pack(side=LEFT)

        canvas = tk.Canvas(stage_lf, highlightthickness=0)
        sb = ttk.Scrollbar(stage_lf, orient=VERTICAL, command=canvas.yview)
        self._stage_frame = ttk.Frame(canvas)
        self._stage_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self._stage_frame, anchor=NW)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"),
        )

        # ── Action buttons ────────────────────────────────────────────
        act = ttk.Frame(self)
        act.pack(fill=X, pady=(0, 4))
        ttk.Button(
            act, text="🔒  Encrypt", bootstyle="warning",
            command=self._do_encrypt,
        ).pack(side=LEFT, expand=True, fill=X, padx=(0, 4), ipady=6)
        ttk.Button(
            act, text="🔓  Decrypt", bootstyle="success",
            command=self._do_decrypt,
        ).pack(side=LEFT, expand=True, fill=X, padx=(4, 0), ipady=6)

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
        for i, s in enumerate(self._stages):
            s.set_index(i)

    def _clear_stages(self):
        for s in self._stages:
            s.destroy()
        self._stages.clear()
        self._add_stage()

    # ── Input + stage helpers ─────────────────────────────────────────

    def _read_input(self) -> tuple[bytes, str | None] | None:
        """Return (raw_bytes, original_name) or show warning and return None."""
        if self.input_type_var.get() == "file":
            src = self.file_sel.get()
            if not src:
                messagebox.showwarning("Input", "Select a file.")
                return None
            p = Path(src)
            return p.read_bytes(), p.name
        raw = self.input_text.get("1.0", END).rstrip("\n")
        if not raw:
            messagebox.showwarning("Input", "Enter text.")
            return None
        return raw.encode("utf-8"), None

    def _get_stages(self) -> list[dict] | None:
        stages = [s.get_config() for s in self._stages]
        if not stages:
            messagebox.showwarning("Pipeline", "Add at least one stage.")
            return None
        return stages

    # ── Encrypt ───────────────────────────────────────────────────────

    def _do_encrypt(self):
        inp = self._read_input()
        if inp is None:
            return
        stages = self._get_stages()
        if stages is None:
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=BYTEFILE_EXT,
            filetypes=[("Encrypted file", f"*{BYTEFILE_EXT}"), ("All files", "*.*")],
        )
        if not dest:
            return
        self._status.set("Encrypting…")
        threading.Thread(
            target=self._encrypt_worker,
            args=(inp, stages, self.mode_var.get(), dest),
            daemon=True,
        ).start()

    def _encrypt_worker(
        self,
        inp: tuple[bytes, str | None],
        stages: list[dict],
        mode: str,
        dest: str,
    ):
        try:
            data, orig_name = inp
            if mode == "multi-encrypt":
                bf = encrypt_multi(data, stages, orig_name=orig_name, orig_size=len(data))
                bf.save(dest)
            else:  # layer-wrap
                result_bytes = encrypt_layer_wrap(
                    data, stages, orig_name=orig_name, orig_size=len(data),
                )
                Path(dest).write_bytes(result_bytes)

            dest_name = Path(dest).name
            self.after(0, lambda n=dest_name: self._status.set(f"✅ Encrypted → {n}"))
            self.after(0, lambda d=dest: messagebox.showinfo("Done", f"Encrypted!\n{d}"))
        except Exception as exc:
            msg = str(exc)
            self.after(0, lambda m=msg: self._status.set(f"❌ {m}"))
            self.after(0, lambda m=msg: messagebox.showerror("Encrypt Error", m))

    # ── Decrypt ───────────────────────────────────────────────────────

    def _do_decrypt(self):
        inp = self._read_input()
        if inp is None:
            return
        stages = self._get_stages()
        if stages is None:
            return
        dest = filedialog.asksaveasfilename(
            filetypes=[("All files", "*.*")],
        )
        if not dest:
            return
        self._status.set("Decrypting…")
        threading.Thread(
            target=self._decrypt_worker,
            args=(inp, stages, self.mode_var.get(), dest),
            daemon=True,
        ).start()

    def _decrypt_worker(
        self,
        inp: tuple[bytes, str | None],
        stages: list[dict],
        mode: str,
        dest: str,
    ):
        try:
            data, _ = inp

            if mode == "multi-encrypt":
                try:
                    bf = ByteFile.parse(data.decode("utf-8"))
                except Exception as exc:
                    raise ValueError(
                        f"Cannot parse input as .isd — {exc}\n"
                        "Make sure the input is a Multi-Encrypt .isd."
                    ) from exc
                result = decrypt_multi(bf, stages)
                Path(dest).write_bytes(result)
                dest_name = Path(dest).name
                self.after(0, lambda n=dest_name: self._status.set(f"✅ Decrypted → {n}"))
                self.after(0, lambda d=dest: messagebox.showinfo("Done", f"Decrypted!\n{d}"))

            else:  # layer-wrap
                try:
                    result = decrypt_layer_wrap(data, stages)
                    Path(dest).write_bytes(result)
                    dest_name = Path(dest).name
                    self.after(0, lambda n=dest_name: self._status.set(f"✅ Decrypted → {n}"))
                    self.after(0, lambda d=dest: messagebox.showinfo("Done", f"Decrypted!\n{d}"))
                except PartialDecryptError as pde:
                    Path(dest).write_bytes(pde.partial)
                    s = pde.stage_num
                    m = str(pde)
                    dest_name = Path(dest).name
                    self.after(0, lambda n=dest_name, stage=s:
                               self._status.set(f"⚠️ Partial decrypt — failed at layer {stage} → {n}"))
                    self.after(0, lambda d=dest, stage=s, msg=m:
                               messagebox.showwarning(
                                   "Partial Decrypt",
                                   f"Decryption failed at layer {stage}:\n{msg}\n\n"
                                   f"Last valid .isd saved to:\n{d}\n\n"
                                   "Open it in the File tab or correct the password and retry.",
                               ))

        except Exception as exc:
            msg = str(exc)
            self.after(0, lambda m=msg: self._status.set(f"❌ {m}"))
            self.after(0, lambda m=msg: messagebox.showerror("Decrypt Error", m))

