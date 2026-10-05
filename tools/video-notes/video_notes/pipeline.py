"""一支影片的完整流程：影片資訊 → 下載 → 抽音訊 → 語音辨識 → AI 筆記 → 通知。

每個階段開始前先看產出檔在不在：
- 在，而且沒被要求重做、上游也沒有重做 → 沿用（省時間、省 API 費用）
- 被要求重做，或上游重新產生過 → 重做（例如重新下載後，音訊與逐字稿一定跟著重做）

要不要重做由呼叫端決定：GUI 先用 Artifacts.status() 顯示「已有：…」讓使用者勾選，
CLI 在互動模式下逐項詢問，或用 --reuse / --redo 參數指定。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from toolzoo import ytdlp
from toolzoo.ai import LLM

from video_notes import media
from video_notes.config import Settings, key_files
from video_notes.naming import Artifacts, VideoRef, classify, find_folder, new_folder
from video_notes.notify import post_result
from video_notes.profiles import AUTO, Plan, PromptLibrary
from video_notes.summarize import NoteWriter, VideoContext
from video_notes.transcribe import Cancelled, Transcriber, Transcript

STAGES = ("info", "download", "audio", "transcribe", "notes", "notify")
REDOABLE = ("download", "transcribe", "notes")

Event = Callable[[str, dict], None]   # (事件名稱, 內容)


@dataclass
class Locks:
    """多個工作共用的節流：下載可以並行，GPU 一次一支，LLM 一次一個請求。"""

    download: threading.Semaphore = field(default_factory=lambda: threading.Semaphore(3))
    transcribe: threading.Semaphore = field(default_factory=lambda: threading.Semaphore(1))
    llm: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class JobOptions:
    plan: Plan
    output_root: Path
    redo: frozenset[str] = frozenset()
    notes: bool = True                 # False：只下載＋轉錄
    keep_video: bool = False
    notify_url: str = ""


class Pipeline:
    def __init__(self, settings: Settings, library: PromptLibrary, locks: Locks | None = None,
                 llm_factory: Callable[[Settings], object] | None = None):
        self.settings = settings
        self.library = library
        self.locks = locks or Locks()
        # 可以注入：測試換成假的 LLM，其他程式也可以換成自己的實作（只要有 stream()）
        self.llm_factory = llm_factory or (
            lambda s: LLM(s.provider, s.model or None, key_files=key_files()))
        self.ffmpeg = ytdlp.find_ffmpeg()

    # ------------------------------------------------------------------ 公開介面
    def run(self, url: str, opts: JobOptions, emit: Event | None = None,
            cancel: threading.Event | None = None) -> dict:
        emit = emit or (lambda _name, _data: None)
        cancel = cancel or threading.Event()
        ref = classify(url)
        started = time.time()
        fresh: set[str] = set()   # 這次重新產生的階段

        def stage(name: str, state: str, **extra) -> None:
            emit("stage", {"stage": name, "state": state, **extra})

        def check() -> None:
            if cancel.is_set():
                raise Cancelled()

        # 1. 影片資訊（決定資料夾名稱；資料夾已存在就不用連網）
        stage("info", "running")
        folder = find_folder(opts.output_root, ref)
        record = _read_json(Artifacts(folder).info) if folder else {}
        info = record.get("video") or {}
        if not info or "download" in opts.redo:
            info = media.fetch_info(url, self.ffmpeg, self.settings.cookies_from_browser)
        if folder is None:
            folder = new_folder(opts.output_root, ref, info.get("title") or ref.video_id)
            folder.mkdir(parents=True, exist_ok=True)
        art = Artifacts(folder)
        record.update({"url": url, "platform": ref.platform, "id": ref.video_id, "kind": ref.kind, "video": info})
        _write_json(art.info, record)
        stage("info", "done", title=info.get("title", ""), folder=str(folder), kind=ref.kind)
        check()

        # 2. 下載
        if art.media() is not None and "download" not in opts.redo:
            stage("download", "reused")
        else:
            stage("download", "running")
            for old in folder.glob("media.*"):   # 使用者要求重新下載：換掉舊檔
                old.unlink()
            with self.locks.download:
                media.download(url, folder, keep_video=opts.keep_video, ffmpeg=self.ffmpeg,
                               cookies=self.settings.cookies_from_browser,
                               on_progress=lambda f, d: emit("progress", {"stage": "download", "value": f, "detail": d}),
                               cancel=cancel)
            if art.media() is None:
                raise RuntimeError("下載結束了，但資料夾裡找不到影音檔")
            fresh.add("download")
            stage("download", "done")
        check()

        # 3. 抽音訊
        if art.audio.exists() and not fresh:
            stage("audio", "reused")
        else:
            stage("audio", "running")
            media.extract_audio(art.media(), art.audio, self.ffmpeg)
            fresh.add("audio")
            stage("audio", "done")
        check()

        # 4. 語音辨識（GPU 一次一支）
        if art.transcript_json.exists() and not fresh and "transcribe" not in opts.redo:
            transcript = Transcript.load(art.transcript_json)
            stage("transcribe", "reused")
        else:
            stage("transcribe", "waiting")
            with self.locks.transcribe:
                check()
                stage("transcribe", "running")
                transcriber = Transcriber(self.settings.whisper_model, self.settings.whisper_device,
                                          self.settings.language, self.settings.traditional)
                emit("log", {"message": f"語音辨識：{self.settings.whisper_model}（{transcriber.device}）"})
                transcript = transcriber.transcribe(
                    art.audio, cancel=cancel,
                    on_progress=lambda f, t: emit("progress", {"stage": "transcribe", "value": f, "detail": t}),
                )
            transcript.save(art.transcript_txt, art.transcript_srt, art.transcript_json)
            fresh.add("transcribe")
            stage("transcribe", "done", language=transcript.language)
        check()

        result = {
            "url": url, "platform": ref.platform, "id": ref.video_id, "kind": ref.kind,
            "title": info.get("title", ""), "folder": str(folder),
            "files": {"info": str(art.info), "media": str(art.media()), "audio": str(art.audio),
                      "transcript": str(art.transcript_txt), "srt": str(art.transcript_srt)},
            "language": transcript.language,
        }

        # 5. AI 筆記（LLM 一次一個請求）
        if opts.notes:
            out = self._notes(ref, info, record, art, transcript, opts, fresh, emit, cancel, stage)
            result.update(out)
            result["files"]["notes"] = out["notes_file"]
            _write_json(art.info, record)

        # 6. 通知其他程式（socket 模式）
        if opts.notify_url:
            stage("notify", "running")
            ok, message = post_result(opts.notify_url, result)
            stage("notify", "done" if ok else "failed", detail=message)
            result["notify"] = {"ok": ok, "message": message}

        record.setdefault("history", []).append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "seconds": round(time.time() - started, 1),
            "redone": sorted(fresh),
            "notes": result.get("notes_file", ""),
        })
        _write_json(art.info, record)
        return result

    # ------------------------------------------------------------------ 筆記
    def _notes(self, ref: VideoRef, info: dict, record: dict, art: Artifacts, transcript: Transcript,
               opts: JobOptions, fresh: set[str], emit: Event, cancel: threading.Event, stage) -> dict:
        plan = opts.plan
        ctx = VideoContext.from_info(ref.url, ref.kind, info)
        writer = None

        def get_writer() -> NoteWriter:
            nonlocal writer
            if writer is None:
                llm = self.llm_factory(self.settings)
                writer = NoteWriter(llm, self.library, lock=self.locks.llm,
                                    long_chars=self.settings.long_transcript_chars)
                emit("log", {"message": f"AI：{llm.provider} / {llm.model}"})
            return writer

        profile_id, reason = plan.profile, ""
        if plan.profile == AUTO:
            cached = record.get("auto_profile")
            if cached in self.library.profiles and "transcribe" not in fresh:
                profile_id, reason = cached, record.get("auto_reason", "")
            else:
                stage("notes", "running", detail="判斷影片類型…")
                profile_id, reason = get_writer().classify(transcript, ctx, cancel)
                record["auto_profile"], record["auto_reason"] = profile_id, reason
            emit("log", {"message": f"自動判斷：{self.library.profiles[profile_id].name}　{reason}"})

        path = art.notes(plan.slug(profile_id))
        if path.exists() and not fresh and "notes" not in opts.redo:
            stage("notes", "reused")
            notes = path.read_text(encoding="utf-8")
        else:
            stage("notes", "waiting")
            notes = get_writer().write(
                plan, profile_id, transcript, ctx, cancel=cancel,
                on_status=lambda msg: stage("notes", "running", detail=msg),
                on_token=lambda tok: emit("token", {"text": tok}),
            )
            path.write_text(notes, encoding="utf-8")
            stage("notes", "done")
        return {"notes": notes, "notes_file": str(path), "profile": profile_id, "profile_reason": reason}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
