"""雲端語音辨識共用的零件：長音訊切段、分段辨識後時間碼接回、錯誤轉成 ToolError。

為什麼要切段（上限調查於 2026-11-12，官方文件）：
- OpenAI 語音辨識：單檔 25 MB 上限；格式 flac/mp3/mp4/mpeg/mpga/m4a/ogg/wav/webm；文件沒有寫時間長度上限。
  只有 whisper-1 能用 response_format=verbose_json 取得「分段時間碼」；gpt-4o-transcribe 只回純文字。
  https://developers.openai.com/api/docs/guides/speech-to-text
- Gemini：官方 OpenAI 相容端點只有 chat completions，音訊用 input_audio（範例是 wav；mp3 也可以），
  整個請求（含 base64）內嵌上限約 20 MB；原生 API 單次提示最長 9.5 小時、支援 WAV/MP3/AIFF/AAC/OGG/FLAC 等。
  相容端點的文件沒有 /audio/transcriptions，所以用 chat completions 加「請逐字轉寫」的提示。
  https://aistudio.google.com/docs/openai 、 https://aistudio.google.com/docs/audio

做法：ffmpeg 把 16 kHz 單聲道 wav 重新編碼成 mp3（32 kbps ≈ 4 KB/s，1 小時 ≈ 14 MB），
每 chunk_seconds 秒切一段（兩家的預設都遠低於上限），逐段送出，再把每段的時間碼加上段落起點接成一份 Transcript。

時間碼的取捨：
- 服務有回分段時間碼（whisper-1）→ 用服務的，加上段落起點。
- 只回純文字（gpt-4o-transcribe、Gemini）→ 把這一段的文字依標點切成句子，依字數比例把這一段的時間分配給各句
  （起點、終點由字數推算，不是真正的對齊；誤差在一段之內，段落越短越準，所以預設 5～10 分鐘一段）。
- 切點用固定秒數、不找靜音：句子可能被切成兩半，換來的是流程簡單、時間碼不會漂移（每段起點 = 序號 × 段長，
  mp3 重新編碼的邊界誤差在幾十毫秒內，不累積）。

暫存檔放在 wav 旁邊的 stt-chunks-* 資料夾（影片資料夾內），不論成功失敗都會刪掉。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from video_notes.errors import Remedy, ToolError, redact, short
from video_notes.transcribe import Cancelled, Segment, Transcript, _opencc

Progress = Callable[[float, str], None]


@dataclass
class ChunkResult:
    """一段音訊的辨識結果。segments 的時間碼是「相對於這一段開頭」；沒有就留 None（由本模組依字數分配）。"""
    text: str
    segments: list[Segment] | None = None
    language: str | None = None


# ---------------------------------------------------------------- 切段

def wav_duration(wav: Path) -> float:
    try:
        with wave.open(str(wav), "rb") as fh:
            return fh.getnframes() / float(fh.getframerate() or 16000)
    except (wave.Error, EOFError, OSError) as exc:
        raise ToolError("bad_input", "讀不了音訊檔（不是正常的 wav）", detail=short(exc),
                        source="stt", remedy=Remedy("none", "重新處理這支影片（會重新抽音訊）")) from exc


def split_audio(wav: Path, workdir: Path, chunk_seconds: int, ffmpeg: str | None) -> list[tuple[float, Path]]:
    """回傳 [(段落起點秒數, 檔案)]。壓成 mp3（32 kbps）讓每段遠小於服務的大小上限。"""
    if not ffmpeg:
        raise ToolError("dependency_missing", "找不到 ffmpeg，無法切分音訊", source="stt",
                        remedy=Remedy("needs_config", "安裝 ffmpeg 並加入 PATH，或在設定裡指定 ffmpeg.exe 的位置"))
    pattern = workdir / "chunk_%04d.mp3"
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), "-vn", "-ac", "1", "-ar", "16000",
           "-c:a", "libmp3lame", "-b:a", "32k", "-f", "segment", "-segment_time", str(int(chunk_seconds)),
           "-reset_timestamps", "1", str(pattern)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        raise ToolError("dependency_missing", "ffmpeg 無法執行", detail=short(exc), source="stt",
                        remedy=Remedy("needs_config", "確認 ffmpeg 安裝正常")) from exc
    files = sorted(workdir.glob("chunk_*.mp3"))
    if result.returncode != 0 or not files:
        raise ToolError("bad_input", "ffmpeg 切分音訊失敗", detail=(result.stderr or "")[-300:], source="stt",
                        remedy=Remedy("none", "確認影片有聲音；重新處理這支影片"))
    return [(i * float(chunk_seconds), f) for i, f in enumerate(files)]


_SENTENCE = re.compile(r"[^。！？!?；;…\n]+(?:[。！？!?；;…]+|\n|$)|[。！？!?；;…]+")


def spread_text(text: str, start: float, end: float) -> list[Segment]:
    """純文字 → 依句子與字數比例分配 [start, end] 的分段（見檔頭的取捨說明）。"""
    text = " ".join(text.split())
    if not text:
        return []
    pieces = [p.strip() for p in _SENTENCE.findall(text) if p.strip()]
    if not pieces:
        pieces = [text]
    # 英文用「. 」結尾：再依「句點＋空白」細分
    refined: list[str] = []
    for p in pieces:
        refined.extend(s.strip() for s in re.split(r"(?<=[.])\s+", p) if s.strip())
    pieces = refined or pieces
    total = sum(len(p) for p in pieces) or 1
    span = max(end - start, 0.0)
    out, cursor = [], start
    for i, p in enumerate(pieces):
        seg_end = end if i == len(pieces) - 1 else cursor + span * len(p) / total
        out.append(Segment(round(cursor, 2), round(seg_end, 2), p))
        cursor = seg_end
    return out


# ---------------------------------------------------------------- 語言

_LANG_NAMES = {"chinese": "zh", "mandarin": "zh", "english": "en", "japanese": "ja", "korean": "ko",
               "french": "fr", "german": "de", "spanish": "es", "russian": "ru", "portuguese": "pt",
               "italian": "it", "vietnamese": "vi", "thai": "th", "indonesian": "id", "cantonese": "yue"}


def normalize_language(raw: str | None, text: str = "") -> str:
    """服務回的語言（"chinese"、"zh"、"zh-TW"…）→ 短代碼；沒有就用文字的文字種類猜（猜不出來 "und"）。"""
    if raw:
        low = raw.strip().lower()
        if low in _LANG_NAMES:
            return _LANG_NAMES[low]
        if re.fullmatch(r"[a-z]{2,3}([-_][a-z0-9]+)?", low):
            return low.split("-")[0].split("_")[0]
    sample = text[:2000]
    if not sample:
        return "und"
    if re.search(r"[぀-ヿ]", sample):
        return "ja"
    if re.search(r"[가-힯]", sample):
        return "ko"
    cjk = len(re.findall(r"[一-鿿]", sample))
    if cjk >= 0.2 * len(sample):
        return "zh"
    return "en" if re.search(r"[A-Za-z]", sample) else "und"


# ---------------------------------------------------------------- 主流程

def transcribe_chunked(wav: Path, *, call: Callable[[Path, str | None], ChunkResult], chunk_seconds: int,
                       traditional: bool = True, language: str | None = None,
                       on_progress: Progress | None = None, cancel: threading.Event | None = None,
                       ffmpeg: str | None = None) -> Transcript:
    """切段 → 逐段 call(檔案, 語言) → 時間碼接回 → 中文轉繁體。call 自己負責把失敗轉成 ToolError。"""
    if ffmpeg is None:
        from toolzoo.ytdlp import find_ffmpeg

        ffmpeg = find_ffmpeg()
    duration = wav_duration(wav)
    workdir = Path(tempfile.mkdtemp(prefix="stt-chunks-", dir=str(wav.parent)))
    try:
        chunks = split_audio(wav, workdir, chunk_seconds, ffmpeg)
        segments: list[Segment] = []
        detected: str | None = None
        for i, (offset, path) in enumerate(chunks):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            result = call(path, language)
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            span_end = min(offset + chunk_seconds, duration) if i < len(chunks) - 1 else max(duration, offset)
            if result.segments:
                part = [Segment(round(offset + s.start, 2), round(offset + s.end, 2), s.text.strip())
                        for s in result.segments if s.text.strip()]
            else:
                part = spread_text(result.text, offset, span_end)
            segments.extend(part)
            detected = detected or result.language
            if on_progress:
                on_progress(min((i + 1) / len(chunks), 1.0), part[-1].text if part else "")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    lang = normalize_language(detected or language, " ".join(s.text for s in segments))
    if traditional and lang.startswith("zh"):
        converter = _opencc()
        if converter:
            segments = [Segment(s.start, s.end, converter.convert(s.text)) for s in segments]
    return Transcript(lang, round(duration, 2), segments)


# ---------------------------------------------------------------- 錯誤轉換

def _body_code(exc: BaseException) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            return str(err.get("code") or err.get("type") or err.get("status") or "")
    return ""


def to_tool_error(exc: BaseException, *, source: str, service: str, key: str = "", key_hint: str = "",
                  billing: str = "") -> ToolError:
    """SDK／網路例外 → ToolError。只看 status_code、類別名稱與訊息文字（不 import 任何 SDK）。
    key 有給就把它從訊息裡抹掉（ToolError 本身也會抹常見金鑰格式）。"""
    if isinstance(exc, ToolError):
        return exc
    detail = short(exc)
    if key:
        detail = detail.replace(key, "***")
    status = getattr(exc, "status_code", None)
    code = _body_code(exc)
    name = type(exc).__name__
    lower = f"{exc}".lower()
    set_key = key_hint or "在專案的 .env 設定金鑰"

    if code in ("insufficient_quota", "billing_not_active") or "exceeded your current quota" in lower:
        return ToolError("resource_exhausted", f"{service} 帳戶額度用完", retryable=False, detail=detail, source=source,
                         remedy=Remedy("needs_owner", f"到 {billing or service + ' 的帳務頁'} 儲值，或在設定改用本機語音辨識"))
    if status == 401 or "invalid api key" in lower or "incorrect api key" in lower or "api key not valid" in lower:
        return ToolError("auth_expired", f"{service} 的金鑰無效或已被撤銷", detail=detail, source=source,
                         remedy=Remedy("needs_config", f"重新產生金鑰後，{set_key}"))
    if status == 403:
        return ToolError("auth_required", f"{service} 拒絕這個請求（金鑰沒有此模型的權限）", detail=detail, source=source,
                         remedy=Remedy("needs_config", "確認帳號有開通這個模型，或在設定換一個語音辨識模型"))
    if status == 404:
        return ToolError("config_invalid", f"{service} 找不到這個語音辨識模型", detail=detail, source=source,
                         remedy=Remedy("needs_config", "在設定檢查模型名稱（stt_model），或留空用預設"))
    if status == 413:
        return ToolError("bad_input", f"{service} 說音訊段落太大", detail=detail, source=source,
                         remedy=Remedy("needs_owner", "把切段秒數調小（這是程式問題，請回報維護者）"))
    if status == 429:
        return ToolError("rate_limited", f"{service} 限流中", detail=detail, source=source,
                         remedy=Remedy("none", "稍後再試；或在設定改用本機語音辨識"))
    if status in (400, 415, 422):
        return ToolError("bad_input", f"{service} 不接受這段音訊或參數", detail=detail, source=source,
                         remedy=Remedy("needs_owner", "把工作紀錄交給維護者；可先改用本機語音辨識"))
    if status is not None and status >= 500:
        return ToolError("network_unreachable", f"{service} 伺服器暫時出錯（HTTP {status}）", detail=detail,
                         source=source, remedy=Remedy("none", "稍後再試"))
    if name in ("APIConnectionError", "APITimeoutError", "ConnectError", "ConnectTimeout", "ReadTimeout",
                "TimeoutError") or isinstance(exc, (ConnectionError, TimeoutError)):
        return ToolError("network_unreachable", f"連不上 {service}（網路問題或逾時）", detail=detail, source=source,
                         remedy=Remedy("none", "檢查網路後重試；或在設定改用本機語音辨識"))
    if isinstance(exc, ImportError):
        return ToolError("dependency_missing", f"缺少呼叫 {service} 需要的套件", detail=detail, source=source,
                         remedy=Remedy("needs_update", "重建這個工具的環境（scripts\\setup-venv.ps1 video-notes -Force）"))
    return ToolError("internal_bug", f"呼叫 {service} 時發生未預期的錯誤", detail=redact(detail), source=source,
                     remedy=Remedy("needs_owner", "把工作紀錄交給維護者"))
