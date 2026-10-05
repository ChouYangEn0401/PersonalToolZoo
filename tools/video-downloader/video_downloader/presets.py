"""畫質 / 格式的預設組合 → yt-dlp 的 format 字串與後處理。

「最相容」優先選 H.264＋AAC 合成 MP4：手機、電視、剪輯軟體都能直接開。
「最高畫質」不限編碼（常是 VP9 / AV1），合成 MKV 避免容器不支援。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    format: str
    merge: str = "mp4"        # 影像＋聲音分開下載時，合併成什麼容器
    audio: str = ""           # 只要音訊時轉成什麼格式（mp3 / m4a）
    description: str = ""


def _height(h: int) -> str:
    return (f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<={h}]+ba/b[height<={h}]/b")


PRESETS: dict[str, Preset] = {p.id: p for p in (
    Preset("compat", "最相容 MP4（H.264）", "bv*[vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
           description="手機、電視、剪輯軟體都能直接播"),
    Preset("best", "最高畫質", "bv*+ba/b", merge="mkv",
           description="不限編碼（常是 VP9 / AV1），合成 MKV"),
    Preset("2160p", "4K（2160p）", _height(2160)),
    Preset("1080p", "1080p", _height(1080)),
    Preset("720p", "720p", _height(720), description="檔案小、速度快"),
    Preset("480p", "480p", _height(480)),
    Preset("audio-mp3", "只要聲音 MP3", "ba/b", audio="mp3", description="Podcast、音樂"),
    Preset("audio-m4a", "只要聲音 M4A", "ba[ext=m4a]/ba/b", audio="m4a", description="不重新編碼，音質最好"),
    Preset("custom", "自訂 format 字串", "", description="yt-dlp 的 -f 語法，例如 bv*[height<=1440]+ba"),
)}

DEFAULT_PRESET = "compat"


def resolve(preset_id: str, custom: str = "") -> Preset:
    preset = PRESETS.get(preset_id) or PRESETS[DEFAULT_PRESET]
    if preset.id == "custom":
        if not custom.strip():
            raise ValueError("選了自訂格式，但沒有填 format 字串")
        return Preset("custom", preset.name, custom.strip())
    return preset
