"""來源 adapter：yt-dlp（通用，支援上千個網站）。把 media.fetch_info／download 包成 SourceAdapter。

- 排在 REGISTRY 最後（order 900）當通用來源：matches() 對所有 http(s) 網址回 True。
- 影片與影片之間的間隔（settings.sleep_between_videos）交給 yt-dlp 的 sleep_interval／max_sleep_interval，不自己 sleep。
- 失敗一律是 ToolError（media.classify_ytdlp 轉換）；記帳（health.json）由呼叫端（pipeline）負責，這裡不寫檔。
"""

from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

from toolzoo import ytdlp

from video_notes import media
from video_notes.adapters.source import REGISTRY, Progress
from video_notes.errors import Remedy, ToolError


class YtdlpSource:
    name = "ytdlp"

    def __init__(self, settings) -> None:
        self.settings = settings
        self._ffmpeg: str | None = None
        self._ffmpeg_looked = False

    @property
    def ffmpeg(self) -> str | None:
        if not self._ffmpeg_looked:
            self._ffmpeg, self._ffmpeg_looked = ytdlp.find_ffmpeg(), True
        return self._ffmpeg

    @property
    def cookies(self) -> str:
        return getattr(self.settings, "cookies_from_browser", "") or ""

    def capabilities(self) -> dict:
        return {"needs_network": True, "needs_key": False, "platforms": "many"}

    def check(self) -> ToolError | None:
        """不連網：套件在不在、ffmpeg、JS 執行環境。"""
        if importlib.util.find_spec("yt_dlp") is None:
            return media.classify_ytdlp(ImportError("No module named 'yt_dlp'"))
        if not self.ffmpeg:
            return ToolError("dependency_missing", "找不到 ffmpeg，無法合併或轉出音訊", source=media.FFMPEG_SOURCE,
                             remedy=Remedy("needs_config", "安裝 ffmpeg 並加入 PATH，或在設定裡指定 ffmpeg.exe 的位置",
                                           "https://ffmpeg.org/download.html"))
        if not ytdlp.find_js_runtimes():
            return media.classify_ytdlp(RuntimeError("No supported JavaScript runtime could be found"))
        return None

    def matches(self, url: str) -> bool:
        return url.strip().lower().startswith(("http://", "https://"))

    def fetch_info(self, url: str) -> dict:
        return media.fetch_info(url, self.ffmpeg, self.cookies)

    def download(self, url: str, folder: Path, *, keep_video: bool, on_progress: Progress | None = None,
                 cancel: threading.Event | None = None) -> None:
        media.download(url, folder, keep_video=keep_video, ffmpeg=self.ffmpeg, cookies=self.cookies,
                       on_progress=on_progress, cancel=cancel,
                       sleep_between=getattr(self.settings, "sleep_between_videos", None))


REGISTRY.register("ytdlp", lambda settings: YtdlpSource(settings), label="yt-dlp（通用）", order=900)
