"""來源（source）adapter：網址 → 影片資訊、下載影音。目前只有 yt-dlp（source_ytdlp.py），之後可加其他片源。

選哪個 adapter：for_url(url) 依 REGISTRY 的順序問每個 adapter 的 matches(url)，第一個說可以的就用它。
yt-dlp 支援上千個網站，所以它排最後當通用來源；專用來源（例如某平台的 API）排前面。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Protocol

from video_notes.adapters import Registry
from video_notes.errors import Remedy, ToolError

Progress = Callable[[float, str], None]


class SourceAdapter(Protocol):
    name: str

    def capabilities(self) -> dict:
        """{needs_network: True, needs_key: bool, platforms: [...] 或 "many"}"""

    def check(self) -> ToolError | None: ...

    def matches(self, url: str) -> bool: ...

    def fetch_info(self, url: str) -> dict:
        """影片資訊，只留 media.INFO_FIELDS 這些欄位。播放清單網址丟 ToolError("bad_input")。"""

    def download(self, url: str, folder: Path, *, keep_video: bool, on_progress: Progress | None = None,
                 cancel: threading.Event | None = None) -> None:
        """下載到 folder/media.<ext>。被取消丟 transcribe.Cancelled；其餘失敗丟 ToolError。"""


REGISTRY: Registry[SourceAdapter] = Registry("影片來源")


def load_builtin() -> None:
    """明確 import（PyInstaller 才看得到）。通用的 yt-dlp 註冊時 order 最大、排最後；專用來源加在這裡。"""
    from video_notes.adapters import source_ytdlp  # noqa: F401


def for_url(url: str, settings) -> SourceAdapter:
    load_builtin()
    for name in REGISTRY.names():
        adapter = REGISTRY.create(name, settings)
        if adapter.matches(url):
            return adapter
    raise ToolError("unsupported_source", "不支援這個網址的影片來源",
                    remedy=Remedy("none", "確認網址是單一影片的頁面"))
