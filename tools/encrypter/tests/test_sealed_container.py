"""ISD2 容器格式：已知答案、往返、竄改、截斷、重排、錯金鑰。

所有金鑰都在測試執行時產生或是寫死的假值，不讀任何真實金鑰。
"""

import hashlib
import io
import os
import struct

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from crypto_tool.sealed.container import (
    HEADER_LEN, TAG_LEN, KeyMaterial, SealReader, SealWriter, parse_header,
)
from crypto_tool.sealed.errors import SealError

FAST = {"scrypt_log_n": 10}  # 只給測試用的低成本 scrypt
RAW = KeyMaterial(raw=bytes(range(32)))


def seal(data: bytes, material=RAW, **options) -> bytes:
    out = io.BytesIO()
    writer = SealWriter(out, material, **options)
    writer.write(data)
    writer.close()
    return out.getvalue()


def unseal(blob: bytes, material=RAW) -> bytes:
    reader = SealReader(io.BytesIO(blob), material)
    return reader.read()


def fail_code(blob: bytes, material=RAW) -> str:
    with pytest.raises(SealError) as caught:
        unseal(blob, material)
    return caught.value.code


# ── 已知答案 ─────────────────────────────────────────────────────────────

SALT = bytes(range(100, 116))
PREFIX = bytes(range(200, 207))


def _expected(aead_cls, aead_id, master, kdf_fields, data, chunk):
    """照格式說明，只用套件的原始元件自己組一次，不經過 SealWriter。"""
    key = HKDF(hashes.SHA256(), 32, SALT, b"ISD2 v1 chunk key").derive(master)
    check = HKDF(hashes.SHA256(), 16, SALT, b"ISD2 v1 key check").derive(master)
    header = (b"ISD2" + bytes([1, aead_id]) + kdf_fields[:1] + b"\x00"
              + struct.pack(">I", chunk) + kdf_fields[1:] + b"\x00"
              + SALT + PREFIX + b"\x00" * 9 + check)
    assert len(header) == HEADER_LEN
    pieces = [data[i:i + chunk] for i in range(0, len(data), chunk)] or [b""]
    body = b""
    for i, piece in enumerate(pieces):
        nonce = PREFIX + struct.pack(">IB", i, 1 if i == len(pieces) - 1 else 0)
        body += aead_cls(key).encrypt(nonce, piece, header)
    return header + body


def test_known_answer_raw_key_aes_gcm():
    data = b"The quick brown fox jumps over the lazy dog"
    blob = seal(data, chunk_size=16, _salt=SALT, _nonce_prefix=PREFIX)
    assert blob == _expected(AESGCM, 1, RAW.raw, b"\x00\x00\x00\x00", data, 16)
    # 釘住位元組：格式不小心改到，這裡會壞
    assert hashlib.sha256(blob).hexdigest() == KNOWN_SHA256
    assert unseal(blob) == data


def test_known_answer_passphrase_chacha():
    data = b"x" * 40
    material = KeyMaterial(passphrase="correct horse battery staple")
    blob = seal(data, material, aead="chacha20-poly1305", chunk_size=32,
                _salt=SALT, _nonce_prefix=PREFIX, **FAST)
    master = Scrypt(salt=SALT, length=32, n=1 << 10, r=8, p=1).derive(
        b"correct horse battery staple")
    assert blob == _expected(ChaCha20Poly1305, 2, master, b"\x01\x0a\x08\x01", data, 32)
    assert unseal(blob, material) == data


KNOWN_SHA256 = "f9bc020ca31d31a13241c8e75cd35865832479846b8d0bc3d0b9cc1ded4c7ea7"


# ── 往返 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 32, 33, 1000])
@pytest.mark.parametrize("aead", ["aes-256-gcm", "chacha20-poly1305"])
def test_roundtrip_sizes(size, aead):
    data = os.urandom(size)
    blob = seal(data, aead=aead, chunk_size=16)
    assert unseal(blob) == data
    chunks = max(1, -(-size // 16))
    assert len(blob) == HEADER_LEN + size + chunks * TAG_LEN


def test_roundtrip_passphrase_and_small_reads():
    material = KeyMaterial(passphrase="密語 with ünïcode")
    data = os.urandom(500)
    blob = seal(data, material, chunk_size=64, **FAST)
    reader = SealReader(io.BytesIO(blob), material)
    got = b""
    while True:
        piece = reader.read(7)
        if not piece:
            break
        got += piece
    assert got == data


def test_each_encryption_is_different():
    assert seal(b"same") != seal(b"same")


def test_ciphertext_does_not_contain_plaintext_or_key():
    data = b"TOP-SECRET-PLAINTEXT-MARKER" * 4
    blob = seal(data)
    assert b"TOP-SECRET" not in blob
    assert RAW.raw not in blob


# ── 錯金鑰 ──────────────────────────────────────────────────────────────

def test_wrong_raw_key():
    assert fail_code(seal(b"data"), KeyMaterial(raw=b"\x01" * 32)) == "wrong_key"


def test_wrong_passphrase():
    blob = seal(b"data", KeyMaterial(passphrase="right one"), **FAST)
    assert fail_code(blob, KeyMaterial(passphrase="wrong one")) == "wrong_key"


def test_key_kind_mismatch_is_explained():
    assert fail_code(seal(b"data"), KeyMaterial(passphrase="words")) == "bad_key_format"
    blob = seal(b"data", KeyMaterial(passphrase="words"), **FAST)
    assert fail_code(blob, RAW) == "bad_key_format"


# ── 竄改、截斷、重排 ────────────────────────────────────────────────────

def test_every_single_byte_flip_is_rejected():
    blob = seal(b"A" * 40, chunk_size=16)
    for i in range(len(blob)):
        bad = bytearray(blob)
        bad[i] ^= 0x01
        with pytest.raises(SealError):
            unseal(bytes(bad))


def test_body_tamper_is_corrupt_not_wrong_key():
    blob = bytearray(seal(b"A" * 40, chunk_size=16))
    blob[HEADER_LEN + 3] ^= 0xFF
    assert fail_code(bytes(blob)) == "corrupt"


def test_truncation_at_every_length_is_rejected():
    blob = seal(b"B" * 50, chunk_size=16)
    for cut in range(len(blob)):
        with pytest.raises(SealError):
            unseal(blob[:cut])


def test_truncation_at_chunk_boundary_is_corrupt():
    blob = seal(b"B" * 48, chunk_size=16)
    one = 16 + TAG_LEN
    assert fail_code(blob[:HEADER_LEN + 2 * one]) == "corrupt"
    assert fail_code(blob[:HEADER_LEN]) == "corrupt"


def test_reordered_duplicated_and_dropped_chunks_are_rejected():
    blob = seal(b"C" * 16 + b"D" * 16 + b"E" * 16, chunk_size=16)
    one = 16 + TAG_LEN
    head, body = blob[:HEADER_LEN], blob[HEADER_LEN:]
    c = [body[i * one:(i + 1) * one] for i in range(3)]
    assert fail_code(head + c[1] + c[0] + c[2]) == "corrupt"   # 對調
    assert fail_code(head + c[0] + c[0] + c[1] + c[2]) == "corrupt"  # 重複
    assert fail_code(head + c[0] + c[2]) == "corrupt"          # 抽掉中間
    assert fail_code(head + c[1] + c[2]) == "corrupt"          # 抽掉開頭


def test_trailing_data_is_rejected():
    blob = seal(b"F" * 20, chunk_size=16)
    assert fail_code(blob + b"\x00") == "corrupt"
    assert fail_code(blob + blob[HEADER_LEN:]) == "corrupt"


def test_chunks_cannot_be_moved_between_files_with_same_key():
    a = seal(b"G" * 16, chunk_size=16)
    b = seal(b"H" * 16, chunk_size=16)
    assert fail_code(a[:HEADER_LEN] + b[HEADER_LEN:]) == "corrupt"


def test_no_plaintext_released_before_failure_on_first_chunk():
    blob = bytearray(seal(b"I" * 10, chunk_size=16))
    blob[-1] ^= 1
    reader = SealReader(io.BytesIO(bytes(blob)), RAW)
    with pytest.raises(SealError):
        reader.read(1)


# ── 檔頭 ────────────────────────────────────────────────────────────────

def test_not_our_format_and_legacy_format():
    with pytest.raises(SealError) as caught:
        parse_header(b"PK\x03\x04" + b"\x00" * 80)
    assert caught.value.code == "unsupported_format"
    with pytest.raises(SealError) as caught:
        parse_header(b'CONTENT="""AAAA"""\nNOTE="""{}"""')
    assert caught.value.code == "legacy_format"


def test_future_version_is_unsupported():
    blob = bytearray(seal(b"x"))
    blob[4] = 2
    assert fail_code(bytes(blob)) == "unsupported_format"


def test_hostile_scrypt_cost_is_refused_before_deriving():
    blob = bytearray(seal(b"x", KeyMaterial(passphrase="pw"), **FAST))
    blob[12] = 40  # 要求 2**40 的 scrypt 成本
    assert fail_code(bytes(blob), KeyMaterial(passphrase="pw")) == "corrupt"


def test_key_material_repr_hides_secrets():
    text = repr(KeyMaterial(raw=b"k" * 32, passphrase="hunter2-hunter2"))
    assert "hunter2" not in text and "kkkk" not in text
