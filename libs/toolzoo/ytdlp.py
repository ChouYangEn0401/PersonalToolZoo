"""yt-dlp 的共用設定（Video Downloader 與 Video Notes 都用）。

兩個容易踩到的坑都在這裡處理：

1. YouTube 從 2025 年底開始要用 JavaScript 解題才拿得到影片網址，yt-dlp 需要一個 JS 執行環境，
   而它預設只找 Deno。這台機器有 Node 或 Bun 也可以用，所以三個都打開，有哪個用哪個；
   解題用的 JS 元件由 yt-dlp-ejs 套件提供（裝 ``yt-dlp[default]`` 就會一起裝）。
2. 合併影音、轉檔需要 ffmpeg。依序找：設定指定的路徑 → PATH → 常見安裝位置。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

JS_RUNTIMES = ("deno", "node", "bun")

_COMMON_FFMPEG = (
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
)


def find_ffmpeg(configured: str = "") -> str | None:
    """回傳 ffmpeg.exe 的完整路徑；找不到回傳 None。"""
    if configured:
        path = Path(configured)
        if path.is_dir():
            path = path / "ffmpeg.exe"
        if path.is_file():
            return str(path)
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in _COMMON_FFMPEG:
        if os.path.isfile(candidate):
            return candidate
    return None


def find_js_runtimes() -> list[str]:
    return [name for name in JS_RUNTIMES if shutil.which(name)]


def base_options(ffmpeg: str | None = None, cookies_from_browser: str = "") -> dict:
    """每次建立 YoutubeDL 都要帶的參數。"""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "js_runtimes": {name: {} for name in JS_RUNTIMES},
    }
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if cookies_from_browser.strip():
        # 例如 ("chrome",)：用瀏覽器登入狀態下載會員、年齡限制等需要登入的影片
        opts["cookiesfrombrowser"] = (cookies_from_browser.strip().lower(),)
    return opts


def version() -> str:
    try:
        from yt_dlp.version import __version__

        return __version__
    except Exception:  # noqa: BLE001
        return "?"
