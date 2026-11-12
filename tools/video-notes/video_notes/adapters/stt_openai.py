"""OpenAI 語音辨識（雲端；會上傳音訊）。

- 預設模型 gpt-4o-transcribe；whisper-1 也能用（只有 whisper-1 會回分段時間碼，見 stt_chunk.py 檔頭的調查結果）。
  注意：OpenAI 文件（2026-11-12）標示 whisper-1／gpt-4o-transcribe 將於 2027-02-26 停用，建議改 gpt-transcribe；
  stt_model 設定可直接填新名稱，這裡不寫死模型清單。
- 單檔上限 25 MB → 每 600 秒切一段（mp3 32 kbps ≈ 2.4 MB）。
- 金鑰：toolzoo.ai 的 find_key("openai")（環境變數或專案 .env 的 OPENAI_API_KEY）。
- SDK 只在真的呼叫時才 import；測試可以傳入假的 client_factory。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from video_notes.adapters import stt
from video_notes.adapters.stt_chunk import ChunkResult, to_tool_error, transcribe_chunked
from video_notes.errors import Remedy, ToolError
from video_notes.transcribe import ZH_PROMPT, Segment, Transcript

NAME = "openai"
DEFAULT_MODEL = "gpt-4o-transcribe"
CHUNK_SECONDS = 600
SERVICE = "OpenAI"
BILLING = "https://platform.openai.com/settings/organization/billing/"


class OpenAIStt:
    name = NAME

    def __init__(self, settings, client_factory: Callable[[str], object] | None = None, ffmpeg: str | None = None):
        self.settings = settings
        self.model = (getattr(settings, "stt_model", "") or "").strip() or DEFAULT_MODEL
        self._client_factory = client_factory
        self._ffmpeg = ffmpeg

    # ---- 固定入口 ----
    def capabilities(self) -> dict:
        return {"needs_network": True, "needs_key": True, "privacy": "cloud", "languages": "auto",
                "max_audio_seconds": None, "cost_hint": "按量計費（約每分鐘音訊 US$0.006）"}

    def check(self) -> ToolError | None:
        from toolzoo.ai import find_key

        if not find_key("openai")[0]:
            return _missing_key()
        return None

    def describe(self) -> str:
        return f"OpenAI {self.model}"

    # ---- 辨識 ----
    def _client(self):
        from toolzoo.ai import find_key

        key = find_key("openai")[0]
        if not key:
            raise _missing_key()
        if self._client_factory is not None:
            return self._client_factory(key), key
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise to_tool_error(exc, source=f"stt:{NAME}", service=SERVICE) from exc
        return OpenAI(api_key=key, timeout=600.0), key

    def transcribe(self, wav: Path, *, language: str | None = None, on_progress=None,
                   cancel: threading.Event | None = None) -> Transcript:
        client, key = self._client()
        language = language or _lang(self.settings)

        def call(path: Path, lang: str | None) -> ChunkResult:
            params: dict = {"model": self.model}
            if lang:
                params["language"] = lang
            if lang and lang.startswith("zh"):
                params["prompt"] = ZH_PROMPT
            with_segments = self.model.startswith("whisper")
            if with_segments:
                params["response_format"] = "verbose_json"
                params["timestamp_granularities"] = ["segment"]
            else:
                params["response_format"] = "json"
            try:
                with open(path, "rb") as fh:
                    resp = client.audio.transcriptions.create(file=fh, **params)
            except Exception as exc:  # noqa: BLE001 — 全部轉成 ToolError
                raise to_tool_error(exc, source=f"stt:{NAME}", service=SERVICE, key=key,
                                    key_hint="在專案的 .env 設定 OPENAI_API_KEY", billing=BILLING) from exc
            text = (getattr(resp, "text", None) or "").strip()
            segs = None
            if with_segments and getattr(resp, "segments", None):
                segs = [Segment(float(_get(s, "start", 0.0)), float(_get(s, "end", 0.0)), str(_get(s, "text", "")))
                        for s in resp.segments]
            return ChunkResult(text, segs, getattr(resp, "language", None))

        return transcribe_chunked(wav, call=call, chunk_seconds=CHUNK_SECONDS,
                                  traditional=getattr(self.settings, "traditional", True), language=language,
                                  on_progress=on_progress, cancel=cancel, ffmpeg=self._ffmpeg)


def _get(obj, name, default):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _lang(settings) -> str | None:
    lang = getattr(settings, "language", "auto")
    return None if lang in ("", "auto", None) else lang


def _missing_key() -> ToolError:
    return ToolError("auth_required", "沒有設定 OpenAI 金鑰", source=f"stt:{NAME}",
                     remedy=Remedy("needs_config", "在專案的 .env 加一行 OPENAI_API_KEY=你的金鑰（範本見 .env.example）"))


stt.REGISTRY.register(NAME, lambda settings: OpenAIStt(settings), label="OpenAI 語音辨識（雲端）", order=10)
