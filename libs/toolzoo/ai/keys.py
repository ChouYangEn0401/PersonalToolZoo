"""API 金鑰：從哪裡讀、存到哪裡。

讀取順序（先找到先用）：

1. 環境變數            —— OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY …
2. 專案的 .env         —— 從原始碼執行時是 repo 根目錄的 .env；打包的 exe 先找 exe 旁邊的 .env
                          （位置規則見 toolzoo.appdirs；範本是 repo 根目錄的 .env.example）
3. 工具額外指定的檔案

舊專案的 .env 寫法（``chatgpt=...``、``gemini=...``）也認得，整個檔案複製過來就能用。

.env 是純文字，已被 .gitignore 擋掉；不要把它傳給別人。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from toolzoo.appdirs import env_file, env_files, loaded_from, read_env_file

# 每個 provider 認得的名稱；第一個是「正式」名稱，存檔時用它
KEY_NAMES: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY", "CHATGPT_API_KEY", "OPENAI_KEY", "OPENAI_APIKEY", "chatgpt", "openai"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "gemini"),
    "anthropic": ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "claude", "anthropic"),
}


def keys_file() -> Path:
    """存金鑰時寫入的 .env。"""
    return env_file()


def find_key(provider: str, extra_files: Iterable[Path] = ()) -> tuple[str, str]:
    """回傳 (金鑰, 來源說明)；找不到就回傳 ("", "")。"""
    names = KEY_NAMES.get(provider, ())
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            # load_env() 從 .env 載進環境變數的，來源寫那個檔案
            source = loaded_from.get(name)
            return value, str(source) if source else f"環境變數 {name}"
    for path in (*env_files(), *extra_files):
        values = read_env_file(Path(path))
        for name in names:
            value = values.get(name, "").strip()
            if value and not value.endswith("..."):  # 範本檔裡的 "sk-proj-......" 不算
                return value, str(path)
    return "", ""


def save_key(provider: str, key: str) -> Path:
    """把金鑰寫進專案的 .env（同一個 provider 的舊值會被取代，其他行與註解都保留）。"""
    canonical = KEY_NAMES[provider][0]
    aliases = set(KEY_NAMES[provider])
    path = keys_file()
    kept: list[str] = []
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            name = raw.split("=", 1)[0].strip() if "=" in raw else ""
            if name not in aliases:
                kept.append(raw)
    else:
        kept.append("# PersonalToolZoo 的金鑰與參數（不進版控；每一項的說明見 .env.example）")
    if key.strip():
        kept.append(f"{canonical}={key.strip()}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept).strip("\n") + "\n", encoding="utf-8")
    return path
