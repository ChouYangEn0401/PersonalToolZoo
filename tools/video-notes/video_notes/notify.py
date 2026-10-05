"""「socket 模式」：處理完一支影片，把結果用 HTTP POST（JSON）送給另一個程式。

用途是串接：例如另一個工具在 localhost 開一個 HTTP 端點，收到筆記後自動寫進 Notion、
丟到 Telegram、存進資料庫……Video Notes 不需要知道對方要做什麼。

設定在工具資料夾的 socket/config.json（打包後放在 exe 旁邊的 socket\\config.json 也可以），
CLI 用 --post 啟用、--post <網址> 臨時指定對象；GUI 在設定頁填網址。
送出的 JSON 格式見 README「socket 模式」。測試時可以先開 debug/notify_receiver.py 接收看看。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from video_notes.config import app_dir, bundle_dir

DEFAULTS = {
    "enabled": False,
    "url": "http://127.0.0.1:8787/video-notes",
    "timeout": 10,
    "headers": {},
    "include_transcript": False,
}


def config_path() -> Path:
    """先找可以改的那份（工具資料夾 / exe 旁），沒有才用隨程式發佈的預設值。"""
    editable = app_dir() / "socket" / "config.json"
    return editable if editable.exists() else bundle_dir() / "socket" / "config.json"


def load_config() -> dict:
    config = dict(DEFAULTS)
    try:
        raw = json.loads(config_path().read_text(encoding="utf-8-sig"))
        config.update({k: v for k, v in raw.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return config


def build_payload(result: dict, include_transcript: bool = False) -> dict:
    payload = {"event": "video-notes.completed", "sent_at": datetime.now().isoformat(timespec="seconds"), **result}
    if include_transcript:
        try:
            payload["transcript"] = Path(result["files"]["transcript"]).read_text(encoding="utf-8")
        except (KeyError, OSError):
            pass
    return payload


def post_result(url: str, result: dict, config: dict | None = None) -> tuple[bool, str]:
    """回傳 (成功與否, 說明)。送不出去不會讓整個流程失敗——筆記已經存在硬碟上了。"""
    config = config or load_config()
    if not url.startswith(("http://", "https://")):
        return False, f"不是 http(s) 網址：{url}"
    body = json.dumps(build_payload(result, bool(config.get("include_transcript"))), ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8", **(config.get("headers") or {})}
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=float(config.get("timeout") or 10)) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}：{exc.reason}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"連不上 {url}：{getattr(exc, 'reason', exc)}"
