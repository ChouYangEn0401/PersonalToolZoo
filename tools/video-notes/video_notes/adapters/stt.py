"""語音辨識（STT）adapter 的介面與登記表。

本機 Whisper（faster-whisper）是預設與底線：沒網路、沒金鑰也一定能跑。雲端服務是可選的升級。

實作檔：stt_local.py（包裝 transcribe.Transcriber）、stt_openai.py、stt_gemini.py……
每個實作檔在被 import 時呼叫 REGISTRY.register(name, factory)；工廠收 Settings。

退路規則（build_stt 負責）：
- 雲端失敗 → 只有 settings.stt_fallback_local 為 True 時才退回本機，並在 analysis 標 quality flag "stt_fallback_local"。
- 本機 → 雲端 **絕不**自動發生（不在使用者沒選的情況下上傳音訊）。
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
    # 第 1 波的 STT agent 在這裡加上 import（local 一定要第一個）


def build_stt(settings) -> SttAdapter:
    """依 settings.stt_provider 建立 adapter；雲端且 settings.stt_fallback_local 時回傳「失敗會退回本機」的包裝。"""
    raise NotImplementedError("第 1 波 STT agent 實作")
