"""金鑰從哪裡來：金鑰檔、環境變數、或密語。這裡的函式都不會印出或記錄金鑰內容。

金鑰檔接受三種寫法：

1. ``.env`` 風格的文字檔（例如 ``.decryption_code.env``）::

       # 註解
       CRYPTO_TOOL_KEY=b64:mJ3...（32 bytes 的 base64）

   值可以是 ``b64:``／``hex:`` 開頭的 32 bytes 金鑰、沒有前綴的 64 個十六進位字元或
   32 bytes 的 base64；其他內容一律當成密語（會經過 scrypt）。
2. 剛好 32 bytes 的二進位檔：直接當金鑰。
3. 只有一行文字的檔案：規則同上面的「值」。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import secrets
from pathlib import Path

from .container import KEY_LEN, KeyMaterial
from .errors import SealError

DEFAULT_KEY_NAME = "CRYPTO_TOOL_KEY"
MAX_KEY_FILE_BYTES = 64 * 1024
MIN_PASSPHRASE_CHARS = 12  # 低於這個長度只警告，不擋

_ASSIGN_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _b64_32(text: str) -> bytes | None:
    """text 是 32 bytes 的 base64（標準或 URL 安全，有沒有補 = 都可以）就回傳，否則 None。"""
    if not 43 <= len(text) <= 44 or not re.fullmatch(r"[A-Za-z0-9+/_-]+=?", text):
        return None
    try:
        raw = base64.urlsafe_b64decode(text.replace("+", "-").replace("/", "_") + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        return None
    return raw if len(raw) == KEY_LEN else None


def parse_secret_value(text: str) -> KeyMaterial:
    """把一個字串解讀成金鑰或密語。同一個字串永遠得到同一種解讀。"""
    value = text.strip()
    if not value:
        raise SealError("key_missing", "金鑰是空的。")
    bad = SealError(
        "bad_key_format",
        "金鑰格式不對：標了 b64: 或 hex:，但內容不是 32 bytes。",
        action="用 keygen 重新產生金鑰檔，或確認檔案沒有被截斷。",
    )
    if value.startswith("b64:"):
        raw = _b64_32(value[4:].strip())
        if raw is None:
            raise bad
        return KeyMaterial(raw=raw)
    if value.startswith("hex:"):
        body = value[4:].strip()
        if not _HEX64_RE.match(body):
            raise bad
        return KeyMaterial(raw=bytes.fromhex(body))
    if _HEX64_RE.match(value):
        return KeyMaterial(raw=bytes.fromhex(value), passphrase=value)
    raw = _b64_32(value)
    if raw is not None:
        return KeyMaterial(raw=raw, passphrase=value)
    return KeyMaterial(passphrase=value)


def passphrase_material(text: str) -> KeyMaterial:
    """使用者親手輸入的密語：一律走 scrypt，不猜它是不是金鑰。"""
    value = text.rstrip("\r\n")
    if not value:
        raise SealError("key_missing", "密語是空的。")
    return KeyMaterial(passphrase=value, prefer_passphrase=True)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def load_key_file(path: str | os.PathLike, name: str | None = None) -> KeyMaterial:
    p = Path(path)
    if not p.is_file():
        raise SealError(
            "key_missing", "找不到金鑰檔。",
            action="確認 --key-file 的路徑；金鑰若放在外接裝置，先接上再試。",
        )
    try:
        if p.stat().st_size > MAX_KEY_FILE_BYTES:
            raise SealError("bad_key_format", "金鑰檔太大，看起來不是金鑰檔。")
        blob = p.read_bytes()
    except OSError as exc:
        raise SealError("io_error", "讀不到金鑰檔。", detail=type(exc).__name__) from None
    if not blob.strip():
        raise SealError("key_missing", "金鑰檔是空的。")

    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = None

    if text is not None:
        pairs: dict[str, str] = {}
        for line in text.splitlines():
            if line.strip().startswith("#"):
                continue
            m = _ASSIGN_RE.match(line)
            # 值是空的不算（補了 = 的 base64 單行金鑰看起來也像「名稱=」）
            if m and _unquote(m.group(2)):
                pairs[m.group(1)] = _unquote(m.group(2))
        if pairs:
            return parse_secret_value(_pick(pairs, name))
    if name is not None:
        raise SealError(
            "key_missing", "金鑰檔裡沒有指定的那個名稱。",
            action="確認 --key-name；這個檔案不是「名稱=值」的格式。",
        )
    if len(blob) == KEY_LEN:
        return KeyMaterial(raw=blob)
    if text is None:
        raise SealError(
            "bad_key_format", "金鑰檔不是文字檔，也不是剛好 32 bytes 的金鑰。",
            action="用 keygen 重新產生金鑰檔。",
        )
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) != 1:
        raise SealError(
            "bad_key_format", "金鑰檔有很多行，但不是「名稱=值」的格式。",
            action="改成一行一個「名稱=值」，或只留一行金鑰。",
        )
    return parse_secret_value(lines[0])


def _pick(pairs: dict[str, str], name: str | None) -> str:
    if name is not None:
        if name not in pairs:
            raise SealError(
                "key_missing", "金鑰檔裡沒有指定的那個名稱。",
                action="確認 --key-name 跟金鑰檔裡的名稱一致。",
            )
        return pairs[name]
    if DEFAULT_KEY_NAME in pairs:
        return pairs[DEFAULT_KEY_NAME]
    if len(pairs) == 1:
        return next(iter(pairs.values()))
    raise SealError(
        "bad_key_format", "金鑰檔裡有好幾個名稱，不知道要用哪一個。",
        action=f"用 --key-name 指定，或把金鑰那一行命名為 {DEFAULT_KEY_NAME}。",
    )


def load_key_env(name: str, environ=None) -> KeyMaterial:
    env = os.environ if environ is None else environ
    if not _NAME_RE.match(name or ""):
        raise SealError("bad_input", "--key-env 要給的是環境變數的「名稱」，不是金鑰本身。")
    value = env.get(name, "")
    if not value.strip():
        raise SealError(
            "key_missing", "指定的環境變數沒有設定或是空的。",
            action="由呼叫的程式在啟動這個指令前設定該環境變數。",
        )
    return parse_secret_value(value)


def key_id(raw: bytes) -> str:
    """金鑰的短指紋，用來核對「備份的是不是同一把」。無法由它反推金鑰。"""
    return hashlib.sha256(b"ISD2 key id\0" + raw).hexdigest()[:12]


def generate_key_file(path: str | os.PathLike, *, fmt: str = "env",
                      name: str = DEFAULT_KEY_NAME, force: bool = False) -> dict:
    """產生一把新的隨機 32 bytes 金鑰並寫進檔案。回傳的資訊不含金鑰。"""
    if fmt not in ("env", "raw"):
        raise SealError("bad_input", "金鑰檔格式只能是 env 或 raw。")
    if not _NAME_RE.match(name):
        raise SealError("bad_input", "金鑰名稱只能用英文字母、數字、底線，且不能以數字開頭。")
    p = Path(path)
    if p.is_dir():
        raise SealError("bad_input", "金鑰檔的路徑是一個資料夾。")
    if not p.parent.is_dir():
        raise SealError("input_missing", "要放金鑰檔的資料夾不存在。")
    raw = secrets.token_bytes(KEY_LEN)
    if fmt == "raw":
        body = raw
    else:
        b64 = base64.urlsafe_b64encode(raw).decode("ascii")
        body = (
            "# CryptoTool Pro key file. Keep it secret and keep a copy OFF this computer.\n"
            f"{name}=b64:{b64}\n"
        ).encode("ascii")
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0)
    flags |= os.O_TRUNC if force else os.O_EXCL
    try:
        fd = os.open(p, flags, 0o600)
    except FileExistsError:
        raise SealError(
            "output_exists", "金鑰檔已經存在，沒有覆蓋。",
            action="換一個檔名；確定要換掉舊金鑰才加 --force（舊金鑰加密的檔案會再也打不開）。",
        ) from None
    except OSError as exc:
        raise SealError("io_error", "寫不了金鑰檔。", detail=type(exc).__name__) from None
    with os.fdopen(fd, "wb") as fh:
        fh.write(body)
    return {"path": str(p), "format": fmt, "name": name if fmt == "env" else None,
            "key_id": key_id(raw)}
