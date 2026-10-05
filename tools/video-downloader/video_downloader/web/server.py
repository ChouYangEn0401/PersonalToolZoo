"""Video Downloader 的 GUI：本機 FastAPI 伺服器＋瀏覽器前端（static/）。

安全措施同 Video Notes：只聽 127.0.0.1、寫入請求要帶 X-Video-Downloader: 1（擋其他網站跨站呼叫）、
檢查 Host（擋 DNS rebinding）、「開啟資料夾 / 檔案」只限輸出資料夾或這次下載過的檔案。

書籤小工具會開 http://127.0.0.1:8765/?add=<目前頁面網址>，前端把網址放進輸入框並自動解析
（解析不會下載任何東西，要使用者按下載才會開始）。
"""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, fields
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from toolzoo import ytdlp
from toolzoo.webapp import run as run_webapp

from version import __version__
from video_downloader.config import Settings, load_settings, save_settings, user_dir
from video_downloader.history import History
from video_downloader.manager import DownloadManager
from video_downloader.options import DownloadRequest
from video_downloader.presets import PRESETS
from video_downloader.probe import probe

APP_NAME = "video-downloader"
PORT = 8765
STATIC = Path(__file__).resolve().parent / "static"


class ProbeRequest(BaseModel):
    urls: list[str]
    headers: dict[str, str] = {}


class Item(BaseModel):
    url: str
    preset: str = ""
    custom_format: str = ""
    filename: str = ""
    subfolder: str = ""
    playlist_items: str = ""
    title: str = ""


class DownloadsRequest(BaseModel):
    items: list[Item]
    headers: dict[str, str] = {}


class OpenRequest(BaseModel):
    path: str
    reveal: bool = False      # True：在檔案總管中選取這個檔案


def environment(settings: Settings) -> dict:
    ffmpeg = ytdlp.find_ffmpeg(settings.ffmpeg_path)
    return {"ffmpeg": ffmpeg or "", "js_runtimes": ytdlp.find_js_runtimes(), "yt_dlp": ytdlp.version()}


def create_app() -> FastAPI:
    app = FastAPI(title="Video Downloader", version=__version__)
    state = {"settings": load_settings()}
    history = History(user_dir() / "history.json")
    manager = DownloadManager(lambda: state["settings"], history, state["settings"].concurrent_downloads)
    probe_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="probe")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        if host not in ("127.0.0.1", "localhost"):
            return JSONResponse({"detail": "forbidden host"}, status_code=403)
        if request.method not in ("GET", "HEAD") and request.headers.get("x-video-downloader") != "1":
            return JSONResponse({"detail": "missing X-Video-Downloader header"}, status_code=403)
        return await call_next(request)

    def allowed(raw: str) -> Path:
        path = Path(raw).resolve()
        root = state["settings"].output_root().resolve()
        known = {str(Path(p).resolve()) for p in manager.known_paths()}
        known |= {str(Path(h[k]).resolve()) for h in history.items() for k in ("path", "folder") if h.get(k)}
        if not (path.is_relative_to(root) or str(path) in known):
            raise HTTPException(403, "只能開啟下載資料夾或下載過的檔案")
        return path

    @app.get("/api/health")
    def health():
        return {"app": APP_NAME, "version": __version__}

    @app.get("/api/state")
    def get_state():
        s = state["settings"]
        return {
            "version": __version__, "settings": asdict(s), "output_root": str(s.output_root()),
            "env": environment(s),
            "presets": [{"id": p.id, "name": p.name, "description": p.description} for p in PRESETS.values()],
        }

    @app.put("/api/settings")
    def put_settings(data: dict):
        known = {f.name for f in fields(Settings)}
        try:
            settings = Settings(**(asdict(state["settings"]) | {k: v for k, v in data.items() if k in known}))
        except TypeError as exc:
            raise HTTPException(400, str(exc)) from exc
        save_settings(settings)
        state["settings"] = settings
        return get_state()

    @app.post("/api/probe")
    def do_probe(req: ProbeRequest):
        urls = [u.strip() for u in req.urls if u.strip()]
        return list(probe_pool.map(lambda u: probe(u, state["settings"], req.headers), urls))

    @app.post("/api/downloads")
    def add_downloads(req: DownloadsRequest):
        jobs = []
        for item in req.items:
            if not item.url.strip():
                continue
            if (item.preset or state["settings"].preset) == "custom" and not (item.custom_format or state["settings"].custom_format):
                raise HTTPException(400, "選了自訂格式，但沒有填 format 字串")
            request = DownloadRequest(**item.model_dump(), headers=req.headers)
            jobs.append(manager.submit(request).snapshot())
        return jobs

    @app.get("/api/downloads")
    def list_downloads():
        return manager.snapshots()

    @app.post("/api/downloads/{job_id}/cancel")
    def cancel(job_id: str):
        return {"cancelled": manager.cancel(job_id)}

    @app.post("/api/downloads/{job_id}/retry")
    def retry(job_id: str):
        job = manager.retry(job_id)
        if job is None:
            raise HTTPException(400, "這個工作還在進行中，或已經不存在")
        return job.snapshot()

    @app.delete("/api/downloads/{job_id}")
    def remove(job_id: str):
        return {"removed": manager.remove(job_id)}

    @app.get("/api/history")
    def get_history():
        return history.items()

    @app.delete("/api/history")
    def clear_history():
        history.clear()
        return {"ok": True}

    @app.post("/api/open")
    def open_path(req: OpenRequest):
        path = allowed(req.path)
        if not path.exists():
            raise HTTPException(404, "檔案或資料夾已經不在了")
        if req.reveal and path.is_file():
            subprocess.Popen(["explorer", "/select,", str(path)])  # noqa: S603,S607 — 本機 GUI 的按鈕
        else:
            os.startfile(path)  # noqa: S606
        return {"ok": True}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.state.manager = manager
    app.state.settings = state
    return app


def run_gui() -> None:
    run_webapp(create_app(), name=APP_NAME, title=f"Video Downloader v{__version__}", port=PORT)
