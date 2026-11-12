"""下載（yt-dlp）與抽音訊（ffmpeg）。

所有外部呼叫都明確 try/except，轉成 errors.ToolError（錯誤合約）：
- classify_ytdlp(exc)：yt-dlp 的上游例外 → ToolError（靠訊息文字比對；上游改了字眼就掉到 internal_bug，不會被吞掉）。
- extract_audio：ffmpeg 不在 → dependency_missing；失敗依 stderr 分 bad_input／resource_exhausted／internal_bug。
被取消（Cancelled）照舊往上丟，不轉換。
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable

from toolzoo import ytdlp

from video_notes.errors import Remedy, ToolError, internal, short
from video_notes.transcribe import Cancelled

YTDLP_SOURCE = "yt-dlp"          # health.json 的記帳名稱
FFMPEG_SOURCE = "ffmpeg"
DOC = "tools/video-notes/README.md（交接：yt-dlp 升級）"

# 只升級 yt-dlp 就好（會連同 yt-dlp-ejs 一起更新）。只「寫出來」，程式絕不自動執行。
UPGRADE_CMD = r'tools\video-notes\.venv\Scripts\python.exe -m pip install -U "yt-dlp[default]<2028"'
UPGRADE_ACTION = f"升級 yt-dlp：{UPGRADE_CMD}（exe 版的 yt-dlp 是打包時固定的，升級後要重新 build.ps1 video-notes）"

# 影片資訊裡只留整理筆記會用到、也方便事後查的欄位（完整的 info 動輒幾百 KB）
INFO_FIELDS = (
    "id", "title", "uploader", "channel", "channel_url", "duration", "upload_date", "description",
    "chapters", "webpage_url", "extractor_key", "width", "height", "thumbnail", "tags", "view_count",
)

# (關鍵字（小寫）, 處理方式)；由上往下第一個命中的算。順序有意義：JS 缺失要在 403 之前、「not a bot」要在「age」之前。
_JS_MARKERS = ("javascript runtime", "js runtime", "js_runtimes", "no supported javascript")
_BOT_MARKERS = ("not a bot", "confirm you're not a bot", "confirm you’re not a bot")
_RATE_MARKERS = ("http error 429", "too many requests", "rate-limit", "rate limit")
_OUTDATED_MARKERS = (
    "http error 403", "403: forbidden", "page needs to be reloaded", "requested format is not available",
    "no video formats found", "nsig", "signature extraction failed", "unable to extract", "sig function",
    "confirm you are on the latest version", "player response",
)
_GONE_MARKERS = (
    "video unavailable", "this video is unavailable", "private video", "this video is private",
    "not available in your country", "not made this video available", "geo restrict", "geo-restrict",
    "does not exist", "has been removed", "been terminated", "http error 404", "is not a valid url",
    "no video could be found", "video has been",
)
_AUTH_MARKERS = ("confirm your age", "age-restricted", "login required", "members-only", "join this channel",
                 "sign in to confirm your age", "requires authentication")
_NETWORK_MARKERS = (
    "unable to download webpage", "temporary failure in name resolution", "getaddrinfo failed",
    "name or service not known", "timed out", "connection reset", "connection refused", "connection aborted",
    "network is unreachable", "remote end closed", "urlopen error", "ssl:", "proxyerror",
)


def _outdated(detail: str) -> ToolError:
    return ToolError("dependency_outdated", "yt-dlp 太舊，跟不上網站的改版（升級通常就能解決）", detail=detail,
                     source=YTDLP_SOURCE, remedy=Remedy("needs_update", UPGRADE_ACTION, DOC))


def classify_ytdlp(exc: BaseException) -> ToolError:
    """yt-dlp（或下載過程）丟出的例外 → ToolError。不認得的 → internal_bug（附短摘要）。"""
    if isinstance(exc, ToolError):
        return exc
    detail = short(exc)
    low = str(exc).lower()
    cls = type(exc).__name__

    if isinstance(exc, ImportError):
        return ToolError("dependency_missing", "沒有安裝 yt-dlp 套件", detail=detail, source=YTDLP_SOURCE,
                         remedy=Remedy("needs_config", r'tools\video-notes\.venv\Scripts\python.exe -m pip install "yt-dlp[default]<2028"', DOC))
    if any(m in low for m in _JS_MARKERS):
        return ToolError("dependency_missing", "找不到 JavaScript 執行環境（YouTube 需要 Deno 2.3 以上或 Node 22 以上）",
                         detail=detail, source=YTDLP_SOURCE,
                         remedy=Remedy("needs_config", "安裝 Deno（2.3 以上）或 Node.js（22 以上）並加入 PATH，然後重開 Video Notes",
                                       "https://github.com/yt-dlp/yt-dlp/wiki/EJS"))
    if any(m in low for m in _BOT_MARKERS):
        return ToolError("rate_limited", "YouTube 要求確認不是機器人（短時間抓太多或網路被標記）", detail=detail,
                         source=YTDLP_SOURCE,
                         remedy=Remedy("needs_owner", "稍後再試、減少同時下載數、拉長影片間隔；要不要改用瀏覽器登入狀態（cookie）由使用者自己決定",
                                       "https://github.com/yt-dlp/yt-dlp/wiki/Extractors"))
    if any(m in low for m in _RATE_MARKERS):
        return ToolError("rate_limited", "對方網站限制了請求頻率（HTTP 429）", detail=detail, source=YTDLP_SOURCE,
                         remedy=Remedy("none", "稍後再試，或減少同時下載數、拉長影片間隔"))
    if any(m in low for m in _OUTDATED_MARKERS):
        return _outdated(detail)
    if cls == "UnsupportedError" or "unsupported url" in low:
        return ToolError("unsupported_source", "yt-dlp 不支援這個網址", detail=detail, source=YTDLP_SOURCE,
                         remedy=Remedy("none", "確認網址是單一影片的頁面；若網站是新的，先升級 yt-dlp 再試"))
    if any(m in low for m in _GONE_MARKERS):
        return ToolError("bad_input", "影片不存在、是私人影片，或在你的地區看不到", detail=detail, source=YTDLP_SOURCE,
                         remedy=Remedy("none", "確認網址能在瀏覽器開啟；私人或會員影片需要登入"))
    if any(m in low for m in _AUTH_MARKERS):
        return ToolError("auth_required", "這支影片需要登入才看得到（年齡限制或會員）", detail=detail, source=YTDLP_SOURCE,
                         remedy=Remedy("needs_config", "在設定裡選擇要用哪個瀏覽器的登入狀態（cookies_from_browser）；是否使用由使用者決定"))
    if isinstance(exc, (TimeoutError, ConnectionError)) or cls in ("URLError", "TransportError", "IncompleteRead") \
            or any(m in low for m in _NETWORK_MARKERS):
        return ToolError("network_unreachable", "連不上影片網站（網路問題或網站暫時無法連線）", detail=detail,
                         source=YTDLP_SOURCE, remedy=Remedy("none", "檢查網路後重試"))
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return ToolError("resource_exhausted", "磁碟空間不足，無法寫入下載的檔案", detail=detail, source=YTDLP_SOURCE,
                         remedy=Remedy("needs_owner", "清出磁碟空間，或把輸出資料夾改到別的磁碟"))
    return internal(exc, source=YTDLP_SOURCE, where="下載")


def _import_ytdlp():
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadCancelled
    except ImportError as exc:
        raise classify_ytdlp(exc) from exc
    return YoutubeDL, DownloadCancelled


def sleep_options(sleep_between: list[float] | tuple[float, ...] | None) -> dict:
    """影片與影片之間的間隔：交給 yt-dlp 的 sleep_interval／max_sleep_interval，不自己 time.sleep。"""
    values = [float(v) for v in (sleep_between or []) if v is not None and float(v) > 0]
    if not values:
        return {}
    return {"sleep_interval": min(values), "max_sleep_interval": max(values)}


def fetch_info(url: str, ffmpeg: str | None, cookies: str = "") -> dict:
    YoutubeDL, _ = _import_ytdlp()
    opts = {**ytdlp.base_options(ffmpeg, cookies), "skip_download": True, "noplaylist": True}
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.sanitize_info(ydl.extract_info(url, download=False))
    except Cancelled:
        raise
    except Exception as exc:  # noqa: BLE001 —— 轉成 ToolError，不吞
        raise classify_ytdlp(exc) from exc
    if info.get("_type") == "playlist":
        raise ToolError("bad_input", "這是播放清單網址，請貼單一影片的網址", source=YTDLP_SOURCE,
                        remedy=Remedy("none", "貼單一影片的網址（或用 Video Downloader 下載整個清單）"))
    return {k: info.get(k) for k in INFO_FIELDS if info.get(k) is not None}


def download(url: str, folder: Path, *, keep_video: bool, ffmpeg: str | None, cookies: str = "",
             on_progress: Callable[[float, str], None] | None = None,
             cancel: threading.Event | None = None,
             sleep_between: list[float] | tuple[float, ...] | None = None) -> None:
    YoutubeDL, DownloadCancelled = _import_ytdlp()

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
        **sleep_options(sleep_between),
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
    except Cancelled:
        raise
    except Exception as exc:  # noqa: BLE001 —— 轉成 ToolError，不吞
        inner = getattr(exc, "exc_info", None)
        if inner and len(inner) > 1 and isinstance(inner[1], DownloadCancelled):
            raise Cancelled() from exc
        raise classify_ytdlp(exc) from exc


def classify_ffmpeg(stderr: str, returncode: int) -> ToolError:
    low = (stderr or "").lower()
    detail = f"ffmpeg 結束碼 {returncode}：{' '.join((stderr or '').split())[-250:]}"
    if "no space left" in low or "disk full" in low:
        return ToolError("resource_exhausted", "磁碟空間不足，ffmpeg 無法寫出音訊", detail=detail, source=FFMPEG_SOURCE,
                         remedy=Remedy("needs_owner", "清出磁碟空間，或把輸出資料夾改到別的磁碟"))
    if any(m in low for m in ("invalid data found", "moov atom not found", "does not contain any stream",
                              "no such file", "error opening input", "matches no streams", "output file is empty")):
        return ToolError("bad_input", "ffmpeg 讀不了這個影音檔（檔案損壞、不完整，或裡面沒有聲音）", detail=detail,
                         source=FFMPEG_SOURCE, remedy=Remedy("none", "重新下載這支影片；仍然一樣就是原片沒有音訊"))
    return ToolError("internal_bug", "ffmpeg 抽音訊失敗（原因不明）", detail=detail, source=FFMPEG_SOURCE,
                     remedy=Remedy("needs_owner", "把工作紀錄（log）與這段訊息交給維護者"))


def extract_audio(media: Path, wav: Path, ffmpeg: str | None) -> None:
    """轉成 16 kHz 單聲道 WAV（Whisper 的原生格式，辨識前不用再轉）。"""
    missing = ToolError("dependency_missing", "找不到 ffmpeg，無法抽出音訊", source=FFMPEG_SOURCE,
                        remedy=Remedy("needs_config", "安裝 ffmpeg 並加入 PATH，或在設定裡指定 ffmpeg.exe 的位置",
                                      "https://ffmpeg.org/download.html"))
    if not ffmpeg:
        raise missing
    tmp = wav.with_suffix(".tmp.wav")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(media),
           "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(tmp)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError as exc:
        raise missing from exc
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        if getattr(exc, "errno", None) == 28:
            raise classify_ffmpeg("No space left on device", -1) from exc
        raise internal(exc, source=FFMPEG_SOURCE, where="啟動 ffmpeg") from exc
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise classify_ffmpeg(result.stderr, result.returncode)
    try:
        tmp.replace(wav)  # 寫完才改名，中途失敗不會留下一個看起來完整的 audio.wav
    except OSError as exc:
        raise internal(exc, source=FFMPEG_SOURCE, where="寫入 audio.wav") from exc
