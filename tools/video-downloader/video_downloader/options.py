"""設定＋這次的下載需求 → yt-dlp 的參數。

先組成 yt-dlp 命令列會用的參數，再交給 yt-dlp 自己的 parse_options() 轉成 Python API 的選項。
這樣「嵌入字幕、縮圖、轉 MP3」這些後處理的設定，保證跟在命令列打 yt-dlp 一模一樣，
不用自己維護 yt-dlp 內部的格式（它改版時也不會壞）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from toolzoo import ytdlp

from video_downloader.config import Settings
from video_downloader.presets import resolve


@dataclass
class DownloadRequest:
    url: str
    preset: str = ""                 # 空白 = 設定裡的預設
    custom_format: str = ""
    filename: str = ""               # 不含副檔名；空白 = 用設定的檔名範本
    subfolder: str = ""              # 播放清單：用清單名稱當子資料夾
    playlist_items: str = ""         # 清單裡沒有自己網址的項目：用「清單網址＋第幾支」下載
    headers: dict[str, str] = field(default_factory=dict)
    title: str = ""                  # 解析時拿到的標題，下載開始前先顯示


def safe_name(name: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join(" " if c in bad or ord(c) < 32 else c for c in name).strip().rstrip(". ")
    return cleaned[:150] or "video"


def parse_headers(text: str) -> dict[str, str]:
    """「Referer: https://…」一行一個 → dict。給直接的 m3u8 網址用（很多 CDN 會檢查 Referer）。"""
    headers: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            name, value = line.split(":", 1)
            if name.strip() and value.strip():
                headers[name.strip()] = value.strip()
    return headers


def output_folder(settings: Settings, req: DownloadRequest) -> Path:
    root = settings.output_root()
    return root / safe_name(req.subfolder) if req.subfolder.strip() else root


def cli_args(settings: Settings, req: DownloadRequest) -> list[str]:
    preset = resolve(req.preset or settings.preset, req.custom_format or settings.custom_format)
    template = f"{safe_name(req.filename)}.%(ext)s" if req.filename.strip() else settings.filename_template
    args = [
        "--ignore-config",                       # 不讀使用者電腦上的 yt-dlp.conf，結果才可預期
        "-f", preset.format,
        "-P", str(output_folder(settings, req)),
        "-o", template,
        "--windows-filenames",
        "--no-mtime",                            # 檔案時間用下載時間，在檔案總管排序比較直覺
        "--retries", "10",
        "--fragment-retries", "20",
        "--concurrent-fragments", str(max(1, settings.concurrent_fragments)),
    ]
    if preset.audio:
        args += ["-x", "--audio-format", preset.audio]
        if preset.audio == "mp3":
            args += ["--audio-quality", "192K"]
    else:
        args += ["--merge-output-format", preset.merge]
    if req.playlist_items == "all":      # 整份播放清單（CLI 的 --playlist）
        args += ["--yes-playlist"]
        if not req.filename.strip():
            args[args.index("-o") + 1] = "%(playlist_title)s/%(playlist_index)03d - " + settings.filename_template
    elif req.playlist_items:
        args += ["--yes-playlist", "--playlist-items", req.playlist_items]
    else:
        args += ["--no-playlist"]
    if settings.subtitles:
        args += ["--write-subs", "--sub-langs", settings.sub_langs or "all"]
        if settings.auto_subtitles:
            args += ["--write-auto-subs"]
        if settings.embed_subs and not preset.audio:
            args += ["--embed-subs"]
    if settings.embed_metadata:
        args += ["--embed-metadata"]
    if settings.embed_thumbnail:
        args += ["--embed-thumbnail"]
    if settings.rate_limit.strip():
        args += ["--limit-rate", settings.rate_limit.strip()]
    if settings.proxy.strip():
        args += ["--proxy", settings.proxy.strip()]
    for name, value in req.headers.items():
        args += ["--add-header", f"{name}:{value}"]
    return args


def build_options(settings: Settings, req: DownloadRequest) -> dict:
    import yt_dlp

    opts = yt_dlp.parse_options(cli_args(settings, req)).ydl_opts
    opts.update(ytdlp.base_options(ytdlp.find_ffmpeg(settings.ffmpeg_path), settings.cookies_from_browser))
    return opts


def probe_options(settings: Settings, headers: dict[str, str]) -> dict:
    opts = ytdlp.base_options(ytdlp.find_ffmpeg(settings.ffmpeg_path), settings.cookies_from_browser)
    opts.update({"skip_download": True, "extract_flat": "in_playlist", "noplaylist": False})
    if headers:
        opts["http_headers"] = headers
    if settings.proxy.strip():
        opts["proxy"] = settings.proxy.strip()
    return opts


_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")

# YouTube 改版、yt-dlp 還沒跟上時常見的錯誤字樣。這類問題升級 yt-dlp 幾乎都會好，
# 加 Referer 或換設定都沒用（yt-dlp 官方 issue 裡這幾種錯誤都是靠新版修掉的）。
_YOUTUBE_STALE_MARKERS = (
    "http error 403", "forbidden", "the page needs to be reloaded", "requested format is not available",
    "nsig extraction failed", "signature extraction failed", "challenge solving failed",
    "only images are available",
)


def _is_youtube(low_message: str, url: str) -> bool:
    low_url = url.lower()
    return any(h in low_url for h in _YOUTUBE_HOSTS) or "[youtube" in low_message


def explain_error(message: str, url: str = "") -> str:
    """yt-dlp 的錯誤 → 加上下一步該怎麼做。url 有給的話，YouTube 的錯誤會給 YouTube 專用的建議。"""
    msg = message.replace("ERROR: ", "").strip()
    low = msg.lower()
    if "drm" in low:
        return msg + "\n→ 這支影片有 DRM 版權保護，無法下載。"
    if any(k in low for k in ("sign in to confirm", "login required", "members-only", "private video",
                              "this video is only available", "account")):
        return msg + "\n→ 需要登入才看得到：在設定選「用哪個瀏覽器的登入狀態」（Windows 上 Firefox 最穩），並先在那個瀏覽器登入。"
    if _is_youtube(low, url) and any(k in low for k in _YOUTUBE_STALE_MARKERS):
        return msg + (
            f"\n→ YouTube 常改版，這通常是 yt-dlp 太舊（目前 {ytdlp.version()}），升級就會好："
            "原始碼執行跑 tools\\video-downloader\\.venv\\Scripts\\python.exe -m pip install -U \"yt-dlp[default]<2028\"；"
            "exe 版升級後要重新 build。也確認標題列的 JS 是 ✓（YouTube 需要 Node 或 Deno）。")
    if "http error 403" in low or "forbidden" in low:
        return msg + "\n→ 伺服器拒絕：在進階選項加上 Referer（影片所在頁面的網址），或改用瀏覽器的登入狀態。"
    if "unsupported url" in low:
        return msg + "\n→ yt-dlp 不認得這個網站：如果是網頁裡的串流，請找出 .m3u8 / .mpd 網址直接貼上（瀏覽器 F12 → Network）。"
    if "requested format is not available" in low:
        return msg + "\n→ 沒有符合這個畫質設定的格式，換「最高畫質」或「最相容」試試。"
    if "ffmpeg" in low and ("not found" in low or "not installed" in low):
        return msg + "\n→ 找不到 ffmpeg：合併影像與聲音、轉 MP3 都需要它。請安裝並加入 PATH，或在設定指定位置。"
    return msg
