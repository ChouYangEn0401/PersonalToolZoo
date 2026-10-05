import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os

from gui.tabs.base_tab import BaseTab
from core.ffmpeg_utils import check_ffmpeg
from core.video_converter import VIDEO_FORMATS, INPUT_VIDEO_EXTENSIONS

_VID_FILETYPES = [
    ("影片檔案", " ".join(f"*{e}" for e in sorted(INPUT_VIDEO_EXTENSIONS))),
    ("所有檔案", "*.*"),
]


class VideoTab(BaseTab):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        self.input_path = None
        self._build_ui()

    def _build_ui(self):
        # ── FFmpeg check ──
        self.ffmpeg_ok = check_ffmpeg()
        if not self.ffmpeg_ok:
            warn = ttk.Label(
                self,
                text="⚠ 未偵測到 FFmpeg，影片轉換功能無法使用。\n請安裝 FFmpeg 並加入系統 PATH 後重新啟動程式。",
                foreground="red",
                wraplength=600,
            )
            warn.pack(pady=20)
            return

        # ── file selection ──
        file_frm = ttk.LabelFrame(self, text="來源影片", padding=5)
        file_frm.pack(fill="x")

        self.file_var = tk.StringVar(value="（尚未選擇）")
        ttk.Button(file_frm, text="選擇影片", command=self._pick_file).pack(side="left")
        ttk.Label(file_frm, textvariable=self.file_var, wraplength=500).pack(
            side="left", padx=8, fill="x", expand=True
        )

        # ── format ──
        opt_frm = ttk.LabelFrame(self, text="輸出設定", padding=5)
        opt_frm.pack(fill="x", pady=6)

        row = ttk.Frame(opt_frm)
        row.pack(fill="x")
        ttk.Label(row, text="輸出格式:").pack(side="left")
        self.fmt_var = tk.StringVar(value="MP4")

        # Separate video & audio groups for clarity
        format_names = list(VIDEO_FORMATS.keys())
        fmt_cb = ttk.Combobox(row, textvariable=self.fmt_var, values=format_names, state="readonly", width=10)
        fmt_cb.pack(side="left", padx=6)

        hint = ttk.Label(opt_frm, text="提示: MP3 / WAV / FLAC / AAC 可僅擷取音訊", foreground="gray")
        hint.pack(anchor="w", pady=2)

        # ── output dir ──
        self.out_dir = self._make_output_dir_row(self)

        # ── convert button ──
        self.convert_btn = ttk.Button(self, text="開始轉換", command=self._start)
        self.convert_btn.pack(pady=6)

        # ── progress ──
        self.progress_var, self.status_var = self._make_progress_section(self)

    def _pick_file(self):
        p = filedialog.askopenfilename(filetypes=_VID_FILETYPES)
        if p:
            self.input_path = p
            self.file_var.set(p)

    def _start(self):
        if not self.input_path:
            messagebox.showwarning("提示", "請先選擇影片檔案。")
            return
        out_dir = self.out_dir.get()
        if not out_dir:
            messagebox.showwarning("提示", "請選擇輸出資料夾。")
            return
        os.makedirs(out_dir, exist_ok=True)

        fmt = self.fmt_var.get()
        self.convert_btn.config(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("轉換中…")

        path = self.input_path

        def progress_cb(pct):
            self._update_progress(self.progress_var, pct)
            self._update_status(self.status_var, f"轉換中… {pct:.0f}%")

        def do():
            from core.video_converter import convert_video
            convert_video(path, out_dir, fmt, progress_callback=progress_cb)

        def done():
            self.convert_btn.config(state="normal")
            self.progress_var.set(100)
            self.status_var.set("轉換完成！")
            messagebox.showinfo("完成", "影片轉換完成！")

        def err(e):
            self.convert_btn.config(state="normal")
            self.status_var.set(f"錯誤: {e}")
            messagebox.showerror("錯誤", str(e))

        self._run_in_thread(do, on_done=done, on_error=err)
