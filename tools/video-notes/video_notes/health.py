"""「壞了就別一直試」的小記帳：data/health.json。

每個外部依賴（source 名稱，例如 "yt-dlp"、"stt:openai"、"llm:claude-sub"）一筆：
    {code, first_seen, last_seen, count, state, version}
- 同一 source 同一 code 連續失敗 DEGRADED_AFTER（3）次 → state = "degraded"：呼叫端用 is_degraded() 問，
  拿到 ToolError 就不再自動重試，GUI／CLI 顯示原因與 remedy。
- 成功一次 → 該 source 的記錄整筆刪除。使用者按「重新檢查」→ clear()。依賴版本改變 → 自動解除。
- 只存代碼、計數、時間、版本；不存訊息內容（reason 與 remedy 由代碼重建）。檔案壞了就當沒有。
- 單一行程內用鎖保護讀改寫（pipeline 是多執行緒）；不處理多個行程同時寫（GUI 與 CLI 同時跑時最後寫的贏，記帳而已）。
- 這些錯誤只算「依賴本身有問題」：bad_input／unsupported_source／cancelled 是這次輸入的問題，不記。
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from video_notes.errors import Remedy, ToolError

DEGRADED_AFTER = 3
IGNORED_CODES = ("bad_input", "unsupported_source", "cancelled")

_REASONS = {
    "dependency_outdated": "這個依賴太舊，已經連續失敗多次",
    "dependency_missing": "缺少這個依賴，已經連續失敗多次",
    "upstream_changed": "對方的網站或 API 改版了，已經連續失敗多次",
    "network_unreachable": "連續連不上對方",
    "auth_required": "缺少金鑰或登入，已經連續失敗多次",
    "auth_expired": "金鑰或登入已過期，已經連續失敗多次",
    "rate_limited": "連續被對方限流",
    "config_invalid": "設定有問題，已經連續失敗多次",
    "resource_exhausted": "資源不足（記憶體或磁碟），已經連續失敗多次",
    "internal_bug": "連續發生未預期的錯誤",
}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _remedy_for(source: str, code: str) -> Remedy:
    if code == "dependency_outdated" and source == "yt-dlp":
        from video_notes.media import DOC, UPGRADE_ACTION

        return Remedy("needs_update", UPGRADE_ACTION, DOC)
    kind = {"dependency_outdated": "needs_update", "dependency_missing": "needs_config", "auth_required": "needs_config",
            "auth_expired": "needs_config", "config_invalid": "needs_config", "internal_bug": "needs_owner"}.get(code, "none")
    return Remedy(kind, "排除原因後，在設定頁按「重新檢查」（或執行 --check）才會再試")


class HealthBook:
    def __init__(self, path: Path | None = None, clock: Callable[[], float] = time.time) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        if self._path is None:
            from video_notes.config import user_dir

            return user_dir() / "health.json"
        return self._path

    # ---- 檔案 ----
    def _load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, dict)}

    def _save(self, data: dict) -> None:
        path = self.path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass   # 記帳寫不進去不該讓處理失敗

    # ---- 記帳 ----
    def record_failure(self, source: str, error: ToolError | str, version: str = "") -> dict | None:
        """記一次失敗，回傳該 source 目前的記錄（被忽略的代碼回傳 None）。"""
        code = error.code if isinstance(error, ToolError) else str(error)
        if code in IGNORED_CODES:
            return None
        now = _iso(self._clock())
        with self._lock:
            data = self._load()
            entry = data.get(source)
            if (not entry or entry.get("code") != code
                    or (version and entry.get("version") and entry["version"] != version)):
                entry = {"code": code, "first_seen": now, "last_seen": now, "count": 0, "state": "failing",
                         "version": version}
            entry["count"] = int(entry.get("count", 0)) + 1
            entry["last_seen"] = now
            if version:
                entry["version"] = version
            if entry["count"] >= DEGRADED_AFTER:
                entry["state"] = "degraded"
            data[source] = entry
            self._save(data)
            return dict(entry)

    def record_success(self, source: str) -> None:
        with self._lock:
            data = self._load()
            if source in data:
                del data[source]
                self._save(data)

    def clear(self, source: str | None = None) -> None:
        """使用者按「重新檢查」：清掉某個 source，或全部。"""
        with self._lock:
            if source is None:
                data = {}
            else:
                data = self._load()
                data.pop(source, None)
            self._save(data)

    # ---- 查詢 ----
    def entries(self) -> dict[str, dict]:
        with self._lock:
            return self._load()

    def is_degraded(self, source: str, version: str = "") -> ToolError | None:
        """已標 degraded 就回傳帶原因與 remedy 的 ToolError（呼叫端不要再自動重試）；否則 None。
        傳入目前的依賴版本：和記錄的不同就視為已更新，自動解除。"""
        with self._lock:
            data = self._load()
            entry = data.get(source)
            if not entry or entry.get("state") != "degraded":
                return None
            if version and entry.get("version") and entry["version"] != version:
                del data[source]
                self._save(data)
                return None
            return self._to_error(source, entry)

    @staticmethod
    def _to_error(source: str, entry: dict) -> ToolError:
        code = entry.get("code", "internal_bug")
        reason = f"{source}：{_REASONS.get(code, _REASONS['internal_bug'])}（{entry.get('count', 0)} 次）"
        err = ToolError(code, reason, retryable=False, remedy=_remedy_for(source, code),
                        detail=f"first_seen={entry.get('first_seen', '')} last_seen={entry.get('last_seen', '')}",
                        source=source)
        return err


_default = HealthBook()


def default() -> HealthBook:
    return _default


def record_failure(source: str, error: ToolError | str, version: str = "") -> dict | None:
    return _default.record_failure(source, error, version)


def record_success(source: str) -> None:
    _default.record_success(source)


def clear(source: str | None = None) -> None:
    _default.clear(source)


def is_degraded(source: str, version: str = "") -> ToolError | None:
    return _default.is_degraded(source, version)


def entries() -> dict[str, dict]:
    return _default.entries()
