"""Tab 2 — Text Encryption / Decryption."""

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
from core.engine import ALGORITHMS, PGP_ALGORITHMS, EncryptionEngine
from core.utils import derive_key_bytes

from .theme import FONT_TITLE, FONT_BODY, FONT_MONO, FONT_SUBTITLE, PAD
from .widgets import PasswordFrame, CollapsiblePanel, Tooltip, _clean_dnd_path, PGPEncryptPanel, PGPDecryptPanel


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
        _load_bf_btn = ttk.Button(btn_row, text=f"Load {BYTEFILE_EXT}", bootstyle="outline-info",
               command=self._load_bytefile)
        _load_bf_btn.pack(side=LEFT, padx=(0, 6))
        Tooltip(_load_bf_btn, f"載入 {BYTEFILE_EXT} 並將內容顯示在輸入框中")
        _load_txt_btn = ttk.Button(btn_row, text="Load text file", bootstyle="outline-secondary",
                   command=self._load_textfile)
        _load_txt_btn.pack(side=LEFT, padx=(0, 6))
        Tooltip(_load_txt_btn, "載入文字檔案（自動嘗試 UTF-8 / latin-1 編碼）")
        ttk.Button(btn_row, text="Clear", bootstyle="outline-danger",
                   command=self._clear_input).pack(side=RIGHT)

        self.input_text = tk.Text(inp_frame, height=6, font=FONT_MONO, wrap=WORD)
        inp_scroll = ttk.Scrollbar(inp_frame, command=self.input_text.yview)
        self.input_text.config(yscrollcommand=inp_scroll.set)
        inp_scroll.pack(side=RIGHT, fill=Y)
        self.input_text.pack(fill=BOTH, expand=True)

        # ── Drag-and-drop onto input text area ────────────────────────
        self.input_text.drop_target_register(DND_FILES)
        self.input_text.dnd_bind("<<Drop>>", self._on_text_drop)

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
        _algo_cb = ttk.Combobox(
            settings, textvariable=self.algo_var, values=ALGORITHMS,
            state="readonly", width=18, font=FONT_BODY,
        )
        _algo_cb.pack(anchor=W, pady=(2, 6))
        Tooltip(_algo_cb, "AES-256-CBC：預設區塊加密 | AES-256-GCM：帶完整性驗證 | ChaCha20：現代高效演算法 | XOR/XOR-FOLD：輕量 | PGP：公開金鑰包覆")

        # PGP options (hidden unless PGP selected)
        self.pgp_inner_var = tk.StringVar(value="None")
        inner_values = ["None"] + [a for a in ALGORITHMS if not a.startswith("PGP")]
        self._pgp_inner_cb = ttk.Combobox(
            settings, textvariable=self.pgp_inner_var, values=inner_values,
            state="readonly", width=18, font=FONT_BODY,
        )
        self._pgp_inner_cb.pack(anchor=W, pady=(0, 4))
        Tooltip(self._pgp_inner_cb, "Inner algorithm used before PGP wrapping")

        self._pgp_pub_list: list[str] = []
        row = ttk.Frame(settings)
        row.pack(anchor=W)
        self._pgp_pub_lbl = ttk.Label(row, text="Recipients: 0")
        self._pgp_pub_lbl.pack(side=LEFT)
        ttk.Button(row, text="Add pubkey", bootstyle="outline-primary", command=self._add_pgp_pubkey).pack(side=LEFT, padx=(6, 4))
        ttk.Button(row, text="Clear", bootstyle="outline-danger", command=self._clear_pgp_pubkeys).pack(side=LEFT)
        # hide until PGP selected
        self._pgp_inner_cb.pack_forget()
        row.pack_forget()
        # show/hide controls when algo changes
        self.algo_var.trace_add("write", lambda *_: self._update_pgp_ui())

    def _add_pgp_pubkey(self):
        p = filedialog.askopenfilename(filetypes=[("PEM", "*.pem"), ("All files", "*")])
        if not p:
            return
        self._pgp_pub_list.append(p)
        self._pgp_pub_lbl.configure(text=f"Recipients: {len(self._pgp_pub_list)}")

    def _clear_pgp_pubkeys(self):
        self._pgp_pub_list.clear()
        self._pgp_pub_lbl.configure(text="Recipients: 0")

    def _update_pgp_ui(self):
        if self.algo_var.get().startswith("PGP"):
            self._pgp_inner_cb.pack(anchor=W, pady=(0, 4))
            self._pgp_pub_lbl.master.pack(anchor=W)
        else:
            try:
                self._pgp_inner_cb.pack_forget()
                self._pgp_pub_lbl.master.pack_forget()
            except Exception:
                pass
        

        self.b64_var = tk.BooleanVar(value=True)
        _b64_cb = ttk.Checkbutton(
            settings, text="Base64 output (display-safe)",
            variable=self.b64_var, bootstyle="round-toggle",
        )
        _b64_cb.pack(anchor=W)
        Tooltip(_b64_cb, "開啟：輸出 Base64 可列印字元 |關閉：輸出原始 Hex 字串")

        # ── PGP panel (shown when a PGP algorithm is selected) ─────────
        self._pgp_frame = ttk.Frame(self)
        self._pgp_enc_panel = PGPEncryptPanel(self._pgp_frame)
        self._pgp_enc_panel.pack(fill=X, pady=(0, 4))
        ttk.Separator(self._pgp_frame).pack(fill=X, pady=(0, 4))
        self._pgp_dec_panel = PGPDecryptPanel(self._pgp_frame)
        self._pgp_dec_panel.pack(fill=X)
        self.algo_var.trace_add("write", lambda *_: self._on_algo_change())

        # ── Action buttons ─────────────────────────────────
        self._btn_frame = ttk.Frame(self)
        btn_frame = self._btn_frame
        btn_frame.pack(fill=X, pady=6)
        _enc_btn = ttk.Button(
            self._btn_frame, text="🔒  Encrypt", bootstyle="warning",
            command=self._do_encrypt,
        )
        _enc_btn.pack(side=LEFT, expand=True, fill=X, padx=(0, 4), ipady=6)
        Tooltip(_enc_btn, "加密輸入框中的文字，結果顯示於下方輸出框")
        _dec_btn = ttk.Button(
            self._btn_frame, text="🔓  Decrypt", bootstyle="success",
            command=self._do_decrypt,
        )
        _dec_btn.pack(side=LEFT, expand=True, fill=X, padx=(4, 0), ipady=6)
        Tooltip(_dec_btn, "解密輸入框中的內容，需輸入加密時相同的密碼")

        # --- Output area ---
        out_frame = ttk.Labelframe(self, text="Output", padding=PAD)
        out_frame.pack(fill=BOTH, expand=True, pady=(0, 4))

        out_btn_row = ttk.Frame(out_frame)
        out_btn_row.pack(fill=X, pady=(0, 4))
        ttk.Button(out_btn_row, text="📋 Copy to clipboard",
                   bootstyle="info", command=self._copy_clipboard).pack(side=LEFT, padx=(0, 6))
        ttk.Button(out_btn_row, text="💾 Save as .txt",
               bootstyle="outline-secondary", command=self._save_txt).pack(side=LEFT, padx=(0, 6))
        ttk.Button(out_btn_row, text=f"💾 Save as {BYTEFILE_EXT}",
               bootstyle="outline-warning", command=self._save_bytefile).pack(side=LEFT)

        self.output_text = tk.Text(out_frame, height=6, font=FONT_MONO, wrap=WORD, state=DISABLED)
        out_scroll = ttk.Scrollbar(out_frame, command=self.output_text.yview)
        self.output_text.config(yscrollcommand=out_scroll.set)
        out_scroll.pack(side=RIGHT, fill=Y)
        self.output_text.pack(fill=BOTH, expand=True)

        # internal storage of last encrypted bytes (for .isd save)
        self._last_encrypted_bytes: bytes | None = None
        self._last_note: dict | None = None

    # ── PGP panel toggle ────────────────────────────────────

    def _on_algo_change(self) -> None:
        if self.algo_var.get() in PGP_ALGORITHMS:
            self._pgp_enc_panel.set_mode(self.algo_var.get())
            self._pgp_frame.pack(fill=X, pady=(0, 6), before=self._btn_frame)
        else:
            self._pgp_frame.pack_forget()

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
        self._load_bytefile_from_path(p)

    def _load_textfile(self):
        p = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not p:
            return
        self._load_text_from_path(p)

    def _load_text_from_path(self, p: str):
        """Load a text file into the input box, trying UTF-8 then latin-1."""
        try:
            content = Path(p).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = Path(p).read_text(encoding="latin-1")
            except Exception as exc:
                messagebox.showerror("Load Error", str(exc))
                return
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))
            return
        self.input_text.delete("1.0", END)
        self.input_text.insert("1.0", content)
        self._status.set(f"Loaded text: {Path(p).name}")

    def _on_text_drop(self, event):
        """Handle a file dropped onto the text input area."""
        path = _clean_dnd_path(event.data)
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() == BYTEFILE_EXT:
            self._load_bytefile_from_path(str(p))
        else:
            self._load_text_from_path(str(p))

    def _load_bytefile_from_path(self, p: str):
        try:
            import base64 as _b64
            bf = ByteFile.load(p)
            b64 = _b64.b64encode(bf.content).decode("ascii")
            self.input_text.delete("1.0", END)
            self.input_text.insert("1.0", b64)
            self._status.set(f"Loaded bytefile: {Path(p).name}")
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
        # If using PGP, ensure inner cipher has a password when required
        if algo in PGP_ALGORITHMS:
            inner_algo = self._pgp_enc_panel.get_inner_algo()
            # 'None' inner algo means skip inner symmetric encryption; no password required
            if inner_algo not in ("None", "Base64") and not pw_source:
                messagebox.showwarning("Password", f"Password required for inner cipher '{inner_algo}'.")
                return
        else:
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
            key_bytes = derive_key_bytes(pw_source, key_type) if pw_source else b""

            if algo in PGP_ALGORITHMS:
                inner_algo = self._pgp_enc_panel.get_inner_algo()
                # If inner_algo == 'None', do not perform inner symmetric encryption
                if inner_algo == "None":
                    inner_ct = data
                else:
                    if not pw_source and inner_algo != "Base64":
                        raise ValueError(f"Password required for inner cipher '{inner_algo}'")
                    inner_ct = data
                    # support iterations if needed
                    for _ in range(1):
                        inner_ct = EncryptionEngine.encrypt(inner_ct, key_bytes, inner_algo)
                pub_pems = self._pgp_enc_panel.get_pub_pems()
                escrow_pem = self._pgp_enc_panel.get_escrow_pem()
                if algo == "PGP":
                    encrypted = EncryptionEngine.pgp_encrypt(inner_ct, pub_pems[0])
                else:
                    all_pems = list(pub_pems) + ([escrow_pem] if escrow_pem else [])
                    encrypted = EncryptionEngine.pgp_encrypt_multi(inner_ct, all_pems)
                self._last_note = default_note(
                    algorithm=inner_algo, key_type=key_type, mode="layered",
                    iterations=1, original_filename=None, original_size=len(data),
                    pgp_mode=algo, pgp_escrow=(algo == "PGP-Escrow"),
                    pgp_recipient_count=len(pub_pems),
                )
            else:
                encrypted = EncryptionEngine.encrypt(data, key_bytes, algo)
                self._last_note = default_note(
                    algorithm=algo, key_type=key_type, mode="layered",
                    iterations=1, original_filename=None, original_size=len(data),
                )

            self._last_encrypted_bytes = encrypted

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
        if not pw_source and algo != "Base64" and algo not in PGP_ALGORITHMS:
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

            key_bytes = derive_key_bytes(pw_source, key_type) if pw_source else b""

            if algo in PGP_ALGORITHMS:
                priv_pem   = self._pgp_dec_panel.get_priv_pem()
                inner_ct   = EncryptionEngine.pgp_decrypt(encrypted, priv_pem)
                inner_algo = self._pgp_enc_panel.get_inner_algo()
                if inner_algo == "None":
                    decrypted = inner_ct  # no inner cipher was applied
                else:
                    decrypted = EncryptionEngine.decrypt(inner_ct, key_bytes, inner_algo)
            else:
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
