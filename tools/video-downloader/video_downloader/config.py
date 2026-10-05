"""設定與預設值。存在 %APPDATA%\\PersonalToolZoo\\video-downloader\\settings.json。"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from toolzoo.appdirs import downloads_dir, tool_data_dir

from video_downloader.presets import DEFAULT_PRESET

TOOL_NAME = "video-downloader"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def user_dir() -> Path:
    return tool_data_dir(TOOL_NAME)


@dataclass
class Settings:
    output_dir: str = ""                      # 空白 = 「下載\Video Downloader」
    preset: str = DEFAULT_PRESET
    custom_format: str = ""
    filename_template: str = "%(title).150B [%(id)s].%(ext)s"
    concurrent_downloads: int = 2             # 同時下載幾支
    concurrent_fragments: int = 4             # m3u8 / DASH 分段同時抓幾段（舊版的 workers）
    subtitles: bool = False
    sub_langs: str = "zh-TW,zh-Hant,zh,en"
    auto_subtitles: bool = False              # 也抓自動產生的字幕
    embed_subs: bool = True
    embed_thumbnail: bool = False
    embed_metadata: bool = True
    cookies_from_browser: str = ""            # chrome / edge / firefox：需要登入的影片用
    rate_limit: str = ""                      # 例如 5M
    proxy: str = ""
    ffmpeg_path: str = ""                     # 空白 = 自動找

    def output_root(self) -> Path:
        return Path(self.output_dir).expanduser() if self.output_dir.strip() else downloads_dir() / "Video Downloader"


def settings_file() -> Path:
    return user_dir() / "settings.json"


def load_settings() -> Settings:
    try:
        raw = json.loads(settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in raw.items() if k in known})


def save_settings(settings: Settings) -> None:
    settings_file().write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
