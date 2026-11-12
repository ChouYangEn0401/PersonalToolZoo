"""Video Notes 的 GUI：本機 FastAPI 伺服器＋瀏覽器前端（static/）。

只聽 127.0.0.1。但瀏覽器裡任何網站都能對 127.0.0.1 發請求，所以：
- 會改變狀態的請求（POST / PUT / DELETE）必須帶 X-Video-Notes: 1 —— 跨站請求加自訂 header 需要 CORS
  預檢，而這裡不回應預檢，所以別的網站沒辦法叫它下載東西、開資料夾。
- Host 只接受 127.0.0.1 / localhost，擋 DNS rebinding。
- 讀檔、開資料夾只限輸出資料夾底下。
"""

from __future__ import annotations

import copy
import dataclasses
import os
import re
import threading
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from toolzoo import ytdlp
from toolzoo.ai import DEFAULT_MODELS, PROVIDERS, MissingKeyError, needs_key, save_key, text_modes
from toolzoo.webapp import run as run_webapp

from version import __version__
from video_notes.config import (OUTPUT_CUSTOM, OUTPUT_DATA, OUTPUT_DOWNLOADS, Settings, load_settings,
                                save_settings)
from video_notes import collection, doctor
from video_notes import deps as deps_mod
from video_notes import health as health_mod
from video_notes.adapters import render as render_mod
from video_notes.adapters import stt as stt_mod
from video_notes.adapters.llm import COMPAT, build_llm
from video_notes.errors import Remedy, ToolError, as_tool_error
from video_notes.jobs import JobManager
from video_notes.library import list_library
from video_notes.media import UPGRADE_ACTION
from video_notes.naming import Artifacts, classify, find_folder
from video_notes.pipeline import REDOABLE, JobOptions, Locks, Pipeline, _read_json
from video_notes.profiles import AUTO
from video_notes.service import environment, library

APP_NAME = "video-notes"
PORT = 8766
STATIC = Path(__file__).resolve().parent / "static"
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]

# 錯誤代碼 → HTTP 狀態（前端靠 body 的 error.reason／remedy 顯示，狀態碼只是讓工具與測試好判斷）
HTTP_STATUS = {"bad_input": 400, "unsupported_source": 400, "config_invalid": 400, "auth_required": 401,
               "auth_expired": 401, "dependency_outdated": 409, "dependency_missing": 409, "upstream_changed": 409,
               "rate_limited": 429, "network_unreachable": 503, "resource_exhausted": 503, "cancelled": 409,
               "internal_bug": 500}
# 輸出檔的 Content-Type：HTML 內嵌顯示（加嚴格 CSP）、文字內嵌、其餘（.xmind／.opml／.mm）一律下載
HTML_CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:"
INLINE_TEXT = {".md": "text/plain", ".mmd": "text/plain", ".txt": "text/plain"}
COMPAT_LABEL = "OpenAI 相容端點（Ollama、LM Studio 等）"
SOURCE_LABELS = {"yt-dlp": "yt-dlp（下載影片）", "ffmpeg": "ffmpeg", "whisper": "本機語音辨識"}


class Hub:
    """伺服器執行期間的狀態：設定、工作管理員。"""

    def __init__(self):
        self.settings = load_settings()
        self.locks = Locks.from_settings(self.settings)
        self.manager = JobManager(self._pipeline(), self.settings.parallel_jobs)
        self.lock = threading.Lock()
        # 「一鍵下載 ffmpeg／Deno」的進度（一次只跑一個）：{name, state: running/done/failed, value, detail, error}
        self.deps_job: dict = {}

    def _pipeline(self) -> Pipeline:
        return Pipeline(self.settings, library(), self.locks)

    def update(self, settings: Settings) -> None:
        with self.lock:
            save_settings(settings)
            self.settings = settings
            self.manager.pipeline = self._pipeline()   # 之後開始的工作用新設定；進行中的不受影響

    def root(self) -> Path:
        return self.settings.output_root()

    def inside_root(self, raw: str) -> Path:
        path = Path(raw).resolve()
        if not path.is_relative_to(self.root().resolve()):
            raise HTTPException(403, "只能存取輸出資料夾底下的檔案")
        return path

    def folder(self, raw: str) -> Path:
        """影片或合併的資料夾：必須在輸出資料夾底下，而且真的存在。"""
        path = self.inside_root(raw)
        if not path.is_dir():
            raise HTTPException(404, "資料夾不存在")
        return path


def safe_slug(slug: str) -> str:
    """slug 會拼進檔名（notes.<slug>.md），不允許路徑符號。"""
    if not slug or re.search(r'[\\/:*?"<>|]', slug) or ".." in slug:
        raise HTTPException(400, "方案名稱不正確")
    return slug


def tool_error(code: str, reason: str, action: str = "", kind: str = "none") -> ToolError:
    return ToolError(code, reason, remedy=Remedy(kind, action))


class CheckRequest(BaseModel):
    urls: list[str]


class DepsRequest(BaseModel):
    name: str


class JobRequest(BaseModel):
    urls: list[str]
    profile: str = AUTO
    modifiers: list[str] = []
    focus: str = ""
    preset: str = ""
    notes: bool = True
    keep_video: bool = False
    redo: dict[str, list[str]] = {}     # 網址 → 要重做的階段
    outputs: list[str] | None = None    # 除了 Markdown 之外要哪些輸出；None = 用設定裡的預設
    stt_provider: str = ""              # 這次用哪個語音辨識服務（不改存檔設定）；空白 = 用設定


class KeyRequest(BaseModel):
    provider: str
    key: str


class RefineRequest(BaseModel):
    text: str
    mode: str
    submode: str


class PathRequest(BaseModel):
    path: str


class PlanFields(BaseModel):
    profile: str = AUTO
    modifiers: list[str] = []
    focus: str = ""
    preset: str = ""
    outputs: list[str] = []


class RenderRequest(BaseModel):
    folder: str
    slug: str
    outputs: list[str]


class ReanalyzeRequest(PlanFields):
    folder: str


class CombineRequest(PlanFields):
    folders: list[str]
    slug: str = ""              # 空白 = 每支影片用「最適合」的分析（同模式優先，否則最新的）
    title: str = ""
    confirmed: bool = False


class RecombineRequest(PlanFields):
    folder: str


def _error_dict(err: ToolError | None) -> dict | None:
    if err is None:
        return None
    return {"reason": err.reason, "action": err.remedy.action, "code": err.code}


def renderer_list() -> list[dict]:
    """每種輸出：名稱、中文標籤、分組（筆記／樹狀圖／網頁）、能不能用（不能用就附原因與怎麼辦）。"""
    render_mod.load_builtin()
    out = []
    for entry in render_mod.REGISTRY.entries():
        item = {"name": entry.name, "label": entry.label, "group": "notes", "extension": "", "available": True,
                "reason": "", "action": "", "always": entry.name == "markdown"}
        try:
            obj = entry.factory()
            item["group"] = (obj.capabilities() or {}).get("group", "notes")
            item["extension"] = getattr(obj, "extension", "")
            err = obj.check()
        except Exception as exc:  # noqa: BLE001 — 一個輸出壞掉不影響其他選項
            err = as_tool_error(exc, f"render:{entry.name}", "檢查輸出格式")
        if err is not None:
            item.update(available=False, reason=err.reason, action=err.remedy.action)
        out.append(item)
    return out


def stt_list(settings: Settings) -> list[dict]:
    """每個語音辨識服務：中文標籤、本機或雲端（雲端會上傳音訊）、要不要金鑰、能不能用。"""
    stt_mod.load_builtin()
    out = []
    for entry in stt_mod.REGISTRY.entries():
        item = {"name": entry.name, "label": entry.label, "privacy": "local", "needs_key": False,
                "available": True, "reason": "", "action": ""}
        try:
            obj = entry.factory(settings)
            caps = obj.capabilities() or {}
            item["privacy"] = caps.get("privacy", "local")
            item["needs_key"] = bool(caps.get("needs_key", False))
            item["cost_hint"] = caps.get("cost_hint", "")
            err = obj.check()
        except Exception as exc:  # noqa: BLE001
            err = as_tool_error(exc, f"stt:{entry.name}", "檢查語音辨識服務")
        if err is not None:
            item.update(available=False, reason=err.reason, action=err.remedy.action)
        out.append(item)
    return out


def _env(settings: Settings) -> dict:
    """service.environment() 再加上「相容端點」這個服務（金鑰選填，寫在 .env，所以不在畫面上貼）。"""
    env = environment()
    env["keys"] = {**env["keys"], COMPAT: bool(settings.compat_base_url.strip())}
    env["keyless"] = [*env["keyless"], COMPAT]
    return env


def ytdlp_info() -> dict:
    """yt-dlp 的版本與距今天數（版本號就是發佈日期）；算不出來 days = None。"""
    ver = ytdlp.version()
    info = {"version": ver, "days": None, "level": "ok", "action": ""}
    m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", ver or "")
    if m:
        try:
            info["days"] = (date.today() - date(int(m[1]), int(m[2]), int(m[3]))).days
        except ValueError:
            return info
        if info["days"] >= doctor.YTDLP_ERROR_DAYS:
            info["level"] = "error"
        elif info["days"] >= doctor.YTDLP_WARN_DAYS:
            info["level"] = "warn"
        if info["level"] != "ok":
            info["action"] = UPGRADE_ACTION
    return info


def degraded_list() -> list[dict]:
    """health.json 裡被標成「壞掉」的項目，轉成給人看的原因與怎麼辦。"""
    try:
        entries = health_mod.entries()
    except Exception:  # noqa: BLE001 — 讀不到就當沒有，不要讓整個畫面起不來
        return []
    out = []
    for source, entry in entries.items():
        if entry.get("state") == "degraded":
            err = health_mod.HealthBook._to_error(source, entry)
            out.append({"source": source, "label": SOURCE_LABELS.get(source, source), "reason": err.reason,
                        "action": err.remedy.action, "doc": err.remedy.doc, "code": err.code})
    return out


def check_outputs(names: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """輸出名稱必須是登記過的；不認得 → 400。"""
    render_mod.load_builtin()
    unknown = [n for n in names if n not in render_mod.REGISTRY]
    if unknown:
        raise tool_error("config_invalid", f"不認得的輸出格式：{'、'.join(unknown)}", "重新整理頁面再選一次")
    return tuple(dict.fromkeys(names))


def estimate_dict(est) -> dict:
    data = asdict(est) if dataclasses.is_dataclass(est) else dict(est)
    data["text"] = (f"共 {data.get('members', 0)} 支影片，約 {data.get('input_tokens', 0):,} token，"
                    f"要呼叫 AI {data.get('calls', 0)} 次")
    return data


def pick_analysis(folder: Path, slug: str, plan) -> Path:
    """這支影片要拿哪一份分析來合併：指定的 slug → 跟這次模式相同的 → 最新的；都沒有就回「不存在的路徑」讓估計列為讀不到。"""
    art = Artifacts(folder)
    if slug:
        return art.analysis(safe_slug(slug))
    if plan.profile != AUTO and art.analysis(plan.slug()).is_file():
        return art.analysis(plan.slug())
    found = sorted(art.all_analyses(), key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0] if found else art.analysis("none")


def _finish_collection(pipeline: Pipeline, result: dict, outputs: tuple[str, ...], emit) -> dict:
    """合併完成後補上使用者勾的其他輸出（combine 已經產生的不重做）；單一格式失敗只記錄。"""
    result = dict(result)
    made = dict(result.get("outputs") or {})
    folder, analysis_file = result.get("folder"), result.get("analysis_file")
    if not result.get("notes") and result.get("notes_file"):
        try:
            result["notes"] = Path(result["notes_file"]).read_text(encoding="utf-8")
        except OSError:
            pass
    todo = [n for n in outputs if n != "markdown" and n not in made]
    errors: dict[str, str] = {}
    if todo and folder and analysis_file:
        slug = Path(analysis_file).name[len("analysis."):-len(".json")]
        emit("stage", {"stage": "outputs", "state": "running"})
        for name in todo:
            try:
                made.update({name: pipeline.render(folder, slug, [name])[name]})
            except Exception as exc:  # noqa: BLE001
                errors[name] = as_tool_error(exc, f"render:{name}", "產生輸出").reason
        emit("stage", {"stage": "outputs", "state": "failed" if len(errors) == len(todo) else "done",
                       "detail": "；".join(f"{k}：{v}" for k, v in errors.items())})
    result["outputs"] = made
    if errors:
        result["output_errors"] = errors
    return result


def create_app() -> FastAPI:
    hub = Hub()
    app = FastAPI(title="Video Notes", version=__version__)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        if host not in ("127.0.0.1", "localhost"):
            return JSONResponse({"detail": "forbidden host"}, status_code=403)
        if request.method not in ("GET", "HEAD") and request.headers.get("x-video-notes") != "1":
            return JSONResponse({"detail": "missing X-Video-Notes header"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ToolError)
    async def tool_error_handler(_request: Request, exc: ToolError):
        # 錯誤合約：前端顯示 reason 與「怎麼辦」（remedy.action），不顯示內部代碼
        return JSONResponse({"error": exc.to_dict()}, status_code=HTTP_STATUS.get(exc.code, 500))

    @app.get("/api/health")
    def health():
        return {"app": APP_NAME, "version": __version__}

    @app.get("/api/state")
    def state():
        lib = library()
        s = hub.settings
        return {
            "version": __version__,
            "settings": asdict(s),
            "env": _env(s),
            "output_root": str(s.output_root()),
            "output_choices": {
                OUTPUT_DOWNLOADS: str(Settings(output=OUTPUT_DOWNLOADS).output_root()),
                OUTPUT_DATA: str(Settings(output=OUTPUT_DATA).output_root()),
                OUTPUT_CUSTOM: s.output_custom,
            },
            "providers": PROVIDERS | {COMPAT: COMPAT_LABEL},
            "default_models": DEFAULT_MODELS | {COMPAT: ""},
            "whisper_models": WHISPER_MODELS,
            "profiles": [{"id": p.id, "name": p.name, "icon": p.icon, "description": p.description}
                         for p in lib.sorted_profiles()],
            "modifiers": [{"id": m.id, "name": m.name, "icon": m.icon, "description": m.description}
                          for m in lib.sorted_modifiers()],
            "presets": [{"id": p.id, "name": p.name, "description": p.description, "profile": p.profile,
                         "modifiers": list(p.modifiers), "focus": p.focus,
                         "outputs": list(getattr(p, "outputs", ()) or ())} for p in lib.presets.values()],
            "renderers": renderer_list(),
            "stt_providers": stt_list(s),
            "ytdlp": ytdlp_info(),
            "degraded": degraded_list(),
            "deps": deps_mod.status(),
            "deps_job": dict(hub.deps_job),
            "text_modes": {mode: list(data.submodes) for mode, data in text_modes.MODES.items()},
        }

    @app.put("/api/settings")
    def put_settings(data: dict):
        known = {f.name for f in fields(Settings)}
        incoming = {k: v for k, v in data.items() if k in known}
        merged = asdict(hub.settings) | incoming
        try:
            if "outputs" in incoming:
                merged["outputs"] = list(check_outputs(list(incoming["outputs"] or [])))
            if "stt_provider" in incoming:
                stt_mod.load_builtin()
                if incoming["stt_provider"] not in stt_mod.REGISTRY:
                    raise tool_error("config_invalid", "不認得這個語音辨識服務", "重新整理頁面再選一次")
            url = str(merged.get("compat_base_url") or "").strip()
            if url and not re.match(r"https?://", url):
                raise tool_error("config_invalid", "相容端點網址要以 http:// 或 https:// 開頭")
            merged["compat_base_url"] = url
            for key in ("parallel_jobs", "max_parallel_downloads", "combine_confirm_tokens"):
                merged[key] = max(1, int(merged[key]))
            gap = [max(0.0, float(x)) for x in merged["sleep_between_videos"]][:2]
            gap = (gap * 2) if len(gap) == 1 else (gap or [5.0, 10.0])
            merged["sleep_between_videos"] = sorted(gap)
            settings = Settings(**merged)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"設定的格式不對：{exc}") from exc
        hub.update(settings)
        return state()

    @app.post("/api/keys")
    def put_key(req: KeyRequest):
        if req.provider not in PROVIDERS:
            raise HTTPException(400, "不認得的服務")
        if not needs_key(req.provider):
            raise HTTPException(400, f"{PROVIDERS[req.provider]} 不需要金鑰")
        path = save_key(req.provider, req.key)
        return {"saved": str(path), "env": _env(hub.settings)}

    @app.post("/api/check")
    def check(req: CheckRequest):
        root, out = hub.root(), []
        for url in (u.strip() for u in req.urls):
            if not url:
                continue
            ref = classify(url)
            folder = find_folder(root, ref)
            item = {"url": url, "platform": ref.platform, "id": ref.video_id, "kind": ref.kind, "folder": "",
                    "status": None, "title": ""}
            if folder:
                record = _read_json(Artifacts(folder).info)
                item.update(folder=str(folder), status=Artifacts(folder).status(),
                            analyses=Artifacts(folder).status()["analyses"],
                            title=(record.get("video") or {}).get("title", ""),
                            auto_profile=record.get("auto_profile"))
            out.append(item)
        return out

    @app.post("/api/jobs")
    def create_jobs(req: JobRequest):
        lib = library()
        try:
            plan = lib.plan(req.profile, req.modifiers, req.focus, req.preset)
        except KeyError as exc:
            raise HTTPException(400, exc.args[0]) from exc
        outputs = check_outputs(req.outputs) if req.outputs is not None else None
        pipeline = None
        if req.stt_provider and req.stt_provider != hub.settings.stt_provider:
            stt_mod.load_builtin()
            if req.stt_provider not in stt_mod.REGISTRY:
                raise tool_error("config_invalid", "不認得這個語音辨識服務", "重新整理頁面再選一次")
            # 只這次用：複製目前的 pipeline（保留注入的假元件），換掉它的設定；不寫回存檔
            pipeline = copy.copy(hub.manager.pipeline)
            pipeline.settings = dataclasses.replace(hub.settings, stt_provider=req.stt_provider)
            if req.stt_provider != stt_mod.LOCAL and not hub.settings.stt_fallback_local:
                err = stt_mod.REGISTRY.create(req.stt_provider, pipeline.settings).check()
                if err is not None:
                    raise err
        root = hub.root()
        root.mkdir(parents=True, exist_ok=True)
        jobs = []
        for url in dict.fromkeys(u.strip() for u in req.urls if u.strip()):
            redo = frozenset(s for s in req.redo.get(url, []) if s in REDOABLE)
            options = JobOptions(plan=plan, output_root=root, redo=redo, notes=req.notes,
                                 keep_video=req.keep_video or hub.settings.keep_video,
                                 notify_url=hub.settings.notify_url, outputs=outputs)
            jobs.append(hub.manager.submit(url, options, pipeline).snapshot(with_notes=False))
        return jobs

    @app.get("/api/jobs")
    def list_jobs():
        return hub.manager.snapshots()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        snap = hub.manager.snapshot(job_id)
        if snap is None:
            raise HTTPException(404, "沒有這個工作")
        return snap

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        return {"cancelled": hub.manager.cancel(job_id)}

    @app.delete("/api/jobs/{job_id}")
    def remove_job(job_id: str):
        return {"removed": hub.manager.remove(job_id)}

    @app.get("/api/library")
    def library_list():
        """{"videos": [...], "collections": [...]}；每筆有 folder、title、notes、analyses、outputs、updated 等。"""
        return list_library(hub.root())

    @app.get("/api/note")
    def read_note(folder: str, slug: str):
        path = hub.folder(folder) / f"notes.{safe_slug(slug)}.md"
        if not path.is_file():
            raise HTTPException(404, "找不到這份筆記")
        return PlainTextResponse(path.read_text(encoding="utf-8"))

    @app.get("/api/transcript")
    def read_transcript(folder: str):
        path = Artifacts(hub.inside_root(folder)).transcript_txt
        if not path.is_file():
            raise HTTPException(404, "還沒有逐字稿")
        return PlainTextResponse(path.read_text(encoding="utf-8"))

    @app.post("/api/render")
    def render_outputs(req: RenderRequest):
        """只從已有的分析產生輸出（不呼叫 AI、不花 token）。回 {outputs: {格式: 檔名}, errors: {格式: 原因}}。"""
        folder, slug = hub.folder(req.folder), safe_slug(req.slug)
        names = check_outputs(req.outputs)
        if not names:
            raise tool_error("bad_input", "請至少選一種輸出格式")
        done: dict[str, str] = {}
        errors: dict[str, str] = {}
        for name in names:
            try:
                path = hub.manager.pipeline.render(folder, slug, [name])[name]
                done[name] = Path(path).name
            except ToolError as exc:
                if exc.source == "pipeline":      # 這支影片還沒有分析結果：整批都不能做
                    raise
                errors[name] = exc.reason + (f"（{exc.remedy.action}）" if exc.remedy.action else "")
            except Exception as exc:  # noqa: BLE001 — 一個格式失敗不影響其他格式
                errors[name] = as_tool_error(exc, f"render:{name}", "產生輸出").reason
        return {"outputs": done, "errors": errors}

    def _plan(req):
        try:
            return library().plan(req.profile, req.modifiers, req.focus, req.preset)
        except KeyError as exc:
            raise tool_error("bad_input", str(exc.args[0])) from exc

    @app.post("/api/reanalyze")
    def reanalyze(req: ReanalyzeRequest):
        """沿用逐字稿，用新的模式重新分析（會花 token）。背景工作，進度同 /api/jobs。"""
        folder = hub.folder(req.folder)
        plan = _plan(req)
        outputs = check_outputs(req.outputs)
        if not Artifacts(folder).transcript_json.exists():
            raise tool_error("bad_input", "這個資料夾沒有逐字稿，無法重新分析", "先對這支影片執行一次完整處理（下載＋辨識）")
        pipeline = hub.manager.pipeline
        record = _read_json(Artifacts(folder).info)
        title = (record.get("video") or {}).get("title") or folder.name
        options = JobOptions(plan=plan, output_root=hub.root(), outputs=outputs)
        job = hub.manager.submit_task(
            "reanalyze", record.get("url") or str(folder), options, title=title, folder=str(folder),
            runner=lambda emit, cancel: pipeline.reanalyze(folder, plan, outputs=outputs, emit=emit, cancel=cancel))
        return job.snapshot(with_notes=False)

    def _members(req: CombineRequest, plan) -> list:
        folders = list(dict.fromkeys(req.folders))
        if len(folders) < 2:
            raise tool_error("bad_input", "合併至少要選兩支影片", "回筆記庫多勾幾支")
        return [collection.Member(folder=f, analysis=pick_analysis(f, req.slug, plan))
                for f in (hub.folder(raw) for raw in folders)]

    @app.post("/api/combine/estimate")
    def combine_estimate(req: CombineRequest):
        plan = _plan(req)
        members = _members(req, plan)
        return estimate_dict(collection.estimate(members, hub.settings))

    @app.post("/api/combine")
    def combine(req: CombineRequest):
        plan = _plan(req)
        outputs = check_outputs(req.outputs)
        members = _members(req, plan)
        est = estimate_dict(collection.estimate(members, hub.settings))
        if est.get("needs_confirm") and not req.confirmed:
            error = {"code": "needs_confirm", "reason": "這次合併要處理的內容比較多，需要你確認", "retryable": False,
                     "remedy": {"kind": "needs_owner", "action": est["text"] + "。確定要做再按一次", "doc": ""},
                     "detail": "", "source": "collection"}
            return JSONResponse({"error": error, "estimate": est}, status_code=409)
        pipeline = hub.manager.pipeline
        root = hub.root()
        title = req.title.strip()

        def run(emit, cancel):
            result = collection.combine(
                members, plan=plan, settings=pipeline.settings, library=pipeline.library,
                llm_factory=pipeline.llm_factory, output_root=root, title=title, lock=hub.locks.llm,
                emit=emit, cancel=cancel)
            return _finish_collection(pipeline, result, outputs, emit)

        options = JobOptions(plan=plan, output_root=root, outputs=outputs)
        label = f"合併 {len(members)} 支影片"
        job = hub.manager.submit_task("combine", label, options, run, title=title or label)
        return job.snapshot(with_notes=False)

    @app.post("/api/recombine")
    def recombine(req: RecombineRequest):
        """合併資料夾換個模式再合併一次（成員沿用 collection.json 記的）。"""
        folder = hub.folder(req.folder)
        fn = getattr(collection, "recombine", None)
        if fn is None:
            raise HTTPException(501, "這個版本還不支援「換模式再合併」")
        plan = _plan(req)
        outputs = check_outputs(req.outputs)
        pipeline = hub.manager.pipeline
        options = JobOptions(plan=plan, output_root=hub.root(), outputs=outputs)

        def run(emit, cancel):
            result = fn(folder, plan=plan, settings=pipeline.settings, library=pipeline.library,
                        llm_factory=pipeline.llm_factory, lock=hub.locks.llm, emit=emit, cancel=cancel)
            return _finish_collection(pipeline, result, outputs, emit)

        job = hub.manager.submit_task("combine", "換模式再合併", options, run, title=folder.name, folder=str(folder))
        return job.snapshot(with_notes=False)

    @app.get("/api/output")
    def read_output(folder: str, name: str):
        """讀 outputs 資料夾底下已經存在的檔（檔名必須是那個資料夾裡真的有的檔，不接受路徑）。"""
        art = Artifacts(hub.folder(folder))
        path = {p.name: p for p in art.all_outputs()}.get(name)
        if path is None:
            raise HTTPException(404, "找不到這個輸出檔")
        headers = {"X-Content-Type-Options": "nosniff"}
        ext = path.suffix.lower()
        if ext in (".html", ".htm"):
            headers["Content-Security-Policy"] = HTML_CSP     # 內容來自網路影片的文字：不准連外、不准載入東西
            return FileResponse(path, media_type="text/html; charset=utf-8", headers=headers)
        if ext in INLINE_TEXT:
            return FileResponse(path, media_type=INLINE_TEXT[ext] + "; charset=utf-8", headers=headers)
        return FileResponse(path, media_type="application/octet-stream", filename=path.name, headers=headers)

    @app.get("/api/deps")
    def deps_status():
        """ffmpeg／Deno 找不找得到、在哪、怎麼手動裝，以及一鍵下載的進度。不連網、不執行任何程式。"""
        return {"items": deps_mod.status(), "job": dict(hub.deps_job)}

    @app.post("/api/deps/install")
    def deps_install(req: DepsRequest):
        """使用者在 GUI 頂端的提醒按「一鍵下載」：背景從官方下載、核對 SHA-256、放到 data\\bin\\。"""
        if req.name not in deps_mod.COMPONENTS:
            raise tool_error("bad_input", f"不認得的元件：{req.name}")
        with hub.lock:
            if hub.deps_job.get("state") == "running":
                raise tool_error("rate_limited", "已經有一個下載在進行中，等它結束再試")
            hub.deps_job = {"name": req.name, "state": "running", "value": 0.0, "detail": "準備下載…", "error": None}

        def progress(value: float, detail: str) -> None:
            hub.deps_job.update(value=round(value, 3), detail=detail)

        def run() -> None:
            try:
                path = deps_mod.install(req.name, on_progress=progress)
                hub.deps_job.update(state="done", value=1.0, detail=f"安裝完成：{path}")
                hub.manager.pipeline.ffmpeg = None    # 下一個工作重新找 ffmpeg
            except ToolError as err:
                hub.deps_job.update(state="failed", error=err.to_dict(), detail=err.reason)
            except Exception as exc:  # noqa: BLE001 —— 背景執行緒：轉成錯誤合約顯示在畫面上
                err = as_tool_error(exc, "deps", "下載")
                hub.deps_job.update(state="failed", error=err.to_dict(), detail=err.reason)

        threading.Thread(target=run, name=f"deps-{req.name}", daemon=True).start()
        return {"job": dict(hub.deps_job)}

    @app.post("/api/health/recheck")
    def health_recheck():
        """使用者按「重新檢查」：清掉「已標記壞掉」的記錄，重跑自我檢查。"""
        health_mod.clear()
        return {"checks": doctor.run_checks(hub.settings), "degraded": degraded_list(), "ytdlp": ytdlp_info()}

    @app.post("/api/open")
    def open_folder(req: PathRequest):
        path = hub.inside_root(req.path)
        if not path.exists():
            raise HTTPException(404, "資料夾不存在")
        os.startfile(path)  # noqa: S606 — 本機 GUI 的「開啟資料夾」按鈕
        return {"ok": True}

    @app.post("/api/refine")
    def refine(req: RefineRequest):
        """用 Better Prompt 的轉換模式二次加工筆記（同一個模式庫：libs/toolzoo/ai/text_modes.py）。"""
        s = hub.settings
        try:
            llm = build_llm(s)     # openai-compat 也能用
        except (MissingKeyError, ToolError) as exc:
            raise HTTPException(400, str(exc)) from exc
        if req.mode not in text_modes.MODES:
            raise HTTPException(400, "不認得的模式")
        system, user = text_modes.build_messages(req.mode, req.submode, req.text)

        def generate():
            try:
                with hub.locks.llm:   # 跟處理中的影片共用同一把鎖，一次一個 AI 請求
                    yield from llm.stream(system, user, temperature=0.5)
            except Exception as exc:  # noqa: BLE001 — 錯誤直接顯示在加工結果裡
                yield f"\n\n❌ {exc}"

        return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.state.hub = hub
    return app


def run_gui() -> None:
    run_webapp(create_app(), name=APP_NAME, title=f"Video Notes v{__version__}", port=PORT)
