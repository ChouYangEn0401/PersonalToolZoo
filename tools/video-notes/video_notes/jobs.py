"""工作管理：同時處理多支影片（GUI 與 CLI 批次共用）。

每支影片是一個 Job，在執行緒池裡跑完整流程。並行的程度由 pipeline.Locks 控制：
下載最多 3 支同時、轉錄一次 1 支（GPU）、LLM 一次 1 個請求（避免被限流）。
Job 的狀態給 GUI 輪詢用，所以每次更新都拿鎖、對外只給快照。
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from video_notes.pipeline import STAGES, JobOptions, Pipeline
from video_notes.transcribe import Cancelled


@dataclass
class Job:
    id: str
    url: str
    options: JobOptions
    status: str = "queued"          # queued / running / done / failed / cancelled
    stage: str = ""
    stages: dict[str, str] = field(default_factory=lambda: {s: "" for s in STAGES})
    progress: float = 0.0
    detail: str = ""
    title: str = ""
    folder: str = ""
    kind: str = ""
    notes: str = ""                 # 串流中的筆記內容；完成後是最終版本
    result: dict = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    error: str = ""
    created: float = field(default_factory=time.time)
    finished: float = 0.0
    cancel: threading.Event = field(default_factory=threading.Event)
    future: object = field(default=None, repr=False)

    def snapshot(self, with_notes: bool = True) -> dict:
        return {
            "id": self.id, "url": self.url, "status": self.status, "stage": self.stage,
            "stages": dict(self.stages), "progress": round(self.progress, 3), "detail": self.detail,
            "title": self.title, "folder": self.folder, "kind": self.kind,
            "profile": self.result.get("profile", self.options.plan.profile),
            "plan": {"profile": self.options.plan.profile, "modifiers": list(self.options.plan.modifiers),
                     "focus": self.options.plan.focus},
            "notes": self.notes if with_notes else "",
            "notes_file": self.result.get("notes_file", ""),
            "files": self.result.get("files", {}),
            "log": list(self.log[-30:]), "error": self.error,
            "created": self.created, "finished": self.finished,
        }


class JobManager:
    def __init__(self, pipeline: Pipeline, max_parallel: int = 3, on_update=None):
        self.pipeline = pipeline
        self._pool = ThreadPoolExecutor(max_workers=max(1, max_parallel), thread_name_prefix="video-notes")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._on_update = on_update   # CLI 用來印進度；GUI 不需要（它用輪詢）

    def submit(self, url: str, options: JobOptions) -> Job:
        job = Job(uuid.uuid4().hex[:10], url.strip(), options)
        with self._lock:
            self._jobs[job.id] = job
        job.future = self._pool.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshots(self) -> list[dict]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)
            return [j.snapshot(with_notes=False) for j in jobs]

    def snapshot(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot() if job else None

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job and job.status in ("queued", "running"):
            job.cancel.set()
            return True
        return False

    def remove(self, job_id: str) -> bool:
        """從清單移除已結束的工作（檔案不會刪）。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status not in ("queued", "running"):
                del self._jobs[job_id]
                return True
        return False

    def wait(self, jobs: list[Job]) -> None:
        for job in jobs:
            job.future.result()

    def shutdown(self) -> None:
        for job in list(self._jobs.values()):
            job.cancel.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    def _emit(self, job: Job, name: str, data: dict) -> None:
        with self._lock:
            if name == "stage":
                job.stage = data["stage"]
                job.stages[data["stage"]] = data["state"]
                job.detail = data.get("detail", "")
                if data["state"] == "running" and data["stage"] != "notes":
                    job.progress = 0.0
                if data["stage"] == "info" and data["state"] == "done":
                    job.title, job.folder, job.kind = data.get("title", ""), data.get("folder", ""), data.get("kind", "")
                if data["stage"] == "notes" and data["state"] == "waiting":
                    job.notes = ""
            elif name == "progress":
                job.progress, job.detail = data["value"], data.get("detail", "")
            elif name == "token":
                job.notes += data["text"]
            elif name == "log":
                job.log.append(data["message"])
        if self._on_update:
            self._on_update(job, name, data)

    def _run(self, job: Job) -> None:
        if job.cancel.is_set():
            job.status, job.finished = "cancelled", time.time()
            return
        job.status = "running"
        try:
            result = self.pipeline.run(job.url, job.options, lambda n, d: self._emit(job, n, d), job.cancel)
            with self._lock:
                job.result = result
                job.notes = result.get("notes", job.notes)
                job.status = "done"
        except Cancelled:
            job.status = "cancelled"
        except Exception as exc:  # noqa: BLE001 — 任何錯誤都要顯示給使用者，不能讓執行緒默默死掉
            job.status = "failed"
            job.error = f"{exc}"
            job.log.append(traceback.format_exc(limit=3))
        finally:
            job.finished = time.time()
            if self._on_update:
                self._on_update(job, "finished", {"status": job.status})
