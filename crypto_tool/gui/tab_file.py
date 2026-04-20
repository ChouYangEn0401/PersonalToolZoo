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

from .theme import (
    FONT_TITLE, FONT_BODY, FONT_SUBTITLE, FONT_SMALL, PAD,
    GOLD_MID, GOLD_BRIGHT, AMBER, FG_MUTED, FG_LIGHT,
)
from .widgets import FileSelector, PasswordFrame, CollapsiblePanel, Tooltip, AlgoBar


class FileTab(ttk.Frame):
    def __init__(self, parent, status_var: tk.StringVar, **kw):
        super().__init__(parent, padding=PAD, **kw)
        self._status = status_var

        # ── Shared state ─────────────────────────────────────────────
        self.algo_var         = tk.StringVar(value="AES-256-CBC")   # encrypt algo
        self.dec_algo_var     = tk.StringVar(value="AES-256-CBC")   # manual decrypt algo
        self.algo_visible_var = tk.BooleanVar(value=True)           # store algo in metadata
        self.author_var       = tk.StringVar(value="@anonymous")
        self.hint_var         = tk.StringVar()
        self.mode_var         = tk.StringVar(value="simple")
        self.iter_var         = tk.IntVar(value=1)
        self._detected_algo: str | None = None  # read from loaded .isd

        self._build_ui()

    # ── Top-level layout ──────────────────────────────────────────────

    def _build_ui(self):
        ttk.Label(self, text="🔐  File Encryption", font=FONT_TITLE).pack(
            anchor=W, pady=(0, PAD)
        )
        cols = ttk.Frame(self)
        cols.pack(fill=BOTH, expand=True)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)
        self._build_encrypt_card(cols)
        self._build_decrypt_card(cols)

    # ── Encrypt card (left) ───────────────────────────────────────────

    def _build_encrypt_card(self, parent):
        card = ttk.Labelframe(parent, text="🔒  Encrypt", padding=PAD)
        card.grid(row=0, column=0, sticky=NSEW, padx=(0, PAD // 2), pady=(0, PAD))

        # ── Source file ───────────────────────────────────────────────
        self.enc_file = FileSelector(card, label="Source file")
        self.enc_file.pack(fill=X, pady=(0, 8))
        Tooltip(self.enc_file._entry, "選擇要加密的檔案，或直接拖拉進此欄位")

        # ── Password ──────────────────────────────────────────────────
        self.enc_pw = PasswordFrame(card, title="Encryption password")
        self.enc_pw.pack(fill=X, pady=(0, 8))
        Tooltip(self.enc_pw._pw_entry, "輸入加密密碼。Key type 可切換為檔案/圖片作為金鑰")

        # ── Advanced Settings (collapsible, INSIDE this card) ─────────
        adv = CollapsiblePanel(card, title="Advanced Settings")
        adv.pack(fill=X, pady=(0, 8))
        self._build_adv_content(adv.content)

        # ── Action button ─────────────────────────────────────────────
        btn = ttk.Button(
            card, text="🔒  Encrypt & Save",
            bootstyle="warning", command=self._do_encrypt,
        )
        btn.pack(fill=X, ipady=6)
        Tooltip(btn, f"加密選取的檔案並儲存為 {BYTEFILE_EXT} 格式")

    def _build_adv_content(self, c: ttk.Frame):
        """Build contents of the Advanced Settings panel."""

        # ── Algorithm bar ─────────────────────────────────────────────
        tk.Label(
            c, text="Algorithm",
            font=("Segoe UI", 9, "bold"),
            fg=GOLD_MID, bg=_bg(c),
        ).pack(anchor=W, pady=(2, 4))

        self._enc_algo_bar = AlgoBar(c, self.algo_var, ALGORITHMS)
        self._enc_algo_bar.pack(fill=X, pady=(0, 6))
        Tooltip(
            self._enc_algo_bar,
            "AES·CBC：業界預設 | AES·GCM：附完整性驗證 | "
            "ChaCha20：現代串流 | Blowfish：經典 | "
            "3DES：相容舊系統 | XOR：輕量 | XOR-FOLD：折疊金鑰的 XOR（強化） | Base64：僅編碼",
        )

        # ── Reveal-algorithm toggle ───────────────────────────────────
        vis_row = ttk.Frame(c)
        vis_row.pack(fill=X, pady=(0, 8))
        _vis = ttk.Checkbutton(
            vis_row,
            text="Reveal algorithm in metadata",
            variable=self.algo_visible_var,
            bootstyle="round-toggle",
        )
        _vis.pack(side=LEFT)
        Tooltip(
            _vis,
            "開啟（預設）：演算法名稱存入 metadata，解密時自動辨識並填入\n"
            "關閉：演算法隱藏，解密方必須手動選擇正確演算法",
        )

        ttk.Separator(c).pack(fill=X, pady=(0, 8))

        # ── Author + Hint (2-col grid) ────────────────────────────────
        g = ttk.Frame(c)
        g.pack(fill=X, pady=(0, 4))
        g.columnconfigure(1, weight=1)

        ttk.Label(g, text="Author:", font=FONT_BODY, width=14).grid(
            row=0, column=0, sticky=W, pady=2
        )
        ttk.Entry(g, textvariable=self.author_var, font=FONT_BODY).grid(
            row=0, column=1, sticky=EW, padx=(4, 0), pady=2
        )

        ttk.Label(g, text="Password hint:", font=FONT_BODY, width=14).grid(
            row=1, column=0, sticky=W, pady=2
        )
        _hint_e = ttk.Entry(g, textvariable=self.hint_var, font=FONT_BODY)
        _hint_e.grid(row=1, column=1, sticky=EW, padx=(4, 0), pady=2)
        Tooltip(_hint_e, f"儲存在 {BYTEFILE_EXT} 中的明文提示，解密時會自動顯示給使用者（非必填）")

        # ── Mode + Iterations ─────────────────────────────────────────
        bot = ttk.Frame(c)
        bot.pack(fill=X, pady=(6, 2))

        ttk.Label(bot, text="Mode:", font=FONT_BODY).pack(side=LEFT)
        _sr = ttk.Radiobutton(bot, text="Simple", variable=self.mode_var, value="simple")
        _sr.pack(side=LEFT, padx=(6, 8))
        Tooltip(_sr, f"連續加密 N 次後整體包成一個 {BYTEFILE_EXT}")
        _nr = ttk.Radiobutton(bot, text="Node", variable=self.mode_var, value="node")
        _nr.pack(side=LEFT, padx=(0, 16))
        Tooltip(_nr, f"每次加密都各自包成一個 {BYTEFILE_EXT}，層層包裝")

        ttk.Label(bot, text="Iter:", font=FONT_BODY).pack(side=LEFT)
        _iter = ttk.Spinbox(
            bot, from_=1, to=20, textvariable=self.iter_var,
            width=4, font=FONT_BODY,
        )
        _iter.pack(side=LEFT, padx=(4, 0))
        Tooltip(_iter, "加密重複次數（1–20）。一般使用 1 即可")

        # ── Original file info reveal toggles ─────────────────────────
        info_row = ttk.Frame(c)
        info_row.pack(fill=X, pady=(6, 2))
        self.reveal_orig_name_var = tk.BooleanVar(value=True)
        self.reveal_orig_size_var = tk.BooleanVar(value=True)
        self.reveal_keytype_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            info_row, text="Reveal original filename", variable=self.reveal_orig_name_var,
            bootstyle="round-toggle"
        ).pack(side=LEFT, padx=(0, 8))
        Tooltip(info_row, f"When enabled, the original filename is stored in the {BYTEFILE_EXT} NOTE")
        ttk.Checkbutton(
            info_row, text="Reveal original size", variable=self.reveal_orig_size_var,
            bootstyle="round-toggle"
        ).pack(side=LEFT, padx=(0, 8))
        ttk.Checkbutton(
            info_row, text="Reveal key type", variable=self.reveal_keytype_var,
            bootstyle="round-toggle"
        ).pack(side=LEFT)
        Tooltip(info_row, f"Control whether the key_type is recorded inside the {BYTEFILE_EXT} NOTE")

    # ── Decrypt card (right) ──────────────────────────────────────────

    def _build_decrypt_card(self, parent):
        card = ttk.Labelframe(parent, text="🔓  Decrypt", padding=PAD)
        card.grid(row=0, column=1, sticky=NSEW, padx=(PAD // 2, 0), pady=(0, PAD))

        # ── .isd selector ────────────────────────────────────────
        self.dec_file = FileSelector(
            card, label=f"Select {BYTEFILE_EXT}",
            filetypes=[("ByteFile", f"*{BYTEFILE_EXT}"), ("All files", "*.*")],
        )
        self.dec_file.pack(fill=X, pady=(0, 8))
        Tooltip(self.dec_file._entry, f"選擇要解密的 {BYTEFILE_EXT}，或直接拖拉進此欄位")

        # ── File Metadata panel ───────────────────────────────────────
        info = ttk.Labelframe(card, text="File Metadata", padding=(8, 6))
        info.pack(fill=X, pady=(0, 8))
        info.columnconfigure(1, weight=1)

        def _mrow(label: str, row: int) -> ttk.Label:
            ttk.Label(
                info, text=label, font=FONT_SMALL,
                foreground=FG_MUTED, width=11,
            ).grid(row=row, column=0, sticky=W, padx=(0, 4), pady=2)
            val = ttk.Label(info, text="—", font=FONT_SMALL)
            val.grid(row=row, column=1, sticky=W, pady=2)
            return val

        self._info_algo_lbl   = _mrow("Algorithm:", 0)
        self._info_hint_lbl   = _mrow("Hint:", 1)
        self._info_author_lbl = _mrow("Author:", 2)

        # Status badge next to algorithm
        self._info_algo_badge = ttk.Label(info, text="", font=FONT_SMALL)
        self._info_algo_badge.grid(row=0, column=2, sticky=W, padx=(6, 0))

        # ── Manual algo selector slot (shown only when algo is hidden) ─
        self._manual_slot = ttk.Frame(card)
        self._manual_slot.pack(fill=X)   # always occupies vertical space
        self._manual_inner = ttk.Frame(self._manual_slot)
        # NOT packed yet — shown on demand by _on_dec_file_change
        tk.Label(
            self._manual_inner,
            text="⚠  Algorithm hidden — please select manually:",
            font=FONT_SMALL,
            fg=AMBER,
            bg=_bg(self._manual_inner),
        ).pack(anchor=W, pady=(4, 4))
        self._dec_algo_bar = AlgoBar(self._manual_inner, self.dec_algo_var, ALGORITHMS)
        self._dec_algo_bar.pack(fill=X, pady=(0, 4))

        # ── Password ──────────────────────────────────────────────────
        self.dec_pw = PasswordFrame(card, title="Decryption password")
        self.dec_pw.pack(fill=X, pady=(8, 10))
        Tooltip(self.dec_pw._pw_entry, "輸入加密時使用的密碼（類型需與加密時相同）")

        # ── Action button ─────────────────────────────────────────────
        btn = ttk.Button(
            card, text="🔓  Decrypt & Save",
            bootstyle="success", command=self._do_decrypt,
        )
        btn.pack(fill=X, ipady=6)
        Tooltip(btn, f"解密 {BYTEFILE_EXT} 並還原原始檔案")

        # Auto-load metadata when file path changes
        self.dec_file.path_var.trace_add(
            "write", lambda *_: self.after(80, self._on_dec_file_change)
        )

    # ── Decrypt metadata auto-fill ────────────────────────────────────

    def _on_dec_file_change(self):
        path = self.dec_file.get()
        if not path or not Path(path).is_file():
            self._reset_dec_info()
            return
        try:
            bf = ByteFile.load(path)
        except Exception:
            self._reset_dec_info()
            return

        # Hint
        hint = bf.note.get("password_hint") or None
        if hint:
            self._info_hint_lbl.configure(text=hint, foreground=GOLD_MID)
        else:
            self._info_hint_lbl.configure(text="(no hint set)", foreground=FG_MUTED)

        # Author
        author = bf.note.get("author") or "—"
        self._info_author_lbl.configure(text=author, foreground=FG_LIGHT)

        # Algorithm — None means hidden
        algo = bf.note.get("algorithm")
        if algo:
            self._info_algo_lbl.configure(text=algo, foreground=GOLD_BRIGHT)
            self._info_algo_badge.configure(text="✓ auto-detected", foreground="#4CAF50")
            self._detected_algo = algo
            self._manual_inner.pack_forget()
        else:
            self._info_algo_lbl.configure(text="hidden", foreground=AMBER)
            self._info_algo_badge.configure(text="⚠ select below", foreground=AMBER)
            self._detected_algo = None
            self._manual_inner.pack(fill=X)
        # show original filename/size only if present
        orig_name = bf.note.get("original_filename")
        orig_size = bf.note.get("original_size")
        if orig_name:
            self._info_author_lbl.configure(text=self._info_author_lbl.cget("text"))
            self._info_algo_lbl.configure(text=self._info_algo_lbl.cget("text"))
        # update hint and author already handled above
        # store for save dialog behavior
        self._bf_orig_name = orig_name
        self._bf_orig_size = orig_size

    def _reset_dec_info(self):
        for lbl in (self._info_algo_lbl, self._info_hint_lbl, self._info_author_lbl):
            lbl.configure(text="—", foreground=FG_MUTED)
        self._info_algo_badge.configure(text="")
        self._detected_algo = None
        self._manual_inner.pack_forget()

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
            # None → algorithm hidden from metadata
            stored_algo = algo if self.algo_visible_var.get() else None

            if mode == "node":
                payload = data
                for i in range(iterations):
                    encrypted = EncryptionEngine.encrypt(payload, key_bytes, algo)
                    note = default_note(
                        algorithm=algo, key_type=key_type, mode="node",
                        iterations=iterations,
                        author=self.author_var.get(),
                        password_hint=self.hint_var.get() or None,
                        original_filename=None,
                        original_size=None,
                    )
                    # reveal flags
                    note["reveal_original_filename"] = bool(self.reveal_orig_name_var.get())
                    note["reveal_original_size"] = bool(self.reveal_orig_size_var.get())
                    note["reveal_key_type"] = bool(self.reveal_keytype_var.get())
                    note["keep_original_file_info"] = (
                        bool(self.reveal_orig_name_var.get()) or bool(self.reveal_orig_size_var.get())
                    )
                    # set visible fields only when reveal toggles enabled (only for first layer)
                    if i == 0 and self.reveal_orig_name_var.get():
                        note["original_filename"] = Path(src).name
                    if i == 0 and self.reveal_orig_size_var.get():
                        note["original_size"] = len(data)
                    # key_type reveal
                    note["key_type"] = key_type if self.reveal_keytype_var.get() else None
                    note["algorithm"] = stored_algo
                    note["layer"] = i + 1
                    note["total_layers"] = iterations
                    bf = ByteFile(encrypted, note)
                    payload = bf.pack().encode("utf-8")
                Path(dest).write_bytes(payload)
            else:
                encrypted = data
                for _ in range(iterations):
                    encrypted = EncryptionEngine.encrypt(encrypted, key_bytes, algo)
                note = default_note(
                    algorithm=algo, key_type=key_type, mode="simple",
                    iterations=iterations,
                    author=self.author_var.get(),
                    password_hint=self.hint_var.get() or None,
                    original_filename=None,
                    original_size=None,
                )
                note["reveal_original_filename"] = bool(self.reveal_orig_name_var.get())
                note["reveal_original_size"] = bool(self.reveal_orig_size_var.get())
                note["reveal_key_type"] = bool(self.reveal_keytype_var.get())
                note["keep_original_file_info"] = (
                    bool(self.reveal_orig_name_var.get()) or bool(self.reveal_orig_size_var.get())
                )
                if self.reveal_orig_name_var.get():
                    note["original_filename"] = Path(src).name
                if self.reveal_orig_size_var.get():
                    note["original_size"] = len(data)
                note["key_type"] = key_type if self.reveal_keytype_var.get() else None
                note["algorithm"] = stored_algo
                bf = ByteFile(encrypted, note)
                bf.save(dest)

            self.after(0, lambda: self._set_status(f"✅ Encrypted → {Path(dest).name}"))
            self.after(0, lambda: messagebox.showinfo("Done", f"File encrypted successfully.\n{dest}"))
        except Exception as exc:
            self.after(0, lambda exc=exc: self._set_status(f"❌ Error: {exc}"))
            self.after(0, lambda exc=exc: messagebox.showerror("Encryption Error", str(exc)))

    def _do_decrypt(self):
        src = self.dec_file.get()
        pw_source = self.dec_pw.get_source()
        key_type = self.dec_pw.get_key_type()

        if not src:
            messagebox.showwarning("Missing input", f"Please select a {BYTEFILE_EXT}.")
            return
        if not pw_source:
            messagebox.showwarning("Missing password", "Please enter a password.")
            return

        # Use auto-detected algo, or fall back to manual selection
        fallback = self._detected_algo or self.dec_algo_var.get()
        self._set_status("Decrypting...")
        threading.Thread(
            target=self._decrypt_worker,
            args=(src, pw_source, key_type, fallback),
            daemon=True,
        ).start()

    def _decrypt_worker(self, src: str, pw_source: str, key_type: str, fallback_algo: str):
        try:
            key_bytes = derive_key_bytes(pw_source, key_type)
            text = Path(src).read_text(encoding="utf-8")
            bf = ByteFile.parse(text)

            # Use stored algo OR fallback (manual or auto-detected)
            algo = bf.note.get("algorithm") or fallback_algo
            mode = bf.mode

            if mode == "node":
                payload = text
                while True:
                    bf = ByteFile.parse(payload)
                    node_algo = bf.note.get("algorithm") or fallback_algo
                    decrypted = EncryptionEngine.decrypt(bf.content, key_bytes, node_algo)
                    try:
                        payload = decrypted.decode("utf-8")
                        ByteFile.parse(payload)
                    except Exception:
                        break
                result = decrypted
                orig_name = bf.original_filename
            else:
                iterations = bf.note.get("iterations", 1)
                result = bf.content
                for _ in range(iterations):
                    result = EncryptionEngine.decrypt(result, key_bytes, algo)
                orig_name = bf.original_filename

            default_name = orig_name or "decrypted_file"
            # if original filename has an extension, use it as the default extension
            default_ext = None
            try:
                default_ext = Path(default_name).suffix or None
            except Exception:
                default_ext = None

            dest = filedialog.asksaveasfilename(
                initialfile=default_name,
                defaultextension=default_ext,
                filetypes=[("All files", "*.*")],
            )
            if not dest:
                self.after(0, lambda: self._set_status("Decrypt cancelled."))
                return

            Path(dest).write_bytes(result)
            self.after(0, lambda: self._set_status(f"✅ Decrypted → {Path(dest).name}"))
            self.after(0, lambda: messagebox.showinfo("Done", f"File decrypted successfully.\n{dest}"))
        except Exception as exc:
            self.after(0, lambda exc=exc: self._set_status(f"❌ Error: {exc}"))
            self.after(0, lambda exc=exc: messagebox.showerror("Decryption Error", str(exc)))


# ── Helper ────────────────────────────────────────────────────────────────

def _bg(widget) -> str:
    """Resolve background colour for plain tk.Label embedded in ttkbootstrap."""
    try:
        import ttkbootstrap as _ttk
        return _ttk.Style().colors.bg
    except Exception:
        return "#212529"

