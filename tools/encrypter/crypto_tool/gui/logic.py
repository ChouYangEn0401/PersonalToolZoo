"""新介面的「腦」：表單檢查、預設檔名、執行加解密、把結果與錯誤變成人話。

這個模組**不 import tkinter**，所以可以直接用單元測試驗證；gui/app.py 只負責把它接到畫面上。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import texts as T

try:  # 測試時是 crypto_tool.gui.logic；實際執行時 crypto_tool/ 在 sys.path 上，是 gui.logic
    from ..sealed import (
        SealError, decrypt_path, default_decrypt_output, default_encrypt_output,
        encrypt_path, generate_key_file, info_path, load_key_file, passphrase_material,
    )
    from ..sealed.keys import MIN_PASSPHRASE_CHARS, key_id
except ImportError:
    from sealed import (
        SealError, decrypt_path, default_decrypt_output, default_encrypt_output,
        encrypt_path, generate_key_file, info_path, load_key_file, passphrase_material,
    )
    from sealed.keys import MIN_PASSPHRASE_CHARS, key_id

ENCRYPT, DECRYPT = "encrypt", "decrypt"
KEY_PASSPHRASE, KEY_FILE = "passphrase", "keyfile"


@dataclass
class JobForm:
    """畫面上一次加密或解密要用到的所有欄位。"""

    action: str = ENCRYPT
    input_path: str = ""
    output_path: str = ""
    key_mode: str = KEY_PASSPHRASE
    passphrase: str = ""
    passphrase_confirm: str = ""
    key_file: str = ""
    cipher: str = "aes-256-gcm"
    overwrite: bool = False
    keep_tar: bool = False


@dataclass
class Message:
    """要顯示在結果區的一則訊息。kind 決定顏色：success／danger／warning／info。"""

    kind: str
    title: str
    lines: list[str]
    code: str = ""


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def first_dropped(paths) -> tuple[str, int]:
    """拖進來的清單 -> (第一個路徑, 被忽略的其他項目數)。一次只處理一個。"""
    items = [str(p).strip() for p in paths if str(p).strip()]
    if not items:
        return "", 0
    return items[0], len(items) - 1


def describe_input(path: str) -> str:
    """使用者選了一個要加密的東西之後，顯示在路徑下面的一行說明。"""
    p = Path(path)
    if p.is_dir():
        return T.KIND_FOLDER
    if p.is_file():
        return f"{T.KIND_FILE}・{human_size(p.stat().st_size)}"
    return T.PROBLEM_INPUT_GONE


def inspect_sealed(path: str) -> tuple[str, dict | None, Message | None]:
    """看一個要解密的檔案。回傳 (說明文字, info 或 None, 錯誤訊息或 None)。"""
    try:
        info = info_path(path)
    except SealError as err:
        if err.code == "input_missing":  # 路徑還在打字、或檔案被移走：只在說明列提醒
            return T.PROBLEM_INPUT_GONE, None, None
        return "", None, error_message(err)
    if info["format"] != "isd2":
        return T.SEALED_LEGACY, info, None
    text = T.SEALED_DESCRIPTION.format(
        cipher=info["cipher"].upper(), key=T.SEALED_KEY[info["kdf"]],
        payload=T.SEALED_PAYLOAD[info["payload"]],
    )
    return f"{text}・{human_size(info['size'])}", info, None


def key_mode_for(info: dict | None) -> str | None:
    """加密檔當初用哪一種鎖，解密畫面就自動切到哪一種。"""
    if not info or info.get("format") != "isd2":
        return None
    return KEY_PASSPHRASE if info["kdf"] == "scrypt" else KEY_FILE


def suggest_output(action: str, input_path: str, keep_tar: bool = False) -> str:
    """選好輸入之後自動填的輸出位置；猜不出來就留空讓使用者自己選。"""
    if not input_path:
        return ""
    if action == ENCRYPT:
        return str(default_encrypt_output(input_path))
    out = default_decrypt_output(input_path)
    if out is None:
        return ""
    return str(out) + (".tar" if keep_tar else "")


def passphrase_strength(text: str) -> tuple[int, str]:
    """很粗的提示（0 空白、1 太短、2 還可以、3 不錯），只看長度與種類，不擋使用者。"""
    if not text:
        return 0, T.STRENGTH_LABELS[0]
    kinds = sum(bool(k) for k in (
        any(c.islower() for c in text), any(c.isupper() for c in text),
        any(c.isdigit() for c in text),
        any(not c.isalnum() for c in text),
    ))
    if len(text) < MIN_PASSPHRASE_CHARS:
        level = 1
    elif len(text) >= 20 or (len(text) >= 16 and kinds >= 3):
        level = 3
    else:
        level = 2
    return level, T.STRENGTH_LABELS[level]


def validate(form: JobForm) -> list[str]:
    """按下按鈕前先檢查；回傳要告訴使用者的問題清單（空的表示可以開始）。"""
    problems: list[str] = []
    if not form.input_path.strip():
        problems.append(T.PROBLEM_NO_INPUT[form.action])
    elif not os.path.exists(form.input_path):
        problems.append(T.PROBLEM_INPUT_GONE)
    if form.key_mode == KEY_PASSPHRASE:
        if not form.passphrase:
            problems.append(T.PROBLEM_NO_PASSPHRASE)
        elif form.action == ENCRYPT and form.passphrase != form.passphrase_confirm:
            problems.append(T.PROBLEM_MISMATCH)
    elif not form.key_file.strip():
        problems.append(T.PROBLEM_NO_KEYFILE)
    if not form.output_path.strip():
        problems.append(T.PROBLEM_NO_OUTPUT)
    return problems


def run_job(form: JobForm, progress=None) -> dict:
    """真的去加密或解密。失敗一律丟 SealError。在背景執行緒呼叫。"""
    if form.key_mode == KEY_PASSPHRASE:
        material = passphrase_material(form.passphrase)
    else:
        material = load_key_file(form.key_file.strip())
    if form.action == ENCRYPT:
        return encrypt_path(form.input_path, form.output_path, material,
                            cipher=form.cipher, force=form.overwrite, progress=progress)
    return decrypt_path(form.input_path, form.output_path, material,
                        force=form.overwrite, keep_tar=form.keep_tar, progress=progress)


def run_job_safely(form: JobForm, progress=None) -> Message:
    """run_job 的包裝：不管發生什麼都回傳一則可以直接顯示的訊息。"""
    try:
        return success_message(run_job(form, progress))
    except SealError as err:
        return error_message(err)
    except Exception as exc:  # 不把例外文字丟到畫面上
        return error_message(SealError("internal_bug", "程式發生沒預期到的錯誤。",
                                       action="把這個畫面截圖回報給維護者。",
                                       detail=type(exc).__name__))


def progress_view(done: int, total: int) -> tuple[int, str]:
    """進度 -> (0–100 的百分比, 進度列旁邊的字)。"""
    if total <= 0:
        return 0, ""
    percent = max(0, min(100, int(done * 100 / total)))
    return percent, f"{percent}%（{human_size(done)}／{human_size(total)}）"


def success_message(result: dict) -> Message:
    action = result["action"]
    lines = [T.SUCCESS_SAVED.format(path=result["output"])]
    if "files" in result:
        lines.append(T.SUCCESS_FILES.format(n=result["files"]))
    if result.get("skipped_links"):
        lines.append(T.SUCCESS_SKIPPED.format(n=result["skipped_links"]))
    if action == ENCRYPT:
        lines += [T.SUCCESS_ORIGINAL_KEPT, T.SUCCESS_BACKUP]
    return Message("success", T.SUCCESS_TITLE[action], lines)


def error_message(err: SealError) -> Message:
    lines = [err.reason]
    if err.action:
        lines.append(err.action)
    if err.code not in ("legacy_format", "output_exists"):
        lines.append(T.ERROR_NOTHING_WRITTEN)
    if err.code == "internal_bug" and err.detail:
        lines.append(f"（{err.detail}）")
    kind = "warning" if err.code in ("output_exists", "legacy_format", "bad_input") else "danger"
    return Message(kind, T.ERROR_TITLES.get(err.code, T.ERROR_TITLES["internal_bug"]), lines,
                   code=err.code)


def create_key_file(path: str) -> Message:
    """「金鑰」分頁的產生按鈕。永遠不覆蓋既有檔案（要換金鑰請使用者自己先處理舊檔）。"""
    if not path.strip():
        return Message("warning", T.ERROR_TITLES["bad_input"], [T.PROBLEM_NO_OUTPUT])
    try:
        info = generate_key_file(path.strip())
    except SealError as err:
        return error_message(err)
    return Message("success", T.KEYS_CREATED.format(path=info["path"]),
                   [T.KEYS_FINGERPRINT.format(key_id=info["key_id"]), T.KEYS_BACKUP_WARNING])


def check_key_file(path: str) -> Message:
    """「金鑰」分頁的檢查按鈕：只說能不能用、是哪一種，不顯示金鑰內容。"""
    if not path.strip():
        return Message("warning", T.ERROR_TITLES["key_missing"], [T.PROBLEM_NO_KEYFILE])
    try:
        material = load_key_file(path.strip())
    except SealError as err:
        return error_message(err)
    if material.raw is not None:
        return Message("success", T.KEYS_CHECK_TITLE,
                       [T.KEYS_CHECK_RAW.format(key_id=key_id(material.raw))])
    return Message("info", T.KEYS_CHECK_TITLE, [T.KEYS_CHECK_PASSPHRASE])
