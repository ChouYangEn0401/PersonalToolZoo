"""網址 → (平台, 影片 ID, 短影音或一般影片)，以及每支影片的檔案放哪裡。

每支影片一個資料夾，資料夾名稱結尾一定是 ``[<kind>-<id>]``，只看網址就算得出來，
所以「這支影片做過了沒、做到哪一步」不用連網、不用下載就能判斷：

    <輸出資料夾>/
      台積電漲太多？鴻海卻漲不動 [video-knWPw9_a5qY]/
        media.m4a            下載的影音（保留影片時是 media.mp4）
        audio.wav            給 Whisper 的 16 kHz 單聲道音訊
        transcript.txt       逐字稿（分段）
        transcript.srt       字幕
        transcript.json      逐字稿＋時間碼（重新整理筆記時用）
        notes.<方案>.md      筆記；不同整理方案各一份，互不覆蓋
        info.json            影片資訊與處理紀錄

產生的檔案一律不刪。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

KIND_SHORT = "short"
KIND_VIDEO = "video"

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass(frozen=True)
class VideoRef:
    url: str        # 原始網址（去掉頭尾空白）
    platform: str   # youtube / tiktok / instagram / facebook / bilibili / other
    video_id: str   # 平台上的 ID；認不得的網站用網址的雜湊
    kind: str       # short / video

    @property
    def tag(self) -> str:
        return f"[{self.kind}-{self.video_id}]"


def _hash_id(url: str) -> str:
    return "h" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def classify(url: str) -> VideoRef:
    """只看網址判斷。網址格式不認得時，ID 用網址雜湊、種類先當一般影片。"""
    url = url.strip()
    parsed = urlparse(url if "://" in url else "https://" + url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    parts = [p for p in parsed.path.split("/") if p]
    query = parse_qs(parsed.query)

    if host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if parts[:1] == ["shorts"] and len(parts) > 1 and _YT_ID.match(parts[1]):
            return VideoRef(url, "youtube", parts[1], KIND_SHORT)
        vid = (query.get("v") or [""])[0]
        if _YT_ID.match(vid):
            return VideoRef(url, "youtube", vid, KIND_VIDEO)
        if parts[:1] in (["live"], ["embed"]) and len(parts) > 1 and _YT_ID.match(parts[1]):
            return VideoRef(url, "youtube", parts[1], KIND_VIDEO)
    if host == "youtu.be" and parts and _YT_ID.match(parts[0]):
        return VideoRef(url, "youtube", parts[0], KIND_VIDEO)

    if host.endswith("tiktok.com"):
        if "video" in parts:
            idx = parts.index("video")
            if idx + 1 < len(parts):
                return VideoRef(url, "tiktok", parts[idx + 1], KIND_SHORT)
        return VideoRef(url, "tiktok", _hash_id(url), KIND_SHORT)

    if host.endswith("instagram.com") and parts[:1] in (["reel"], ["reels"], ["p"], ["tv"]) and len(parts) > 1:
        return VideoRef(url, "instagram", parts[1], KIND_SHORT)

    if host.endswith("facebook.com") or host == "fb.watch":
        if parts[:1] == ["reel"] and len(parts) > 1:
            return VideoRef(url, "facebook", parts[1], KIND_SHORT)
        vid = (query.get("v") or [""])[0]
        if vid:
            return VideoRef(url, "facebook", vid, KIND_VIDEO)
        return VideoRef(url, "facebook", _hash_id(url), KIND_VIDEO)

    if host.endswith("bilibili.com") and parts[:1] == ["video"] and len(parts) > 1:
        return VideoRef(url, "bilibili", parts[1], KIND_VIDEO)

    return VideoRef(url, "other", _hash_id(url), KIND_VIDEO)


def safe_title(title: str, limit: int = 80) -> str:
    """Windows 檔名不能用的字元換掉，太長的截斷，結尾不能是點或空白。"""
    cleaned = _ILLEGAL.sub(" ", title or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > limit:
        cleaned = cleaned[:limit].rstrip()
    return cleaned.rstrip(". ") or "untitled"


def find_folder(root: Path, ref: VideoRef) -> Path | None:
    """找這支影片已經存在的資料夾（標題改過也找得到，因為只比對結尾的 tag）。"""
    if not root.is_dir():
        return None
    suffix = " " + ref.tag
    for child in root.iterdir():
        if child.is_dir() and (child.name.endswith(suffix) or child.name == ref.tag):
            return child
    return None


def new_folder(root: Path, ref: VideoRef, title: str) -> Path:
    return root / f"{safe_title(title)} {ref.tag}"


@dataclass(frozen=True)
class Artifacts:
    """一支影片資料夾裡各個產出檔的位置。"""

    folder: Path

    @property
    def info(self) -> Path:
        return self.folder / "info.json"

    @property
    def audio(self) -> Path:
        return self.folder / "audio.wav"

    @property
    def transcript_txt(self) -> Path:
        return self.folder / "transcript.txt"

    @property
    def transcript_srt(self) -> Path:
        return self.folder / "transcript.srt"

    @property
    def transcript_json(self) -> Path:
        return self.folder / "transcript.json"

    def media(self) -> Path | None:
        """已下載的影音檔（副檔名看當初下載到什麼格式）。"""
        for path in sorted(self.folder.glob("media.*")):
            if path.suffix not in (".part", ".ytdl", ".temp") and path.stat().st_size > 0:
                return path
        return None

    def notes(self, slug: str) -> Path:
        return self.folder / f"notes.{slug}.md"

    def all_notes(self) -> list[Path]:
        return sorted(self.folder.glob("notes.*.md"))

    def status(self) -> dict[str, object]:
        """各階段做完了沒（給 GUI 顯示「已有：…」、給 CLI 問要不要重做）。"""
        return {
            "media": self.media() is not None,
            "audio": self.audio.exists(),
            "transcript": self.transcript_json.exists() and self.transcript_txt.exists(),
            "notes": [p.name[len("notes."):-len(".md")] for p in self.all_notes()],
        }
