import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os

from gui.tabs.base_tab import BaseTab
from core.ffmpeg_utils import check_ffmpeg
from core.video_extractor import FRAME_FORMATS, AUDIO_FORMATS
from core.video_converter import INPUT_VIDEO_EXTENSIONS

_VID_FILETYPES = [
    ("影片檔案", " ".join(f"*{e}" for e in sorted(INPUT_VIDEO_EXTENSIONS))),
    ("所有檔案", "*.*"),
]


class ExtractorTab(BaseTab):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        self.input_path = None
        self._build_ui()

    def _build_ui(self):
        self.ffmpeg_ok = check_ffmpeg()
        if not self.ffmpeg_ok:
            ttk.Label(
                self,
                text="⚠ 未偵測到 FFmpeg，擷取功能無法使用。",
                foreground="red",
            ).pack(pady=20)
            return

        # ── file selection ──
        file_frm = ttk.LabelFrame(self, text="來源影片", padding=5)
        file_frm.pack(fill="x")
        self.file_var = tk.StringVar(value="（尚未選擇）")
        ttk.Button(file_frm, text="選擇影片", command=self._pick_file).pack(side="left")
        ttk.Label(file_frm, textvariable=self.file_var, wraplength=500).pack(
            side="left", padx=8, fill="x", expand=True
        )

        # ── extract mode ──
        mode_frm = ttk.LabelFrame(self, text="擷取選項", padding=5)
        mode_frm.pack(fill="x", pady=6)

        self.mode_var = tk.StringVar(value="both")
        modes = [("擷取影格 + 音訊", "both"), ("僅影格", "frames"), ("僅音訊", "audio")]
        for text, val in modes:
            ttk.Radiobutton(mode_frm, text=text, variable=self.mode_var, value=val).pack(
                side="left", padx=8
            )

        # ── format options ──
        fmt_frm = ttk.Frame(mode_frm)
        fmt_frm.pack(fill="x", pady=(6, 0))

        ttk.Label(fmt_frm, text="影格格式:").pack(side="left")
        self.frame_fmt = tk.StringVar(value="PNG")
        ttk.Combobox(fmt_frm, textvariable=self.frame_fmt, values=FRAME_FORMATS, state="readonly", width=6).pack(
            side="left", padx=(4, 16)
        )

        ttk.Label(fmt_frm, text="音訊格式:").pack(side="left")
        self.audio_fmt = tk.StringVar(value="WAV")
        ttk.Combobox(
            fmt_frm,
            textvariable=self.audio_fmt,
            values=list(AUDIO_FORMATS.keys()),
            state="readonly",
            width=6,
        ).pack(side="left", padx=4)

        # ── output dir ──
        self.out_dir = self._make_output_dir_row(self)

        # ── info label ──
        ttk.Label(
            self,
            text="輸出結構: <輸出資料夾>/<影片名稱>/frames/  與  <輸出資料夾>/<影片名稱>/audio/",
            foreground="gray",
        ).pack(anchor="w")

        # ── button ──
        self.convert_btn = ttk.Button(self, text="開始擷取", command=self._start)
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
            messagebox.showwarning("提示", "請先選擇影片。")
            return
        out_dir = self.out_dir.get()
        if not out_dir:
            messagebox.showwarning("提示", "請選擇輸出資料夾。")
            return
        os.makedirs(out_dir, exist_ok=True)

        mode = self.mode_var.get()
        ffmt = self.frame_fmt.get()
        afmt = self.audio_fmt.get()
        path = self.input_path

        self.convert_btn.config(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("擷取中…")

        def progress_cb(pct):
            self._update_progress(self.progress_var, pct)
            self._update_status(self.status_var, f"擷取中… {pct:.0f}%")

        def do():
            from core.video_extractor import extract_frames, extract_audio, extract_all

            if mode == "both":
                extract_all(path, out_dir, ffmt, afmt, progress_callback=progress_cb)
            elif mode == "frames":
                extract_frames(path, out_dir, ffmt, progress_callback=progress_cb)
            else:
                extract_audio(path, out_dir, afmt, progress_callback=progress_cb)

        def done():
            self.convert_btn.config(state="normal")
            self.progress_var.set(100)
            self.status_var.set("擷取完成！")
            messagebox.showinfo("完成", "影片擷取完成！")

        def err(e):
            self.convert_btn.config(state="normal")
            self.status_var.set(f"錯誤: {e}")
            messagebox.showerror("錯誤", str(e))

        self._run_in_thread(do, on_done=done, on_error=err)
