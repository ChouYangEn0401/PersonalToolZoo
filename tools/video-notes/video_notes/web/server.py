"""Video Notes 的 GUI：本機 FastAPI 伺服器＋瀏覽器前端（static/）。

只聽 127.0.0.1。但瀏覽器裡任何網站都能對 127.0.0.1 發請求，所以：
- 會改變狀態的請求（POST / PUT / DELETE）必須帶 X-Video-Notes: 1 —— 跨站請求加自訂 header 需要 CORS
  預檢，而這裡不回應預檢，所以別的網站沒辦法叫它下載東西、開資料夾。
- Host 只接受 127.0.0.1 / localhost，擋 DNS rebinding。
- 讀檔、開資料夾只限輸出資料夾底下。
"""

from __future__ import annotations

import os
import threading
from dataclasses import asdict, fields
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from toolzoo.ai import DEFAULT_MODELS, LLM, PROVIDERS, MissingKeyError, needs_key, save_key, text_modes
from toolzoo.webapp import run as run_webapp

from version import __version__
from video_notes.config import (OUTPUT_CUSTOM, OUTPUT_DATA, OUTPUT_DOWNLOADS, Settings, app_dir, key_files,
                                load_settings, save_settings)
from video_notes.jobs import JobManager
from video_notes.naming import Artifacts, classify, find_folder
from video_notes.pipeline import REDOABLE, JobOptions, Locks, Pipeline, _read_json
from video_notes.profiles import AUTO
from video_notes.service import environment, library

APP_NAME = "video-notes"
PORT = 8766
STATIC = Path(__file__).resolve().parent / "static"
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]


class Hub:
    """伺服器執行期間的狀態：設定、工作管理員。"""

    def __init__(self):
        self.settings = load_settings()
        self.locks = Locks()
        self.manager = JobManager(self._pipeline(), self.settings.parallel_jobs)
        self.lock = threading.Lock()

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


class CheckRequest(BaseModel):
    urls: list[str]


class JobRequest(BaseModel):
    urls: list[str]
    profile: str = AUTO
    modifiers: list[str] = []
    focus: str = ""
    preset: str = ""
    notes: bool = True
    keep_video: bool = False
    redo: dict[str, list[str]] = {}     # 網址 → 要重做的階段


class KeyRequest(BaseModel):
    provider: str
    key: str


class RefineRequest(BaseModel):
    text: str
    mode: str
    submode: str


class PathRequest(BaseModel):
    path: str


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
            "env": environment(),
            "output_root": str(s.output_root()),
            "output_choices": {
                OUTPUT_DOWNLOADS: str(Settings(output=OUTPUT_DOWNLOADS).output_root()),
                OUTPUT_DATA: str(app_dir() / "data"),
                OUTPUT_CUSTOM: s.output_custom,
            },
            "providers": PROVIDERS,
            "default_models": DEFAULT_MODELS,
            "whisper_models": WHISPER_MODELS,
            "profiles": [{"id": p.id, "name": p.name, "icon": p.icon, "description": p.description}
                         for p in lib.sorted_profiles()],
            "modifiers": [{"id": m.id, "name": m.name, "icon": m.icon, "description": m.description}
                          for m in lib.sorted_modifiers()],
            "presets": [{"id": p.id, "name": p.name, "description": p.description, "profile": p.profile,
                         "modifiers": list(p.modifiers), "focus": p.focus} for p in lib.presets.values()],
            "text_modes": {mode: list(data.submodes) for mode, data in text_modes.MODES.items()},
        }

    @app.put("/api/settings")
    def put_settings(data: dict):
        known = {f.name for f in fields(Settings)}
        merged = asdict(hub.settings) | {k: v for k, v in data.items() if k in known}
        try:
            settings = Settings(**merged)
        except TypeError as exc:
            raise HTTPException(400, str(exc)) from exc
        hub.update(settings)
        return state()

    @app.post("/api/keys")
    def put_key(req: KeyRequest):
        if req.provider not in PROVIDERS:
            raise HTTPException(400, "不認得的服務")
        if not needs_key(req.provider):
            raise HTTPException(400, f"{PROVIDERS[req.provider]} 不需要金鑰")
        path = save_key(req.provider, req.key)
        return {"saved": str(path), "env": environment()}

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
        root = hub.root()
        root.mkdir(parents=True, exist_ok=True)
        jobs = []
        for url in dict.fromkeys(u.strip() for u in req.urls if u.strip()):
            redo = frozenset(s for s in req.redo.get(url, []) if s in REDOABLE)
            options = JobOptions(plan=plan, output_root=root, redo=redo, notes=req.notes,
                                 keep_video=req.keep_video or hub.settings.keep_video,
                                 notify_url=hub.settings.notify_url)
            jobs.append(hub.manager.submit(url, options).snapshot(with_notes=False))
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
        root, items = hub.root(), []
        if root.is_dir():
            for folder in root.iterdir():
                art = Artifacts(folder)
                if not art.info.is_file():
                    continue
                record = _read_json(art.info)
                status = art.status()
                items.append({
                    "folder": str(folder), "url": record.get("url", ""), "kind": record.get("kind", ""),
                    "title": (record.get("video") or {}).get("title") or folder.name,
                    "notes": status["notes"], "transcript": status["transcript"],
                    "updated": art.info.stat().st_mtime,
                })
        return sorted(items, key=lambda x: x["updated"], reverse=True)

    @app.get("/api/note")
    def read_note(folder: str, slug: str):
        path = hub.inside_root(folder) / f"notes.{slug}.md"
        if not path.is_file():
            raise HTTPException(404, "找不到這份筆記")
        return PlainTextResponse(path.read_text(encoding="utf-8"))

    @app.get("/api/transcript")
    def read_transcript(folder: str):
        path = Artifacts(hub.inside_root(folder)).transcript_txt
        if not path.is_file():
            raise HTTPException(404, "還沒有逐字稿")
        return PlainTextResponse(path.read_text(encoding="utf-8"))

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
            llm = LLM(s.provider, s.model or None, key_files=key_files())
        except MissingKeyError as exc:
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
