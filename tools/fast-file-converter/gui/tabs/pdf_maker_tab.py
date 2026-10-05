import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os

from gui.tabs.base_tab import BaseTab
from core.pdf_maker import SUPPORTED_EXTENSIONS

_IMG_FILETYPES = [
    ("圖片檔案", " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))),
    ("所有檔案", "*.*"),
]


class PdfMakerTab(BaseTab):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        self._build_ui()

    def _build_ui(self):
        # ── file list with reorder ──
        file_frm = ttk.LabelFrame(self, text="圖片檔案（順序即為 PDF 頁序）", padding=5)
        file_frm.pack(fill="both", expand=True)

        btn_bar = ttk.Frame(file_frm)
        btn_bar.pack(fill="x")

        self.file_paths = []

        def add_files():
            paths = filedialog.askopenfilenames(filetypes=_IMG_FILETYPES)
            for p in paths:
                if p not in self.file_paths:
                    self.file_paths.append(p)
                    self.lb.insert(tk.END, p)

        def remove_selected():
            for idx in reversed(self.lb.curselection()):
                self.file_paths.pop(idx)
                self.lb.delete(idx)

        def move_up():
            sel = self.lb.curselection()
            if not sel or sel[0] == 0:
                return
            for idx in sel:
                self.file_paths[idx - 1], self.file_paths[idx] = (
                    self.file_paths[idx],
                    self.file_paths[idx - 1],
                )
                text = self.lb.get(idx)
                self.lb.delete(idx)
                self.lb.insert(idx - 1, text)
                self.lb.selection_set(idx - 1)

        def move_down():
            sel = self.lb.curselection()
            if not sel or sel[-1] >= len(self.file_paths) - 1:
                return
            for idx in reversed(sel):
                self.file_paths[idx + 1], self.file_paths[idx] = (
                    self.file_paths[idx],
                    self.file_paths[idx + 1],
                )
                text = self.lb.get(idx)
                self.lb.delete(idx)
                self.lb.insert(idx + 1, text)
                self.lb.selection_set(idx + 1)

        ttk.Button(btn_bar, text="添加檔案", command=add_files).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="移除選取", command=remove_selected).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="▲ 上移", command=move_up).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="▼ 下移", command=move_down).pack(side="left", padx=2)

        list_frm = ttk.Frame(file_frm)
        list_frm.pack(fill="both", expand=True, pady=(5, 0))
        sb = ttk.Scrollbar(list_frm)
        sb.pack(side="right", fill="y")
        self.lb = tk.Listbox(list_frm, selectmode=tk.EXTENDED, yscrollcommand=sb.set, height=8)
        self.lb.pack(fill="both", expand=True)
        sb.config(command=self.lb.yview)

        # ── output pdf path ──
        out_frm = ttk.Frame(self)
        out_frm.pack(fill="x", pady=4)
        ttk.Label(out_frm, text="輸出 PDF:").pack(side="left")
        self.out_var = tk.StringVar()
        ttk.Entry(out_frm, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=4)

        def browse_pdf():
            p = filedialog.asksaveasfilename(
                defaultextension=".pdf", filetypes=[("PDF", "*.pdf")]
            )
            if p:
                self.out_var.set(p)

        ttk.Button(out_frm, text="瀏覽…", command=browse_pdf).pack(side="right")

        # ── button ──
        self.convert_btn = ttk.Button(self, text="產生 PDF", command=self._start)
        self.convert_btn.pack(pady=6)

        # ── progress ──
        self.progress_var, self.status_var = self._make_progress_section(self)

    def _start(self):
        if not self.file_paths:
            messagebox.showwarning("提示", "請先添加圖片。")
            return
        out_path = self.out_var.get()
        if not out_path:
            messagebox.showwarning("提示", "請指定輸出 PDF 路徑。")
            return

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        self.convert_btn.config(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("產生 PDF 中…")
        paths = list(self.file_paths)

        def do():
            from core.pdf_maker import images_to_pdf
            images_to_pdf(paths, out_path)

        def done():
            self.convert_btn.config(state="normal")
            self.progress_var.set(100)
            self.status_var.set("完成！")
            messagebox.showinfo("完成", f"PDF 已產生:\n{out_path}")

        def err(e):
            self.convert_btn.config(state="normal")
            self.status_var.set(f"錯誤: {e}")
            messagebox.showerror("錯誤", str(e))

        self._run_in_thread(do, on_done=done, on_error=err)
