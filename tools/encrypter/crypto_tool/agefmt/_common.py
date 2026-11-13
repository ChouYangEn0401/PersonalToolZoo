"""agefmt 內部共用：錯誤、base64（無 padding、正規形式）、密碼學原語的接線。

密碼學原語全部來自 ``cryptography`` 套件（X25519、ChaCha20-Poly1305、HKDF-SHA-256、
HMAC-SHA-256、scrypt），這裡只做「照 age 規格接起來」，不自創任何原語。
"""

from __future__ import annotations

import base64
import hmac as _hmac
import re

try:  # 測試時是 crypto_tool.agefmt；從 GUI__Encrypter.py 執行時 crypto_tool/ 在 sys.path 上，是 agefmt
    from ..sealed.errors import SealError
except ImportError:  # pragma: no cover - 依執行方式而定
    from sealed.errors import SealError

try:  # cryptography 42 起就有下面這些 API
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives import hmac as _c_hmac
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    _IMPORT_ERROR: Exception | None = None
except ImportError as _exc:  # pragma: no cover - 只有沒裝套件時會走到
    _IMPORT_ERROR = _exc

    class InvalidTag(Exception):  # type: ignore[no-redef]
        pass


# --- 錯誤 -------------------------------------------------------------------

def fail(code: str, reason: str, action: str = "", detail: str = "") -> SealError:
    """建立 SealError（呼叫端 raise）。reason／action 是給人看的話，不放任何祕密。"""
    return SealError(code, reason, action, detail)


def header_error(detail: str, reason: str = "") -> SealError:
    return fail(
        "corrupt",
        reason or "age 檔的標頭格式不正確，檔案可能損壞或被改過。",
        "確認拿到的是完整、沒被改過的原始檔；如果有備份，改用備份。",
        "header:" + detail,
    )


def armor_error(detail: str) -> SealError:
    return fail(
        "corrupt",
        "age 文字封裝（ASCII armor）格式不正確，檔案可能被改過、截斷，或複製貼上時被改了。",
        "請取得原始檔再試；文字封裝的開頭與結尾行、每行 64 字都要原封不動。",
        "armor:" + detail,
    )


def payload_error(detail: str) -> SealError:
    return fail(
        "corrupt",
        "加密內容驗證失敗：檔案被截斷、被改過，或後面多了資料。沒有留下任何解密結果。",
        "確認檔案完整（大小與原始檔相同）；如果有備份，改用備份。",
        "payload:" + detail,
    )


def require_crypto() -> None:
    if _IMPORT_ERROR is not None:
        raise fail(
            "dependency_missing",
            "缺少 cryptography 套件，無法處理 age 格式。",
            "安裝工具的 requirements.txt 裡列的套件後再試。",
            type(_IMPORT_ERROR).__name__,
        )


# --- base64：標準字母、無 padding、必須是正規形式 ------------------------------

_RAW_B64 = re.compile(rb"[A-Za-z0-9+/]*")
_PADDED_B64 = re.compile(rb"[A-Za-z0-9+/]*={0,2}")


def b64_encode_raw(data: bytes) -> bytes:
    return base64.b64encode(data).rstrip(b"=")


def b64_decode_raw(s: bytes) -> bytes:
    """規格：無 padding、正規形式；遇到 ``=``、換行或任何非字母字元都拒絕。"""
    if not _RAW_B64.fullmatch(s) or len(s) % 4 == 1:
        raise ValueError("invalid base64")
    out = base64.b64decode(s + b"=" * (-len(s) % 4), validate=True)
    if b64_encode_raw(out) != s:
        raise ValueError("non-canonical base64")
    return out


def b64_decode_padded(s: bytes) -> bytes:
    """armor 用的 base64：有 padding、必須是正規形式（RFC 4648 第 3.5 節）。"""
    if len(s) % 4 or not _PADDED_B64.fullmatch(s):
        raise ValueError("invalid base64")
    out = base64.b64decode(s, validate=True)
    if base64.b64encode(out) != s:
        raise ValueError("non-canonical base64")
    return out


# --- 原語接線 -----------------------------------------------------------------

ZERO_NONCE = b"\x00" * 12


def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    require_crypto()
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def hmac_sha256(key: bytes, data: bytes) -> bytes:
    require_crypto()
    h = _c_hmac.HMAC(key, hashes.SHA256())
    h.update(data)
    return h.finalize()


def consteq(a: bytes, b: bytes) -> bool:
    return _hmac.compare_digest(a, b)


def chacha(key: bytes):
    require_crypto()
    return ChaCha20Poly1305(key)


def x25519_public(secret: bytes) -> bytes:
    require_crypto()
    return X25519PrivateKey.from_private_bytes(secret).public_key().public_bytes_raw()


def x25519_shared(secret: bytes, public: bytes) -> bytes | None:
    """回傳共享祕密；對方的點是低階點（結果全零）時回傳 None。"""
    require_crypto()
    try:
        shared = X25519PrivateKey.from_private_bytes(secret).exchange(
            X25519PublicKey.from_public_bytes(public))
    except ValueError:  # OpenSSL 對全零結果直接報錯
        return None
    if shared == b"\x00" * 32:
        return None
    return shared


def scrypt_key(passphrase: bytes, salt: bytes, log_n: int) -> bytes:
    require_crypto()
    try:
        return Scrypt(salt=salt, length=32, n=1 << log_n, r=8, p=1).derive(passphrase)
    except MemoryError:
        raise fail("io_error", "記憶體不足，無法計算密語金鑰。",
                   "關掉一些程式後再試。", "scrypt:memory") from None
