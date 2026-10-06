"""CLI 與 GUI 共用的東西：提示詞庫在哪、執行環境的狀態。"""

from __future__ import annotations

from pathlib import Path

from toolzoo import ytdlp
from toolzoo.ai import PROVIDERS, claude_code, find_key, needs_key

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
    claude_ok, claude_text = claude_code.available()
    return {
        "ffmpeg": ffmpeg or "",
        "gpu": gpu,
        "gpu_text": gpu_text,
        "js_runtimes": ytdlp.find_js_runtimes(),
        "yt_dlp": ytdlp.version(),
        # 每個服務能不能用：要金鑰的看有沒有金鑰；Claude 訂閱看找不找得到 Claude Code（只找執行檔，不花錢）
        "keys": {p: claude_ok if p == claude_code.KEY else bool(find_key(p, key_files())[0]) for p in PROVIDERS},
        "keyless": [p for p in PROVIDERS if not needs_key(p)],
        "claude_code": claude_text,   # 找到的 claude 執行檔，或找不到的原因
        "user_prompts": str(user_dir() / "prompts"),
    }
