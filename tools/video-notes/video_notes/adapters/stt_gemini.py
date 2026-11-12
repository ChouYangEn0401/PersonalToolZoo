"""Gemini 音訊辨識（雲端；會上傳音訊），走 Gemini 的 OpenAI 相容端點、用 openai SDK，不新增依賴。

- 相容端點（https://generativelanguage.googleapis.com/v1beta/openai/）文件只列 chat completions，沒有 /audio/transcriptions：
  音訊以 input_audio（base64，format="mp3"）放進訊息，再用文字提示要求「逐字轉寫、不要加時間碼或說明」。
  來源：https://aistudio.google.com/docs/openai 、 https://aistudio.google.com/docs/audio
- 請求上限約 20 MB（含 base64，約 +33%）；原生單次提示最長 9.5 小時、32 token／秒。
  mp3 32 kbps 每 300 秒 ≈ 1.2 MB，遠低於上限；段落短也讓「依字數分配時間碼」更準。
- 模型只回純文字 → 時間碼由 stt_chunk.spread_text 依句子字數在該段內平均分配（取捨寫在 stt_chunk.py 檔頭）。
- 金鑰：toolzoo.ai 的 find_key("gemini")（GEMINI_API_KEY）。預設模型 gemini-2.5-flash（跟 toolzoo.ai 一致）。
"""

from __future__ import annotations

import base64
import threading
from pathlib import Path
from typing import Callable

from video_notes.adapters import stt
from video_notes.adapters.stt_chunk import ChunkResult, to_tool_error, transcribe_chunked
from video_notes.errors import Remedy, ToolError
from video_notes.transcribe import Transcript

NAME = "gemini"
DEFAULT_MODEL = "gemini-2.5-flash"
CHUNK_SECONDS = 300
SERVICE = "Gemini"
BILLING = "https://aistudio.google.com/apikey"

PROMPT = ("請把這段音訊逐字轉寫成文字。只輸出轉寫內容：不要加時間碼、不要加說話者標記、不要加任何說明或前言；"
          "保持原本的語言（不要翻譯）；適當加上標點。如果沒有人聲，輸出空白。")


class GeminiStt:
    name = NAME

    def __init__(self, settings, client_factory: Callable[[str], object] | None = None, ffmpeg: str | None = None):
        self.settings = settings
        self.model = (getattr(settings, "stt_model", "") or "").strip() or DEFAULT_MODEL
        self._client_factory = client_factory
        self._ffmpeg = ffmpeg

    def capabilities(self) -> dict:
        return {"needs_network": True, "needs_key": True, "privacy": "cloud", "languages": "auto",
                "max_audio_seconds": None, "cost_hint": "按量計費（音訊約 32 token／秒；免費額度內可能不用錢）"}

    def check(self) -> ToolError | None:
        from toolzoo.ai import find_key

        if not find_key("gemini")[0]:
            return _missing_key()
        return None

    def describe(self) -> str:
        return f"Gemini {self.model}"

    def _client(self):
        from toolzoo.ai import find_key

        key = find_key("gemini")[0]
        if not key:
            raise _missing_key()
        if self._client_factory is not None:
            return self._client_factory(key), key
        try:
            from toolzoo.ai.openai_compat import make_client

            return make_client("gemini", key, 600.0), key
        except ImportError as exc:
            raise to_tool_error(exc, source=f"stt:{NAME}", service=SERVICE) from exc

    def transcribe(self, wav: Path, *, language: str | None = None, on_progress=None,
                   cancel: threading.Event | None = None) -> Transcript:
        client, key = self._client()
        cfg_lang = getattr(self.settings, "language", "auto")
        language = language or (None if cfg_lang in ("", "auto", None) else cfg_lang)

        def call(path: Path, lang: str | None) -> ChunkResult:
            prompt = PROMPT + (f"（音訊語言：{lang}）" if lang else "")
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            messages = [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "input_audio", "input_audio": {"data": data, "format": "mp3"}},
            ]}]
            try:
                resp = client.chat.completions.create(model=self.model, messages=messages)
                text = (resp.choices[0].message.content or "").strip() if resp.choices else ""
            except Exception as exc:  # noqa: BLE001 — 全部轉成 ToolError
                raise to_tool_error(exc, source=f"stt:{NAME}", service=SERVICE, key=key,
                                    key_hint="在專案的 .env 設定 GEMINI_API_KEY", billing=BILLING) from exc
            return ChunkResult(text, None, None)

        return transcribe_chunked(wav, call=call, chunk_seconds=CHUNK_SECONDS,
                                  traditional=getattr(self.settings, "traditional", True), language=language,
                                  on_progress=on_progress, cancel=cancel, ffmpeg=self._ffmpeg)


def _missing_key() -> ToolError:
    return ToolError("auth_required", "沒有設定 Gemini 金鑰", source=f"stt:{NAME}",
                     remedy=Remedy("needs_config", "在專案的 .env 加一行 GEMINI_API_KEY=你的金鑰（範本見 .env.example）"))


stt.REGISTRY.register(NAME, lambda settings: GeminiStt(settings), label="Gemini 音訊辨識（雲端）", order=20)
