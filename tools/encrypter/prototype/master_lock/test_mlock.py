"""Tests for the master-lock prototype (mlock.py). 全部離線；測試用金鑰都在測試中產生。

執行（需要 ``cryptography`` 50+，它不在 Encrypter 的 requirements 裡，所以缺少時整個模組會被略過）::

    python -I -m unittest discover -s tools/encrypter/prototype/master_lock -t tools/encrypter/prototype/master_lock -v
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
import sys
import unittest

try:
    import cryptography  # noqa: F401
    from cryptography.hazmat.primitives import hpke  # noqa: F401  (cryptography 50+)
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("cryptography with HPKE support is not installed")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mlock  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402
from cryptography.hazmat.primitives.kdf.hkdf import HKDF  # noqa: E402
from mlock import (  # noqa: E402
    MasterIdentity,
    MlockError,
    Passphrase,
    SessionKey,
)

FAST = 15  # 測試用的 scrypt log_n（正式預設 17）


class DetRng:
    """可重現的「亂數」：只給已知答案測試用，正式程式一律 os.urandom。"""

    def __init__(self, seed: bytes):
        self.seed = seed
        self.counter = 0
        self.log: list[bytes] = []

    def __call__(self, n: int) -> bytes:
        out = b""
        while len(out) < n:
            out += hashlib.sha256(self.seed + self.counter.to_bytes(8, "big")).digest()
            self.counter += 1
        self.log.append(out[:n])
        return out[:n]


def code_of(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except MlockError as e:
        return e.code
    raise AssertionError("expected MlockError")


def flip(blob: bytes, index: int, mask: int = 0x01) -> bytes:
    b = bytearray(blob)
    b[index] ^= mask
    return bytes(b)


def payload_start(blob: bytes) -> int:
    return mlock.inspect(blob).header_len


class Keys:
    """每個測試類別共用一組在測試中產生的金鑰。"""

    master = MasterIdentity.generate()
    other_master = MasterIdentity.generate()
    session = SessionKey.generate()
    other_session = SessionKey.generate()
    pw = Passphrase("correct horse battery staple 測試", log_n=FAST)
    wrong_pw = Passphrase("correct horse battery stapler 測試", log_n=FAST)


# ── 已知答案（標準向量） ──────────────────────────────────────────────────────


class TestPrimitiveKnownAnswers(unittest.TestCase):
    def test_scrypt_rfc7914_vector(self):
        # RFC 7914 §12：P="password", S="NaCl", N=1024, r=8, p=16, dkLen=64
        out = mlock.scrypt_kek(b"password", b"NaCl", 10, 8, 16, length=64)
        self.assertEqual(
            out.hex(),
            "fdbabe1c9d3472007856e7190d01e9fe7c6ad7cbc8237830e77376634b373162"
            "2eaf30d92e22a3886ff109279d9830dac727afb94a83ee6d8360cbdfa2cc0640",
        )

    def test_hkdf_rfc5869_case1(self):
        okm = mlock._hkdf(b"\x0b" * 22, bytes(range(13)), bytes(range(0xF0, 0xFA)), 42)
        self.assertEqual(
            okm.hex(),
            "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865",
        )

    def test_passphrase_nfc_normalisation(self):
        composed = Passphrase("café", log_n=FAST)
        decomposed = Passphrase("café", log_n=FAST)
        self.assertEqual(composed._bytes, decomposed._bytes)


# ── 格式的已知答案向量（固定亂數；釘住格式，正式實作必須產生一模一樣的位元組） ──────────

KAT_SEED = b"mlock-v1-kat"
KAT_SESSION_KEY = bytes(range(32))
KAT_PASSPHRASE = "kat passphrase"
KAT_PLAINTEXT = bytes(range(256)) * 16 + b"tail"  # 4100 bytes → chunk_log2=12 時兩塊
# 亂數取用順序：DEK(32)、file_id(32)、本次金鑰槽 nonce(12)、密語槽 salt(16)、密語槽 nonce(12)
KAT_EXPECTED_DEK_HEX = "3936b60626bc7d3378f274806bdd1c5ab2255429f9c13dd7fd016ec2dcbcc100"
KAT_EXPECTED_HEADER_HEX = (
    "4d4c4f434b0001010cae302a952451863a177a08f1c616c365d0f88c88e25e5c3cefa911f04d88186a"
    "0000000002"
    "030044"
    "1b5ecb6b38831ddd"
    "214adc37e7b9c07e9e7d160c"
    "5ca4af1d47984fa7b94c0c5a3b46882fbfb184dfe965c4934a16e9683f6c253dd49651c64dd4b09d7aa45a025a28d71f"
    "02004f"
    "114d4d8ae1f800a427074f6dc55c2982"
    "0f0801"
    "f230d6876883e50d66e71fdb"
    "2e23feda01aef2f68a0acdafa844010c7313125585299a769d21b93b7fd41409172a2ff310ed8a9dc15e23c953edeed1"
    "4c2766e5d02bc6fc45efca781c581b6206bf5b67d5f988ee22779ec3bd1a8a47"
)
KAT_EXPECTED_BLOB_SHA256 = "c935cf3d42a93c8baec2028d322acab2d8a50e078dd6aa51fb21d1a5f65cff09"


def kat_blob() -> tuple[bytes, DetRng]:
    rng = DetRng(KAT_SEED)
    blob = mlock.encrypt(
        KAT_PLAINTEXT,
        [SessionKey(KAT_SESSION_KEY), Passphrase(KAT_PASSPHRASE, log_n=FAST)],
        chunk_log2=12,
        require_master=False,
        rng=rng,
    )
    return blob, rng


class TestFormatVector(unittest.TestCase):
    def test_format_vector(self):
        blob, rng = kat_blob()
        start = payload_start(blob)
        self.assertEqual(rng.log[0].hex(), KAT_EXPECTED_DEK_HEX)
        self.assertEqual(blob[:start].hex(), KAT_EXPECTED_HEADER_HEX)
        self.assertEqual(hashlib.sha256(blob).hexdigest(), KAT_EXPECTED_BLOB_SHA256)
        self.assertEqual(mlock.decrypt(blob, [SessionKey(KAT_SESSION_KEY)]), KAT_PLAINTEXT)
        self.assertEqual(mlock.decrypt(blob, [Passphrase(KAT_PASSPHRASE, log_n=FAST)]), KAT_PLAINTEXT)

    def test_spec_conformance_by_hand(self):
        """只用規格文件與原語（不呼叫 mlock 的內部函式）解開向量，確認文件與程式一致。"""
        blob, rng = kat_blob()
        dek_expected, file_id_expected = rng.log[0], rng.log[1]
        # 固定段
        self.assertEqual(blob[:6], b"MLOCK\x00")
        version, suite, chunk_log2 = blob[6], blob[7], blob[8]
        self.assertEqual((version, suite, chunk_log2), (1, 1, 12))
        file_id = blob[9:41]
        self.assertEqual(file_id, file_id_expected)
        core = blob[:41]
        generation, slot_count = struct.unpack(">IB", blob[41:46])
        self.assertEqual((generation, slot_count), (0, 2))
        # 槽 0：本次金鑰
        off = 46
        kind, blen = struct.unpack(">BH", blob[off : off + 3])
        self.assertEqual((kind, blen), (0x03, 8 + 12 + 48))
        body = blob[off + 3 : off + 3 + blen]
        kid, nonce, ct = body[:8], body[8:20], body[20:]
        self.assertEqual(kid, hmac.new(KAT_SESSION_KEY, b"mlock/v1/key-id" + file_id, hashlib.sha256).digest()[:8])
        kek = HKDF(hashes.SHA256(), 32, file_id, b"mlock/v1/slot/key").derive(KAT_SESSION_KEY)
        dek = AESGCM(kek).decrypt(nonce, ct, b"mlock/v1/slot/key" + core + kid)
        self.assertEqual(dek, dek_expected)
        off += 3 + blen
        # 槽 1：密語
        kind, blen = struct.unpack(">BH", blob[off : off + 3])
        self.assertEqual((kind, blen), (0x02, 16 + 3 + 12 + 48))
        off += 3 + blen
        # 檔頭 MAC
        mac_key = HKDF(hashes.SHA256(), 32, file_id, b"mlock/v1/header").derive(dek)
        self.assertEqual(blob[off : off + 32], hmac.new(mac_key, blob[:off], hashlib.sha256).digest())
        off += 32
        # 內容：4096+16 一塊，再 4+16 最後一塊
        payload = blob[off:]
        self.assertEqual(len(payload), (4096 + 16) + (4 + 16))
        pk = HKDF(hashes.SHA256(), 32, file_id, b"mlock/v1/payload").derive(dek)
        c0 = AESGCM(pk).decrypt((0).to_bytes(11, "big") + b"\x00", payload[:4112], core)
        c1 = AESGCM(pk).decrypt((1).to_bytes(11, "big") + b"\x01", payload[4112:], core)
        self.assertEqual(c0 + c1, KAT_PLAINTEXT)


# ── 往返 ─────────────────────────────────────────────────────────────────────


class TestRoundTrip(unittest.TestCase, Keys):
    def test_every_slot_type_opens(self):
        data = os.urandom(70_000)
        blob = mlock.encrypt(data, [self.master.recipient(), self.session, self.pw], chunk_log2=12)
        for ident in (self.master, self.session, self.pw):
            with self.subTest(ident=repr(ident)):
                self.assertEqual(mlock.decrypt(blob, [ident]), data)

    def test_sizes_around_chunk_boundaries(self):
        size = 1 << 12
        for n in (0, 1, size - 1, size, size + 1, 2 * size, 3 * size + 7):
            with self.subTest(n=n):
                data = os.urandom(n)
                blob = mlock.encrypt(data, [self.master.recipient()], chunk_log2=12)
                self.assertEqual(mlock.decrypt(blob, [self.master]), data)
                self.assertEqual(mlock.inspect(blob).plaintext_len, n)

    def test_default_chunk_size(self):
        data = os.urandom(200_000)
        blob = mlock.encrypt(data, [self.master.recipient(), self.session])
        self.assertEqual(mlock.inspect(blob).chunk_size, 65536)
        self.assertEqual(mlock.decrypt(blob, [self.session]), data)

    def test_try_several_identities(self):
        blob = mlock.encrypt(b"x", [self.master.recipient()])
        self.assertEqual(mlock.decrypt(blob, [self.other_session, self.wrong_pw, self.master]), b"x")

    def test_same_plaintext_encrypts_differently(self):
        a = mlock.encrypt(b"same", [self.master.recipient(), self.session])
        b = mlock.encrypt(b"same", [self.master.recipient(), self.session])
        self.assertNotEqual(a, b)


# ── 錯的金鑰 ─────────────────────────────────────────────────────────────────


class TestWrongKeys(unittest.TestCase, Keys):
    def setUp(self):
        self.blob = mlock.encrypt(b"secret data", [self.master.recipient(), self.session, self.pw])

    def test_wrong_master(self):
        self.assertEqual(code_of(mlock.decrypt, self.blob, [self.other_master]), "MLK-E05")

    def test_wrong_session_key(self):
        self.assertEqual(code_of(mlock.decrypt, self.blob, [self.other_session]), "MLK-E05")

    def test_wrong_passphrase(self):
        self.assertEqual(code_of(mlock.decrypt, self.blob, [self.wrong_pw]), "MLK-E05")

    def test_no_identity(self):
        self.assertEqual(code_of(mlock.decrypt, self.blob, []), "MLK-E14")

    def test_master_public_key_cannot_decrypt(self):
        with self.assertRaises(Exception):
            mlock.decrypt(self.blob, [self.master.recipient()])


# ── 竄改、截斷、降級 ─────────────────────────────────────────────────────────


class TestTampering(unittest.TestCase, Keys):
    def setUp(self):
        self.data = os.urandom(10_000)
        self.blob = mlock.encrypt(self.data, [self.master.recipient(), self.session], chunk_log2=12)
        self.start = payload_start(self.blob)

    def test_every_header_byte_is_protected(self):
        for i in range(self.start):
            with self.subTest(offset=i):
                with self.assertRaises(MlockError):
                    mlock.decrypt(flip(self.blob, i), [self.master])
                with self.assertRaises(MlockError):
                    mlock.decrypt(flip(self.blob, i), [self.session])

    def test_payload_bytes_are_protected(self):
        for i in range(self.start, len(self.blob), 97):
            with self.subTest(offset=i):
                self.assertEqual(code_of(mlock.decrypt, flip(self.blob, i), [self.master]), "MLK-E07")

    def test_specific_header_codes(self):
        self.assertEqual(code_of(mlock.decrypt, flip(self.blob, 0), [self.master]), "MLK-E01")
        self.assertEqual(code_of(mlock.decrypt, flip(self.blob, 6), [self.master]), "MLK-E02")
        self.assertEqual(code_of(mlock.decrypt, flip(self.blob, 7, 0x03), [self.master]), "MLK-E03")
        # 世代欄位被改 → 槽還打得開，但檔頭 MAC 不符
        self.assertEqual(code_of(mlock.decrypt, flip(self.blob, 44), [self.master]), "MLK-E06")
        # 檔頭 MAC 本身被改
        self.assertEqual(code_of(mlock.decrypt, flip(self.blob, self.start - 1), [self.master]), "MLK-E06")

    def test_chunk_size_change_is_detected(self):
        self.assertIn(code_of(mlock.decrypt, flip(self.blob, 8, 0x01), [self.master]), {"MLK-E05", "MLK-E06"})

    def test_truncated_at_chunk_boundary(self):
        ct = (1 << 12) + 16
        cut = self.blob[: self.start + ct]  # 只留第一塊（它不是最後一塊）
        self.assertEqual(code_of(mlock.decrypt, cut, [self.master]), "MLK-E08")

    def test_truncated_mid_chunk_and_to_header(self):
        self.assertEqual(code_of(mlock.decrypt, self.blob[:-5], [self.master]), "MLK-E07")
        self.assertEqual(code_of(mlock.decrypt, self.blob[: self.start], [self.master]), "MLK-E08")
        self.assertEqual(code_of(mlock.decrypt, self.blob[: self.start - 10], [self.master]), "MLK-E04")
        self.assertEqual(code_of(mlock.decrypt, self.blob[:3], [self.master]), "MLK-E01")

    def test_trailing_data_rejected(self):
        for extra in (b"\x00", os.urandom(16), os.urandom((1 << 12) + 16)):
            with self.subTest(n=len(extra)):
                self.assertIn(code_of(mlock.decrypt, self.blob + extra, [self.master]), {"MLK-E07", "MLK-E08"})

    def test_chunks_cannot_be_reordered(self):
        ct = (1 << 12) + 16
        p = self.blob[self.start :]
        swapped = self.blob[: self.start] + p[ct : 2 * ct] + p[:ct] + p[2 * ct :]
        self.assertEqual(code_of(mlock.decrypt, swapped, [self.master]), "MLK-E07")

    def test_slot_transplant_between_files(self):
        other = mlock.encrypt(b"other", [self.master.recipient(), self.session])
        # 把另一個檔案的整段檔頭（含槽）接到這份內容上
        hybrid = other[: payload_start(other)] + self.blob[self.start :]
        self.assertEqual(code_of(mlock.decrypt, hybrid, [self.session]), "MLK-E07")
        # 只搬一個槽：key_id／AAD 綁了 file_id，打不開
        o_start = 46
        _, blen = struct.unpack(">BH", other[o_start : o_start + 3])
        mine = bytearray(self.blob)
        mine[46 : 46 + 3 + blen] = other[o_start : o_start + 3 + blen]
        self.assertEqual(code_of(mlock.decrypt, bytes(mine), [self.master]), "MLK-E05")

    def test_suite_and_version_downgrade_rejected(self):
        for off, val, code in ((6, 0, "MLK-E02"), (6, 2, "MLK-E02"), (7, 0, "MLK-E03"), (7, 2, "MLK-E03")):
            b = bytearray(self.blob)
            b[off] = val
            self.assertEqual(code_of(mlock.decrypt, bytes(b), [self.master]), code)

    def test_scrypt_parameter_downgrade(self):
        blob = mlock.encrypt(b"pw", [self.master.recipient(), self.pw])
        info = mlock.inspect(blob)
        # 找到密語槽，log_n 改小（低於下限）→ E09；改成範圍內其他值 → AAD 不符 → E05
        off = 46
        for s in info.slots:
            kind, blen = struct.unpack(">BH", blob[off : off + 3])
            if kind == mlock.SLOT_SCRYPT:
                pos = off + 3 + 16
                weak = bytearray(blob)
                weak[pos] = 10
                self.assertEqual(code_of(mlock.decrypt, bytes(weak), [self.pw]), "MLK-E09")
                other = bytearray(blob)
                other[pos] = FAST + 1
                self.assertEqual(code_of(mlock.decrypt, bytes(other), [self.pw]), "MLK-E05")
                break
            off += 3 + blen
        else:
            self.fail("no scrypt slot")

    def test_too_many_slots_in_header(self):
        b = bytearray(self.blob)
        b[45] = mlock.MAX_SLOTS + 1
        self.assertEqual(code_of(mlock.decrypt, bytes(b), [self.master]), "MLK-E10")

    def test_garbage_and_wrong_types(self):
        self.assertEqual(code_of(mlock.decrypt, b"", [self.master]), "MLK-E01")
        self.assertEqual(code_of(mlock.decrypt, os.urandom(500), [self.master]), "MLK-E01")
        self.assertEqual(code_of(mlock.decrypt, "text", [self.master]), "MLK-E14")


# ── 換槽、加槽、移除、rekey ──────────────────────────────────────────────────


class TestRotation(unittest.TestCase, Keys):
    def setUp(self):
        self.data = os.urandom(150_000)
        self.old_session = SessionKey.generate()
        self.blob = mlock.encrypt(self.data, [self.master.recipient(), self.old_session])

    def test_rewrap_revokes_old_session_key_and_keeps_master(self):
        new_session = SessionKey.generate()
        idx = mlock.find_slot(self.blob, self.old_session)
        new = mlock.replace_slot(self.blob, [self.master], idx, new_session)
        self.assertEqual(code_of(mlock.decrypt, new, [self.old_session]), "MLK-E05")
        self.assertEqual(mlock.decrypt(new, [new_session]), self.data)
        self.assertEqual(mlock.decrypt(new, [self.master]), self.data)
        # 換槽很便宜：內容位元組完全一樣
        self.assertEqual(new[payload_start(new) :], self.blob[payload_start(self.blob) :])
        old_info, new_info = mlock.inspect(self.blob), mlock.inspect(new)
        self.assertEqual(new_info.generation, old_info.generation + 1)
        self.assertEqual(new_info.file_id, old_info.file_id)
        self.assertNotEqual(new_info.fingerprint, old_info.fingerprint)

    def test_limit_old_copy_still_opens_with_old_key(self):
        """誠實的限制：換槽只影響新檔案。被複製走的舊檔案，用舊本次金鑰照樣打得開。"""
        new = mlock.replace_slot(self.blob, [self.master], mlock.find_slot(self.blob, self.old_session),
                                 SessionKey.generate())
        self.assertNotEqual(new, self.blob)
        self.assertEqual(mlock.decrypt(self.blob, [self.old_session]), self.data)

    def test_limit_captured_dek_survives_rewrap_but_not_rekey(self):
        """誠實的限制：曾經解開過的人可能留著 DEK；換槽擋不住，rekey 才擋得住。"""
        _, _, captured_dek, _ = mlock._open(self.blob, [self.old_session])
        rewrapped = mlock.replace_slot(self.blob, [self.master], 1, SessionKey.generate())
        header, start = mlock._parse(rewrapped)
        self.assertEqual(mlock._decrypt_payload(captured_dek, header, rewrapped[start:]), self.data)

        new_session = SessionKey.generate()
        rekeyed = mlock.rekey(rewrapped, [self.master], [self.master.recipient(), new_session])
        header2, start2 = mlock._parse(rekeyed)
        self.assertEqual(code_of(mlock._decrypt_payload, captured_dek, header2, rekeyed[start2:]), "MLK-E07")
        self.assertEqual(code_of(mlock.decrypt, rekeyed, [self.old_session]), "MLK-E05")
        self.assertEqual(mlock.decrypt(rekeyed, [self.master]), self.data)
        self.assertEqual(mlock.decrypt(rekeyed, [new_session]), self.data)
        self.assertNotEqual(mlock.inspect(rekeyed).file_id, mlock.inspect(rewrapped).file_id)

    def test_add_and_remove_slot(self):
        added = mlock.add_slot(self.blob, [self.master], self.pw)
        self.assertEqual(len(mlock.inspect(added).slots), 3)
        self.assertEqual(mlock.decrypt(added, [self.pw]), self.data)
        removed = mlock.remove_slot(added, [self.master], mlock.find_slot(added, self.pw))
        self.assertEqual(code_of(mlock.decrypt, removed, [self.pw]), "MLK-E05")
        self.assertEqual(mlock.decrypt(removed, [self.old_session]), self.data)

    def test_session_holder_can_also_rewrap(self):
        """限制：任何槽的持有人都能改槽（例如加自己的密語）。檔頭 MAC 擋外人，不擋槽持有人。"""
        added = mlock.add_slot(self.blob, [self.old_session], self.pw)
        self.assertEqual(mlock.decrypt(added, [self.pw]), self.data)

    def test_cannot_remove_last_slot(self):
        only = mlock.encrypt(b"x", [self.master.recipient()])
        self.assertEqual(code_of(mlock.remove_slot, only, [self.master], 0), "MLK-E11")

    def test_master_slot_is_protected(self):
        self.assertEqual(code_of(mlock.remove_slot, self.blob, [self.master], 0), "MLK-E12")
        self.assertEqual(code_of(mlock.replace_slot, self.blob, [self.master], 0, SessionKey.generate()), "MLK-E12")
        forced = mlock.remove_slot(self.blob, [self.master], 0, allow_remove_master=True)
        self.assertEqual(code_of(mlock.decrypt, forced, [self.master]), "MLK-E05")

    def test_replace_master_with_new_master(self):
        new_master = MasterIdentity.generate()
        moved = mlock.replace_slot(self.blob, [self.master], 0, new_master.recipient())
        self.assertEqual(mlock.decrypt(moved, [new_master]), self.data)
        self.assertEqual(code_of(mlock.decrypt, moved, [self.master]), "MLK-E05")

    def test_new_files_require_master(self):
        self.assertEqual(code_of(mlock.encrypt, b"x", [self.session]), "MLK-E13")
        self.assertEqual(code_of(mlock.rekey, self.blob, [self.master], [self.session]), "MLK-E13")
        blob = mlock.encrypt(b"x", [self.session], require_master=False)
        self.assertEqual(mlock.decrypt(blob, [self.session]), b"x")

    def test_slot_limit(self):
        many = [self.master.recipient()] + [SessionKey.generate() for _ in range(mlock.MAX_SLOTS - 1)]
        blob = mlock.encrypt(b"x", many)
        self.assertEqual(code_of(mlock.add_slot, blob, [self.master], SessionKey.generate()), "MLK-E10")
        self.assertEqual(code_of(mlock.encrypt, b"x", many + [SessionKey.generate()]), "MLK-E10")

    def test_session_key_id_not_linkable_across_files(self):
        a = mlock.encrypt(b"a", [self.master.recipient(), self.session])
        b = mlock.encrypt(b"b", [self.master.recipient(), self.session])
        self.assertNotEqual(mlock.inspect(a).slots[1].key_id, mlock.inspect(b).slots[1].key_id)
        self.assertNotEqual(mlock.inspect(a).slots[0].key_id, mlock.inspect(b).slots[0].key_id)


# ── 檢視與私鑰檔 ─────────────────────────────────────────────────────────────


class TestInspectAndIdentity(unittest.TestCase, Keys):
    def test_inspect_without_and_with_key(self):
        blob = mlock.encrypt(os.urandom(1000), [self.master.recipient(), self.session, self.pw])
        info = mlock.inspect(blob)
        self.assertEqual([s.kind for s in info.slots], ["master", "session-key", "passphrase"])
        self.assertEqual(info.slots[2].scrypt_log_n, FAST)
        self.assertFalse(info.verified)
        checked = mlock.inspect(blob, [self.session])
        self.assertTrue(checked.verified)
        self.assertEqual(checked.opened_by, 1)
        self.assertEqual(code_of(mlock.inspect, flip(blob, 44), [self.session]), "MLK-E06")

    def test_identity_file_roundtrip(self):
        sealed = mlock.seal_identity(self.master, self.pw)
        opened = mlock.open_identity(sealed, self.pw)
        self.assertEqual(opened.private_bytes(), self.master.private_bytes())
        self.assertEqual(code_of(mlock.open_identity, sealed, self.wrong_pw), "MLK-E15")
        for i in range(len(sealed)):
            with self.subTest(offset=i):
                self.assertIn(code_of(mlock.open_identity, flip(sealed, i), self.pw), {"MLK-E15", "MLK-E09"})
        self.assertNotIn(self.master.private_bytes(), sealed)


# ── 祕密不外洩 ───────────────────────────────────────────────────────────────


class TestNoSecretLeak(unittest.TestCase, Keys):
    def test_output_contains_no_key_material(self):
        rng = DetRng(b"leak-test")
        session = SessionKey(os.urandom(32))
        pw_text = "a fairly unique passphrase 4471"
        blob = mlock.encrypt(b"plaintext marker 12345" * 50,
                             [self.master.recipient(), session, Passphrase(pw_text, log_n=FAST)], rng=rng)
        dek, file_id = rng.log[0], rng.log[1]
        for secret in (dek, session.key, pw_text.encode(), self.master.private_bytes(), b"plaintext marker"):
            self.assertNotIn(secret, blob)
        self.assertIn(file_id, blob)  # file_id 是公開的，本來就在檔頭

    def test_reprs_and_errors_do_not_show_secrets(self):
        pw_text = "do-not-print-me-889"
        pw = Passphrase(pw_text, log_n=FAST)
        sk = SessionKey.generate()
        for obj in (pw, sk, self.master, self.master.recipient()):
            text = repr(obj) + str(obj)
            self.assertNotIn(pw_text, text)
            self.assertNotIn(sk.key.hex(), text)
            self.assertNotIn(self.master.private_bytes().hex(), text)
        blob = mlock.encrypt(b"x", [self.master.recipient(), sk])
        for bad in ([pw], [SessionKey.generate()]):
            try:
                mlock.decrypt(blob, bad)
            except MlockError as e:
                msg = str(e) + repr(e) + e.hint
                self.assertNotIn(pw_text, msg)
                self.assertNotIn(sk.key.hex(), msg)
                self.assertTrue(e.code.startswith("MLK-E"))
        info_text = repr(mlock.inspect(blob, [sk]))
        self.assertNotIn(sk.key.hex(), info_text)
        self.assertNotIn(self.master.private_bytes().hex(), info_text)

    def test_every_error_code_has_hint(self):
        for code, (name, hint) in mlock.ERROR_HINTS.items():
            self.assertRegex(code, r"^MLK-E\d\d$")
            self.assertTrue(name and hint)


if __name__ == "__main__":
    unittest.main()
