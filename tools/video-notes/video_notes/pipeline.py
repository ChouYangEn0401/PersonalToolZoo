"""一支影片的完整流程：影片資訊 → 下載 → 抽音訊 → 語音辨識 → 分析（analysis.json）→ 輸出 → 通知。

v2 的資料流：來源 adapter → 語音辨識 adapter → **Analyzer 產生 analysis.<slug>.json（存起來）** →
輸出 adapter（markdown 一律產生；其他格式依 JobOptions.outputs）。AI 只在「分析」那一步花 token，
換輸出格式（`render()`）只讀 analysis，不呼叫 AI。

每個階段開始前先看產出檔在不在：
- 在，而且沒被要求重做、上游也沒有重做 → 沿用（省時間、省 API 費用）
- 被要求重做，或上游重新產生過 → 重做（例如重新下載後，音訊與逐字稿一定跟著重做）
- 舊資料夾（只有 notes.<slug>.md、沒有 analysis）：只要 Markdown 就沿用舊筆記；要其他輸出才重新分析

要不要重做由呼叫端決定：GUI 先用 Artifacts.status() 顯示「已有：…」讓使用者勾選，
CLI 在互動模式下逐項詢問，或用 --reuse / --redo 參數指定。

給 GUI／CLI 用的另外兩個入口：reanalyze()（沿用逐字稿重新分析，不下載）、render()（只讀 analysis 轉格式）。
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from toolzoo import ytdlp
from toolzoo.ai import LLM

from video_notes import analysis as analysis_mod
from video_notes import media
from video_notes.adapters import render as render_mod
from video_notes.analyze import Analyzer
from video_notes.config import Settings
from video_notes.errors import Remedy, ToolError, as_tool_error
from video_notes.naming import Artifacts, VideoRef, classify, find_folder, new_folder
from video_notes.notify import post_result
from video_notes.profiles import AUTO, Plan, PromptLibrary
from video_notes.summarize import VideoContext
from video_notes.transcribe import Cancelled, Transcript

STAGES = ("info", "download", "audio", "transcribe", "notes", "outputs", "notify")
REDOABLE = ("download", "transcribe", "notes")

Event = Callable[[str, dict], None]   # (事件名稱, 內容)


@dataclass
class Locks:
    """多個工作共用的節流：下載可以並行，GPU 一次一支，LLM 一次一個請求。"""

    download: threading.Semaphore = field(default_factory=lambda: threading.Semaphore(2))
    transcribe: threading.Semaphore = field(default_factory=lambda: threading.Semaphore(1))
    llm: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Locks":
        """同時下載幾支由 settings.max_parallel_downloads 決定（至少 1）。"""
        return cls(download=threading.Semaphore(max(1, int(settings.max_parallel_downloads))))


@dataclass
class JobOptions:
    plan: Plan
    output_root: Path
    redo: frozenset[str] = frozenset()
    notes: bool = True                 # False：只下載＋轉錄
    keep_video: bool = False
    notify_url: str = ""
    # 除了 markdown（一律產生）之外還要哪些輸出（adapters/render.py 的名稱）；None = 用 settings.outputs
    outputs: tuple[str, ...] | None = None


def _default_source(url: str, settings: Settings):
    from video_notes.adapters import source

    return source.for_url(url, settings)


def _default_stt(settings: Settings):
    from video_notes.adapters import stt

    return stt.build_stt(settings)


class Pipeline:
    def __init__(self, settings: Settings, library: PromptLibrary, locks: Locks | None = None,
                 llm_factory: Callable[[Settings], object] | None = None,
                 source_factory: Callable[[str, Settings], object] | None = None,
                 stt_factory: Callable[[Settings], object] | None = None):
        self.settings = settings
        self.library = library
        self.locks = locks or Locks.from_settings(settings)
        # 都可以注入：測試換成假的，其他程式也可以換成自己的實作（Protocol 見 adapters/）
        self.llm_factory = llm_factory or (lambda s: LLM(s.provider, s.model or None))
        self.source_factory = source_factory or (lambda url, s: _default_source(url, s))
        self.stt_factory = stt_factory or (lambda s: _default_stt(s))
        self.ffmpeg = ytdlp.find_ffmpeg()

    # ------------------------------------------------------------------ 公開介面
    def run(self, url: str, opts: JobOptions, emit: Event | None = None,
            cancel: threading.Event | None = None) -> dict:
        emit = emit or (lambda _name, _data: None)
        cancel = cancel or threading.Event()
        ref = classify(url)
        started = time.time()
        fresh: set[str] = set()   # 這次重新產生的階段
        source = None

        def get_source():
            nonlocal source
            if source is None:
                source = self.source_factory(url, self.settings)
            return source

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
            info = get_source().fetch_info(url)
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
                get_source().download(
                    url, folder, keep_video=opts.keep_video, cancel=cancel,
                    on_progress=lambda f, d: emit("progress", {"stage": "download", "value": f, "detail": d}))
            if art.media() is None:
                raise ToolError("internal_bug", "下載結束了，但資料夾裡找不到影音檔",
                                remedy=Remedy("needs_owner", "把工作紀錄交給維護者"))
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
                stt = self.stt_factory(self.settings)
                emit("log", {"message": f"語音辨識：{stt.describe()}"})
                language = None if self.settings.language in ("", "auto") else self.settings.language
                transcript = stt.transcribe(
                    art.audio, language=language, cancel=cancel,
                    on_progress=lambda f, t: emit("progress", {"stage": "transcribe", "value": f, "detail": t}),
                )
            # 辨識服務退回本機時，之後的分析要標 stt_fallback_local；記在 info.json 讓沿用逐字稿時也看得到
            fell_back = bool(getattr(stt, "fell_back", False))
            record["stt"] = {"adapter": getattr(stt, "name", ""), "model": getattr(stt, "model", ""),
                             "fell_back": fell_back}
            if fell_back:
                emit("log", {"message": "雲端語音辨識失敗，已退回本機辨識"})
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

        # 5. 分析 + 輸出（LLM 一次一個請求）
        if opts.notes:
            out = self._notes(ref, info, record, art, transcript, opts, fresh, emit, cancel, stage)
            result.update(out)
            result["files"]["notes"] = out["notes_file"]
            if out.get("analysis_file"):
                result["files"]["analysis"] = out["analysis_file"]
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

    def reanalyze(self, folder: Path | str, plan: Plan, *, outputs: tuple[str, ...] | None = None,
                  emit: Event | None = None, cancel: threading.Event | None = None) -> dict:
        """沿用這個資料夾的逐字稿重新分析（不下載、不重新辨識），重寫 analysis 與各輸出。"""
        emit = emit or (lambda _name, _data: None)
        cancel = cancel or threading.Event()
        folder = Path(folder)
        art = Artifacts(folder)
        if not art.transcript_json.exists():
            raise ToolError("bad_input", "這個資料夾沒有逐字稿，無法重新分析", source="pipeline",
                            remedy=Remedy("auto_fixable", "先對這支影片執行一次完整處理（下載＋辨識）"))
        record = _read_json(art.info)
        info = record.get("video") or {}
        match = re.search(r"\[(video|short)-([^\]]+)\]$", folder.name)
        ref = VideoRef(url=record.get("url", ""), platform=record.get("platform") or "other",
                       video_id=record.get("id") or (match.group(2) if match else folder.name),
                       kind=record.get("kind") or (match.group(1) if match else "video"))
        transcript = Transcript.load(art.transcript_json)
        opts = JobOptions(plan=plan, output_root=folder.parent, redo=frozenset({"notes"}), outputs=outputs)

        def stage(name: str, state: str, **extra) -> None:
            emit("stage", {"stage": name, "state": state, **extra})

        out = self._notes(ref, info, record, art, transcript, opts, set(), emit, cancel, stage)
        _write_json(art.info, record)
        return {"url": ref.url, "platform": ref.platform, "id": ref.video_id, "kind": ref.kind,
                "title": info.get("title", ""), "folder": str(folder), "language": transcript.language, **out}

    def render(self, folder: Path | str, slug: str, renderers) -> dict[str, str]:
        """把已有的 analysis 轉成指定格式（不呼叫 AI）。analysis 不存在 → ToolError，提示先重新分析。"""
        art = Artifacts(Path(folder))
        path = art.analysis(slug)
        if not path.exists():
            raise ToolError("bad_input", "這支影片還沒有分析結果，無法轉成這些格式", source="pipeline",
                            remedy=Remedy("auto_fixable", "先對這支影片選「重新分析」，再產生其他格式"))
        data = analysis_mod.load(path)
        ctx = self._render_ctx(data)
        return {name: str(self._render_one(art, slug, data, name, ctx)) for name in dict.fromkeys(renderers)}

    # ------------------------------------------------------------------ 輸出
    def _render_ctx(self, data: dict) -> render_mod.RenderContext:
        mode = data.get("mode") or {}
        profile = self.library.profiles.get(mode.get("profile", ""))
        mods = [self.library.modifiers[m].name for m in mode.get("modifiers") or [] if m in self.library.modifiers]
        name = f"{profile.icon} {profile.name}" if profile else mode.get("profile", "")
        return render_mod.RenderContext(profile_name=name, modifier_names=mods)

    @staticmethod
    def _renderer(name: str):
        from video_notes.adapters import render_markdown  # noqa: F401 — 登記 "markdown"（不靠其他人的 render 模組存在）

        if name not in render_mod.REGISTRY:
            render_mod.load_builtin()
        return render_mod.REGISTRY.create(name)

    def _render_one(self, art: Artifacts, slug: str, data: dict, name: str, ctx: render_mod.RenderContext) -> Path:
        renderer = self._renderer(name)
        content = renderer.render(data, ctx)
        path = art.output(slug, name, renderer.extension)
        path.parent.mkdir(parents=True, exist_ok=True)
        if renderer.binary:
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def _extra_outputs(self, opts: JobOptions) -> list[str]:
        names = self.settings.outputs if opts.outputs is None else opts.outputs
        return [n for n in dict.fromkeys(names or ()) if n and n != "markdown"]

    # ------------------------------------------------------------------ 分析
    def _notes(self, ref: VideoRef, info: dict, record: dict, art: Artifacts, transcript: Transcript,
               opts: JobOptions, fresh: set[str], emit: Event, cancel: threading.Event, stage) -> dict:
        plan = opts.plan
        ctx = VideoContext.from_info(ref.url, ref.kind, info)
        analyzer = None

        def get_analyzer() -> Analyzer:
            nonlocal analyzer
            if analyzer is None:
                llm = self.llm_factory(self.settings)
                analyzer = Analyzer(llm, self.library, self.settings, lock=self.locks.llm)
                emit("log", {"message": f"AI：{llm.provider} / {llm.model}"})
            return analyzer

        profile_id, reason = plan.profile, ""
        if plan.profile == AUTO:
            cached = record.get("auto_profile")
            if cached in self.library.profiles and "transcribe" not in fresh:
                profile_id, reason = cached, record.get("auto_reason", "")
            else:
                stage("notes", "running", detail="判斷影片類型…")
                profile_id, reason = get_analyzer().classify(transcript, ctx, cancel)
                record["auto_profile"], record["auto_reason"] = profile_id, reason
            emit("log", {"message": f"自動判斷：{self.library.profiles[profile_id].name}　{reason}"})

        slug = plan.slug(profile_id)
        a_path = art.analysis(slug)
        md_path = art.output(slug, "markdown", ".md")
        extra = self._extra_outputs(opts)
        redo = "notes" in opts.redo or bool(fresh)

        data = None
        if a_path.exists() and not redo:
            try:
                data = analysis_mod.load(a_path)
            except ToolError as exc:
                if exc.code != "bad_input":     # 只有壞掉的檔案才重做；版本太新等要讓使用者看到
                    raise
                emit("log", {"message": f"分析結果檔讀不了，重新分析：{exc.reason}"})

        fallback_md = ""
        if data is None:
            if md_path.exists() and not a_path.exists() and not redo and not extra:
                # 舊資料夾：只有 Markdown 筆記而且只要 Markdown → 沿用，不花 token
                stage("notes", "reused")
                return {"notes": md_path.read_text(encoding="utf-8"), "notes_file": str(md_path), "profile": profile_id,
                        "profile_reason": reason, "analysis_file": "", "outputs": {"markdown": str(md_path)}}
            stage("notes", "waiting")
            stt_info = record.get("stt") or {"adapter": "local", "model": ""}
            outcome = get_analyzer().analyze(
                plan, profile_id, transcript, ctx, ref=ref, folder_name=art.folder.name, stt=stt_info, cancel=cancel,
                on_status=lambda msg: stage("notes", "running", detail=msg),
                on_token=lambda tok: emit("token", {"text": tok}),
            )
            data, fallback_md = outcome.analysis, outcome.fallback_markdown
            analysis_mod.save(a_path, data)
            cost = data.get("cost") or {}
            emit("log", {"message": f"分析完成（{'估計' if cost.get('estimated') else '實際'} token："
                                    f"輸入 {cost.get('input_tokens', 0)}／輸出 {cost.get('output_tokens', 0)}）"})
            stage("notes", "done")
            made_new = True
        else:
            stage("notes", "reused")
            made_new = False

        # Markdown 筆記：新分析一定重寫；沿用分析時只在檔案不見才補
        rctx = self._render_ctx(data)
        if made_new or not md_path.exists():
            if fallback_md:     # 降級：用舊寫法產生的筆記文字，標頭仍由程式產生
                from video_notes.adapters import render_markdown

                md_path.write_text("\n".join(render_markdown.header(data, rctx)) + "\n" + fallback_md,
                                   encoding="utf-8")
            else:
                self._render_one(art, slug, data, "markdown", rctx)
        outputs = {"markdown": str(md_path)}
        errors: dict[str, str] = {}

        # 其他輸出：單一格式失敗只記錄，不讓整支影片失敗
        if extra:
            stage("outputs", "running")
            for name in extra:
                if cancel.is_set():
                    raise Cancelled()
                try:
                    outputs[name] = str(self._render_one(art, slug, data, name, rctx))
                except Cancelled:
                    raise
                except Exception as exc:    # noqa: BLE001
                    err = as_tool_error(exc, source=f"render:{name}", where=f"產生「{name}」輸出")
                    errors[name] = f"{err.reason}（{err.detail}）" if err.detail else err.reason
                    emit("log", {"message": f"輸出「{name}」失敗：{err}"})
            stage("outputs", "failed" if len(errors) == len(extra) else "done",
                  detail="；".join(f"{k}：{v}" for k, v in errors.items()))

        result = {"notes": md_path.read_text(encoding="utf-8"), "notes_file": str(md_path), "profile": profile_id,
                  "profile_reason": reason, "analysis_file": str(a_path), "outputs": outputs}
        if errors:
            result["output_errors"] = errors
        return result


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
