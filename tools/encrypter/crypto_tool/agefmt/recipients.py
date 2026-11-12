"""age 的原生收件人與身分：X25519（金鑰）與 scrypt（密語）。

* 收件人（recipient）＝上鎖用的公開資料：``age1…`` 公鑰，或密語。
* 身分（identity）＝開鎖用的祕密：``AGE-SECRET-KEY-1…`` 私鑰，或密語。

所有物件的 ``repr``／``str`` 都不含祕密；要取出私鑰文字必須明確呼叫 ``secret_key_string()``。
"""

from __future__ import annotations

import os
import re

from . import bech32
from ._common import (
    InvalidTag, ZERO_NONCE, b64_decode_raw, b64_encode_raw, chacha, fail, header_error,
    hkdf_sha256, scrypt_key, x25519_public, x25519_shared,
)
from .header import Stanza

FILE_KEY_SIZE = 16
X25519_LABEL = b"age-encryption.org/v1/X25519"
SCRYPT_LABEL = b"age-encryption.org/v1/scrypt"
SCRYPT_SALT_SIZE = 16
DEFAULT_SCRYPT_WORK_FACTOR = 18      # 與 age 參考實作的加密預設相同
MAX_SCRYPT_WORK_FACTOR = 22          # 與 age 參考實作解密時的預設上限相同
_WRAPPED_SIZE = FILE_KEY_SIZE + 16
_DIGITS = re.compile(r"[1-9][0-9]*")

PUBLIC_HRP = "age"
SECRET_HRP = "AGE-SECRET-KEY-"


def _aead_seal(key: bytes, file_key: bytes) -> bytes:
    return chacha(key).encrypt(ZERO_NONCE, file_key, None)


def _aead_open(key: bytes, body: bytes) -> bytes | None:
    try:
        return chacha(key).decrypt(ZERO_NONCE, body, None)
    except InvalidTag:
        return None


def _check_passphrase(passphrase) -> bytes:
    if not isinstance(passphrase, str):
        raise fail("bad_input", "密語必須是文字。")
    if passphrase == "":
        raise fail("key_missing", "密語是空的。", "輸入密語後再試。")
    return passphrase.encode("utf-8")


# --- X25519 ------------------------------------------------------------------

class X25519Recipient:
    """``age1…`` 公鑰。"""

    __slots__ = ("_public",)
    kind = "X25519"

    def __init__(self, public: bytes):
        if not isinstance(public, (bytes, bytearray)) or len(public) != 32:
            raise fail("bad_key_format", "公鑰長度不對（應為 32 位元組）。")
        self._public = bytes(public)

    @property
    def public_bytes(self) -> bytes:
        return self._public

    def __str__(self) -> str:
        return bech32.encode(PUBLIC_HRP, self._public)

    def __repr__(self) -> str:
        return f"X25519Recipient({self!s})"

    def __eq__(self, other) -> bool:
        return isinstance(other, X25519Recipient) and other._public == self._public

    def __hash__(self) -> int:
        return hash(("X25519", self._public))

    def wrap(self, file_key: bytes) -> Stanza:
        ephemeral = os.urandom(32)
        share = x25519_public(ephemeral)
        shared = x25519_shared(ephemeral, self._public)
        if shared is None:  # 公鑰是低階點：任何人都算得出共享祕密，拒絕
            raise fail("bad_key_format", "這把公鑰無效（是低階點），不能用來加密。",
                       "向對方重新索取公鑰。")
        key = hkdf_sha256(shared, share + self._public, X25519_LABEL)
        return Stanza("X25519", (b64_encode_raw(share).decode("ascii"),), _aead_seal(key, file_key))


class X25519Identity:
    """``AGE-SECRET-KEY-1…`` 私鑰。"""

    __slots__ = ("_secret", "_public")
    kind = "X25519"

    def __init__(self, secret: bytes):
        if not isinstance(secret, (bytes, bytearray)) or len(secret) != 32:
            raise fail("bad_key_format", "私鑰長度不對（應為 32 位元組）。")
        self._secret = bytes(secret)
        self._public = x25519_public(self._secret)

    @property
    def recipient(self) -> X25519Recipient:
        return X25519Recipient(self._public)

    @property
    def public_key(self) -> str:
        return str(self.recipient)

    def secret_key_string(self) -> str:
        """私鑰的 Bech32 文字（``AGE-SECRET-KEY-1…``）。只在要寫進身分檔時呼叫。"""
        return bech32.encode(SECRET_HRP, self._secret)

    def __repr__(self) -> str:
        return f"X25519Identity(public={self.public_key}, secret=<hidden>)"

    __str__ = __repr__

    def __reduce__(self):  # 不讓 pickle 把私鑰默默寫出去
        raise TypeError("X25519Identity cannot be pickled")

    def __eq__(self, other) -> bool:
        return isinstance(other, X25519Identity) and other._public == self._public

    def __hash__(self) -> int:
        return hash(("X25519-id", self._public))

    def unwrap(self, stanzas) -> bytes | None:
        """找出寫給自己的 X25519 區塊並解出 file key；都不是時回傳 None。

        照規格：第一個引數不是 ``X25519`` 的區塊一律忽略；是的話，引數數量、
        臨時公鑰的編碼與長度、本體長度不對就丟錯（不是「不符」）。
        """
        for s in stanzas:
            if s.type != "X25519":
                continue
            if len(s.args) != 1:
                raise header_error("x25519-arguments")
            try:
                share = b64_decode_raw(s.args[0].encode("ascii"))
            except ValueError:
                raise header_error("x25519-share-encoding") from None
            if len(share) != 32:
                raise header_error("x25519-share-length")
            if len(s.body) != _WRAPPED_SIZE:
                raise header_error("x25519-body-length")
            shared = x25519_shared(self._secret, share)
            if shared is None:
                raise header_error("x25519-low-order-share")
            key = hkdf_sha256(shared, share + self._public, X25519_LABEL)
            file_key = _aead_open(key, s.body)
            if file_key is not None:
                return file_key
        return None


def generate_identity() -> X25519Identity:
    """產生一把新的 X25519 私鑰（32 位元組 CSPRNG，與 age-keygen 相同）。"""
    return X25519Identity(os.urandom(32))


def parse_recipient(s: str) -> X25519Recipient:
    """解讀一個 ``age1…`` 公鑰。錯誤訊息不會把輸入印回去（以免輸入其實是私鑰）。"""
    if not isinstance(s, str):
        raise fail("bad_input", "公鑰必須是文字。")
    text = s.strip()
    if not text:
        raise fail("key_missing", "沒有提供公鑰。", "提供 age1 開頭的公鑰。")
    if text.upper().startswith("AGE-SECRET-KEY-"):
        raise fail("bad_key_format", "這是私鑰，不是公鑰；加密只需要對方的公鑰（age1 開頭）。",
                   "請不要把私鑰交給別人或貼在這裡；改用 age1 開頭的公鑰。")
    if text.startswith(("age1pq1", "age1tag")):
        raise fail("unsupported_format", "這個工具不支援後量子（age1pq）或硬體標籤（age1tag）收件人。",
                   "請對方改提供 X25519 公鑰（age-keygen 預設產生的 age1…）。")
    if text.startswith(("ssh-", "ecdsa-")):
        raise fail("unsupported_format", "這個工具不支援 SSH 公鑰收件人。",
                   "請對方提供 age1 開頭的公鑰。")
    try:
        hrp, data = bech32.decode(text)
    except bech32.Bech32Error:
        raise fail("bad_key_format", "公鑰格式不正確（不是有效的 age1 公鑰，可能少字、多字或打錯）。",
                   "重新複製完整的 age1 公鑰。") from None
    if hrp != PUBLIC_HRP:
        raise fail("bad_key_format", "這不是 age 的公鑰（開頭應為小寫 age1）。",
                   "重新複製完整的 age1 公鑰。")
    if len(data) != 32:
        raise fail("bad_key_format", "公鑰長度不對。", "重新複製完整的 age1 公鑰。")
    return X25519Recipient(data)


def parse_identity(s: str) -> X25519Identity:
    """解讀一個 ``AGE-SECRET-KEY-1…`` 私鑰。錯誤訊息不含輸入。"""
    if not isinstance(s, str):
        raise fail("bad_input", "私鑰必須是文字。")
    text = s.strip()
    if text.startswith("AGE-SECRET-KEY-PQ-1"):
        raise fail("unsupported_format", "這個工具不支援後量子（PQ）私鑰。",
                   "改用 X25519 私鑰（age-keygen 預設產生的）。")
    if text.startswith("AGE-PLUGIN-"):
        raise fail("unsupported_format", "這個工具不支援 age 外掛（plugin）私鑰。",
                   "改用 X25519 私鑰。")
    try:
        hrp, data = bech32.decode(text)
    except bech32.Bech32Error:
        raise fail("bad_key_format", "私鑰格式不正確（不是有效的 AGE-SECRET-KEY-1 私鑰）。",
                   "確認身分檔沒有被截斷或改到。") from None
    if hrp != SECRET_HRP or len(data) != 32:
        raise fail("bad_key_format", "私鑰格式不正確（不是 AGE-SECRET-KEY-1 開頭的 X25519 私鑰）。",
                   "確認身分檔沒有被截斷或改到。")
    return X25519Identity(data)


# --- scrypt（密語）------------------------------------------------------------

class ScryptRecipient:
    """用密語上鎖。規格規定：檔案裡有 scrypt 區塊時，它必須是唯一的區塊。"""

    __slots__ = ("_passphrase", "work_factor")
    kind = "scrypt"

    def __init__(self, passphrase: str, work_factor: int = DEFAULT_SCRYPT_WORK_FACTOR):
        self._passphrase = _check_passphrase(passphrase)
        if not isinstance(work_factor, int) or not 1 <= work_factor <= MAX_SCRYPT_WORK_FACTOR:
            raise fail("bad_input", f"密語運算成本必須是 1～{MAX_SCRYPT_WORK_FACTOR}（2 的次方數）。")
        self.work_factor = work_factor

    def __repr__(self) -> str:
        return f"ScryptRecipient(work_factor={self.work_factor}, passphrase=<hidden>)"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("ScryptRecipient cannot be pickled")

    def wrap(self, file_key: bytes) -> Stanza:
        salt = os.urandom(SCRYPT_SALT_SIZE)
        key = scrypt_key(self._passphrase, SCRYPT_LABEL + salt, self.work_factor)
        return Stanza("scrypt", (b64_encode_raw(salt).decode("ascii"), str(self.work_factor)),
                      _aead_seal(key, file_key))


class ScryptIdentity:
    """用密語開鎖。``max_work_factor`` 是可接受的上限（預設 22，與 age 參考實作相同）。"""

    __slots__ = ("_passphrase", "max_work_factor")
    kind = "scrypt"

    def __init__(self, passphrase: str, max_work_factor: int = MAX_SCRYPT_WORK_FACTOR):
        self._passphrase = _check_passphrase(passphrase)
        if not isinstance(max_work_factor, int) or not 1 <= max_work_factor <= 30:
            raise fail("bad_input", "密語運算成本上限必須是 1～30。")
        self.max_work_factor = max_work_factor

    def __repr__(self) -> str:
        return f"ScryptIdentity(max_work_factor={self.max_work_factor}, passphrase=<hidden>)"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("ScryptIdentity cannot be pickled")

    def unwrap(self, stanzas) -> bytes | None:
        if any(s.type == "scrypt" for s in stanzas) and len(stanzas) != 1:
            raise scrypt_not_alone()
        for s in stanzas:
            if s.type != "scrypt":
                continue
            if len(s.args) != 2:
                raise header_error("scrypt-arguments")
            try:
                salt = b64_decode_raw(s.args[0].encode("ascii"))
            except ValueError:
                raise header_error("scrypt-salt-encoding") from None
            if len(salt) != SCRYPT_SALT_SIZE:
                raise header_error("scrypt-salt-length")
            if not _DIGITS.fullmatch(s.args[1]):
                raise header_error("scrypt-work-factor-encoding")
            log_n = int(s.args[1]) if len(s.args[1]) <= 3 else 10 ** 9
            if log_n > self.max_work_factor:
                raise fail(
                    "unsupported_format",
                    f"這個密語檔要求的運算成本（2 的 {min(log_n, 999)} 次方）超過上限"
                    f"（2 的 {self.max_work_factor} 次方），為了避免耗盡記憶體而拒絕處理。",
                    "如果檔案來源可信，請改用 age 官方工具解開；來源不明的檔案可能是惡意的。",
                    "header:scrypt-work-factor-too-large",
                )
            if len(s.body) != _WRAPPED_SIZE:
                raise header_error("scrypt-body-length")
            key = scrypt_key(self._passphrase, SCRYPT_LABEL + salt, log_n)
            return _aead_open(key, s.body)
        return None


def scrypt_not_alone():
    return header_error(
        "scrypt-not-alone",
        "這個 age 檔同時有密語區塊和其他收件人，規格禁止這種組合（檔案可能被改過）。",
    )


def passphrase_recipient(passphrase: str, work_factor: int = DEFAULT_SCRYPT_WORK_FACTOR) -> ScryptRecipient:
    return ScryptRecipient(passphrase, work_factor)


def passphrase_identity(passphrase: str, max_work_factor: int = MAX_SCRYPT_WORK_FACTOR) -> ScryptIdentity:
    return ScryptIdentity(passphrase, max_work_factor)
