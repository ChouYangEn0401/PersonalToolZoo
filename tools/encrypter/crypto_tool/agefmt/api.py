"""age v1 的串流與檔案層 API（給 CLI／視窗程式整合用）。

* ``encrypt_stream``／``decrypt_stream``：在已開啟的二進位串流上工作，記憶體不隨大小成長。
  注意 ``decrypt_stream`` 會邊驗證邊寫出「已驗證的分塊」；要「全部驗證通過才出現結果」
  請用 ``decrypt_file``。
* ``encrypt_file``／``decrypt_file``：輸出先寫暫存檔、fsync，
  全部成功才原子換名；失敗時刪掉暫存檔。
* ``inspect``：不需要金鑰，看標頭與大小。
* 結果物件只含公開資訊（種類、數量、大小、公鑰），不含金鑰、密語或明文。
"""

from __future__ import annotations

import io
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from ._common import fail, header_error
from ._fileio import as_path, atomic_write, check_input, check_output, same_file
from .armor import BEGIN, MAX_WHITESPACE, ArmorReader, ArmorWriter, looks_armored
from .header import VERSION_PREFIX, Header, Source, parse_header, seal_header, verify_mac
from .recipients import (
    FILE_KEY_SIZE, ScryptIdentity, ScryptRecipient, X25519Identity, X25519Recipient,
    parse_identity, parse_recipient, scrypt_not_alone,
)
from .stream import NONCE_SIZE, decrypt_payload, encrypt_payload, payload_key, plaintext_size

Progress = Callable[[int, int], None]
_HEAD = MAX_WHITESPACE + len(BEGIN)


# --- 結果物件 -------------------------------------------------------------------

@dataclass(frozen=True)
class EncryptResult:
    output: str | None
    armored: bool
    recipient_types: tuple[str, ...]
    recipient_count: int
    plaintext_size: int
    output_size: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DecryptResult:
    output: str | None
    armored: bool
    stanza_types: tuple[str, ...]
    matched: str            # "X25519 age1…"（公鑰）或 "scrypt"
    plaintext_size: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgeInfo:
    path: str | None
    armored: bool
    stanza_types: tuple[str, ...]
    stanza_counts: dict
    header_size: int          # 二進位標頭位元組數（含 MAC 行）
    payload_size: int         # 標頭之後的位元組數（含 16 位元組 nonce）
    plaintext_size: int | None  # 由大小推算；大小不合法（截斷、加料）時是 None
    file_size: int
    passphrase_protected: bool
    scrypt_work_factor: int | None

    def to_dict(self) -> dict:
        return asdict(self)


# --- 偵測 -----------------------------------------------------------------------

def detect(head: bytes) -> str | None:
    """看檔頭判斷：``"binary"``、``"armor"`` 或 None（不是 age）。"""
    if not isinstance(head, (bytes, bytearray)):
        return None
    head = bytes(head)
    if head.startswith(VERSION_PREFIX):
        return "binary"
    if head[:_HEAD].lstrip(b" \t\r\n\x0b\x0c").startswith(BEGIN):
        return "armor"
    return None


def is_age(head_bytes: bytes) -> bool:
    """檔頭是不是 age 檔（二進位 ``age-encryption.org/…`` 或文字封裝）。

    建議傳入檔案開頭至少 1100 位元組（armor 前面可以有最多 1024 位元組空白）。
    版本不是 v1 的也回傳 True，交給解密時說明「不支援的版本」。
    """
    return detect(head_bytes) is not None


# --- 內部：收件人／身分 ------------------------------------------------------------

def _as_list(items, single_types) -> list:
    if items is None:
        return []
    if isinstance(items, (str, bytes) + single_types):
        return [items]
    return list(items)


def normalize_recipients(recipients) -> list:
    out: list = []
    for r in _as_list(recipients, (X25519Recipient, ScryptRecipient, X25519Identity)):
        if isinstance(r, str):
            r = parse_recipient(r)
        elif isinstance(r, X25519Identity):
            r = r.recipient
        elif not isinstance(r, (X25519Recipient, ScryptRecipient)):
            raise fail("bad_input", "收件人必須是 age1 公鑰或密語收件人。")
        if r not in out:
            out.append(r)
    if not out:
        raise fail("key_missing", "沒有指定任何收件人（公鑰或密語）。", "至少提供一把 age1 公鑰或一個密語。")
    if any(isinstance(r, ScryptRecipient) for r in out) and len(out) > 1:
        raise fail(
            "bad_input",
            "密語不能和其他收件人放在同一個 age 檔（age 規格規定密語必須是唯一的收件人）。",
            "要「密語＋萬用鎖」請改用 PGP 模式；或全部改用金鑰（age1 公鑰）。",
            "scrypt-not-alone",
        )
    return out


def _normalize_identities(identities) -> list:
    out: list = []
    for i in _as_list(identities, (X25519Identity, ScryptIdentity)):
        if isinstance(i, str):
            i = parse_identity(i)
        elif not isinstance(i, (X25519Identity, ScryptIdentity)):
            raise fail("bad_input", "身分必須是 age 私鑰或密語。")
        out.append(i)
    return out  # 空清單要等標頭解析完才報錯（先判斷檔案本身對不對）


def _describe(identity) -> str:
    if isinstance(identity, X25519Identity):
        return "X25519 " + identity.public_key
    return "scrypt"


def _unwrap(header: Header, identities: list) -> tuple[bytes, str]:
    types = header.stanza_types
    if "scrypt" in types and len(types) != 1:
        raise scrypt_not_alone()
    if not identities:
        raise fail("key_missing", "沒有提供任何私鑰或密語，無法解密。", "提供身分檔（私鑰）或密語。")
    for ident in identities:
        file_key = ident.unwrap(header.stanzas)
        if file_key is not None:
            if len(file_key) != FILE_KEY_SIZE:  # 長度已在前面檢查，這裡只是保險
                raise header_error("file-key-length")
            verify_mac(file_key, header)
            return file_key, _describe(ident)
    has_scrypt = "scrypt" in types
    only_pass = all(isinstance(i, ScryptIdentity) for i in identities)
    only_keys = all(isinstance(i, X25519Identity) for i in identities)
    if has_scrypt and only_keys:
        reason, action = "這個檔案是用密語加密的，提供的私鑰打不開。", "改用密語解密。"
    elif not has_scrypt and only_pass:
        reason, action = "這個檔案是用金鑰加密的，密語打不開。", "改用對應的私鑰（身分檔）解密。"
    elif has_scrypt:
        reason, action = "密語不對。", "確認密語（大小寫、空白、輸入法）後再試。"
    else:
        reason, action = "提供的私鑰都不是這個檔案的收件人。", "確認用的是正確的身分檔，或改用萬用鎖的私鑰。"
    raise fail("wrong_key", reason, action, "no-match")


# --- 內部：讀來源 -------------------------------------------------------------------

def _open_source(raw, armor: bool | None) -> tuple[Source, bool, ArmorReader | None]:
    base = Source(raw)
    armored = looks_armored(base.peek(_HEAD)) if armor is None else bool(armor)
    if armored:
        reader = ArmorReader(base)
        return Source(reader), True, reader
    return base, False, None


def _read_nonce(src: Source) -> bytes:
    nonce = src.read(NONCE_SIZE)
    if len(nonce) != NONCE_SIZE:
        raise header_error("missing-nonce", "age 檔在標頭之後就結束了（缺少內容），檔案被截斷。")
    return nonce


class _Counter:
    """數寫出了多少位元組。"""

    def __init__(self, write):
        self._write = write
        self.n = 0

    def write(self, data: bytes) -> None:
        self._write(data)
        self.n += len(data)


# --- 串流 API -----------------------------------------------------------------------

def encrypt_stream(src, dst, recipients, *, armor: bool = False,
                   progress: Callable[[int], None] | None = None) -> EncryptResult:
    """把 src（二進位可讀）加密寫進 dst（二進位可寫）。"""
    recips = normalize_recipients(recipients)
    file_key = os.urandom(FILE_KEY_SIZE)
    header = seal_header(file_key, [r.wrap(file_key) for r in recips])
    counted = _Counter(dst.write)
    writer = ArmorWriter(counted) if armor else counted
    writer.write(header.marshal())
    nonce = os.urandom(NONCE_SIZE)
    writer.write(nonce)
    size = encrypt_payload(src.read, writer.write, payload_key(file_key, nonce), progress)
    if armor:
        writer.close()
    return EncryptResult(None, bool(armor), tuple(r.kind for r in recips), len(recips), size, counted.n)


def decrypt_stream(src, dst, identities, *, armor: bool | None = None,
                   progress: Callable[[int], None] | None = None) -> DecryptResult:
    """解密 src 寫進 dst。armor=None 時自動辨識文字封裝。

    出錯時 dst 可能已經有「錯誤之前、已驗證的分塊」；要全有或全無請用 ``decrypt_file``。
    """
    ids = _normalize_identities(identities)
    source, armored, _ = _open_source(src, armor)
    header = parse_header(source)
    file_key, matched = _unwrap(header, ids)
    nonce = _read_nonce(source)
    total = 0
    for chunk in decrypt_payload(source.read, payload_key(file_key, nonce)):
        dst.write(chunk)
        total += len(chunk)
        if progress:
            progress(total)
    return DecryptResult(None, armored, header.stanza_types, matched, total)


# --- 檔案 API -----------------------------------------------------------------------

def _progress_adapter(progress: Progress | None, total: int):
    if progress is None:
        return None
    return lambda done: progress(done, total)


def encrypt_file(src, dst, recipients, *, armor: bool = False, overwrite: bool = False,
                 progress: Progress | None = None) -> EncryptResult:
    """加密一個檔案。progress(已處理明文位元組, 輸入檔大小)。"""
    src_p, dst_p = as_path(src, "輸入"), as_path(dst, "輸出")
    size = check_input(src_p)
    if same_file(src_p, dst_p):
        raise fail("bad_input", "輸出位置不能跟輸入是同一個檔案。")
    check_output(dst_p, overwrite)
    recips = normalize_recipients(recipients)

    def work(out):
        try:
            with open(src_p, "rb") as fin:
                return encrypt_stream(fin, out, recips, armor=armor,
                                      progress=_progress_adapter(progress, size))
        except FileNotFoundError:
            raise fail("input_missing", "找不到輸入檔。") from None

    r = atomic_write(dst_p, overwrite, work)
    return EncryptResult(str(dst_p), r.armored, r.recipient_types, r.recipient_count,
                         r.plaintext_size, r.output_size)


def decrypt_file(src, dst, identities, *, overwrite: bool = False,
                 progress: Progress | None = None) -> DecryptResult:
    """解密一個檔案：全部驗證通過才出現 dst；任何失敗都不留下半個檔案。"""
    src_p, dst_p = as_path(src, "輸入"), as_path(dst, "輸出")
    size = check_input(src_p)
    if same_file(src_p, dst_p):
        raise fail("bad_input", "輸出位置不能跟輸入是同一個檔案。")
    check_output(dst_p, overwrite)
    ids = _normalize_identities(identities)

    def work(out):
        with open(src_p, "rb") as fin:
            return decrypt_stream(fin, out, ids, progress=_progress_adapter(progress, size))

    r = atomic_write(dst_p, overwrite, work)
    return DecryptResult(str(dst_p), r.armored, r.stanza_types, r.matched, r.plaintext_size)


def inspect(path) -> AgeInfo:
    """不需要金鑰：是否文字封裝、收件人區塊的種類與數量、標頭大小、推算的明文大小。"""
    p = as_path(path, "輸入")
    file_size = check_input(p)
    try:
        with open(p, "rb") as fin:
            source, armored, reader = _open_source(fin, None)
            header = parse_header(source)
            header_size = source.consumed
            while source.read(1 << 16):
                pass
            payload = source.consumed - header_size
    except OSError as exc:
        raise fail("io_error", "讀不到檔案。", "確認權限後再試。", type(exc).__name__) from None
    counts: dict = {}
    for t in header.stanza_types:
        counts[t] = counts.get(t, 0) + 1
    work_factor = None
    for s in header.stanzas:
        if s.type == "scrypt" and len(s.args) == 2 and s.args[1].isdigit() and len(s.args[1]) <= 3:
            work_factor = int(s.args[1])
    plain = plaintext_size(payload - NONCE_SIZE) if payload >= NONCE_SIZE else None
    return AgeInfo(str(p), armored, header.stanza_types, counts, header_size, payload, plain,
                   file_size, "scrypt" in counts, work_factor)


# --- 記憶體內的小工具（身分檔等小資料用）-------------------------------------------------

def encrypt_bytes(data: bytes, recipients, *, armor: bool = False) -> bytes:
    out = io.BytesIO()
    encrypt_stream(io.BytesIO(data), out, recipients, armor=armor)
    return out.getvalue()


def decrypt_bytes(data: bytes, identities, *, armor: bool | None = None) -> bytes:
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(data), out, identities, armor=armor)
    return out.getvalue()


__all__ = [
    "AgeInfo", "DecryptResult", "EncryptResult", "decrypt_bytes", "decrypt_file",
    "decrypt_stream", "detect", "encrypt_bytes", "encrypt_file", "encrypt_stream", "inspect",
    "is_age", "normalize_recipients",
]
