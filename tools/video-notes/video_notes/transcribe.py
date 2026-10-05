"""語音辨識（faster-whisper）與逐字稿格式。

GPU：CTranslate2 需要 CUDA 12 的 cuBLAS 與 cuDNN 9。requirements.txt 裝的 nvidia-cublas-cu12 /
nvidia-cudnn-cu12 會把 DLL 放在 site-packages/nvidia/*/bin，但那不在 Windows 的 DLL 搜尋路徑上，
所以載入模型前要先 add_dll_directory。舊版是 import torch 間接把 DLL 帶進來（為了印一行
「GPU 可用」裝了 2.5 GB 的 torch），現在不需要了。DLL 不齊時自動改用 CPU（int8）。

打包成 exe 時不把這些 DLL（約 2 GB）塞進去，exe 會到這些地方找：
環境變數 VIDEO_NOTES_CUDA_DIR、repo 裡這個工具的 .venv（exe 在 <repo>\\dist\\video-notes\\ 時）、系統 PATH。
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

CUDA_DLLS = ("cublas64_12.dll", "cublasLt64_12.dll", "cudnn_ops64_9.dll", "cudnn_cnn64_9.dll")

# 中文時給 Whisper 的提示：讓它傾向輸出繁體字並加標點（Whisper 中文常常整段沒有標點）
ZH_PROMPT = "以下是繁體中文的影片逐字稿，句子之間有標點符號。"

_dll_dirs_added = False


def _dll_search_bases() -> list[Path]:
    bases = [Path(p) for p in sys.path]
    custom = os.environ.get("VIDEO_NOTES_CUDA_DIR", "").strip()
    if custom:
        bases.append(Path(custom))
    if getattr(sys, "frozen", False):
        # exe 在 <repo>\dist\video-notes\ 的話，借用 repo 裡這個工具 venv 的 nvidia DLL
        exe_dir = Path(sys.executable).resolve().parent
        bases.append(exe_dir.parent.parent / "tools" / "video-notes" / ".venv" / "Lib" / "site-packages")
    return bases


def _add_dll_dir(path: Path) -> None:
    try:
        os.add_dll_directory(str(path))
        os.environ["PATH"] = str(path) + os.pathsep + os.environ.get("PATH", "")
    except OSError:
        pass


def _add_cuda_dll_dirs() -> None:
    global _dll_dirs_added
    if _dll_dirs_added or sys.platform != "win32":
        return
    _dll_dirs_added = True
    for base in _dll_search_bases():
        if any((base / dll).is_file() for dll in CUDA_DLLS):   # 直接放 DLL 的資料夾
            _add_dll_dir(base)
        nvidia = base / "nvidia"
        if nvidia.is_dir():
            for bin_dir in nvidia.glob("*/bin"):
                _add_dll_dir(bin_dir)


def cuda_status() -> tuple[bool, str]:
    """(能不能用 GPU, 給使用者看的說明)。"""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() <= 0:
            return False, "沒有偵測到 NVIDIA 顯示卡，使用 CPU"
    except Exception as exc:  # noqa: BLE001
        return False, f"CTranslate2 無法使用 CUDA（{exc}），使用 CPU"
    _add_cuda_dll_dirs()
    if sys.platform == "win32":
        for dll in CUDA_DLLS:
            try:
                ctypes.WinDLL(dll)
            except OSError:
                return False, f"有 NVIDIA 顯示卡但找不到 {dll}，使用 CPU（見 README 的 GPU 段落）"
    return True, "使用 GPU（CUDA）"


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    language: str
    duration: float
    segments: list[Segment]

    # ---- 格式 ----
    def paragraphs(self, gap: float = 1.6, max_chars: int = 350) -> list[tuple[float, str]]:
        """依停頓切段落：(段落開始秒數, 段落文字)。"""
        out: list[tuple[float, str]] = []
        start, buf, last_end = 0.0, [], None
        for seg in self.segments:
            text = seg.text.strip()
            if not text:
                continue
            too_long = sum(len(t) for t in buf) >= max_chars
            if buf and ((last_end is not None and seg.start - last_end > gap) or too_long):
                out.append((start, " ".join(buf)))
                buf = []
            if not buf:
                start = seg.start
            buf.append(text)
            last_end = seg.end
        if buf:
            out.append((start, " ".join(buf)))
        return out

    def plain_text(self) -> str:
        return "\n\n".join(text for _, text in self.paragraphs())

    def timed_text(self) -> str:
        return "\n\n".join(f"[{clock(t)}] {text}" for t, text in self.paragraphs())

    def to_srt(self) -> str:
        lines = []
        for i, seg in enumerate((s for s in self.segments if s.text.strip()), start=1):
            lines += [str(i), f"{srt_time(seg.start)} --> {srt_time(seg.end)}", seg.text.strip(), ""]
        return "\n".join(lines)

    def to_txt(self) -> str:
        """一行一句、段落之間空一行：給人看的逐字稿。"""
        blocks, current, last_end = [], [], None
        for seg in self.segments:
            text = seg.text.strip()
            if not text:
                continue
            if current and last_end is not None and seg.start - last_end > 1.6:
                blocks.append("\n".join(current))
                current = []
            current.append(text)
            last_end = seg.end
        if current:
            blocks.append("\n".join(current))
        return "\n\n".join(blocks) + "\n"

    # ---- 存讀 ----
    def save(self, txt: Path, srt: Path, js: Path) -> None:
        txt.write_text(self.to_txt(), encoding="utf-8")
        srt.write_text(self.to_srt(), encoding="utf-8")
        js.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, js: Path) -> "Transcript":
        raw = json.loads(js.read_text(encoding="utf-8"))
        return cls(raw["language"], raw["duration"], [Segment(**s) for s in raw["segments"]])


def clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"


class Cancelled(Exception):
    pass


class Transcriber:
    """同一個模型只載入一次，多個工作共用（模型很大，重複載入既慢又吃顯示記憶體）。"""

    _models: dict[tuple[str, str], object] = {}
    _load_lock = threading.Lock()

    def __init__(self, model_size: str = "medium", device: str = "auto", language: str = "auto",
                 traditional: bool = True):
        self.model_size = model_size
        self.language = None if language in ("", "auto") else language
        self.traditional = traditional
        if device == "auto":
            device = "cuda" if cuda_status()[0] else "cpu"
        elif device == "cuda":
            _add_cuda_dll_dirs()
        self.device = device

    def _model(self):
        key = (self.model_size, self.device)
        with self._load_lock:
            if key not in self._models:
                _add_cuda_dll_dirs()
                from faster_whisper import WhisperModel

                compute = "float16" if self.device == "cuda" else "int8"
                self._models[key] = WhisperModel(self.model_size, device=self.device, compute_type=compute)
            return self._models[key]

    def transcribe(self, wav: Path, on_progress: Callable[[float, str], None] | None = None,
                   cancel: threading.Event | None = None) -> Transcript:
        from faster_whisper import decode_audio

        model = self._model()
        audio = decode_audio(str(wav), sampling_rate=16000)  # 解碼一次，語言判斷和辨識共用
        language = self.language
        if language is None:
            # 先判斷語言，才知道要不要加中文提示（中文提示套在英文影片上會讓它亂翻譯）。
            # 開 VAD：片頭音樂不會被拿來判斷語言
            language = model.detect_language(audio, vad_filter=True)[0]
        prompt = ZH_PROMPT if language.startswith("zh") else None
        segments_iter, info = model.transcribe(
            audio, language=language, vad_filter=True, initial_prompt=prompt, beam_size=5,
        )
        converter = _opencc() if (self.traditional and language.startswith("zh")) else None
        segments: list[Segment] = []
        for seg in segments_iter:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            text = converter.convert(seg.text) if converter else seg.text
            segments.append(Segment(round(seg.start, 2), round(seg.end, 2), text.strip()))
            if on_progress and info.duration:
                on_progress(min(seg.end / info.duration, 1.0), text.strip())
        return Transcript(language, round(info.duration, 2), segments)


def _opencc():
    try:
        from opencc import OpenCC

        return OpenCC("s2twp")  # 簡體 → 繁體（台灣用詞）
    except Exception:  # noqa: BLE001 — 沒裝 opencc 就保持 Whisper 的原樣輸出
        return None
