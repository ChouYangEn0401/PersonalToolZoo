"""錯誤合約：所有外部呼叫（yt-dlp、ffmpeg、語音辨識、AI、HTTP 通知）失敗時都轉成 ToolError。

為什麼：上游的原始訊息（英文、一長串）人看不懂，agent 也無法判斷「要升級套件、要設定、還是只是這次輸入不對」。
ToolError 固定帶：

    code       穩定的小寫代碼（CODES），程式與 agent 靠它判斷，不靠文字
    reason     一句人話：為什麼壞（≤ 120 字，不含金鑰、不含完整路徑）
    retryable  重試有沒有可能成功
    remedy     Remedy(kind, action, doc)：下一步怎麼辦。action 只「寫出來」，程式絕不自動執行（例如不自動 pip install）
    detail     上游訊息的短摘要（≤ 300 字，已去敏感資訊）；完整內容只寫進工作 log

規則：每個外部呼叫點都要明確 try/except 並轉成 ToolError；不准吞例外、不准只印 str(e)。
CLI 的退出碼由 code 決定（exit_code()），見 README 與 docs/analysis-schema.md 的「錯誤合約」。
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field

# 代碼 → (預設可否重試, 退出碼分類)
CODES: dict[str, tuple[bool, str]] = {
    "dependency_outdated": (False, "env"),     # 套件太舊（yt-dlp 跟不上網站改版最常見）
    "dependency_missing": (False, "env"),      # ffmpeg／JS 執行環境／Python 套件／本機模型不在
    "upstream_changed": (False, "env"),        # 網站或 API 改了，升級也還沒修
    "network_unreachable": (True, "transient"),
    "auth_required": (False, "env"),           # 需要金鑰或登入
    "auth_expired": (False, "env"),
    "rate_limited": (True, "transient"),
    "config_invalid": (False, "env"),
    "unsupported_source": (False, "input"),
    "resource_exhausted": (True, "transient"),  # GPU 記憶體、磁碟
    "bad_input": (False, "input"),             # 只有這次輸入有問題（網址錯、影片不存在、檔案壞）
    "cancelled": (False, "other"),
    "internal_bug": (False, "other"),          # 其餘；reason 要附 log 位置
}

# 退出碼：0 成功、2 輸入有問題、3 依賴或環境問題、4 暫時性可重試、1 其他
EXIT_CODES = {"input": 2, "env": 3, "transient": 4, "other": 1}

REMEDY_KINDS = ("needs_update", "needs_config", "needs_owner", "auto_fixable", "none")

REASON_LIMIT = 120
DETAIL_LIMIT = 300


@dataclass
class Remedy:
    kind: str = "none"     # REMEDY_KINDS
    action: str = ""       # 要做的事（給人或 agent 看）；程式不自動執行
    doc: str = ""          # 說明連結或本專案文件路徑（相對 repo）


@dataclass
class ToolError(Exception):
    code: str
    reason: str
    retryable: bool | None = None
    remedy: Remedy = field(default_factory=Remedy)
    detail: str = ""
    source: str = ""       # 哪個依賴／adapter（例如 "yt-dlp"、"stt:openai"），health.json 用它記帳

    def __post_init__(self) -> None:
        if self.code not in CODES:
            self.code = "internal_bug"
        if self.retryable is None:
            self.retryable = CODES[self.code][0]
        self.reason = redact(self.reason)[:REASON_LIMIT]
        self.detail = redact(self.detail)[:DETAIL_LIMIT]
        super().__init__(self.reason)

    def __str__(self) -> str:   # dataclass 會蓋掉 Exception.__str__；畫面上只顯示人話
        text = self.reason
        if self.remedy.action:
            text += f"（{self.remedy.action}）"
        return text

    def to_dict(self) -> dict:
        return {"code": self.code, "reason": self.reason, "retryable": self.retryable,
                "remedy": asdict(self.remedy), "detail": self.detail, "source": self.source}

    @property
    def exit_code(self) -> int:
        return exit_code(self.code)


def exit_code(code: str) -> int:
    return EXIT_CODES[CODES.get(code, CODES["internal_bug"])[1]]


# ---- 去敏感資訊：金鑰、Bearer token、使用者資料夾路徑 ----
_SECRETS = [   # 整段換成 ***
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{12,}"),        # OpenAI / Anthropic 風格
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),                  # Google
    re.compile(r"\b(?:ntn|secret)_[A-Za-z0-9]{20,}"),          # Notion
]
_PREFIXED = [  # 保留前綴（group 1），只換值
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)((?:api[_-]?key|token|authorization)\s*[=:]\s*)['\"]?[^\s'\",]{8,}"),
]
_PATH_PATTERN = re.compile(r"(?i)\b[a-z]:\\(?:users|documents and settings)\\[^\\\s\"']+")


def redact(text: str) -> str:
    if not text:
        return ""
    out = str(text)
    for pat in _SECRETS:
        out = pat.sub("***", out)
    for pat in _PREFIXED:
        out = pat.sub(r"\1***", out)
    out = _PATH_PATTERN.sub("<使用者資料夾>", out)
    home = os.path.expanduser("~")
    if home and home != "~":
        out = out.replace(home, "<使用者資料夾>")
    return out


def short(exc: BaseException) -> str:
    """上游例外的短摘要（給 detail 用）。"""
    text = f"{type(exc).__name__}: {exc}".strip()
    return redact(" ".join(text.split()))[:DETAIL_LIMIT]


def internal(exc: BaseException, source: str = "", where: str = "") -> ToolError:
    """不認得的例外 → internal_bug。where 寫是哪一步（例如「抽音訊」）。"""
    return ToolError("internal_bug", f"{where or '處理'}時發生未預期的錯誤", detail=short(exc), source=source,
                     remedy=Remedy("needs_owner", "把工作紀錄（log）與這段訊息交給維護者"))


def as_tool_error(exc: BaseException, source: str = "", where: str = "") -> ToolError:
    """任何例外 → ToolError（已經是就原樣回傳）。"""
    if isinstance(exc, ToolError):
        return exc
    return internal(exc, source, where)
