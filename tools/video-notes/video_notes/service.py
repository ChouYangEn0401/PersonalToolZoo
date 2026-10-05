"""CLI 與 GUI 共用的東西：提示詞庫在哪、執行環境的狀態。"""

from __future__ import annotations

from pathlib import Path

from toolzoo import ytdlp
from toolzoo.ai import PROVIDERS, find_key

from video_notes.config import bundle_dir, key_files, user_dir
from video_notes.profiles import PromptLibrary
from video_notes.transcribe import cuda_status


def prompt_dirs() -> list[Path]:
    """內建的在前、使用者的在後（同 id 由後者覆蓋）。"""
    user = user_dir() / "prompts"
    for sub in ("profiles", "modifiers", "presets"):
        (user / sub).mkdir(parents=True, exist_ok=True)
    return [bundle_dir() / "prompts", user]


def library() -> PromptLibrary:
    """每次重新讀檔：使用者改了 TOML，GUI 重新整理頁面就生效，不用重開程式。"""
    return PromptLibrary(*prompt_dirs())


def environment() -> dict:
    gpu, gpu_text = cuda_status()
    ffmpeg = ytdlp.find_ffmpeg()
    return {
        "ffmpeg": ffmpeg or "",
        "gpu": gpu,
        "gpu_text": gpu_text,
        "js_runtimes": ytdlp.find_js_runtimes(),
        "yt_dlp": ytdlp.version(),
        "keys": {p: bool(find_key(p, key_files())[0]) for p in PROVIDERS},
        "user_prompts": str(user_dir() / "prompts"),
    }
