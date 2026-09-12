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
from core.engine import STAGE_ALGORITHMS, PGP_ALGORITHMS

from .theme import FONT_TITLE, FONT_BODY, FONT_MONO, FONT_SMALL, PAD
from .widgets import FileSelector, _clean_dnd_path, Tooltip


# ── Embedded PGP key UI for one pipeline stage ────────────────────────────

class _PGPStageSection(ttk.Frame):
    """
    Compact PGP key inputs inside a stage row.
    Adapts between PGP (1 pub key), PGP-Multi (N pub keys), PGP-Escrow (N + escrow).
    """

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._pub_rows: list[tuple[tk.StringVar, ttk.Frame]] = []

        # Public key section
        self._pub_title = ttk.Label(self, text="Public key (encrypt):", font=FONT_SMALL)
        self._pub_title.pack(anchor=W)
        self._pub_frame = ttk.Frame(self)
        self._pub_frame.pack(fill=X, pady=(0, 2))
        self._add_recip_btn = ttk.Button(
            self, text="＋ Add recipient", bootstyle="outline-primary",
            command=self._add_pub_row,
        )

        # Escrow section (hidden initially)
        self._escrow_sep = ttk.Separator(self)
        self._escrow_lbl = ttk.Label(self, text="⚠  Escrow key:", font=FONT_SMALL)
        self._escrow_var = tk.StringVar()
        self._escrow_row_f = ttk.Frame(self)
        self._build_path_field(self._escrow_row_f, self._escrow_var)

        # Private key (always present)
        ttk.Separator(self).pack(fill=X, pady=(4, 2))
        ttk.Label(self, text="Private key (decrypt):", font=FONT_SMALL).pack(anchor=W)
        self._priv_var = tk.StringVar()
        priv_f = ttk.Frame(self)
        priv_f.pack(fill=X)
        self._build_path_field(priv_f, self._priv_var)

        # Seed first pub row (non-removable)
        self._add_pub_row(removable=False)

    def _build_path_field(self, frame: ttk.Frame, var: tk.StringVar) -> None:
        ttk.Entry(frame, textvariable=var, font=FONT_SMALL).pack(
            side=LEFT, fill=X, expand=True, padx=(0, 2))
        ttk.Button(frame, text="📁", width=3, bootstyle="outline",
                   command=lambda: self._browse_pem(var)).pack(side=LEFT)

    def _browse_pem(self, var: tk.StringVar) -> None:
        p = filedialog.askopenfilename(
            filetypes=[("PEM / Key files", "*.pem *.key *.pub *.txt"), ("All files", "*.*")]
        )
        if p:
            var.set(p)

    def _add_pub_row(self, removable: bool = True) -> None:
        var = tk.StringVar()
        row = ttk.Frame(self._pub_frame)
        if removable:
            ttk.Button(row, text="–", width=2, bootstyle="outline-danger",
                       command=lambda r=row, v=var: self._remove_pub_row(r, v)
                       ).pack(side=LEFT, padx=(0, 2))
        ttk.Entry(row, textvariable=var, font=FONT_SMALL).pack(
            side=LEFT, fill=X, expand=True, padx=(0, 2))
        ttk.Button(row, text="📁", width=3, bootstyle="outline",
                   command=lambda v=var: self._browse_pem(v)).pack(side=LEFT)
        row.pack(fill=X, pady=(0, 1))
        self._pub_rows.append((var, row))

    def _remove_pub_row(self, row: ttk.Frame, var: tk.StringVar) -> None:
        if len(self._pub_rows) <= 1:
            return
        row.destroy()
        self._pub_rows = [(v, r) for v, r in self._pub_rows
                          if r.winfo_exists() and r is not row]

    def set_mode(self, algo: str) -> None:
        is_multi = algo in ("PGP-Multi", "PGP-Escrow")
        self._pub_title.config(
            text="Public keys (encrypt):" if is_multi else "Public key (encrypt):")
        if is_multi:
            self._add_recip_btn.pack(anchor=W, pady=(2, 0))
        else:
            self._add_recip_btn.pack_forget()
            while len(self._pub_rows) > 1:
                _, r = self._pub_rows.pop()
                r.destroy()
        if algo == "PGP-Escrow":
            self._escrow_sep.pack(fill=X, pady=(4, 2))
            self._escrow_lbl.pack(anchor=W)
            self._escrow_row_f.pack(fill=X, pady=(0, 2))
        else:
            self._escrow_sep.pack_forget()
            self._escrow_lbl.pack_forget()
            self._escrow_row_f.pack_forget()

    def get_config(self, algo: str) -> dict:
        base: dict = {
            "algorithm": algo, "key_type": "pgp", "pw_source": "",
            "priv_pem_path": self._priv_var.get().strip(),
        }
        if algo == "PGP":
            base["pub_pem_path"] = (self._pub_rows[0][0].get().strip()
                                    if self._pub_rows else "")
        else:
            base["pub_pem_paths"] = [v.get().strip() for v, _ in self._pub_rows
                                     if v.get().strip()]
            if algo == "PGP-Escrow":
                base["escrow_pem_path"] = self._escrow_var.get().strip()
        return base


# ── One pipeline stage row ────────────────────────────────────────────────

class _StageRow(ttk.Frame):
    """
    One stage: algorithm + password (or PGP keys).
    ↑/↓ buttons allow reordering within the pipeline.
    """

    _KEY_TYPES = ["text", "file", "image", "video", "bytefile", "txtfile"]

    def __init__(self, parent, index: int, on_delete, on_move):
        super().__init__(parent)
        self.columnconfigure(1, weight=1)
        self._on_delete = on_delete
        self._on_move = on_move

        # ── Index label ───────────────────────────────────────────────
        self._lbl = ttk.Label(self, font=FONT_BODY, width=3)
        self._lbl.grid(row=0, column=0, rowspan=2, padx=(0, 6))
        self.set_index(index)

        # ── Algorithm ─────────────────────────────────────────────────
        self.algo_var = tk.StringVar(value="AES-256-CBC")
        algo_cb = ttk.Combobox(
            self, textvariable=self.algo_var, values=STAGE_ALGORITHMS,
            state="readonly", width=18, font=FONT_BODY,
        )
        algo_cb.grid(row=0, column=1, sticky=W, pady=(0, 2))
        Tooltip(algo_cb, "保持加密與解密的 stage 順序一致；程式會依 layer 資訊自動以正確順序解密，無需手動調整。")

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

        # ── PGP section (shown when algo is PGP / PGP-Multi / PGP-Escrow) ─
        self._pgp_section = _PGPStageSection(self)
        # NOT gridded initially

        # ── Control buttons: ↑ ↓ ✕ ──────────────────────────────────
        ctrl = ttk.Frame(self)
        ctrl.grid(row=0, column=2, rowspan=2, padx=(6, 0), sticky=N)
        ttk.Button(ctrl, text="↑", width=2, bootstyle="outline-secondary",
                   command=lambda: self._on_move(self, -1)).pack(pady=(0, 1))
        ttk.Button(ctrl, text="↓", width=2, bootstyle="outline-secondary",
                   command=lambda: self._on_move(self, +1)).pack(pady=(0, 1))
        ttk.Button(ctrl, text="✕", width=2, bootstyle="outline-danger",
                   command=lambda: self._on_delete(self)).pack()

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
        algo = self.algo_var.get()
        if algo in PGP_ALGORITHMS:
            self._pw_row.grid_remove()
            self._pgp_section.set_mode(algo)
            self._pgp_section.grid(row=1, column=1, sticky=EW, pady=(0, 2))
        else:
            self._pgp_section.grid_remove()
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

    def _on_pw_drop(self, event):
        path = _clean_dnd_path(event.data)
        if path:
            if self.key_type_var.get() == "text":
                self.key_type_var.set("file")
            self.pw_var.set(path)

    # ── Public API ────────────────────────────────────────────────────

    def get_config(self) -> dict:
        """
        Return raw stage config.  Key derivation is deferred to the worker.
        """
        algo = self.algo_var.get()
        if algo in PGP_ALGORITHMS:
            return self._pgp_section.get_config(algo)
        return {
            "algorithm": algo,
            "key_type": self.key_type_var.get(),
            "pw_source": self.pw_var.get(),
        }


# ── MixtureTab ────────────────────────────────────────────────────────────

class MixtureTab(ttk.Frame):
    """
    Multi-stage pipeline encryption with two modes.

    All-In-One  — all stages fused into ONE .isd (decrypt order: N→1).
    Layered     — each stage wraps content in its own .isd; peel one layer at a
                 time in File tab (each layer = different password supported).
    """

    _MODES = [
        ("All-In-One", "all-in-one",
         f"content → enc₁ → enc₂ → … → ONE {BYTEFILE_EXT}  【decrypt: N→1】"),
        ("Layered", "layered",
         f"content → isd₁ → isd₂ → … → outer {BYTEFILE_EXT}  【File tab peels one layer】"),
    ]

    def __init__(self, parent, status_var: tk.StringVar, **kw):
        super().__init__(parent, padding=PAD, **kw)
        self._status = status_var
        self._stages: list[_StageRow] = []
        self._last_bytes: bytes | None = None   # for text-mode save buttons
        self._result_shown = False
        self._build_ui()
        self._add_stage()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self):
        ttk.Label(self, text="🔗  Mixture Pipeline", font=FONT_TITLE).pack(
            anchor=W, pady=(0, 4))
        ttk.Label(
            self,
            text=(
                "N stages, each with its own algorithm & password.  "
                "Encrypt: 1→N  |  Decrypt: N→1.  "
                "Multi-Encrypt = one .isd for all stages.  "
                "Layer-Wrap = each stage wraps its own .isd (File tab peels one layer at a time)."
            ),
            font=FONT_SMALL, wraplength=740,
        ).pack(anchor=W, pady=(0, PAD))

        # ── Mode + Input type ─────────────────────────────────────────
        top = ttk.Frame(self)
        top.pack(fill=X, pady=(0, 8))

        mode_lf = ttk.Labelframe(top, text="Mode", padding=8)
        mode_lf.pack(side=LEFT, padx=(0, 12))
        self.mode_var = tk.StringVar(value="all-in-one")
        for label, value, hint in self._MODES:
            ttk.Radiobutton(
                mode_lf, text=f"{label}  —  {hint}",
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

        # File mode widget
        self.file_sel = FileSelector(self._input_container, label="Select input file")
        self.file_sel.pack(fill=X)

        # Text mode widget (hidden by default)
        self._text_frame = ttk.Frame(self._input_container)
        in_lf = ttk.Labelframe(
            self._text_frame,
            text="Input  (for decrypt: paste the .isd content here, or drag-drop the file)",
            padding=4,
        )
        in_lf.pack(fill=X, pady=(0, 4))
        self.input_text = tk.Text(in_lf, height=5, font=FONT_MONO, wrap=WORD)
        self.input_text.pack(fill=X)
        # DnD: load .isd file content into text area
        self.input_text.drop_target_register(DND_FILES)
        self.input_text.dnd_bind("<<Drop>>", self._on_text_drop)

        # ── Pipeline stages (scrollable canvas) ───────────────────────
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
        self._act_frame = ttk.Frame(self)
        self._act_frame.pack(fill=X, pady=(0, 4))
        ttk.Button(
            self._act_frame, text="🔒  Encrypt", bootstyle="warning",
            command=self._do_encrypt,
        ).pack(side=LEFT, expand=True, fill=X, padx=(0, 4), ipady=6)
        ttk.Button(
            self._act_frame, text="🔓  Decrypt", bootstyle="success",
            command=self._do_decrypt,
        ).pack(side=LEFT, expand=True, fill=X, padx=(4, 0), ipady=6)

        # ── Text-mode result area (hidden until first text-mode operation) ─
        self._result_lf = ttk.Labelframe(self, text="Result", padding=6)
        # packed on first use via _show_result()
        result_hint = ttk.Label(
            self._result_lf,
            text="Use  ↩ Use as Input  to chain operations (e.g. decrypt outer, then decrypt inner).",
            font=FONT_SMALL,
        )
        result_hint.pack(anchor=W, pady=(0, 2))
        self.output_text = tk.Text(
            self._result_lf, height=6, font=FONT_MONO, wrap=WORD, state="disabled",
        )
        self.output_text.pack(fill=X, pady=(0, 4))
        result_btns = ttk.Frame(self._result_lf)
        result_btns.pack(fill=X)
        ttk.Button(
            result_btns, text="📋 Copy", bootstyle="outline",
            command=self._copy_result,
        ).pack(side=LEFT, padx=(0, 4))
        ttk.Button(
            result_btns, text=f"💾 Save {BYTEFILE_EXT}", bootstyle="outline",
            command=lambda: self._save_result(BYTEFILE_EXT),
        ).pack(side=LEFT, padx=(0, 4))
        ttk.Button(
            result_btns, text="💾 Save .txt", bootstyle="outline",
            command=lambda: self._save_result(".txt"),
        ).pack(side=LEFT, padx=(0, 4))
        ttk.Button(
            result_btns, text="↩ Use as Input", bootstyle="outline-info",
            command=self._use_result_as_input,
        ).pack(side=LEFT)

    # ── Input switching ───────────────────────────────────────────────

    def _switch_input(self):
        if self.input_type_var.get() == "file":
            self._text_frame.pack_forget()
            if self._result_shown:
                self._result_lf.pack_forget()
            self.file_sel.pack(fill=X)
        else:
            self.file_sel.pack_forget()
            self._text_frame.pack(fill=X)
            if self._result_shown:
                self._result_lf.pack(fill=X, pady=(0, 4))

    def _on_text_drop(self, event):
        """Load a dropped .isd file's text content into the input area."""
        path = _clean_dnd_path(event.data)
        if path and Path(path).exists():
            try:
                content = Path(path).read_text(encoding="utf-8")
                self.input_text.delete("1.0", END)
                self.input_text.insert("1.0", content)
            except Exception as exc:
                messagebox.showerror("Load Error", str(exc))

    # ── Stage management ──────────────────────────────────────────────

    def _add_stage(self):
        idx = len(self._stages)
        row = _StageRow(self._stage_frame, idx, self._remove_stage, self._move_stage)
        row.pack(fill=X, padx=4, pady=2)
        self._stages.append(row)

    def _remove_stage(self, row: _StageRow):
        if len(self._stages) <= 1:
            return
        row.destroy()
        self._stages.remove(row)
        for i, s in enumerate(self._stages):
            s.set_index(i)

    def _move_stage(self, row: _StageRow, delta: int):
        """Move *row* up (delta=-1) or down (delta=+1) in the pipeline."""
        i = self._stages.index(row)
        j = i + delta
        if j < 0 or j >= len(self._stages):
            return
        self._stages[i], self._stages[j] = self._stages[j], self._stages[i]
        for s in self._stages:
            s.pack_forget()
        for k, s in enumerate(self._stages):
            s.pack(fill=X, padx=4, pady=2)
            s.set_index(k)

    def _clear_stages(self):
        for s in self._stages:
            s.destroy()
        self._stages.clear()
        self._add_stage()

    # ── Input + stage helpers ─────────────────────────────────────────

    def _read_input(self) -> tuple[bytes, str | None] | None:
        """Return (raw_bytes, original_name_or_None), or show warning and None."""
        if self.input_type_var.get() == "file":
            src = self.file_sel.get()
            if not src:
                messagebox.showwarning("Input", "Select a file.")
                return None
            p = Path(src)
            return p.read_bytes(), p.name
        raw = self.input_text.get("1.0", END).rstrip("\n")
        if not raw:
            messagebox.showwarning("Input", "Enter text or paste .isd content.")
            return None
        return raw.encode("utf-8"), None

    def _get_stages(self) -> list[dict] | None:
        stages = [s.get_config() for s in self._stages]
        if not stages:
            messagebox.showwarning("Pipeline", "Add at least one stage.")
            return None
        return stages

    # ── Text-mode result helpers ──────────────────────────────────────

    def _show_result(self, raw_bytes: bytes) -> None:
        """Populate the result area and make it visible (text mode only)."""
        self._last_bytes = raw_bytes
        try:
            display = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            import base64 as _b64
            display = (
                "(binary result — displayed as Base64)\n"
                + _b64.b64encode(raw_bytes).decode("ascii")
            )
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", END)
        self.output_text.insert("1.0", display)
        self.output_text.config(state="disabled")
        if not self._result_shown:
            self._result_lf.pack(fill=X, pady=(0, 4))
            self._result_shown = True

    def _copy_result(self):
        txt = self.output_text.get("1.0", END).rstrip("\n")
        self.clipboard_clear()
        self.clipboard_append(txt)
        self._status.set("✅ Copied to clipboard")

    def _save_result(self, ext: str):
        if self._last_bytes is None:
            messagebox.showwarning("No Result", "No result to save yet.")
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[
                ("Encrypted file", f"*{BYTEFILE_EXT}"),
                ("Text file", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if dest:
            Path(dest).write_bytes(self._last_bytes)
            self._status.set(f"✅ Saved → {Path(dest).name}")

    def _use_result_as_input(self):
        """Copy the result text back into the input area for chained operations."""
        txt = self.output_text.get("1.0", END).rstrip("\n")
        self.input_text.delete("1.0", END)
        self.input_text.insert("1.0", txt)
        self._status.set("↩ Result moved to Input — ready for next operation")

    # ── Encrypt ───────────────────────────────────────────────────────

    def _do_encrypt(self):
        inp = self._read_input()
        if inp is None:
            return
        stages = self._get_stages()
        if stages is None:
            return

        is_text = self.input_type_var.get() == "text"
        dest = None
        if not is_text:
            dest = filedialog.asksaveasfilename(
                defaultextension=BYTEFILE_EXT,
                filetypes=[("Encrypted file", f"*{BYTEFILE_EXT}"), ("All files", "*.*")],
            )
            if not dest:
                return

        self._status.set("Encrypting…")
        threading.Thread(
            target=self._encrypt_worker,
            args=(inp, stages, self.mode_var.get(), dest, is_text),
            daemon=True,
        ).start()

    def _encrypt_worker(
        self,
        inp: tuple[bytes, str | None],
        stages: list[dict],
        mode: str,
        dest: str | None,
        is_text: bool,
    ):
        try:
            data, orig_name = inp
            if mode == "multi-encrypt":
                bf = encrypt_multi(data, stages,
                                   orig_name=orig_name, orig_size=len(data))
                result_bytes = bf.pack().encode("utf-8")
                if dest:
                    bf.save(dest)
            else:  # layer-wrap
                result_bytes = encrypt_layer_wrap(
                    data, stages,
                    orig_name=orig_name or "text", orig_size=len(data),
                )
                if dest:
                    Path(dest).write_bytes(result_bytes)

            if is_text:
                self.after(0, lambda rb=result_bytes: self._show_result(rb))
                self.after(0, lambda: self._status.set("✅ Encrypted — result shown below"))
            else:
                n = Path(dest).name
                self.after(0, lambda n=n: self._status.set(f"✅ Encrypted → {n}"))
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

        is_text = self.input_type_var.get() == "text"
        dest = None
        if not is_text:
            dest = filedialog.asksaveasfilename(filetypes=[("All files", "*.*")])
            if not dest:
                return

        self._status.set("Decrypting…")
        threading.Thread(
            target=self._decrypt_worker,
            args=(inp, stages, self.mode_var.get(), dest, is_text),
            daemon=True,
        ).start()

    def _decrypt_worker(
        self,
        inp: tuple[bytes, str | None],
        stages: list[dict],
        mode: str,
        dest: str | None,
        is_text: bool,
    ):
        def _finish_ok(result: bytes):
            if is_text:
                self.after(0, lambda r=result: self._show_result(r))
                self.after(0, lambda: self._status.set("✅ Decrypted — result shown below"))
            else:
                Path(dest).write_bytes(result)
                n = Path(dest).name
                self.after(0, lambda n=n: self._status.set(f"✅ Decrypted → {n}"))
                self.after(0, lambda d=dest: messagebox.showinfo("Done", f"Decrypted!\n{d}"))

        try:
            data, _ = inp

            if mode == "multi-encrypt":
                try:
                    bf = ByteFile.parse(data.decode("utf-8"))
                except Exception as exc:
                    raise ValueError(
                        f"Cannot parse input as {BYTEFILE_EXT} — {exc}\n"
                        "Paste the full .isd text or switch to File input and select the file."
                    ) from exc
                result = decrypt_multi(bf, stages)
                _finish_ok(result)

            else:  # layer-wrap
                try:
                    result = decrypt_layer_wrap(data, stages)
                    _finish_ok(result)
                except PartialDecryptError as pde:
                    partial = pde.partial
                    s, m = pde.stage_num, str(pde)
                    if is_text:
                        self.after(0, lambda p=partial: self._show_result(p))
                        self.after(0, lambda stage=s, msg=m:
                                   self._status.set(
                                       f"⚠️ Partial decrypt — failed at layer {stage}"))
                        self.after(0, lambda stage=s, msg=m:
                                   messagebox.showwarning(
                                       "Partial Decrypt",
                                       f"Failed at layer {stage}:\n{msg}\n\n"
                                       "Last valid .isd shown in result area.\n"
                                       "Use 'Save .isd' to keep it or '↩ Use as Input' "
                                       "to retry with the correct password.",
                                   ))
                    else:
                        Path(dest).write_bytes(pde.partial)
                        n = Path(dest).name
                        self.after(0, lambda n=n, stage=s:
                                   self._status.set(
                                       f"⚠️ Partial — failed at layer {stage} → {n}"))
                        self.after(0, lambda d=dest, stage=s, msg=m:
                                   messagebox.showwarning(
                                       "Partial Decrypt",
                                       f"Failed at layer {stage}:\n{msg}\n\n"
                                       f"Last valid .isd saved to:\n{d}\n\n"
                                       "Open it in File tab or correct the password and retry.",
                                   ))

        except Exception as exc:
            msg = str(exc)
            self.after(0, lambda m=msg: self._status.set(f"❌ {m}"))
            self.after(0, lambda m=msg: messagebox.showerror("Decrypt Error", m))

