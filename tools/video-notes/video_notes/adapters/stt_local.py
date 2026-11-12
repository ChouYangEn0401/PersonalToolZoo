"""本機 Whisper（faster-whisper）：把 transcribe.Transcriber 包成 SttAdapter，行為完全不變。

模型、GPU／CPU、繁體轉換都由 Transcriber 處理；這裡只做 adapter 要求的固定入口與錯誤轉換。
faster_whisper 只在真的辨識時才載入（check() 只用 find_spec 看有沒有裝）。
"""

from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

from video_notes.adapters import stt
from video_notes.errors import Remedy, ToolError, internal, short
from video_notes.transcribe import Cancelled, Transcriber, Transcript

NAME = stt.LOCAL
SOURCE = "stt:local"


class LocalStt:
    name = NAME

    def __init__(self, settings):
        self.settings = settings
        self.model = settings.whisper_model

    def capabilities(self) -> dict:
        return {"needs_network": False, "needs_key": False, "privacy": "local", "languages": "auto",
                "max_audio_seconds": None, "cost_hint": "免費（用這台電腦的 GPU／CPU，第一次需下載模型）"}

    def check(self) -> ToolError | None:
        if importlib.util.find_spec("faster_whisper") is None:
            return ToolError("dependency_missing", "沒有安裝 faster-whisper（本機語音辨識）", source=SOURCE,
                             remedy=Remedy("auto_fixable", "重建工具環境：scripts\\setup-venv.ps1 video-notes -Force"))
        return None

    def describe(self) -> str:
        device = self.settings.whisper_device
        label = {"cuda": "GPU", "cpu": "CPU"}.get(device, "自動選 GPU／CPU")
        return f"{self.model}（{label}）"

    def transcribe(self, wav: Path, *, language: str | None = None, on_progress=None,
                   cancel: threading.Event | None = None) -> Transcript:
        error = self.check()
        if error:
            raise error
        lang = language if language is not None else self.settings.language
        try:
            transcriber = Transcriber(self.settings.whisper_model, self.settings.whisper_device, lang or "auto",
                                      self.settings.traditional)
            return transcriber.transcribe(wav, on_progress, cancel)
        except Cancelled:
            raise
        except ToolError:
            raise
        except ImportError as exc:
            raise ToolError("dependency_missing", "本機語音辨識需要的套件載入失敗", detail=short(exc), source=SOURCE,
                            remedy=Remedy("auto_fixable", "重建工具環境：scripts\\setup-venv.ps1 video-notes -Force")) from exc
        except MemoryError as exc:
            raise _oom(exc) from exc
        except (ConnectionError, TimeoutError) as exc:
            raise ToolError("network_unreachable", "下載 Whisper 模型時連不上網路", detail=short(exc), source=SOURCE,
                            remedy=Remedy("none", "連上網路後重試（模型只需下載一次）")) from exc
        except Exception as exc:  # noqa: BLE001
            if "out of memory" in str(exc).lower():
                raise _oom(exc) from exc
            raise internal(exc, SOURCE, "本機語音辨識") from exc


def _oom(exc: BaseException) -> ToolError:
    return ToolError("resource_exhausted", "語音辨識記憶體不足", detail=short(exc), source=SOURCE,
                     remedy=Remedy("needs_config", "設定改用較小的 Whisper 模型（small／base）或改用 CPU"))


stt.REGISTRY.register(NAME, lambda settings: LocalStt(settings), label="本機 Whisper（預設）", order=0)
