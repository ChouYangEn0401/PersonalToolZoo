"""錯誤合約：每個失敗都有穩定的代碼、一句人話的原因，以及下一步怎麼辦。

呼叫端（別的程式、AI 助理）靠 ``code`` 與退出碼判斷，不靠文字。
這裡的任何欄位都不可以放金鑰、密語或明文。
"""

from __future__ import annotations

# 退出碼。0／1／2／3／4 的意義跟 repo 裡其他工具一致；5、6 是加密工具專用。
EXIT_OK = 0
EXIT_OTHER = 1          # 其他（讀寫失敗、程式錯誤）
EXIT_BAD_INPUT = 2      # 這次的輸入有問題（路徑、參數、金鑰格式、目標已存在）
EXIT_ENVIRONMENT = 3    # 環境問題（缺套件）
EXIT_WRONG_KEY = 5      # 金鑰／密語不對
EXIT_CORRUPT = 6        # 檔案被改過、截斷或損壞

# code -> (退出碼, remedy.kind)
_CODES: dict[str, tuple[int, str]] = {
    "bad_input": (EXIT_BAD_INPUT, "none"),
    "input_missing": (EXIT_BAD_INPUT, "none"),
    "output_exists": (EXIT_BAD_INPUT, "none"),
    "key_missing": (EXIT_BAD_INPUT, "needs_config"),
    "bad_key_format": (EXIT_BAD_INPUT, "needs_config"),
    "unsupported_format": (EXIT_BAD_INPUT, "none"),
    "legacy_format": (EXIT_BAD_INPUT, "none"),
    "unsafe_archive": (EXIT_BAD_INPUT, "needs_owner"),
    "dependency_missing": (EXIT_ENVIRONMENT, "needs_config"),
    "wrong_key": (EXIT_WRONG_KEY, "needs_config"),
    "corrupt": (EXIT_CORRUPT, "needs_owner"),
    "io_error": (EXIT_OTHER, "none"),
    "internal_bug": (EXIT_OTHER, "needs_owner"),
}


class SealError(Exception):
    """加解密流程裡所有「預期內」的失敗。"""

    def __init__(self, code: str, reason: str, action: str = "", detail: str = ""):
        if code not in _CODES:
            raise ValueError(f"unknown error code: {code}")
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.action = action
        self.detail = detail

    @property
    def exit_code(self) -> int:
        return _CODES[self.code][0]

    @property
    def remedy_kind(self) -> str:
        return _CODES[self.code][1]

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "reason": self.reason,
            "retryable": False,
            "remedy": {"kind": self.remedy_kind, "action": self.action},
            "detail": self.detail,
        }


def all_codes() -> dict[str, int]:
    """代碼 -> 退出碼（給文件與測試用）。"""
    return {code: pair[0] for code, pair in _CODES.items()}
