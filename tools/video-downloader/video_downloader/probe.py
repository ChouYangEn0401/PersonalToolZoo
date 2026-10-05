"""下載前先解析網址：單支影片 → 標題、長度、有哪些畫質；播放清單 → 每一支的清單（可以勾選）。"""

from __future__ import annotations

from video_downloader.config import Settings
from video_downloader.options import explain_error, probe_options


def probe(url: str, settings: Settings, headers: dict[str, str] | None = None) -> dict:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    url = url.strip()
    try:
        with YoutubeDL(probe_options(settings, headers or {})) as ydl:
            info = ydl.sanitize_info(ydl.extract_info(url, download=False))
    except DownloadError as exc:
        return {"url": url, "error": explain_error(str(exc))}

    if info.get("_type") in ("playlist", "multi_video"):
        entries = []
        for i, e in enumerate(info.get("entries") or [], start=1):
            entry_url = e.get("url") or e.get("webpage_url") or ""
            if entry_url and not entry_url.startswith("http"):
                entry_url = ""   # 某些網站的扁平清單只給 ID，這種就用「清單網址＋第幾支」下載
            entries.append({"index": i, "url": entry_url, "title": e.get("title") or f"第 {i} 支",
                            "duration": e.get("duration"), "id": e.get("id", "")})
        return {"url": url, "type": "playlist", "title": info.get("title") or "播放清單",
                "uploader": info.get("uploader") or info.get("channel") or "", "count": len(entries),
                "entries": entries, "extractor": info.get("extractor_key", "")}

    formats = info.get("formats") or []
    heights = sorted({f["height"] for f in formats if f.get("height") and f.get("vcodec") not in (None, "none")},
                     reverse=True)
    return {
        "url": info.get("webpage_url") or url, "type": "video", "id": info.get("id", ""),
        "title": info.get("title") or url, "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": info.get("duration"), "thumbnail": info.get("thumbnail") or "",
        "extractor": info.get("extractor_key", ""), "heights": heights,
        "audio_only": bool(formats) and not heights, "is_live": bool(info.get("is_live")),
        "subtitles": sorted((info.get("subtitles") or {}).keys())[:20],
    }
