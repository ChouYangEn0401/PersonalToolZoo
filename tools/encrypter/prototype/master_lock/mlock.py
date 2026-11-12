"""Master-lock (萬用鎖) reference prototype: envelope encryption with key slots.

研究用的參考實作，**不是** Encrypter 的正式功能，也不被 GUI 或打包使用。
規格與設計理由見 ``tools/encrypter/docs/master-lock-research.md``。

做法（與 age、OpenPGP 多收件人、LUKS 金鑰槽同一類）：

* 每個檔案產生一把隨機的資料金鑰（DEK，32 bytes），只用它加密內容。
* DEK 再被「包」進一個或多個槽（slot）：萬用鎖（X25519 公鑰，RFC 9180 HPKE）、
  本次金鑰（32 bytes 隨機金鑰，HKDF + AES-256-GCM）、密語（scrypt + AES-256-GCM）。
  任何一個槽打得開，就能取得 DEK（「或」的關係，不是巢狀加密的「且」）。
* 換本次金鑰只要重包槽（rewrap），內容不必重新加密；要讓「曾經拿到 DEK 的人」也失效，
  要用 rekey（新 DEK、整份內容重新加密）。
* 檔頭以 DEK 衍生的 HMAC-SHA256 保護；內容分塊用 AES-256-GCM，nonce 規則同 age 的 STREAM。

只用 ``cryptography`` 的標準原語：AES-256-GCM、HKDF-SHA256、HMAC-SHA256、scrypt、
X25519 HPKE（RFC 9180，base mode）。不自創密碼學。

整份資料放在記憶體裡處理（bytes in / bytes out），格式本身支援串流，正式實作應改成串流。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Sequence, Union

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, hpke, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# ── 常數（改了任何一個都是新版格式） ───────────────────────────────────────────

MAGIC = b"MLOCK\x00"  # 6 bytes
FORMAT_VERSION = 1
SUITE_V1 = 1  # AES-256-GCM 內容 + HKDF-SHA256 + HMAC-SHA256 檔頭 + HPKE(X25519, HKDF-SHA256, AES-256-GCM)

DEFAULT_CHUNK_LOG2 = 16  # 64 KiB
MIN_CHUNK_LOG2 = 12
MAX_CHUNK_LOG2 = 20
MAX_SLOTS = 16
MAX_SLOT_BODY = 1024

DEK_LEN = 32
FILE_ID_LEN = 32
KEY_ID_LEN = 8
NONCE_LEN = 12
TAG_LEN = 16
MAC_LEN = 32
WRAPPED_DEK_LEN = DEK_LEN + TAG_LEN  # 48

SCRYPT_SALT_LEN = 16
SCRYPT_LOG_N_DEFAULT = 17  # 2^17 * r(8) * 128 B = 128 MiB 記憶體
SCRYPT_LOG_N_MIN = 15
SCRYPT_LOG_N_MAX = 20
SCRYPT_R = 8
SCRYPT_P = 1

SLOT_HPKE = 0x01  # 萬用鎖：X25519 公鑰
SLOT_SCRYPT = 0x02  # 密語
SLOT_KEY = 0x03  # 本次金鑰（32 bytes 隨機）
SLOT_GPG = 0x04  # 保留：DEK 由 gpg 包（原型不實作，視為未知型別保留原樣）

SLOT_NAMES = {SLOT_HPKE: "master", SLOT_SCRYPT: "passphrase", SLOT_KEY: "session-key", SLOT_GPG: "gpg"}

L_PAYLOAD = b"mlock/v1/payload"
L_HEADER = b"mlock/v1/header"
L_SLOT_HPKE = b"mlock/v1/slot/hpke"
L_SLOT_SCRYPT = b"mlock/v1/slot/scrypt"
L_SLOT_KEY = b"mlock/v1/slot/key"
L_KEY_ID = b"mlock/v1/key-id"
L_IDENTITY = b"mlock/v1/identity"

IDENTITY_MAGIC = b"MLOCKID\x00"
IDENTITY_VERSION = 1

# 檔頭固定段：magic(6) version(1) suite(1) chunk_log2(1) file_id(32) = 41 bytes
_CORE_LEN = len(MAGIC) + 3 + FILE_ID_LEN
_FIXED_LEN = _CORE_LEN + 4 + 1  # + generation(u32) + slot_count(u8)

_HPKE_SUITE = hpke.Suite(hpke.KEM.X25519, hpke.KDF.HKDF_SHA256, hpke.AEAD.AES_256_GCM)
_HPKE_ENC_LEN = 32

Rng = Callable[[int], bytes]


# ── 錯誤：穩定的代碼 + 補救建議，訊息裡永遠不放祕密 ──────────────────────────────

ERROR_HINTS = {
    "MLK-E01": ("NOT_MLOCK", "這不是萬用鎖格式的檔案（檔頭標記不符）。確認選對檔案。"),
    "MLK-E02": ("UNSUPPORTED_VERSION", "檔案格式版本比這個程式新或已淘汰。請用支援該版本的程式開啟。"),
    "MLK-E03": ("UNSUPPORTED_SUITE", "檔案使用未知或已停用的演算法組合。不會自動改用其他演算法（防降級）。"),
    "MLK-E04": ("MALFORMED_HEADER", "檔頭結構損毀或被截斷。從備份或雲端版本紀錄取回較早的副本。"),
    "MLK-E05": ("NO_MATCHING_SLOT", "提供的金鑰／密語打不開任何槽：可能是金鑰錯誤、已被換掉，或該槽被竄改。改用萬用鎖試試。"),
    "MLK-E06": ("HEADER_TAMPERED", "槽打開了，但檔頭驗證失敗：檔頭（槽清單、世代、參數）被改過。不要信任這份檔案，從備份取回。"),
    "MLK-E07": ("PAYLOAD_TAMPERED", "內容區塊驗證失敗：內容被改過或損毀。沒有輸出任何明文；從備份取回。"),
    "MLK-E08": ("TRUNCATED", "內容在最後一塊之前就結束了（檔案被截斷）。重新下載或從備份取回完整檔案。"),
    "MLK-E09": ("KDF_PARAMS_OUT_OF_RANGE", "密語槽的 scrypt 參數超出允許範圍（太弱或太耗記憶體）。用萬用鎖開啟後重建該槽。"),
    "MLK-E10": ("TOO_MANY_SLOTS", f"槽的數量超過上限（{MAX_SLOTS}）。先移除不用的槽。"),
    "MLK-E11": ("LAST_SLOT", "不能移除最後一個槽，否則檔案永遠打不開。"),
    "MLK-E12": ("MASTER_SLOT_PROTECTED", "這個動作會移除萬用鎖槽；萬用鎖是最後的取回手段，需明確確認（allow_remove_master）。"),
    "MLK-E13": ("NO_MASTER_SLOT", "新檔案必須至少有一個萬用鎖槽（require_master）。"),
    "MLK-E14": ("BAD_ARGUMENT", "參數不正確（金鑰長度、空密語、槽編號等）。"),
    "MLK-E15": ("BAD_IDENTITY_FILE", "萬用鎖私鑰檔損毀、密語錯誤或格式不符。改用另一份備份。"),
}


class MlockError(Exception):
    """所有失敗都用這個型別，``code`` 穩定（MLK-Exx），``name`` 是代碼名稱，``hint`` 是補救建議。"""

    def __init__(self, code: str, detail: str = ""):
        name, hint = ERROR_HINTS[code]
        self.code = code
        self.name = name
        self.hint = hint
        self.detail = detail
        msg = f"{code} {name}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


# ── 金鑰型別（repr 一律遮蔽祕密） ─────────────────────────────────────────────


class MasterRecipient:
    """萬用鎖的公鑰（32 bytes X25519）。可以放在日常電腦上，用來加密；打不開任何東西。"""

    def __init__(self, public_bytes: bytes):
        if not isinstance(public_bytes, (bytes, bytearray)) or len(public_bytes) != 32:
            raise MlockError("MLK-E14", "master public key must be 32 bytes")
        self.public_bytes = bytes(public_bytes)
        self._pk = X25519PublicKey.from_public_bytes(self.public_bytes)

    def __repr__(self) -> str:
        return f"MasterRecipient(fp={hashlib.sha256(self.public_bytes).hexdigest()[:16]})"


class MasterIdentity:
    """萬用鎖的私鑰。應離線保管；只有取回／換槽時才需要。"""

    def __init__(self, private_key: X25519PrivateKey):
        self._sk = private_key

    @classmethod
    def generate(cls) -> "MasterIdentity":
        return cls(X25519PrivateKey.generate())

    @classmethod
    def from_private_bytes(cls, raw: bytes) -> "MasterIdentity":
        if not isinstance(raw, (bytes, bytearray)) or len(raw) != 32:
            raise MlockError("MLK-E14", "master private key must be 32 bytes")
        return cls(X25519PrivateKey.from_private_bytes(bytes(raw)))

    def private_bytes(self) -> bytes:
        return self._sk.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )

    def recipient(self) -> MasterRecipient:
        return MasterRecipient(
            self._sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        )

    def __repr__(self) -> str:
        return f"MasterIdentity({self.recipient()!r}, private=<redacted>)"


class SessionKey:
    """本次金鑰：32 bytes 隨機金鑰（交給別人短期使用的那把）。同一把可以用來加槽與開槽。"""

    def __init__(self, key: bytes):
        if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
            raise MlockError("MLK-E14", "session key must be 32 bytes")
        self.key = bytes(key)

    @classmethod
    def generate(cls, rng: Rng = os.urandom) -> "SessionKey":
        return cls(rng(32))

    def __repr__(self) -> str:
        return "SessionKey(<redacted>)"


class Passphrase:
    """密語（人記得住的字串）。用 scrypt 衍生；``log_n`` 只在建立槽時使用。"""

    def __init__(self, text: str, log_n: int = SCRYPT_LOG_N_DEFAULT):
        if not isinstance(text, str) or not text:
            raise MlockError("MLK-E14", "passphrase must be a non-empty string")
        if not (SCRYPT_LOG_N_MIN <= log_n <= SCRYPT_LOG_N_MAX):
            raise MlockError("MLK-E09", f"log_n must be {SCRYPT_LOG_N_MIN}..{SCRYPT_LOG_N_MAX}")
        self._bytes = unicodedata.normalize("NFC", text).encode("utf-8")
        self.log_n = log_n

    def __repr__(self) -> str:
        return f"Passphrase(<redacted>, log_n={self.log_n})"


Recipient = Union[MasterRecipient, SessionKey, Passphrase]
Identity = Union[MasterIdentity, SessionKey, Passphrase]


# ── 小工具 ───────────────────────────────────────────────────────────────────


def _hkdf(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def scrypt_kek(passphrase_bytes: bytes, salt: bytes, log_n: int, r: int, p: int, length: int = 32) -> bytes:
    """scrypt（RFC 7914）。不檢查範圍，範圍由呼叫端負責（測試要用 RFC 向量）。"""
    return Scrypt(salt=salt, length=length, n=1 << log_n, r=r, p=p).derive(passphrase_bytes)


def _session_key_id(key: bytes, file_id: bytes) -> bytes:
    # 每個檔案不同：同一把本次金鑰在不同檔案上的 key_id 不會一樣（雲端無法用它串連檔案）
    return hmac.new(key, L_KEY_ID + file_id, hashlib.sha256).digest()[:KEY_ID_LEN]


def _master_key_id(public_bytes: bytes, file_id: bytes) -> bytes:
    # 任何知道萬用鎖公鑰的人都能算出來：公鑰別公開張貼
    return hashlib.sha256(L_KEY_ID + file_id + public_bytes).digest()[:KEY_ID_LEN]


def _chunk_nonce(counter: int, last: bool) -> bytes:
    if counter >= 1 << 88:
        raise MlockError("MLK-E14", "too many chunks")
    return counter.to_bytes(11, "big") + (b"\x01" if last else b"\x00")


# ── 檔頭 ─────────────────────────────────────────────────────────────────────


@dataclass
class _Slot:
    kind: int
    body: bytes

    def encode(self) -> bytes:
        return struct.pack(">BH", self.kind, len(self.body)) + self.body


@dataclass
class _Header:
    chunk_log2: int
    file_id: bytes
    generation: int
    slots: list = field(default_factory=list)
    mac: bytes = b""

    @property
    def core(self) -> bytes:
        """不會因換槽而改變的部分；同時是每個內容區塊的 AAD。"""
        return MAGIC + bytes([FORMAT_VERSION, SUITE_V1, self.chunk_log2]) + self.file_id

    def body(self) -> bytes:
        out = self.core + struct.pack(">IB", self.generation, len(self.slots))
        for s in self.slots:
            out += s.encode()
        return out

    def encode(self) -> bytes:
        return self.body() + self.mac


def _parse(blob: bytes) -> tuple[_Header, int]:
    """嚴格解析檔頭（不需要金鑰）。回傳 (header, 內容起點)。"""
    if not isinstance(blob, (bytes, bytearray)):
        raise MlockError("MLK-E14", "input must be bytes")
    blob = bytes(blob)
    if len(blob) < len(MAGIC) or blob[: len(MAGIC)] != MAGIC:
        raise MlockError("MLK-E01")
    if len(blob) < _FIXED_LEN:
        raise MlockError("MLK-E04", "header shorter than fixed part")
    off = len(MAGIC)
    version, suite, chunk_log2 = blob[off], blob[off + 1], blob[off + 2]
    off += 3
    if version != FORMAT_VERSION:
        raise MlockError("MLK-E02", f"version {version}")
    if suite != SUITE_V1:
        raise MlockError("MLK-E03", f"suite {suite}")
    if not (MIN_CHUNK_LOG2 <= chunk_log2 <= MAX_CHUNK_LOG2):
        raise MlockError("MLK-E04", "chunk size out of range")
    file_id = blob[off : off + FILE_ID_LEN]
    off += FILE_ID_LEN
    generation, slot_count = struct.unpack(">IB", blob[off : off + 5])
    off += 5
    if slot_count == 0:
        raise MlockError("MLK-E04", "no slots")
    if slot_count > MAX_SLOTS:
        raise MlockError("MLK-E10")
    slots = []
    for _ in range(slot_count):
        if len(blob) < off + 3:
            raise MlockError("MLK-E04", "slot header truncated")
        kind, blen = struct.unpack(">BH", blob[off : off + 3])
        off += 3
        if blen > MAX_SLOT_BODY or len(blob) < off + blen:
            raise MlockError("MLK-E04", "slot body truncated or too long")
        body = blob[off : off + blen]
        off += blen
        expected = {SLOT_HPKE: KEY_ID_LEN + _HPKE_ENC_LEN + WRAPPED_DEK_LEN,
                    SLOT_SCRYPT: SCRYPT_SALT_LEN + 3 + NONCE_LEN + WRAPPED_DEK_LEN,
                    SLOT_KEY: KEY_ID_LEN + NONCE_LEN + WRAPPED_DEK_LEN}.get(kind)
        if expected is not None and blen != expected:
            raise MlockError("MLK-E04", "slot body has wrong length")
        slots.append(_Slot(kind, body))
    if len(blob) < off + MAC_LEN:
        raise MlockError("MLK-E04", "header MAC missing")
    mac = blob[off : off + MAC_LEN]
    off += MAC_LEN
    return _Header(chunk_log2, file_id, generation, slots, mac), off


def _header_mac(dek: bytes, header: _Header) -> bytes:
    key = _hkdf(dek, header.file_id, L_HEADER)
    return hmac.new(key, header.body(), hashlib.sha256).digest()


# ── 槽：包（wrap）與開（unwrap） ──────────────────────────────────────────────


def _wrap(dek: bytes, recipient: Recipient, header: _Header, rng: Rng) -> _Slot:
    core = header.core
    if isinstance(recipient, MasterRecipient):
        kid = _master_key_id(recipient.public_bytes, header.file_id)
        sealed = _HPKE_SUITE.encrypt(dek, recipient._pk, info=L_SLOT_HPKE + core + kid)
        return _Slot(SLOT_HPKE, kid + sealed)
    if isinstance(recipient, SessionKey):
        kid = _session_key_id(recipient.key, header.file_id)
        kek = _hkdf(recipient.key, header.file_id, L_SLOT_KEY)
        nonce = rng(NONCE_LEN)
        ct = AESGCM(kek).encrypt(nonce, dek, L_SLOT_KEY + core + kid)
        return _Slot(SLOT_KEY, kid + nonce + ct)
    if isinstance(recipient, Passphrase):
        salt = rng(SCRYPT_SALT_LEN)
        params = bytes([recipient.log_n, SCRYPT_R, SCRYPT_P])
        kek = scrypt_kek(recipient._bytes, salt, recipient.log_n, SCRYPT_R, SCRYPT_P)
        nonce = rng(NONCE_LEN)
        ct = AESGCM(kek).encrypt(nonce, dek, L_SLOT_SCRYPT + core + salt + params)
        return _Slot(SLOT_SCRYPT, salt + params + nonce + ct)
    raise MlockError("MLK-E14", f"unsupported recipient type {type(recipient).__name__}")


def _try_unwrap(slot: _Slot, identity: Identity, header: _Header) -> bytes | None:
    core = header.core
    try:
        if slot.kind == SLOT_HPKE and isinstance(identity, MasterIdentity):
            kid, sealed = slot.body[:KEY_ID_LEN], slot.body[KEY_ID_LEN:]
            if kid != _master_key_id(identity.recipient().public_bytes, header.file_id):
                return None
            return _HPKE_SUITE.decrypt(sealed, identity._sk, info=L_SLOT_HPKE + core + kid)
        if slot.kind == SLOT_KEY and isinstance(identity, SessionKey):
            kid = slot.body[:KEY_ID_LEN]
            if kid != _session_key_id(identity.key, header.file_id):
                return None
            nonce = slot.body[KEY_ID_LEN : KEY_ID_LEN + NONCE_LEN]
            ct = slot.body[KEY_ID_LEN + NONCE_LEN :]
            kek = _hkdf(identity.key, header.file_id, L_SLOT_KEY)
            return AESGCM(kek).decrypt(nonce, ct, L_SLOT_KEY + core + kid)
        if slot.kind == SLOT_SCRYPT and isinstance(identity, Passphrase):
            salt = slot.body[:SCRYPT_SALT_LEN]
            params = slot.body[SCRYPT_SALT_LEN : SCRYPT_SALT_LEN + 3]
            log_n, r, p = params
            if not (SCRYPT_LOG_N_MIN <= log_n <= SCRYPT_LOG_N_MAX) or r != SCRYPT_R or p != SCRYPT_P:
                raise MlockError("MLK-E09", f"log_n={log_n} r={r} p={p}")
            nonce = slot.body[SCRYPT_SALT_LEN + 3 : SCRYPT_SALT_LEN + 3 + NONCE_LEN]
            ct = slot.body[SCRYPT_SALT_LEN + 3 + NONCE_LEN :]
            kek = scrypt_kek(identity._bytes, salt, log_n, r, p)
            return AESGCM(kek).decrypt(nonce, ct, L_SLOT_SCRYPT + core + salt + params)
    except InvalidTag:
        return None
    except MlockError:
        raise
    except Exception:  # 例如 HPKE 收到無效的 enc；一律視為「打不開」
        return None
    return None


def _open(blob: bytes, identities: Sequence[Identity]) -> tuple[_Header, int, bytes, int]:
    """解析 + 找到能開的槽 + 驗證檔頭 MAC。回傳 (header, 內容起點, DEK, 槽編號)。"""
    header, start = _parse(blob)
    if not identities:
        raise MlockError("MLK-E14", "no key given")
    for identity in identities:
        for index, slot in enumerate(header.slots):
            dek = _try_unwrap(slot, identity, header)
            if dek is None:
                continue
            if len(dek) != DEK_LEN:
                raise MlockError("MLK-E06", "wrapped key has wrong length")
            if not hmac.compare_digest(_header_mac(dek, header), header.mac):
                raise MlockError("MLK-E06")
            return header, start, dek, index
    raise MlockError("MLK-E05")


# ── 內容（STREAM：11-byte 計數器 + 最後一塊旗標） ─────────────────────────────


def _encrypt_payload(dek: bytes, header: _Header, plaintext: bytes) -> bytes:
    aead = AESGCM(_hkdf(dek, header.file_id, L_PAYLOAD))
    size = 1 << header.chunk_log2
    chunks = [plaintext[i : i + size] for i in range(0, len(plaintext), size)] or [b""]
    out = bytearray()
    for i, chunk in enumerate(chunks):
        out += aead.encrypt(_chunk_nonce(i, i == len(chunks) - 1), chunk, header.core)
    return bytes(out)


def _decrypt_payload(dek: bytes, header: _Header, payload: bytes) -> bytes:
    aead = AESGCM(_hkdf(dek, header.file_id, L_PAYLOAD))
    ct_size = (1 << header.chunk_log2) + TAG_LEN
    if len(payload) < TAG_LEN:
        raise MlockError("MLK-E08", "no final chunk")
    n = -(-len(payload) // ct_size)  # ceil
    last_len = len(payload) - (n - 1) * ct_size
    if last_len < TAG_LEN:
        raise MlockError("MLK-E07", "final chunk shorter than a tag")
    if n > 1 and last_len == TAG_LEN:
        raise MlockError("MLK-E07", "empty final chunk after data")
    out = bytearray()
    for i in range(n):
        piece = payload[i * ct_size : (i + 1) * ct_size]
        last = i == n - 1
        try:
            out += aead.decrypt(_chunk_nonce(i, last), piece, header.core)
        except InvalidTag:
            if last:
                # 能用「非最後一塊」解開 → 檔案在區塊邊界被截斷
                try:
                    aead.decrypt(_chunk_nonce(i, False), piece, header.core)
                except InvalidTag:
                    pass
                else:
                    raise MlockError("MLK-E08") from None
            raise MlockError("MLK-E07", f"chunk {i}") from None
    return bytes(out)


# ── 公開 API ─────────────────────────────────────────────────────────────────


def _check_recipients(recipients: Sequence[Recipient], require_master: bool) -> None:
    if not recipients:
        raise MlockError("MLK-E14", "at least one recipient is required")
    if len(recipients) > MAX_SLOTS:
        raise MlockError("MLK-E10")
    if require_master and not any(isinstance(r, MasterRecipient) for r in recipients):
        raise MlockError("MLK-E13")


def _build(dek: bytes, file_id: bytes, generation: int, chunk_log2: int,
           recipients: Sequence[Recipient], rng: Rng) -> _Header:
    header = _Header(chunk_log2, file_id, generation)
    header.slots = [_wrap(dek, r, header, rng) for r in recipients]
    header.mac = _header_mac(dek, header)
    return header


def encrypt(plaintext: bytes, recipients: Sequence[Recipient], *, chunk_log2: int = DEFAULT_CHUNK_LOG2,
            require_master: bool = True, rng: Rng = os.urandom) -> bytes:
    """加密。``recipients`` 每一個變成一個槽；預設要求至少一個萬用鎖槽。"""
    _check_recipients(recipients, require_master)
    if not (MIN_CHUNK_LOG2 <= chunk_log2 <= MAX_CHUNK_LOG2):
        raise MlockError("MLK-E14", "chunk_log2 out of range")
    dek = rng(DEK_LEN)
    header = _build(dek, rng(FILE_ID_LEN), 0, chunk_log2, recipients, rng)
    return header.encode() + _encrypt_payload(dek, header, bytes(plaintext))


def decrypt(blob: bytes, identities: Sequence[Identity]) -> bytes:
    """解密。先驗證檔頭，再逐塊驗證；任何一步失敗都不回傳任何明文。"""
    header, start, dek, _ = _open(blob, identities)
    return _decrypt_payload(dek, header, bytes(blob)[start:])


def find_slot(blob: bytes, identity: Identity) -> int:
    """回傳這把金鑰能開的槽編號（會驗證檔頭）。用來「找出舊本次金鑰的槽」再移除。"""
    return _open(blob, [identity])[3]


def _rewrite_slots(blob: bytes, opener: Sequence[Identity], new_slots_fn, rng: Rng) -> bytes:
    header, start, dek, _ = _open(blob, opener)
    new_header = _Header(header.chunk_log2, header.file_id, header.generation + 1)
    new_header.slots = new_slots_fn(header, new_header, dek)
    if not new_header.slots:
        raise MlockError("MLK-E11")
    if len(new_header.slots) > MAX_SLOTS:
        raise MlockError("MLK-E10")
    new_header.mac = _header_mac(dek, new_header)
    # 內容區塊的 AAD 只綁 core（不含槽與世代），所以內容原封不動
    return new_header.encode() + bytes(blob)[start:]


def add_slot(blob: bytes, opener: Sequence[Identity], new: Recipient, *, rng: Rng = os.urandom) -> bytes:
    """用任一把能開的金鑰（通常是萬用鎖）加一個槽。內容不重新加密。"""
    return _rewrite_slots(blob, opener, lambda old, h, dek: list(old.slots) + [_wrap(dek, new, h, rng)], rng)


def _guard_removal(old: _Header, index: int, allow_remove_master: bool) -> None:
    if not (0 <= index < len(old.slots)):
        raise MlockError("MLK-E14", "slot index out of range")
    if len(old.slots) == 1:
        raise MlockError("MLK-E11")
    if old.slots[index].kind == SLOT_HPKE and not allow_remove_master:
        others = [s for i, s in enumerate(old.slots) if i != index and s.kind == SLOT_HPKE]
        if not others:
            raise MlockError("MLK-E12")


def remove_slot(blob: bytes, opener: Sequence[Identity], index: int, *,
                allow_remove_master: bool = False, rng: Rng = os.urandom) -> bytes:
    """移除一個槽。不能移除最後一個；移除唯一的萬用鎖槽要 ``allow_remove_master=True``。"""

    def fn(old, h, dek):
        _guard_removal(old, index, allow_remove_master)
        return [s for i, s in enumerate(old.slots) if i != index]

    return _rewrite_slots(blob, opener, fn, rng)


def replace_slot(blob: bytes, opener: Sequence[Identity], index: int, new: Recipient, *,
                 allow_remove_master: bool = False, rng: Rng = os.urandom) -> bytes:
    """換槽（rewrap）：移除第 ``index`` 個槽、加入新的。DEK 與內容不變。

    限制：拿過舊槽、而且曾經解開過（因此可能留著 DEK 或明文）的人不受影響；那種情況要用 :func:`rekey`。
    """

    def fn(old, h, dek):
        if not (0 <= index < len(old.slots)):
            raise MlockError("MLK-E14", "slot index out of range")
        remaining = [s for i, s in enumerate(old.slots) if i != index]
        if old.slots[index].kind == SLOT_HPKE and not allow_remove_master \
                and not any(s.kind == SLOT_HPKE for s in remaining) and not isinstance(new, MasterRecipient):
            raise MlockError("MLK-E12")
        return remaining + [_wrap(dek, new, h, rng)]

    return _rewrite_slots(blob, opener, fn, rng)


def rekey(blob: bytes, opener: Sequence[Identity], recipients: Sequence[Recipient], *,
          require_master: bool = True, rng: Rng = os.urandom) -> bytes:
    """換資料金鑰：新 DEK、新 file_id、整份內容重新加密、所有槽重建。

    用在「拿過本次金鑰的人可能已經留著 DEK」的情況。已經被複製走的舊檔案仍然照舊打得開。
    """
    _check_recipients(recipients, require_master)
    header, start, dek, _ = _open(blob, opener)
    plaintext = _decrypt_payload(dek, header, bytes(blob)[start:])
    new_dek = rng(DEK_LEN)
    new_header = _build(new_dek, rng(FILE_ID_LEN), header.generation + 1, header.chunk_log2, recipients, rng)
    return new_header.encode() + _encrypt_payload(new_dek, new_header, plaintext)


@dataclass
class SlotInfo:
    index: int
    kind: str
    key_id: str | None = None
    scrypt_log_n: int | None = None


@dataclass
class FileInfo:
    format_version: int
    suite: int
    chunk_size: int
    file_id: str
    generation: int
    slots: list
    header_len: int
    payload_len: int
    plaintext_len: int | None
    fingerprint: str  # SHA-256(整個檔頭)，用來記住「最新版」以偵測被換回舊版
    verified: bool = False
    opened_by: int | None = None


def inspect(blob: bytes, identities: Sequence[Identity] | None = None) -> FileInfo:
    """不需要金鑰就能看的資訊（也是雲端看得到的資訊）。給了金鑰就順便驗證檔頭。"""
    header, start = _parse(blob)
    slots = []
    for i, s in enumerate(header.slots):
        info = SlotInfo(i, SLOT_NAMES.get(s.kind, f"unknown-0x{s.kind:02x}"))
        if s.kind in (SLOT_HPKE, SLOT_KEY):
            info.key_id = s.body[:KEY_ID_LEN].hex()
        elif s.kind == SLOT_SCRYPT:
            info.scrypt_log_n = s.body[SCRYPT_SALT_LEN]
        slots.append(info)
    payload_len = len(blob) - start
    ct_size = (1 << header.chunk_log2) + TAG_LEN
    n = -(-payload_len // ct_size) if payload_len else 0
    plaintext_len = payload_len - n * TAG_LEN if n and payload_len - (n - 1) * ct_size >= TAG_LEN else None
    fi = FileInfo(FORMAT_VERSION, SUITE_V1, 1 << header.chunk_log2, header.file_id.hex(), header.generation,
                  slots, start, payload_len, plaintext_len, hashlib.sha256(bytes(blob)[:start]).hexdigest())
    if identities:
        _, _, _, idx = _open(blob, identities)
        fi.verified, fi.opened_by = True, idx
    return fi


# ── 萬用鎖私鑰檔（用密語封起來，給離線備份用） ──────────────────────────────────


def seal_identity(identity: MasterIdentity, passphrase: Passphrase, *, rng: Rng = os.urandom) -> bytes:
    """把萬用鎖私鑰用密語封成一個小檔（scrypt + AES-256-GCM）。檔頭同時是 AAD。"""
    salt = rng(SCRYPT_SALT_LEN)
    head = IDENTITY_MAGIC + bytes([IDENTITY_VERSION, passphrase.log_n, SCRYPT_R, SCRYPT_P]) + salt
    kek = scrypt_kek(passphrase._bytes, salt, passphrase.log_n, SCRYPT_R, SCRYPT_P)
    nonce = rng(NONCE_LEN)
    return head + nonce + AESGCM(kek).encrypt(nonce, identity.private_bytes(), L_IDENTITY + head)


def open_identity(blob: bytes, passphrase: Passphrase) -> MasterIdentity:
    head_len = len(IDENTITY_MAGIC) + 4 + SCRYPT_SALT_LEN
    if len(blob) != head_len + NONCE_LEN + 32 + TAG_LEN or blob[: len(IDENTITY_MAGIC)] != IDENTITY_MAGIC:
        raise MlockError("MLK-E15", "not an identity file")
    head = blob[:head_len]
    version, log_n, r, p = head[len(IDENTITY_MAGIC) : len(IDENTITY_MAGIC) + 4]
    if version != IDENTITY_VERSION:
        raise MlockError("MLK-E15", "unsupported identity version")
    if not (SCRYPT_LOG_N_MIN <= log_n <= SCRYPT_LOG_N_MAX) or r != SCRYPT_R or p != SCRYPT_P:
        raise MlockError("MLK-E09")
    salt = head[-SCRYPT_SALT_LEN:]
    nonce = blob[head_len : head_len + NONCE_LEN]
    kek = scrypt_kek(passphrase._bytes, salt, log_n, r, p)
    try:
        raw = AESGCM(kek).decrypt(nonce, blob[head_len + NONCE_LEN :], L_IDENTITY + head)
    except InvalidTag:
        raise MlockError("MLK-E15", "wrong passphrase or damaged file") from None
    return MasterIdentity.from_private_bytes(raw)
