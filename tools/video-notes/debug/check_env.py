"""印出執行環境：ffmpeg、GPU、yt-dlp 的 JS 執行環境、各家 AI 能不能用（Claude Code、API 金鑰）、設定檔位置。

出問題時第一個跑這支：
    .\\tools\\video-notes\\.venv\\Scripts\\python.exe tools\\video-notes\\debug\\check_env.py
"""

import json
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from toolzoo.ai import keys_file  # noqa: E402

from video_notes.config import load_settings, settings_file  # noqa: E402
from video_notes.service import environment  # noqa: E402

if __name__ == "__main__":
    env = environment()
    settings = load_settings()
    print(json.dumps(env, ensure_ascii=False, indent=2))
    print(f"\n設定檔：{settings_file()}")
    print(f"金鑰檔：{keys_file()}")
    print(f"輸出資料夾：{settings.output_root()}")
    if not env["ffmpeg"]:
        print("\n!! 找不到 ffmpeg —— 下載與抽音訊會失敗")
    if not env["js_runtimes"]:
        print("\n!! 沒有 deno / node / bun —— YouTube 可能抓不到影片網址")
    if not any(env["keys"].values()):
        print("\n!! 沒有可用的 AI（找不到 Claude Code，也沒有任何 API 金鑰）—— 只能用 --no-notes 產生逐字稿")
