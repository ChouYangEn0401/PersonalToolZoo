"""下載（yt-dlp）與抽音訊（ffmpeg）。"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable

from toolzoo import ytdlp

from video_notes.transcribe import Cancelled

# 影片資訊裡只留整理筆記會用到、也方便事後查的欄位（完整的 info 動輒幾百 KB）
INFO_FIELDS = (
    "id", "title", "uploader", "channel", "channel_url", "duration", "upload_date", "description",
    "chapters", "webpage_url", "extractor_key", "width", "height", "thumbnail", "tags", "view_count",
)


def fetch_info(url: str, ffmpeg: str | None, cookies: str = "") -> dict:
    from yt_dlp import YoutubeDL

    opts = {**ytdlp.base_options(ffmpeg, cookies), "skip_download": True, "noplaylist": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.sanitize_info(ydl.extract_info(url, download=False))
    if info.get("_type") == "playlist":
        raise ValueError("這是播放清單網址，請貼單一影片的網址（或用 Video Downloader 下載整個清單）")
    return {k: info.get(k) for k in INFO_FIELDS if info.get(k) is not None}


def download(url: str, folder: Path, *, keep_video: bool, ffmpeg: str | None, cookies: str = "",
             on_progress: Callable[[float, str], None] | None = None,
             cancel: threading.Event | None = None) -> None:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadCancelled

    def hook(d: dict) -> None:
        if cancel is not None and cancel.is_set():
            raise DownloadCancelled()
        if d.get("status") == "downloading" and on_progress:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            speed = d.get("speed") or 0
            detail = f"{done / 1048576:.1f} MB" + (f" · {speed / 1048576:.1f} MB/s" if speed else "")
            on_progress(done / total if total else 0.0, detail)

    opts = {
        **ytdlp.base_options(ffmpeg, cookies),
        "outtmpl": str(folder / "media.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [hook],
        "continuedl": True,
        "retries": 5,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
    }
    if keep_video:
        opts["format"] = "bestvideo*+bestaudio/best"
        opts["merge_output_format"] = "mp4"
    else:
        opts["format"] = "bestaudio/best"
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except DownloadCancelled as exc:
        raise Cancelled() from exc


def extract_audio(media: Path, wav: Path, ffmpeg: str | None) -> None:
    """轉成 16 kHz 單聲道 WAV（Whisper 的原生格式，辨識前不用再轉）。"""
    if not ffmpeg:
        raise RuntimeError("找不到 ffmpeg：請安裝 ffmpeg 並加入 PATH，或在設定裡指定 ffmpeg.exe 的位置")
    tmp = wav.with_suffix(".tmp.wav")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(media),
           "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(tmp)]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg 抽音訊失敗：{result.stderr.strip()[-500:]}")
    tmp.replace(wav)  # 寫完才改名，中途失敗不會留下一個看起來完整的 audio.wav
