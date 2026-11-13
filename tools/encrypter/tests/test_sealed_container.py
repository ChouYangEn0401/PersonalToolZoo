"""ISD2 容器格式：已知答案、往返、竄改、截斷、重排、錯金鑰。

所有金鑰都在測試執行時產生或是寫死的假值，不讀任何真實金鑰。
"""

import hashlib
import io
import os
import struct
import unittest

from _support import FAST, Case

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from crypto_tool.sealed.container import (
    HEADER_LEN, TAG_LEN, KeyMaterial, SealReader, SealWriter, parse_header,
)
from crypto_tool.sealed.errors import SealError

RAW = KeyMaterial(raw=bytes(range(32)))
SALT = bytes(range(100, 116))
PREFIX = bytes(range(200, 207))
KNOWN_SHA256 = "f9bc020ca31d31a13241c8e75cd35865832479846b8d0bc3d0b9cc1ded4c7ea7"


def seal(data: bytes, material=RAW, **options) -> bytes:
    out = io.BytesIO()
    writer = SealWriter(out, material, **options)
    writer.write(data)
    writer.close()
    return out.getvalue()


def unseal(blob: bytes, material=RAW) -> bytes:
    return SealReader(io.BytesIO(blob), material).read()


def expected(aead_cls, aead_id, master, kdf_fields, data, chunk):
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


class ContainerCase(Case):
    def fail_code(self, blob: bytes, material=RAW) -> str:
        return self.code_of(unseal, blob, material)


class KnownAnswerTests(ContainerCase):
    def test_raw_key_aes_gcm(self):
        data = b"The quick brown fox jumps over the lazy dog"
        blob = seal(data, chunk_size=16, _salt=SALT, _nonce_prefix=PREFIX)
        self.assertEqual(blob, expected(AESGCM, 1, RAW.raw, b"\x00\x00\x00\x00", data, 16))
        # 釘住位元組：格式不小心改到，這裡會壞
        self.assertEqual(hashlib.sha256(blob).hexdigest(), KNOWN_SHA256)
        self.assertEqual(unseal(blob), data)

    def test_passphrase_chacha(self):
        data = b"x" * 40
        material = KeyMaterial(passphrase="correct horse battery staple")
        blob = seal(data, material, aead="chacha20-poly1305", chunk_size=32,
                    _salt=SALT, _nonce_prefix=PREFIX, **FAST)
        master = Scrypt(salt=SALT, length=32, n=1 << 10, r=8, p=1).derive(
            b"correct horse battery staple")
        self.assertEqual(
            blob, expected(ChaCha20Poly1305, 2, master, b"\x01\x0a\x08\x01", data, 32))
        self.assertEqual(unseal(blob, material), data)


class RoundTripTests(ContainerCase):
    def test_sizes_around_chunk_boundaries(self):
        for aead in ("aes-256-gcm", "chacha20-poly1305"):
            for size in (0, 1, 15, 16, 17, 32, 33, 1000):
                with self.subTest(aead=aead, size=size):
                    data = os.urandom(size)
                    blob = seal(data, aead=aead, chunk_size=16)
                    self.assertEqual(unseal(blob), data)
                    chunks = max(1, -(-size // 16))
                    self.assertEqual(len(blob), HEADER_LEN + size + chunks * TAG_LEN)

    def test_passphrase_and_small_reads(self):
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
        self.assertEqual(got, data)

    def test_each_encryption_is_different(self):
        self.assertNotEqual(seal(b"same"), seal(b"same"))

    def test_ciphertext_does_not_contain_plaintext_or_key(self):
        blob = seal(b"TOP-SECRET-PLAINTEXT-MARKER" * 4)
        self.assertNotIn(b"TOP-SECRET", blob)
        self.assertNotIn(RAW.raw, blob)


class WrongKeyTests(ContainerCase):
    def test_wrong_raw_key(self):
        self.assertEqual(self.fail_code(seal(b"data"), KeyMaterial(raw=b"\x01" * 32)), "wrong_key")

    def test_wrong_passphrase(self):
        blob = seal(b"data", KeyMaterial(passphrase="right one"), **FAST)
        self.assertEqual(self.fail_code(blob, KeyMaterial(passphrase="wrong one")), "wrong_key")

    def test_key_kind_mismatch_is_explained(self):
        self.assertEqual(self.fail_code(seal(b"data"), KeyMaterial(passphrase="words")),
                         "bad_key_format")
        blob = seal(b"data", KeyMaterial(passphrase="words"), **FAST)
        self.assertEqual(self.fail_code(blob, RAW), "bad_key_format")


class TamperTests(ContainerCase):
    def test_every_single_byte_flip_is_rejected(self):
        blob = seal(b"A" * 40, chunk_size=16)
        for i in range(len(blob)):
            bad = bytearray(blob)
            bad[i] ^= 0x01
            with self.assertRaises(SealError, msg=f"byte {i}"):
                unseal(bytes(bad))

    def test_body_tamper_is_corrupt_not_wrong_key(self):
        blob = bytearray(seal(b"A" * 40, chunk_size=16))
        blob[HEADER_LEN + 3] ^= 0xFF
        self.assertEqual(self.fail_code(bytes(blob)), "corrupt")

    def test_truncation_at_every_length_is_rejected(self):
        blob = seal(b"B" * 50, chunk_size=16)
        for cut in range(len(blob)):
            with self.assertRaises(SealError, msg=f"cut {cut}"):
                unseal(blob[:cut])

    def test_truncation_at_chunk_boundary_is_corrupt(self):
        blob = seal(b"B" * 48, chunk_size=16)
        one = 16 + TAG_LEN
        self.assertEqual(self.fail_code(blob[:HEADER_LEN + 2 * one]), "corrupt")
        self.assertEqual(self.fail_code(blob[:HEADER_LEN]), "corrupt")

    def test_reordered_duplicated_and_dropped_chunks_are_rejected(self):
        blob = seal(b"C" * 16 + b"D" * 16 + b"E" * 16, chunk_size=16)
        one = 16 + TAG_LEN
        head, body = blob[:HEADER_LEN], blob[HEADER_LEN:]
        c = [body[i * one:(i + 1) * one] for i in range(3)]
        self.assertEqual(self.fail_code(head + c[1] + c[0] + c[2]), "corrupt")         # 對調
        self.assertEqual(self.fail_code(head + c[0] + c[0] + c[1] + c[2]), "corrupt")  # 重複
        self.assertEqual(self.fail_code(head + c[0] + c[2]), "corrupt")                # 抽掉中間
        self.assertEqual(self.fail_code(head + c[1] + c[2]), "corrupt")                # 抽掉開頭

    def test_trailing_data_is_rejected(self):
        blob = seal(b"F" * 20, chunk_size=16)
        self.assertEqual(self.fail_code(blob + b"\x00"), "corrupt")
        self.assertEqual(self.fail_code(blob + blob[HEADER_LEN:]), "corrupt")

    def test_chunks_cannot_be_moved_between_files_with_same_key(self):
        a = seal(b"G" * 16, chunk_size=16)
        b = seal(b"H" * 16, chunk_size=16)
        self.assertEqual(self.fail_code(a[:HEADER_LEN] + b[HEADER_LEN:]), "corrupt")

    def test_no_plaintext_released_when_first_chunk_fails(self):
        blob = bytearray(seal(b"I" * 10, chunk_size=16))
        blob[-1] ^= 1
        reader = SealReader(io.BytesIO(bytes(blob)), RAW)
        with self.assertRaises(SealError):
            reader.read(1)


class HeaderTests(ContainerCase):
    def test_not_our_format_and_legacy_format(self):
        self.assertEqual(self.code_of(parse_header, b"PK\x03\x04" + b"\x00" * 80),
                         "unsupported_format")
        self.assertEqual(self.code_of(parse_header, b'CONTENT="""AAAA"""\nNOTE="""{}"""'),
                         "legacy_format")

    def test_future_version_is_unsupported(self):
        blob = bytearray(seal(b"x"))
        blob[4] = 2
        self.assertEqual(self.fail_code(bytes(blob)), "unsupported_format")

    def test_hostile_scrypt_cost_is_refused_before_deriving(self):
        blob = bytearray(seal(b"x", KeyMaterial(passphrase="pw"), **FAST))
        blob[12] = 40  # 要求 2**40 的 scrypt 成本
        self.assertEqual(self.fail_code(bytes(blob), KeyMaterial(passphrase="pw")), "corrupt")

    def test_key_material_repr_hides_secrets(self):
        text = repr(KeyMaterial(raw=b"k" * 32, passphrase="hunter2-hunter2"))
        self.assertNotIn("hunter2", text)
        self.assertNotIn("kkkk", text)


if __name__ == "__main__":
    unittest.main()
