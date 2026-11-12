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
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from video_notes.config import app_dir, bundle_dir
from video_notes.errors import Remedy, ToolError, internal, short

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


SOURCE = "notify"


def _host(url: str) -> str:
    """只留主機名（網址可能夾帶 token，不放進訊息）。"""
    try:
        return urllib.parse.urlsplit(url).netloc.rpartition("@")[2] or "對方"
    except ValueError:
        return "對方"


def classify_http_error(exc: BaseException, url: str) -> ToolError:
    """POST 失敗 → ToolError（錯誤合約）。"""
    host = _host(url)
    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        if code in (401, 403):
            return ToolError("auth_required", f"對方（{host}）拒絕了請求（HTTP {code}），可能缺少或填錯授權標頭",
                             detail=f"HTTP {code} {exc.reason}", source=SOURCE,
                             remedy=Remedy("needs_config", "檢查 socket/config.json 的 headers"))
        if code == 429:
            return ToolError("rate_limited", f"對方（{host}）限制了請求頻率（HTTP 429）", detail="HTTP 429", source=SOURCE,
                             remedy=Remedy("none", "稍後再試"))
        if code == 404:
            return ToolError("config_invalid", f"對方（{host}）沒有這個路徑（HTTP 404）", detail="HTTP 404", source=SOURCE,
                             remedy=Remedy("needs_config", "檢查通知網址（socket/config.json 的 url 或設定頁）"))
        if code >= 500:
            return ToolError("network_unreachable", f"對方（{host}）內部錯誤（HTTP {code}）", retryable=True,
                             detail=f"HTTP {code} {exc.reason}", source=SOURCE, remedy=Remedy("none", "稍後再試"))
        return ToolError("bad_input", f"對方（{host}）回傳 HTTP {code}", detail=f"HTTP {code} {exc.reason}", source=SOURCE)
    return ToolError("network_unreachable", f"連不上 {host}", detail=short(exc), source=SOURCE,
                     remedy=Remedy("needs_config", "確認接收端有開、通知網址正確"))


def post_result_checked(url: str, result: dict, config: dict | None = None) -> str:
    """送出，成功回傳 "HTTP 200" 這類說明；失敗丟 ToolError。"""
    config = config or load_config()
    if not url.startswith(("http://", "https://")):
        raise ToolError("config_invalid", "通知網址不是 http(s) 開頭", source=SOURCE,
                        remedy=Remedy("needs_config", "改成 http:// 或 https:// 開頭的網址"))
    try:
        body = json.dumps(build_payload(result, bool(config.get("include_transcript"))), ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise internal(exc, source=SOURCE, where="組通知內容") from exc
    headers = {"Content-Type": "application/json; charset=utf-8", **(config.get("headers") or {})}
    try:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=float(config.get("timeout") or 10)) as resp:
            return f"HTTP {resp.status}"
    except ValueError as exc:
        raise ToolError("config_invalid", "通知網址格式不正確", detail=short(exc), source=SOURCE,
                        remedy=Remedy("needs_config", "檢查通知網址")) from exc
    except (urllib.error.URLError, OSError) as exc:   # HTTPError 是 URLError 的子類
        raise classify_http_error(exc, url) from exc


def post_result(url: str, result: dict, config: dict | None = None) -> tuple[bool, str]:
    """回傳 (成功與否, 說明)。送不出去不會讓整個流程失敗——筆記已經存在硬碟上了。
    失敗的說明用錯誤合約的 reason（不含網址上的 token）。"""
    try:
        return True, post_result_checked(url, result, config)
    except ToolError as err:
        return False, str(err)
