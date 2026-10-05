import tkinter as tk
from tkinter import ttk, messagebox
import os

from gui.tabs.base_tab import BaseTab
from core.image_converter import (
    SUPPORTED_OUTPUT_FORMATS,
    SUPPORTED_INPUT_EXTENSIONS,
    ICO_SIZES,
    convert_image,
)

_IMG_FILETYPES = [
    ("圖片檔案", " ".join(f"*{e}" for e in sorted(SUPPORTED_INPUT_EXTENSIONS))),
    ("所有檔案", "*.*"),
]


class ImageTab(BaseTab):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        self._build_ui()

    def _build_ui(self):
        # ── file list ──
        file_frm, self.lb, self.file_paths = self._make_file_list_section(
            _IMG_FILETYPES, "圖片檔案"
        )
        file_frm.pack(fill="both", expand=True)

        # ── options ──
        opt_frm = ttk.LabelFrame(self, text="轉換設定", padding=5)
        opt_frm.pack(fill="x", pady=6)

        row1 = ttk.Frame(opt_frm)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="輸出格式:").pack(side="left")
        self.fmt_var = tk.StringVar(value="PNG")
        fmt_cb = ttk.Combobox(
            row1,
            textvariable=self.fmt_var,
            values=list(SUPPORTED_OUTPUT_FORMATS.keys()),
            state="readonly",
            width=10,
        )
        fmt_cb.pack(side="left", padx=6)
        fmt_cb.bind("<<ComboboxSelected>>", self._on_format_change)

        # ICO sizes (hidden by default)
        self.ico_frame = ttk.Frame(row1)
        ttk.Label(self.ico_frame, text="ICO 尺寸:").pack(side="left", padx=(12, 4))
        self.ico_vars = {}
        for s in ICO_SIZES:
            var = tk.BooleanVar(value=(s == 256))
            cb = ttk.Checkbutton(self.ico_frame, text=f"{s}", variable=var)
            cb.pack(side="left", padx=1)
            self.ico_vars[s] = var

        # Lossy hint
        self.lossy_label = ttk.Label(opt_frm, text="", foreground="orange")
        self.lossy_label.pack(anchor="w")

        # ── output dir ──
        self.out_dir = self._make_output_dir_row(self)

        # ── convert button ──
        self.convert_btn = ttk.Button(self, text="開始轉換", command=self._start)
        self.convert_btn.pack(pady=6)

        # ── progress ──
        self.progress_var, self.status_var = self._make_progress_section(self)

    def _on_format_change(self, _event=None):
        fmt = self.fmt_var.get()
        if fmt == "ICO":
            self.ico_frame.pack(side="left")
        else:
            self.ico_frame.pack_forget()

        if fmt == "JPEG":
            self.lossy_label.config(text="⚠ JPEG 為有損格式，轉換後畫質可能略有降低")
        else:
            self.lossy_label.config(text="")

    def _start(self):
        if not self.file_paths:
            messagebox.showwarning("提示", "請先添加圖片檔案。")
            return
        out_dir = self.out_dir.get()
        if not out_dir:
            messagebox.showwarning("提示", "請選擇輸出資料夾。")
            return
        os.makedirs(out_dir, exist_ok=True)

        fmt = self.fmt_var.get()
        ico_sizes = None
        if fmt == "ICO":
            ico_sizes = [s for s, v in self.ico_vars.items() if v.get()]
            if not ico_sizes:
                ico_sizes = [256]

        self.convert_btn.config(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("轉換中…")
        paths = list(self.file_paths)

        def do():
            total = len(paths)
            errors = []
            for i, p in enumerate(paths, 1):
                self._update_status(self.status_var, f"轉換中 ({i}/{total}): {os.path.basename(p)}")
                try:
                    convert_image(p, out_dir, fmt, ico_sizes=ico_sizes)
                except Exception as e:
                    errors.append(f"{os.path.basename(p)}: {e}")
                self._update_progress(self.progress_var, i / total * 100)

            if errors:
                msg = "以下檔案轉換失敗:\n" + "\n".join(errors)
                self.root.after(0, lambda: messagebox.showwarning("部分失敗", msg))

        def done():
            self.convert_btn.config(state="normal")
            self.status_var.set("轉換完成！")
            messagebox.showinfo("完成", f"已轉換 {len(paths)} 個檔案。")

        def err(e):
            self.convert_btn.config(state="normal")
            self.status_var.set(f"錯誤: {e}")
            messagebox.showerror("錯誤", str(e))

        self._run_in_thread(do, on_done=done, on_error=err)
