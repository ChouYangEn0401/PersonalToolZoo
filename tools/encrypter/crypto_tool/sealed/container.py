"""ISD2 容器格式：標準的認證加密，分塊串流。

只用 ``cryptography`` 套件裡經過審查的元件，沒有任何自製的加密步驟：

* 加密：AES-256-GCM 或 ChaCha20-Poly1305（都是「認證加密」，解密時會驗證內容沒被改過）
* 密語 -> 金鑰：scrypt
* 每個檔案自己的金鑰：HKDF-SHA256（主金鑰 + 檔頭裡的隨機 salt）

檔案長相（檔頭固定 64 bytes，後面接一塊一塊的密文）::

    0   4  魔術字 "ISD2"
    4   1  格式版本 (1)
    5   1  加密法     1 = AES-256-GCM, 2 = ChaCha20-Poly1305
    6   1  金鑰來源   0 = 直接給 32 bytes 金鑰, 1 = 密語經 scrypt
    7   1  內容種類   0 = 單一檔案, 1 = tar（資料夾）
    8   4  每塊明文大小 (big-endian)
    12  1  scrypt log2(N)   （不是密語時為 0）
    13  1  scrypt r
    14  1  scrypt p
    15  1  保留 (0)
    16 16  salt（每個檔案隨機）
    32  7  nonce 前綴（每個檔案隨機）
    39  9  保留 (0)
    48 16  金鑰檢查碼（HKDF 另外導出的，用來分辨「金鑰不對」與「檔案被改過」）

    之後每一塊 = 密文 + 16 bytes 驗證碼。
    nonce = 前綴(7) + 第幾塊(4, big-endian) + 是不是最後一塊(1)
    每一塊都把整個檔頭當作 AAD 一起驗證。

這個排法的效果：改檔頭、改任何一塊、把塊對調、刪掉結尾、在結尾加東西，解密都會失敗。
"""

from __future__ import annotations

import hmac
import os
import struct
import unicodedata
from dataclasses import dataclass, field

from .errors import SealError

try:  # 缺套件時讓呼叫端拿到明確的錯誤，而不是一長串 traceback
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    _IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # pragma: no cover - 只有環境沒裝好才會走到
    _IMPORT_ERROR = exc

MAGIC = b"ISD2"
FORMAT_VERSION = 1
HEADER_LEN = 64
TAG_LEN = 16
KEY_LEN = 32
DEFAULT_CHUNK_SIZE = 1024 * 1024
MAX_CHUNK_SIZE = 64 * 1024 * 1024
EXTENSION = ".isd2"

AEAD_IDS = {"aes-256-gcm": 1, "chacha20-poly1305": 2}
AEAD_NAMES = {v: k for k, v in AEAD_IDS.items()}
KDF_RAW, KDF_SCRYPT = 0, 1
KDF_NAMES = {KDF_RAW: "raw-key", KDF_SCRYPT: "scrypt"}
PAYLOAD_FILE, PAYLOAD_TAR = 0, 1
PAYLOAD_NAMES = {PAYLOAD_FILE: "file", PAYLOAD_TAR: "folder"}

# scrypt：N = 2**17、r = 8、p = 1（約用 128 MB 記憶體，目前一般建議的互動式強度）
SCRYPT_LOG_N = 17
SCRYPT_R = 8
SCRYPT_P = 1
# 解密時願意接受的上限：擋掉惡意檔頭要求幾 GB 記憶體
_MAX_LOG_N, _MAX_R, _MAX_P = 20, 16, 4

_HEADER_STRUCT = struct.Struct(">4sBBBBIBBBB16s7s9s16s")
assert _HEADER_STRUCT.size == HEADER_LEN


def require_backend() -> None:
    if _IMPORT_ERROR is not None:
        raise SealError(
            "dependency_missing",
            "找不到加密套件 cryptography。",
            action="用這個工具自己的環境執行（tools\\encrypter\\run.bat），"
                   "或依 requirements.txt 重新建立環境。",
            detail=type(_IMPORT_ERROR).__name__,
        )


@dataclass(frozen=True)
class KeyMaterial:
    """金鑰來源。``raw`` 是 32 bytes 金鑰，``passphrase`` 是密語；可以同時有（見 keys.py）。

    ``repr`` 不會印出內容，避免不小心進到 log。
    """

    raw: bytes | None = field(default=None, repr=False)
    passphrase: str | None = field(default=None, repr=False)
    prefer_passphrase: bool = False

    def kdf_for_encrypt(self) -> int:
        if self.raw is not None and not self.prefer_passphrase:
            return KDF_RAW
        if self.passphrase is not None:
            return KDF_SCRYPT
        if self.raw is not None:
            return KDF_RAW
        raise SealError("key_missing", "沒有提供金鑰或密語。")


@dataclass(frozen=True)
class Header:
    aead: int
    kdf: int
    payload: int
    chunk_size: int
    log_n: int
    r: int
    p: int
    salt: bytes
    nonce_prefix: bytes
    key_check: bytes

    def pack(self) -> bytes:
        return _HEADER_STRUCT.pack(
            MAGIC, FORMAT_VERSION, self.aead, self.kdf, self.payload, self.chunk_size,
            self.log_n, self.r, self.p, 0, self.salt, self.nonce_prefix, b"\0" * 9,
            self.key_check,
        )

    def describe(self) -> dict:
        return {
            "format": "isd2",
            "format_version": FORMAT_VERSION,
            "cipher": AEAD_NAMES[self.aead],
            "kdf": KDF_NAMES[self.kdf],
            "payload": PAYLOAD_NAMES[self.payload],
            "chunk_size": self.chunk_size,
        }


def parse_header(blob: bytes) -> Header:
    """讀檔頭並檢查每個欄位都在允許範圍內。不需要金鑰。"""
    if len(blob) < 4 or blob[:4] != MAGIC:
        if blob.lstrip()[:8] == b"CONTENT=":
            raise SealError(
                "legacy_format",
                "這是舊版格式（.isd）的檔案，命令列不處理舊格式。",
                action="用視窗程式的「關於 → 開啟舊版工具」解密。",
            )
        raise SealError("unsupported_format", "這不是這個工具加密的檔案（不是 ISD2 格式）。")
    if len(blob) < HEADER_LEN:
        raise SealError("corrupt", "檔案不完整：檔頭被截斷。")
    (_magic, version, aead, kdf, payload, chunk_size, log_n, r, p, reserved1,
     salt, nonce_prefix, reserved2, key_check) = _HEADER_STRUCT.unpack(blob[:HEADER_LEN])
    if version != FORMAT_VERSION:
        raise SealError(
            "unsupported_format",
            f"這個檔案是格式第 {version} 版，這個程式只認得第 {FORMAT_VERSION} 版。",
            action="更新這個工具後再試。",
        )
    ok = (
        aead in AEAD_NAMES and kdf in KDF_NAMES and payload in PAYLOAD_NAMES
        and 1 <= chunk_size <= MAX_CHUNK_SIZE
        and reserved1 == 0 and reserved2 == b"\0" * 9
    )
    if ok and kdf == KDF_SCRYPT:
        ok = 1 <= log_n <= _MAX_LOG_N and 1 <= r <= _MAX_R and 1 <= p <= _MAX_P
    elif ok:
        ok = log_n == 0 and r == 0 and p == 0
    if not ok:
        raise SealError("corrupt", "檔頭的內容不合理，檔案可能損壞或被改過。")
    return Header(aead, kdf, payload, chunk_size, log_n, r, p, salt, nonce_prefix, key_check)


def _master_key(material: KeyMaterial, kdf: int, salt: bytes, log_n: int, r: int, p: int) -> bytes:
    if kdf == KDF_RAW:
        if material.raw is None:
            raise SealError(
                "bad_key_format",
                "這個檔案是用「金鑰檔」加密的，需要 32 bytes 的金鑰，不是密語。",
                action="改用當初加密時的金鑰檔（--key-file）或環境變數（--key-env）。",
            )
        if len(material.raw) != KEY_LEN:
            raise SealError("bad_key_format", "金鑰長度不對，必須是 32 bytes。")
        return material.raw
    if material.passphrase is None:
        raise SealError(
            "bad_key_format",
            "這個檔案是用「密語」加密的，需要密語，不是金鑰檔。",
            action="改用當初加密時的密語（--passphrase-stdin）。",
        )
    if not material.passphrase:
        raise SealError("key_missing", "密語是空的。")
    secret = unicodedata.normalize("NFC", material.passphrase).encode("utf-8")
    return Scrypt(salt=salt, length=KEY_LEN, n=1 << log_n, r=r, p=p).derive(secret)


def _derive(master: bytes, salt: bytes) -> tuple[bytes, bytes]:
    """主金鑰 -> (這個檔案的加密金鑰, 金鑰檢查碼)。兩者用不同的 info，互相推不出來。"""
    enc = HKDF(hashes.SHA256(), KEY_LEN, salt, b"ISD2 v1 chunk key").derive(master)
    check = HKDF(hashes.SHA256(), 16, salt, b"ISD2 v1 key check").derive(master)
    return enc, check


def _cipher(aead: int, key: bytes):
    return AESGCM(key) if aead == AEAD_IDS["aes-256-gcm"] else ChaCha20Poly1305(key)


def _nonce(prefix: bytes, counter: int, final: bool) -> bytes:
    if counter > 0xFFFFFFFF:
        raise SealError("bad_input", "檔案太大，超過這個格式能處理的塊數。")
    return prefix + struct.pack(">IB", counter, 1 if final else 0)


class SealWriter:
    """把寫進來的明文分塊加密後寫到 ``fileobj``。用完一定要 ``close()``。"""

    def __init__(
        self,
        fileobj,
        material: KeyMaterial,
        *,
        aead: str = "aes-256-gcm",
        payload: int = PAYLOAD_FILE,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        scrypt_log_n: int = SCRYPT_LOG_N,
        _salt: bytes | None = None,
        _nonce_prefix: bytes | None = None,
    ):
        require_backend()
        if aead not in AEAD_IDS:
            raise SealError("bad_input", "不支援的加密法。",
                            action="可用的有：" + "、".join(AEAD_IDS))
        if not 1 <= chunk_size <= MAX_CHUNK_SIZE:
            raise SealError("bad_input", "分塊大小不合理。")
        kdf = material.kdf_for_encrypt()
        salt = _salt if _salt is not None else os.urandom(16)
        prefix = _nonce_prefix if _nonce_prefix is not None else os.urandom(7)
        log_n, r, p = (scrypt_log_n, SCRYPT_R, SCRYPT_P) if kdf == KDF_SCRYPT else (0, 0, 0)
        master = _master_key(material, kdf, salt, log_n, r, p)
        key, check = _derive(master, salt)
        self.header = Header(AEAD_IDS[aead], kdf, payload, chunk_size, log_n, r, p,
                             salt, prefix, check)
        self._aad = self.header.pack()
        self._aead = _cipher(self.header.aead, key)
        self._out = fileobj
        self._buf = bytearray()
        self._counter = 0
        self._closed = False
        self.bytes_in = 0
        self._out.write(self._aad)

    def write(self, data) -> int:
        if self._closed:
            raise ValueError("write to closed SealWriter")
        self._buf += data
        self.bytes_in += len(data)
        size = self.header.chunk_size
        # 嚴格大於才送出，確保最後一定留下一塊標成「結尾」的資料
        while len(self._buf) > size:
            self._emit(bytes(self._buf[:size]), final=False)
            del self._buf[:size]
        return len(data)

    def _emit(self, chunk: bytes, final: bool) -> None:
        nonce = _nonce(self.header.nonce_prefix, self._counter, final)
        self._out.write(self._aead.encrypt(nonce, chunk, self._aad))
        self._counter += 1

    def close(self) -> None:
        if self._closed:
            return
        self._emit(bytes(self._buf), final=True)
        self._buf.clear()
        self._closed = True


class SealReader:
    """驗證並解密。每一塊都通過驗證才會交出明文；讀到結尾才算整個檔案完整。"""

    def __init__(self, fileobj, material: KeyMaterial):
        require_backend()
        self._in = fileobj
        self.header = parse_header(fileobj.read(HEADER_LEN))
        h = self.header
        master = _master_key(material, h.kdf, h.salt, h.log_n, h.r, h.p)
        key, check = _derive(master, h.salt)
        if not hmac.compare_digest(check, h.key_check):
            raise SealError(
                "wrong_key",
                "金鑰或密語不對（或檔頭被改過），無法解密。",
                action="確認用的是當初加密這個檔案的那一把金鑰或密語。",
            )
        self._aad = h.pack()
        self._aead = _cipher(h.aead, key)
        self._blob_len = h.chunk_size + TAG_LEN
        self._pending = self._in.read(self._blob_len)
        self._counter = 0
        self._buf = b""
        self._pos = 0
        self._done = False
        if not self._pending:
            raise SealError("corrupt", "檔案不完整：只有檔頭，內容被截斷。")

    def _fill(self) -> None:
        current = self._pending
        self._pending = self._in.read(self._blob_len)
        final = not self._pending
        if len(current) < TAG_LEN or (not final and len(current) != self._blob_len):
            raise SealError("corrupt", "檔案不完整或被改過（資料塊長度不對）。")
        nonce = _nonce(self.header.nonce_prefix, self._counter, final)
        try:
            self._buf = self._aead.decrypt(nonce, current, self._aad)
            self._pos = 0
        except InvalidTag:
            raise SealError(
                "corrupt",
                "檔案被改過、截斷或損壞，驗證沒有通過，沒有輸出任何內容。",
                action="重新取得一份完整的加密檔（例如從備份）。",
            ) from None
        self._counter += 1
        self._done = final

    def read(self, size: int = -1) -> bytes:
        parts = []
        want = size if size is not None and size >= 0 else None
        while want is None or want > 0:
            if self._pos >= len(self._buf):
                if self._done:
                    break
                self._fill()
                continue
            end = len(self._buf) if want is None else min(len(self._buf), self._pos + want)
            take = self._buf[self._pos:end]
            self._pos = end
            parts.append(take)
            if want is not None:
                want -= len(take)
        return b"".join(parts)

    def drain(self) -> None:
        """把剩下的內容讀完並驗證（確認結尾沒有被截斷或加料）。"""
        while self.read(1024 * 1024):
            pass
