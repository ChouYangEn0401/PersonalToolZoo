import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os

from gui.tabs.base_tab import BaseTab

OUTPUT_MODES = {
    "純文字 (.txt)": "txt",
    "Word 文件 (.docx)": "docx",
    "簡報 (.pptx) — 每頁轉為投影片圖片": "pptx",
}


class PdfExtractTab(BaseTab):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        self.input_path = None
        self._build_ui()

    def _build_ui(self):
        # ── file selection ──
        file_frm = ttk.LabelFrame(self, text="來源 PDF", padding=5)
        file_frm.pack(fill="x")
        self.file_var = tk.StringVar(value="（尚未選擇）")
        ttk.Button(file_frm, text="選擇 PDF", command=self._pick_file).pack(side="left")
        ttk.Label(file_frm, textvariable=self.file_var, wraplength=500).pack(
            side="left", padx=8, fill="x", expand=True
        )

        # ── output mode ──
        mode_frm = ttk.LabelFrame(self, text="輸出格式", padding=5)
        mode_frm.pack(fill="x", pady=6)

        self.mode_var = tk.StringVar(value="txt")
        for label, val in OUTPUT_MODES.items():
            ttk.Radiobutton(mode_frm, text=label, variable=self.mode_var, value=val).pack(
                anchor="w", pady=1
            )

        # ── output dir ──
        self.out_dir = self._make_output_dir_row(self)

        # ── button ──
        self.convert_btn = ttk.Button(self, text="開始轉換", command=self._start)
        self.convert_btn.pack(pady=6)

        # ── progress ──
        self.progress_var, self.status_var = self._make_progress_section(self)

    def _pick_file(self):
        p = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf"), ("所有檔案", "*.*")])
        if p:
            self.input_path = p
            self.file_var.set(p)

    def _start(self):
        if not self.input_path:
            messagebox.showwarning("提示", "請先選擇 PDF 檔案。")
            return
        out_dir = self.out_dir.get()
        if not out_dir:
            messagebox.showwarning("提示", "請選擇輸出資料夾。")
            return
        os.makedirs(out_dir, exist_ok=True)

        mode = self.mode_var.get()
        path = self.input_path
        base_name = os.path.splitext(os.path.basename(path))[0]
        out_path = os.path.join(out_dir, base_name + f".{mode}")

        self.convert_btn.config(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("轉換中…")

        def do():
            from core.pdf_extractor import pdf_to_text, pdf_to_docx, pdf_to_pptx

            if mode == "txt":
                pdf_to_text(path, out_path)
            elif mode == "docx":
                pdf_to_docx(path, out_path)
            elif mode == "pptx":
                pdf_to_pptx(path, out_path)

        def done():
            self.convert_btn.config(state="normal")
            self.progress_var.set(100)
            self.status_var.set("轉換完成！")
            messagebox.showinfo("完成", f"已輸出:\n{out_path}")

        def err(e):
            self.convert_btn.config(state="normal")
            self.status_var.set(f"錯誤: {e}")
            messagebox.showerror("錯誤", str(e))

        self._run_in_thread(do, on_done=done, on_error=err)
