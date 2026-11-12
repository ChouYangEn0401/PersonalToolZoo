"""age 身分檔（私鑰檔）：讀、寫、密語保護。

格式與 ``age-keygen`` 相同，可以放多把：

    # created: 2026-01-02T15:04:05+08:00
    # public key: age1…
    AGE-SECRET-KEY-1…

另外：
* 讀取時也接受 ``.env`` 風格的行：``NAME=AGE-SECRET-KEY-1…``（可加 ``export ``、引號）；
  其他不是私鑰的 ``NAME=值`` 設定行會略過。寫出一律用 age-keygen 格式。
* 「用密語保護的身分檔」＝把上面的文字用 age 加密、收件人是 scrypt（密語），
  這是 age 的標準做法（``age -d`` 讀身分檔時遇到 age 檔頭就會要密語）。
  讀取時看到 age 檔頭或文字封裝，會呼叫 ``passphrase_provider()`` 取得密語。
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path
from typing import Callable, Iterable

try:  # 測試時是 crypto_tool.agefmt；從 GUI__Encrypter.py 執行時 crypto_tool/ 在 sys.path 上，是 agefmt
    from ..sealed.errors import SealError
except ImportError:  # pragma: no cover - 依執行方式而定
    from sealed.errors import SealError
from ._common import fail
from ._fileio import as_path, atomic_write, check_output
from .api import decrypt_bytes, detect, encrypt_bytes
from .recipients import (
    DEFAULT_SCRYPT_WORK_FACTOR, MAX_SCRYPT_WORK_FACTOR, ScryptIdentity, ScryptRecipient,
    X25519Identity, parse_identity,
)

MAX_IDENTITY_FILE = 1 << 24  # 16 MiB，與 age 參考實作相同
_ENV_LINE = re.compile(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)")

PassphraseProvider = Callable[[], str]


def _as_bytes(text) -> bytes:
    if isinstance(text, str):
        return text.encode("utf-8")
    if isinstance(text, (bytes, bytearray)):
        return bytes(text)
    raise fail("bad_input", "身分檔內容必須是文字或位元組。")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip()
    return value


def is_encrypted_identity_file(data) -> bool:
    """內容是不是「用密語保護的身分檔」（age 檔頭或文字封裝）。"""
    return detect(_as_bytes(data)[:2048]) is not None


def parse_identity_file(text, passphrase_provider: PassphraseProvider | None = None,
                        *, max_work_factor: int = MAX_SCRYPT_WORK_FACTOR) -> list[X25519Identity]:
    """解讀身分檔內容（str 或 bytes），回傳私鑰清單（至少一把）。

    內容是 age 加密的（密語保護）時，呼叫 ``passphrase_provider()`` 取得密語；
    沒有提供 provider 就丟 ``key_missing``。錯誤訊息只說第幾行，不會印出內容。
    """
    data = _as_bytes(text)
    if len(data) > MAX_IDENTITY_FILE:
        raise fail("bad_key_format", "身分檔太大（超過 16 MiB），不像是身分檔。", "確認選對了檔案。")
    if detect(data[:2048]) is not None:
        if passphrase_provider is None:
            raise fail("key_missing", "這個身分檔有密語保護，需要密語才能讀取。", "輸入身分檔的密語。",
                       "identity-file-encrypted")
        passphrase = passphrase_provider()
        if not isinstance(passphrase, str) or passphrase == "":
            raise fail("key_missing", "沒有輸入身分檔的密語。", "輸入身分檔的密語。", "identity-file-encrypted")
        data = decrypt_bytes(data, [ScryptIdentity(passphrase, max_work_factor)])
        if detect(data[:2048]) is not None:
            raise fail("bad_key_format", "身分檔解開後還是加密的，不支援多層保護的身分檔。")
    return _parse_plain(data)


def _parse_plain(data: bytes) -> list[X25519Identity]:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise fail("bad_key_format", "身分檔不是 UTF-8 文字。", "確認選對了檔案。") from None
    found: list[X25519Identity] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        candidate = None
        if line.startswith("AGE-"):
            candidate = line
        else:
            m = _ENV_LINE.fullmatch(line)
            if m is None:
                raise fail("bad_key_format", f"身分檔第 {number} 行看不懂（不是私鑰、註解或 NAME=值）。",
                           "確認身分檔沒有被改到；私鑰行應以 AGE-SECRET-KEY-1 開頭。")
            value = _unquote(m.group(2))
            if value.startswith("AGE-"):
                candidate = value
        if candidate is None:
            continue  # 其他設定（例如公鑰、路徑）不是私鑰，略過
        try:
            ident = parse_identity(candidate)
        except SealError as exc:  # 補上行號；原本的訊息就不含內容
            raise fail(exc.code, f"身分檔第 {number} 行的私鑰無法使用：{exc.reason}", exc.action) from None
        if ident not in found:
            found.append(ident)
    if not found:
        raise fail("key_missing", "身分檔裡沒有任何私鑰（AGE-SECRET-KEY-1…）。", "確認選對了身分檔。")
    return found


def load_identity_file(path, passphrase_provider: PassphraseProvider | None = None,
                       *, max_work_factor: int = MAX_SCRYPT_WORK_FACTOR) -> list[X25519Identity]:
    p = as_path(path, "身分檔")
    if not p.is_file():
        raise fail("input_missing", "找不到身分檔。", "確認路徑是否正確。")
    try:
        with open(p, "rb") as fh:
            data = fh.read(MAX_IDENTITY_FILE + 1)
    except OSError as exc:
        raise fail("io_error", "讀不到身分檔。", "確認權限後再試。", type(exc).__name__) from None
    return parse_identity_file(data, passphrase_provider, max_work_factor=max_work_factor)


def _now() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def format_identity_file(identities, *, created: str | None = None) -> str:
    """寫成 age-keygen 格式的文字（每把三行，中間空一行）。"""
    ids = list(identities) if not isinstance(identities, X25519Identity) else [identities]
    if not ids or not all(isinstance(i, X25519Identity) for i in ids):
        raise fail("bad_input", "要寫進身分檔的必須是 X25519 私鑰。")
    stamp = created or _now()
    blocks = [f"# created: {stamp}\n# public key: {i.public_key}\n{i.secret_key_string()}\n" for i in ids]
    return "\n".join(blocks)


def write_identity_file(path, identities: Iterable[X25519Identity] | X25519Identity, *,
                        passphrase: str | None = None, armor: bool = True, overwrite: bool = False,
                        work_factor: int = DEFAULT_SCRYPT_WORK_FACTOR, created: str | None = None) -> Path:
    """寫出身分檔（權限 0600）。給了 passphrase 就寫成 age 加密（scrypt）的身分檔，
    預設用文字封裝，方便放在 ``.env`` 之類的文字檔位置。"""
    p = as_path(path, "身分檔")
    check_output(p, overwrite)
    content = format_identity_file(identities, created=created).encode("utf-8")
    if passphrase is not None:
        content = encrypt_bytes(content, [ScryptRecipient(passphrase, work_factor)], armor=armor)
    atomic_write(p, overwrite, lambda fh: fh.write(content))
    if os.name != "nt":
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
    return p
