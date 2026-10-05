"""API 金鑰：從哪裡讀、存到哪裡。

讀取順序（先找到先用）：

1. 環境變數            —— OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY …
2. 共用金鑰檔          —— %APPDATA%\\PersonalToolZoo\\keys.env（所有工具共用，設一次就好）
3. 工具額外指定的檔案   —— 例如工具資料夾裡的 .env（開發時方便；已被 .gitignore 擋掉）

舊專案的 .env 寫法（``chatgpt=...``、``gemini=...``）也認得，整個檔案複製過來就能用。

金鑰檔是純文字，跟 ~/.aws/credentials 一樣靠「放在自己的使用者資料夾」保護，
不要把它放進 repo 或傳給別人。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from toolzoo.appdirs import data_root

# 每個 provider 認得的名稱；第一個是「正式」名稱，存檔時用它
KEY_NAMES: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY", "CHATGPT_API_KEY", "OPENAI_KEY", "OPENAI_APIKEY", "chatgpt", "openai"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "gemini"),
    "anthropic": ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "claude", "anthropic"),
}


def keys_file() -> Path:
    return data_root() / "keys.env"


def read_env_file(path: Path) -> dict[str, str]:
    """讀 KEY=VALUE 格式的檔案（.env）。不認得的行直接略過，不會丟例外。"""
    data: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, value = line.split("=", 1)
        data[name.strip()] = value.strip().strip('"').strip("'")
    return data


def find_key(provider: str, extra_files: Iterable[Path] = ()) -> tuple[str, str]:
    """回傳 (金鑰, 來源說明)；找不到就回傳 ("", "")。"""
    names = KEY_NAMES.get(provider, ())
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value, f"環境變數 {name}"
    for path in (keys_file(), *extra_files):
        values = read_env_file(Path(path))
        for name in names:
            value = values.get(name, "").strip()
            if value and not value.endswith("..."):  # 範本檔裡的 "sk-proj-......" 不算
                return value, str(path)
    return "", ""


def save_key(provider: str, key: str) -> Path:
    """把金鑰寫進共用金鑰檔（同一個 provider 的舊值會被取代，其他行保留）。"""
    canonical = KEY_NAMES[provider][0]
    aliases = set(KEY_NAMES[provider])
    path = keys_file()
    kept: list[str] = []
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            name = raw.split("=", 1)[0].strip() if "=" in raw else ""
            if name not in aliases:
                kept.append(raw)
    if key.strip():
        kept.append(f"{canonical}={key.strip()}")
    header = "# PersonalToolZoo 共用 API 金鑰（所有工具都會讀這個檔）\n"
    body = "\n".join(line for line in kept if not line.startswith("# PersonalToolZoo 共用"))
    path.write_text(header + body.strip("\n") + "\n", encoding="utf-8")
    return path
