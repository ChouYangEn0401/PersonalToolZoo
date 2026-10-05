"""下載佇列：同時下載 N 支、進度、取消、重試、完成後寫進紀錄。

取消 = 在 yt-dlp 的進度回呼裡丟 DownloadCancelled；已下載的部分留在 .part 檔，
按「重試」會用同樣的設定重新開始，yt-dlp 會從 .part 接著下載（舊版的斷點續傳）。
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from video_downloader.config import Settings
from video_downloader.history import History
from video_downloader.options import DownloadRequest, build_options, explain_error, output_folder

PP_NAMES = {
    "Merger": "合併影像與聲音", "ExtractAudio": "轉換音訊格式", "EmbedSubtitle": "嵌入字幕",
    "FFmpegEmbedSubtitle": "嵌入字幕", "Metadata": "寫入影片資訊", "FFmpegMetadata": "寫入影片資訊",
    "EmbedThumbnail": "嵌入縮圖", "VideoConvertor": "轉檔", "FixupM3u8": "修正串流格式",
    "FFmpegFixupM3u8": "修正串流格式", "MoveFiles": "整理檔案",
}


@dataclass
class DownloadJob:
    id: str
    request: DownloadRequest
    settings: Settings
    status: str = "queued"            # queued / downloading / processing / done / failed / cancelled
    progress: float = 0.0
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    eta: int | None = None
    stage: str = ""
    title: str = ""
    filepath: str = ""
    folder: str = ""
    error: str = ""
    created: float = field(default_factory=time.time)
    finished: float = 0.0
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    future: object = field(default=None, repr=False)

    def snapshot(self) -> dict:
        return {
            "id": self.id, "url": self.request.url, "title": self.title or self.request.title or self.request.url,
            "status": self.status, "progress": round(self.progress, 4), "downloaded": self.downloaded,
            "total": self.total, "speed": self.speed, "eta": self.eta, "stage": self.stage,
            "filepath": self.filepath, "folder": self.folder, "error": self.error,
            "preset": self.request.preset or self.settings.preset,
            "created": self.created, "finished": self.finished,
        }


class DownloadManager:
    def __init__(self, get_settings: Callable[[], Settings], history: History, workers: int = 2,
                 on_update: Callable[[DownloadJob, str], None] | None = None):
        self._get_settings = get_settings
        self.history = history
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="download")
        self._jobs: dict[str, DownloadJob] = {}
        self._lock = threading.Lock()
        self._on_update = on_update

    # ------------------------------------------------------------------ 對外
    def submit(self, request: DownloadRequest) -> DownloadJob:
        settings = replace(self._get_settings())   # 這個工作用「送出當下」的設定
        job = DownloadJob(uuid.uuid4().hex[:10], request, settings, title=request.title,
                          folder=str(output_folder(settings, request)))
        with self._lock:
            self._jobs[job.id] = job
        job.future = self._pool.submit(self._run, job)
        return job

    def retry(self, job_id: str) -> DownloadJob | None:
        job = self.get(job_id)
        if job is None or job.status in ("queued", "downloading", "processing"):
            return None
        self.remove(job_id)
        return self.submit(job.request)

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job and job.status in ("queued", "downloading", "processing"):
            job.cancel.set()
            return True
        return False

    def remove(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status not in ("queued", "downloading", "processing"):
                del self._jobs[job_id]
                return True
        return False

    def get(self, job_id: str) -> DownloadJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshots(self) -> list[dict]:
        with self._lock:
            return [j.snapshot() for j in sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)]

    def known_paths(self) -> set[str]:
        with self._lock:
            return {p for j in self._jobs.values() for p in (j.filepath, j.folder) if p}

    def wait(self, jobs: list[DownloadJob]) -> None:
        for job in jobs:
            job.future.result()

    def shutdown(self) -> None:
        for job in list(self._jobs.values()):
            job.cancel.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ 執行
    def _notify(self, job: DownloadJob, event: str) -> None:
        if self._on_update:
            self._on_update(job, event)

    def _progress_hook(self, job: DownloadJob, d: dict) -> None:
        from yt_dlp.utils import DownloadCancelled

        if job.cancel.is_set():
            raise DownloadCancelled()
        info = d.get("info_dict") or {}
        if info.get("title") and (not job.title or job.title == job.request.url):
            job.title = info["title"]
        if d.get("status") == "downloading":
            job.status = "downloading"
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            job.downloaded, job.total = int(d.get("downloaded_bytes") or 0), int(total)
            if total:
                job.progress = min(job.downloaded / total, 1.0)
            elif d.get("fragment_count"):
                job.progress = (d.get("fragment_index") or 0) / d["fragment_count"]
            job.speed = float(d.get("speed") or 0)
            job.eta = d.get("eta")
            part = "聲音" if info.get("vcodec") == "none" else "影像" if info.get("acodec") == "none" else ""
            frag = f"（第 {d['fragment_index']}/{d['fragment_count']} 段）" if d.get("fragment_count") else ""
            job.stage = f"下載{part}{frag}"
            self._notify(job, "progress")
        elif d.get("status") == "finished":
            job.progress = 1.0
            job.stage = "下載完成"

    def _pp_hook(self, job: DownloadJob, d: dict) -> None:
        if d.get("status") == "started":
            job.status = "processing"
            name = d.get("postprocessor", "")
            job.stage = PP_NAMES.get(name, f"處理中（{name}）")
            self._notify(job, "processing")

    def _run(self, job: DownloadJob) -> None:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadCancelled, DownloadError

        if job.cancel.is_set():
            job.status, job.finished = "cancelled", time.time()
            return
        job.status = "downloading"
        job.stage = "連線中…"
        self._notify(job, "start")
        try:
            opts = build_options(job.settings, job.request)
            opts["progress_hooks"] = [lambda d: self._progress_hook(job, d)]
            opts["postprocessor_hooks"] = [lambda d: self._pp_hook(job, d)]
            opts["post_hooks"] = [lambda path: setattr(job, "filepath", str(path))]
            Path(job.folder).mkdir(parents=True, exist_ok=True)
            with YoutubeDL(opts) as ydl:
                ydl.download([job.request.url])
            job.status, job.stage, job.progress = "done", "完成", 1.0
        except DownloadCancelled:
            job.status, job.stage = "cancelled", "已取消（已下載的部分保留，按重試會接著下載）"
        except DownloadError as exc:
            job.status, job.error = "failed", explain_error(str(exc))
        except Exception as exc:  # noqa: BLE001 — 任何錯誤都要顯示，不能讓執行緒默默死掉
            job.status, job.error = "failed", explain_error(f"{type(exc).__name__}: {exc}")
        finally:
            job.finished = time.time()
            if job.status in ("done", "failed"):
                size = Path(job.filepath).stat().st_size if job.filepath and Path(job.filepath).exists() else 0
                self.history.add({
                    "url": job.request.url, "title": job.title or job.request.url, "path": job.filepath,
                    "folder": job.folder, "size": size, "status": job.status, "error": job.error,
                    "preset": job.request.preset or job.settings.preset,
                    "finished": datetime.now().isoformat(timespec="seconds"),
                    "request": asdict(job.request),
                })
            self._notify(job, "finished")
