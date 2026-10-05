"""設定：預設值、存檔位置、輸出資料夾的三種選擇。

設定存在 %APPDATA%\\PersonalToolZoo\\video-notes\\settings.json（GUI 改了就寫回去），
CLI 的參數只影響那一次執行，不會改到存檔。
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from toolzoo.appdirs import downloads_dir, tool_data_dir

TOOL_NAME = "video-notes"

# 輸出資料夾的三種選擇，順序就是預設的優先順序
OUTPUT_DOWNLOADS = "downloads"   # 使用者的「下載」\Video Notes
OUTPUT_DATA = "data"             # 工具資料夾（或 exe 旁邊）的 data\
OUTPUT_CUSTOM = "custom"         # 自選


def app_dir() -> Path:
    """原始碼執行時是 tools/video-notes/，打包後是 exe 所在的資料夾。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    """隨程式一起發佈的唯讀檔案（prompts/、web 前端）在哪裡。"""
    return Path(getattr(sys, "_MEIPASS", app_dir()))


def user_dir() -> Path:
    return tool_data_dir(TOOL_NAME)


@dataclass
class Settings:
    # 輸出
    output: str = OUTPUT_DOWNLOADS
    output_custom: str = ""
    keep_video: bool = False          # False：只下載音訊（快很多）；True：連影片一起留

    # 語音辨識
    whisper_model: str = "medium"
    whisper_device: str = "auto"      # auto / cuda / cpu
    # Whisper 的語言。auto = 先判斷語言再辨識；強制 zh 會把英文影片硬翻成（錯的）中文
    language: str = "auto"
    traditional: bool = True          # 中文逐字稿轉成繁體（台灣用語）

    # AI 整理
    provider: str = "openai"
    model: str = ""                   # 空白 = 該 provider 的預設模型
    profile: str = "auto"
    modifiers: list[str] = field(default_factory=list)
    long_transcript_chars: int = 60000  # 逐字稿超過這個長度就分段整理再合併

    # 同時處理幾支影片（下載可以並行；轉錄一次一支、AI 一次一個請求，避免搶 GPU 與被限流）
    parallel_jobs: int = 3

    # 下載
    cookies_from_browser: str = ""    # 例如 "chrome"、"edge"：需要登入才看得到的影片用

    # 處理完要不要把結果 POST 給別的程式（GUI 用；CLI 看 socket/config.json 或 --post）
    notify_url: str = ""

    def output_root(self) -> Path:
        if self.output == OUTPUT_CUSTOM and self.output_custom.strip():
            return Path(self.output_custom.strip()).expanduser()
        if self.output == OUTPUT_DATA:
            return app_dir() / "data"
        return downloads_dir() / "Video Notes"


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


def key_files() -> tuple[Path, ...]:
    """除了共用金鑰檔以外，也接受放在工具資料夾（或 exe 旁）的 .env——舊專案的 .env 直接複製過來就能用。"""
    return (app_dir() / ".env",)
