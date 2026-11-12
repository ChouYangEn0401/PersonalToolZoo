"""語音辨識（STT）adapter 的介面與登記表。

本機 Whisper（faster-whisper）是預設與底線：沒網路、沒金鑰也一定能跑。雲端服務是可選的升級。

實作檔：stt_local.py（包裝 transcribe.Transcriber）、stt_openai.py、stt_gemini.py……
每個實作檔在被 import 時呼叫 REGISTRY.register(name, factory)；工廠收 Settings。

退路規則（build_stt 負責）：
- 雲端失敗 → 只有 settings.stt_fallback_local 為 True 時才退回本機，並在 analysis 標 quality flag "stt_fallback_local"。
- 本機 → 雲端 **絕不**自動發生（不在使用者沒選的情況下上傳音訊）。
- 讓 pipeline 知道有退路：build_stt 回傳的包裝（FallbackStt）有 `fell_back: bool` 與 `fallback_error`；
  沒有退路能力的 adapter 沒有這兩個屬性，用 getattr(adapter, "fell_back", False) 讀。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Protocol

from video_notes.adapters import Registry
from video_notes.errors import ToolError
from video_notes.transcribe import Transcript

Progress = Callable[[float, str], None]   # (0~1, 目前辨識到的文字)

LOCAL = "local"


class SttAdapter(Protocol):
    name: str          # 登記名稱，例如 "local"、"openai"
    model: str         # 實際使用的模型（寫進 analysis.provenance.stt）

    def capabilities(self) -> dict:
        """{needs_network, needs_key, privacy: "local"|"cloud", languages: "auto"|[...],
            max_audio_seconds: int|None（單次上限；adapter 自己負責切段，不是使用者的限制）, cost_hint: str}"""

    def check(self) -> ToolError | None: ...

    def describe(self) -> str:
        """給工作紀錄看的一行，例如「medium（GPU）」、「OpenAI gpt-4o-transcribe」。"""

    def transcribe(self, wav: Path, *, language: str | None = None, on_progress: Progress | None = None,
                   cancel: threading.Event | None = None) -> Transcript:
        """wav 是 16 kHz 單聲道（media.extract_audio 的輸出）。language=None 表示自動判斷。
        回傳的 Transcript 中文已轉繁體（settings.traditional）；被取消丟 transcribe.Cancelled；其餘失敗丟 ToolError。"""


REGISTRY: Registry[SttAdapter] = Registry("語音辨識服務")


def load_builtin() -> None:
    """import 內建實作（各自註冊）。沒裝某家 SDK 不影響其他家：SDK 只在 transcribe() 裡才 import。"""
    # 明確 import（PyInstaller 才看得到）；順序由各自註冊的 order 決定（local 是 0）
    from video_notes.adapters import stt_gemini, stt_local, stt_openai  # noqa: F401


class FallbackStt:
    """雲端 adapter 的包裝：雲端丟 ToolError（或任何非取消的例外）就改用本機 Whisper。

    讓 pipeline 知道發生了退路（選擇的方式：adapter 上的屬性，不改 Transcript）：
        fell_back: bool                    最近一次 transcribe() 有沒有退回本機（每次呼叫開頭重設為 False）
        fallback_error: ToolError | None   雲端為什麼失敗（pipeline 可寫進工作紀錄）
    pipeline 在 transcribe() 之後讀 `getattr(adapter, "fell_back", False)`，為 True 就在 analysis 的
    quality_flags 加 "stt_fallback_local"；provenance 讀 name／model，退路後它們會變成本機的值。
    取消（transcribe.Cancelled）不算失敗，原樣往上丟。
    """

    def __init__(self, primary: SttAdapter, local: SttAdapter):
        self.primary = primary
        self.local = local
        self.fell_back = False
        self.fallback_error: ToolError | None = None

    @property
    def _active(self) -> SttAdapter:
        return self.local if self.fell_back else self.primary

    @property
    def name(self) -> str:
        return self._active.name

    @property
    def model(self) -> str:
        return self._active.model

    def capabilities(self) -> dict:
        return self.primary.capabilities()

    def check(self) -> ToolError | None:
        return self.primary.check()

    def describe(self) -> str:
        text = self._active.describe()
        return f"{text}（雲端失敗，已退回本機）" if self.fell_back else text

    def transcribe(self, wav: Path, *, language: str | None = None, on_progress: Progress | None = None,
                   cancel: threading.Event | None = None) -> Transcript:
        from video_notes.errors import as_tool_error
        from video_notes.transcribe import Cancelled

        self.fell_back = False
        self.fallback_error = None
        try:
            error = self.primary.check()
            if error is not None:
                raise error
            return self.primary.transcribe(wav, language=language, on_progress=on_progress, cancel=cancel)
        except Cancelled:
            raise
        except Exception as exc:  # noqa: BLE001 — 雲端的任何失敗都走退路
            self.fallback_error = as_tool_error(exc, f"stt:{self.primary.name}", "雲端語音辨識")
        self.fell_back = True
        if on_progress:
            on_progress(0.0, "")
        return self.local.transcribe(wav, language=language, on_progress=on_progress, cancel=cancel)


def build_stt(settings) -> SttAdapter:
    """依 settings.stt_provider 建立 adapter；雲端且 settings.stt_fallback_local 時回傳「失敗會退回本機」的包裝。

    本機 adapter 永遠不包退路（本機絕不自動退到雲端）。名稱不存在丟 ToolError(config_invalid)。
    """
    load_builtin()
    name = (getattr(settings, "stt_provider", "") or LOCAL).strip() or LOCAL
    adapter = REGISTRY.create(name, settings)
    if name == LOCAL or not getattr(settings, "stt_fallback_local", False):
        return adapter
    return FallbackStt(adapter, REGISTRY.create(LOCAL, settings))
