"""Tab 4 — Large File Mode (chunked encryption/decryption)."""

from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from core.bytefile import ByteFile, BYTEFILE_EXT, default_note
from core.engine import ALGORITHMS, EncryptionEngine
from core.utils import derive_key_bytes, human_size

from .theme import FONT_TITLE, FONT_BODY, FONT_MONO, FONT_SMALL, PAD
from .widgets import FileSelector, DirSelector, PasswordFrame, Tooltip


class _ChunkStageRow(ttk.Frame):
    """One stage in the chunk encryption pipeline (simplified)."""

    def __init__(self, parent, index: int, on_delete):
        super().__init__(parent)
        self.index = index
        self._on_delete = on_delete
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text=f"#{index + 1}", font=FONT_BODY, width=3).grid(row=0, column=0, padx=(0, 6))

        self.algo_var = tk.StringVar(value="AES-256-CBC")
        ttk.Combobox(
            self, textvariable=self.algo_var, values=ALGORITHMS,
            state="readonly", width=16, font=FONT_BODY,
        ).grid(row=0, column=1, sticky=W, padx=(0, 6))

        self.key_type_var = tk.StringVar(value="text")
        ttk.Combobox(
            self, textvariable=self.key_type_var,
            values=["text", "file", "image", "video", "bytefile"],
            state="readonly", width=8, font=FONT_SMALL,
        ).grid(row=0, column=2, padx=(0, 6))

        self.pw_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.pw_var, show="●", font=FONT_BODY, width=18).grid(
            row=0, column=3, sticky=EW, padx=(0, 6))

        ttk.Button(self, text="✕", width=3, bootstyle="outline-danger",
                   command=lambda: self._on_delete(self)).grid(row=0, column=4)

    def get_config(self) -> dict:
        return {
            "algorithm": self.algo_var.get(),
            "key_bytes": derive_key_bytes(self.pw_var.get(), self.key_type_var.get()),
            "key_type": self.key_type_var.get(),
        }


class LargeFileTab(ttk.Frame):
    def __init__(self, parent, status_var: tk.StringVar, **kw):
        super().__init__(parent, padding=PAD, **kw)
        self._status = status_var
        self._stages: list[_ChunkStageRow] = []
        self._build_ui()
        self._add_stage()

    def _build_ui(self):
        ttk.Label(self, text="📦  Large File Mode", font=FONT_TITLE).pack(anchor=W, pady=(0, 4))
        ttk.Label(self, text="Split large files into encrypted chunks. Each chunk is a .bytefile with a manifest for reassembly.",
                  font=FONT_SMALL, wraplength=700).pack(anchor=W, pady=(0, PAD))

        # ── Operation toggle ──────────────────────────────────────────
        op_frame = ttk.Frame(self)
        op_frame.pack(fill=X, pady=(0, 8))
        self.op_var = tk.StringVar(value="encrypt")
        ttk.Radiobutton(op_frame, text="Encrypt (split & encrypt)",
                        variable=self.op_var, value="encrypt",
                        command=self._switch_op).pack(side=LEFT, padx=(0, 16))
        ttk.Radiobutton(op_frame, text="Decrypt (reassemble)",
                        variable=self.op_var, value="decrypt",
                        command=self._switch_op).pack(side=LEFT)

        # ── Encrypt panel ─────────────────────────────────────────────
        self._enc_panel = ttk.Labelframe(self, text="Encrypt", padding=PAD)
        self._enc_panel.pack(fill=BOTH, expand=True, pady=(0, 8))

        self.enc_file = FileSelector(self._enc_panel, label="Source file")
        self.enc_file.pack(fill=X, pady=(0, 6))
        Tooltip(self.enc_file._entry, "選擇要分段加密的大檔案，或直接拖拉進來")

        chunk_row = ttk.Frame(self._enc_panel)
        chunk_row.pack(fill=X, pady=(0, 6))
        ttk.Label(chunk_row, text="Chunk size (MB):", font=FONT_BODY).pack(side=LEFT)
        self.chunk_mb_var = tk.IntVar(value=64)
        _chunk_sb = ttk.Spinbox(chunk_row, from_=1, to=1024, textvariable=self.chunk_mb_var,
                     width=6, font=FONT_BODY)
        _chunk_sb.pack(side=LEFT, padx=(6, 12))
        Tooltip(_chunk_sb, "每個 chunk 的大小。檔案越大建議設為 64–256 MB")

        mode_frame = ttk.Frame(self._enc_panel)
        mode_frame.pack(fill=X, pady=(0, 6))
        ttk.Label(mode_frame, text="Mode:", font=FONT_BODY).pack(side=LEFT)
        self.mode_var = tk.StringVar(value="simple")
        ttk.Radiobutton(mode_frame, text="Simple", variable=self.mode_var, value="simple").pack(side=LEFT, padx=(6, 12))
        ttk.Radiobutton(mode_frame, text="Node", variable=self.mode_var, value="node").pack(side=LEFT)

        # Pipeline stages
        stage_lbl = ttk.Label(self._enc_panel, text="Encryption pipeline:", font=FONT_BODY)
        stage_lbl.pack(anchor=W, pady=(0, 4))
        stage_btn_row = ttk.Frame(self._enc_panel)
        stage_btn_row.pack(fill=X, pady=(0, 4))
        ttk.Button(stage_btn_row, text="＋ Add", bootstyle="outline-primary",
                   command=self._add_stage).pack(side=LEFT, padx=(0, 6))
        ttk.Button(stage_btn_row, text="Clear", bootstyle="outline-danger",
                   command=self._clear_stages).pack(side=LEFT)

        self._stage_frame = ttk.Frame(self._enc_panel)
        self._stage_frame.pack(fill=X, pady=(0, 6))

        self.enc_out_dir = DirSelector(self._enc_panel, label="Output directory")
        self.enc_out_dir.pack(fill=X, pady=(0, 8))
        Tooltip(self.enc_out_dir._entry,
                "加密輸出目錄，會儲存所有 chunk .bytefile 及 manifest.json。可拖拉資料夾進來")

        _enc_go_btn = ttk.Button(self._enc_panel, text="🔒  Start Chunked Encryption",
                   bootstyle="warning", command=self._do_encrypt)
        _enc_go_btn.pack(fill=X, ipady=6)
        Tooltip(_enc_go_btn, "開始分段加密，完成後會產出 manifest.json + 各個 chunk .bytefile")

        # ── Decrypt panel (hidden initially) ──────────────────────────
        self._dec_panel = ttk.Labelframe(self, text="Decrypt (Reassemble)", padding=PAD)

        self.manifest_file = FileSelector(
            self._dec_panel, label="Manifest file (manifest.json)",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        self.manifest_file.pack(fill=X, pady=(0, 6))
        Tooltip(self.manifest_file._entry,
                "分段加密產出的 manifest.json，包含每個 chunk 的資訊。可拖拉進來")

        self.dec_pw = PasswordFrame(self._dec_panel, title="Password (same as encryption)")
        self.dec_pw.pack(fill=X, pady=(0, 6))

        self.dec_out_file = FileSelector(
            self._dec_panel, label="Output file", save=True,
        )
        self.dec_out_file.pack(fill=X, pady=(0, 8))

        ttk.Button(self._dec_panel, text="🔓  Reassemble & Decrypt",
                   bootstyle="success", command=self._do_decrypt).pack(fill=X, ipady=6)

        # ── Progress bar ──────────────────────────────────────────────
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress.pack(fill=X, pady=(4, 0))

    # ── Panel switching ───────────────────────────────────────────────

    def _switch_op(self):
        if self.op_var.get() == "encrypt":
            self._dec_panel.pack_forget()
            self._enc_panel.pack(fill=BOTH, expand=True, pady=(0, 8))
        else:
            self._enc_panel.pack_forget()
            self._dec_panel.pack(fill=BOTH, expand=True, pady=(0, 8))
        self.progress.pack(fill=X, pady=(4, 0))

    # ── Stage management ──────────────────────────────────────────────

    def _add_stage(self):
        idx = len(self._stages)
        row = _ChunkStageRow(self._stage_frame, idx, self._remove_stage)
        row.pack(fill=X, padx=4, pady=2)
        self._stages.append(row)

    def _remove_stage(self, row):
        if len(self._stages) <= 1:
            return
        row.destroy()
        self._stages.remove(row)

    def _clear_stages(self):
        for s in self._stages:
            s.destroy()
        self._stages.clear()
        self._add_stage()

    # ── Encrypt ───────────────────────────────────────────────────────

    def _do_encrypt(self):
        src = self.enc_file.get()
        out_dir = self.enc_out_dir.get()
        if not src or not Path(src).is_file():
            messagebox.showwarning("Input", "Select a valid source file.")
            return
        if not out_dir:
            messagebox.showwarning("Output", "Select an output directory.")
            return

        try:
            chain = [s.get_config() for s in self._stages]
        except Exception as exc:
            messagebox.showerror("Config", str(exc))
            return

        self._status.set("Chunked encryption starting...")
        self.progress_var.set(0)
        threading.Thread(
            target=self._encrypt_worker,
            args=(src, out_dir, chain),
            daemon=True,
        ).start()

    def _encrypt_worker(self, src: str, out_dir: str, chain: list[dict]):
        try:
            src_path = Path(src)
            out_path = Path(out_dir)
            out_path.mkdir(parents=True, exist_ok=True)

            file_size = src_path.stat().st_size
            chunk_size = self.chunk_mb_var.get() * 1024 * 1024
            mode = self.mode_var.get()
            chain_meta = [{"algorithm": s["algorithm"], "key_type": s["key_type"]} for s in chain]

            chunks_info = []
            chunk_idx = 0

            with open(src, "rb") as f:
                while True:
                    chunk_data = f.read(chunk_size)
                    if not chunk_data:
                        break

                    # Encrypt this chunk
                    if mode == "node":
                        payload = chunk_data
                        for i, step in enumerate(chain):
                            encrypted = EncryptionEngine.encrypt(payload, step["key_bytes"], step["algorithm"])
                            note = default_note(
                                algorithm=step["algorithm"], key_type=step["key_type"],
                                mode="node", iterations=len(chain),
                            )
                            note["layer"] = i + 1
                            note["total_layers"] = len(chain)
                            bf = ByteFile(encrypted, note)
                            payload = bf.pack().encode("utf-8")
                        chunk_filename = f"chunk_{chunk_idx:04d}{BYTEFILE_EXT}"
                        (out_path / chunk_filename).write_bytes(payload)
                    else:
                        encrypted = EncryptionEngine.encrypt_chain(chunk_data, chain)
                        note = default_note(
                            algorithm=chain[0]["algorithm"], key_type=chain[0]["key_type"],
                            mode="simple", iterations=len(chain),
                            mixture_chain=chain_meta,
                        )
                        bf = ByteFile(encrypted, note)
                        chunk_filename = f"chunk_{chunk_idx:04d}{BYTEFILE_EXT}"
                        bf.save(out_path / chunk_filename)

                    chunks_info.append({
                        "index": chunk_idx,
                        "filename": chunk_filename,
                        "original_size": len(chunk_data),
                    })
                    chunk_idx += 1

                    progress = min(100, (f.tell() / file_size) * 100)
                    self.after(0, lambda p=progress: self.progress_var.set(p))
                    self.after(0, lambda ci=chunk_idx: self._status.set(
                        f"Encrypting chunk {ci}..."
                    ))

            # Write manifest
            manifest = {
                "type": "chunk_manifest",
                "original_filename": src_path.name,
                "original_size": file_size,
                "chunk_count": chunk_idx,
                "chunk_size_mb": self.chunk_mb_var.get(),
                "mode": mode,
                "encryption_chain": chain_meta,
                "chunks": chunks_info,
            }
            manifest_path = out_path / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

            self.after(0, lambda: self.progress_var.set(100))
            self.after(0, lambda: self._status.set(
                f"✅ {chunk_idx} chunks encrypted → {out_path.name}/"
            ))
            self.after(0, lambda: messagebox.showinfo(
                "Done",
                f"Encrypted {chunk_idx} chunks + manifest.json\n"
                f"Directory: {out_path}",
            ))
        except Exception as exc:
            self.after(0, lambda: self._status.set(f"❌ {exc}"))
            self.after(0, lambda: messagebox.showerror("Error", str(exc)))

    # ── Decrypt / Reassemble ──────────────────────────────────────────

    def _do_decrypt(self):
        manifest_src = self.manifest_file.get()
        dest = self.dec_out_file.get()
        pw_source = self.dec_pw.get_source()
        key_type = self.dec_pw.get_key_type()

        if not manifest_src:
            messagebox.showwarning("Input", "Select the manifest.json file.")
            return
        if not dest:
            messagebox.showwarning("Output", "Select an output file.")
            return

        self._status.set("Reassembling & decrypting...")
        self.progress_var.set(0)
        threading.Thread(
            target=self._decrypt_worker,
            args=(manifest_src, dest, pw_source, key_type),
            daemon=True,
        ).start()

    def _decrypt_worker(self, manifest_src: str, dest: str, pw_source: str, key_type: str):
        try:
            manifest_path = Path(manifest_src)
            chunk_dir = manifest_path.parent
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            mode = manifest.get("mode", "simple")
            chain_meta = manifest.get("encryption_chain", [])
            chunks = manifest.get("chunks", [])
            total = len(chunks)

            key_bytes = derive_key_bytes(pw_source, key_type)
            # Rebuild the chain with the same key for all stages
            chain = [{"algorithm": s["algorithm"], "key_bytes": key_bytes} for s in chain_meta]

            with open(dest, "wb") as out_f:
                for ci, chunk_info in enumerate(chunks):
                    chunk_path = chunk_dir / chunk_info["filename"]
                    if mode == "node":
                        payload = chunk_path.read_text(encoding="utf-8")
                        for step in reversed(chain):
                            bf = ByteFile.parse(payload)
                            decrypted = EncryptionEngine.decrypt(bf.content, step["key_bytes"], step["algorithm"])
                            try:
                                payload = decrypted.decode("utf-8")
                                ByteFile.parse(payload)
                            except Exception:
                                break
                        out_f.write(decrypted)
                    else:
                        bf = ByteFile.load(chunk_path)
                        decrypted = EncryptionEngine.decrypt_chain(bf.content, chain)
                        out_f.write(decrypted)

                    progress = ((ci + 1) / total) * 100
                    self.after(0, lambda p=progress: self.progress_var.set(p))
                    self.after(0, lambda c=ci + 1: self._status.set(
                        f"Decrypting chunk {c}/{total}..."
                    ))

            self.after(0, lambda: self.progress_var.set(100))
            self.after(0, lambda: self._status.set(f"✅ Reassembled → {Path(dest).name}"))
            self.after(0, lambda: messagebox.showinfo("Done", f"File reassembled!\n{dest}"))
        except Exception as exc:
            self.after(0, lambda: self._status.set(f"❌ {exc}"))
            self.after(0, lambda: messagebox.showerror("Error", str(exc)))
