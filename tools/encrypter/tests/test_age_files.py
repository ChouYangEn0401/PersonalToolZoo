"""檔案層：加解密檔案、不留半成品、覆蓋規則、inspect、換鎖（rewrap）、換檔案金鑰（rekey）、
大檔串流記憶體。"""

import hashlib
import os
import time
import tracemalloc
import unittest
from unittest import mock

from _support import Case

from crypto_tool import agefmt
from crypto_tool.agefmt import api as api_mod
from crypto_tool.sealed.errors import SealError

LOW = 10


def leftovers(folder):
    return sorted(p.name for p in folder.iterdir() if ".partial-" in p.name)


class FileApiTests(Case):
    def setUp(self):
        super().setUp()
        self.a = agefmt.generate_identity()
        self.src = self.tmp / "report.pdf"
        self.data = os.urandom(200_000)
        self.src.write_bytes(self.data)

    def test_encrypt_decrypt_file(self):
        enc = self.tmp / "report.pdf.age"
        calls = []
        res = agefmt.encrypt_file(self.src, enc, [self.a.recipient], progress=lambda d, t: calls.append((d, t)))
        self.assertEqual(res.output, str(enc))
        self.assertEqual(res.plaintext_size, len(self.data))
        self.assertEqual(res.output_size, enc.stat().st_size)
        self.assertEqual(calls[-1], (len(self.data), len(self.data)))
        out = self.tmp / "out.pdf"
        res2 = agefmt.decrypt_file(enc, out, [self.a])
        self.assertEqual(out.read_bytes(), self.data)
        self.assertEqual(res2.plaintext_size, len(self.data))
        self.assertEqual(res2.stanza_types, ("X25519",))
        self.assertEqual(leftovers(self.tmp), [])

    def test_armored_file_and_inspect(self):
        enc = self.tmp / "r.age"
        agefmt.encrypt_file(self.src, enc, [self.a.recipient, agefmt.generate_identity().recipient], armor=True)
        self.assertTrue(enc.read_bytes().startswith(b"-----BEGIN AGE ENCRYPTED FILE-----\n"))
        info = agefmt.inspect(enc)
        self.assertTrue(info.armored)
        self.assertEqual(info.stanza_counts, {"X25519": 2})
        self.assertEqual(info.plaintext_size, len(self.data))
        self.assertFalse(info.passphrase_protected)
        self.assertGreater(info.header_size, 100)
        out = self.tmp / "o"
        agefmt.decrypt_file(enc, out, [self.a])
        self.assertEqual(out.read_bytes(), self.data)

    def test_inspect_detects_bad_size_without_key(self):
        enc = self.tmp / "r.age"
        agefmt.encrypt_file(self.src, enc, [agefmt.passphrase_recipient("pw", LOW)])
        info = agefmt.inspect(enc)
        self.assertTrue(info.passphrase_protected)
        self.assertEqual(info.scrypt_work_factor, LOW)
        self.assertEqual(info.payload_size, enc.stat().st_size - info.header_size)
        # 只看大小能抓到的截斷：最後一塊剩下 0～16 位元組（不可能的長度）
        last_plain = len(self.data) % 65536
        for cut_bytes in (last_plain, last_plain + 8):
            cut = self.tmp / f"cut{cut_bytes}.age"
            cut.write_bytes(enc.read_bytes()[:-cut_bytes])
            self.assertIsNone(agefmt.inspect(cut).plaintext_size, cut_bytes)
        with self.assertRaises(SealError) as caught:
            agefmt.inspect(self.src)
        self.assertEqual(caught.exception.code, "unsupported_format")

    def test_failed_decrypt_leaves_nothing(self):
        enc = self.tmp / "r.age"
        agefmt.encrypt_file(self.src, enc, [self.a.recipient])
        blob = bytearray(enc.read_bytes())
        blob[-3] ^= 1   # 最後一塊的標籤被改：前面的塊都會先驗證通過
        bad = self.tmp / "bad.age"
        bad.write_bytes(bytes(blob))
        out = self.tmp / "out.pdf"
        with self.assertRaises(SealError) as caught:
            agefmt.decrypt_file(bad, out, [self.a])
        self.assertEqual(caught.exception.code, "corrupt")
        self.assertFalse(out.exists())
        self.assertEqual(leftovers(self.tmp), [])
        with self.assertRaises(SealError) as caught:
            agefmt.decrypt_file(enc, out, [agefmt.generate_identity()])
        self.assertEqual(caught.exception.code, "wrong_key")
        self.assertFalse(out.exists())
        self.assertEqual(leftovers(self.tmp), [])

    def test_failed_encrypt_leaves_nothing(self):
        def boom(read, write, key, progress=None):
            write(b"x" * 1000)
            raise OSError("disk full")

        out = self.tmp / "r.age"
        with mock.patch.object(api_mod, "encrypt_payload", boom):
            with self.assertRaises(SealError) as caught:
                agefmt.encrypt_file(self.src, out, [self.a.recipient])
        self.assertEqual(caught.exception.code, "io_error")
        self.assertFalse(out.exists())
        self.assertEqual(leftovers(self.tmp), [])

    def test_interrupted_decrypt_leaves_nothing(self):
        enc = self.tmp / "r.age"
        agefmt.encrypt_file(self.src, enc, [self.a.recipient])
        out = self.tmp / "o"

        def stop(done, total):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            agefmt.decrypt_file(enc, out, [self.a], progress=stop)
        self.assertFalse(out.exists())
        self.assertEqual(leftovers(self.tmp), [])

    def test_overwrite_rules(self):
        enc = self.tmp / "r.age"
        agefmt.encrypt_file(self.src, enc, [self.a.recipient])
        out = self.tmp / "existing.txt"
        out.write_bytes(b"keep me")
        with self.assertRaises(SealError) as caught:
            agefmt.decrypt_file(enc, out, [self.a])
        self.assertEqual(caught.exception.code, "output_exists")
        self.assertEqual(out.read_bytes(), b"keep me")
        agefmt.decrypt_file(enc, out, [self.a], overwrite=True)
        self.assertEqual(out.read_bytes(), self.data)
        with self.assertRaises(SealError) as caught:
            agefmt.encrypt_file(self.src, enc, [self.a.recipient])
        self.assertEqual(caught.exception.code, "output_exists")
        for func, args in ((agefmt.encrypt_file, (self.src, self.src, [self.a.recipient])),
                           (agefmt.decrypt_file, (enc, enc, [self.a]))):
            with self.assertRaises(SealError) as caught:
                func(*args, overwrite=True)
            self.assertEqual(caught.exception.code, "bad_input")

    def test_missing_input_and_output_folder(self):
        with self.assertRaises(SealError) as caught:
            agefmt.encrypt_file(self.tmp / "nope", self.tmp / "x.age", [self.a.recipient])
        self.assertEqual(caught.exception.code, "input_missing")
        with self.assertRaises(SealError) as caught:
            agefmt.encrypt_file(self.src, self.tmp / "no-dir" / "x.age", [self.a.recipient])
        self.assertEqual(caught.exception.code, "input_missing")
        with self.assertRaises(SealError) as caught:
            agefmt.encrypt_file(self.tmp, self.tmp / "x.age", [self.a.recipient])
        self.assertEqual(caught.exception.code, "bad_input")


class RewrapTests(Case):
    def setUp(self):
        super().setUp()
        self.old = agefmt.generate_identity()
        self.master = agefmt.generate_identity()     # 萬用鎖
        self.new = agefmt.generate_identity()
        self.data = os.urandom(150_000)
        src = self.tmp / "plain"
        src.write_bytes(self.data)
        self.enc = self.tmp / "plain.age"
        agefmt.encrypt_file(src, self.enc, [self.old.recipient, self.master.recipient])
        self.copy = self.tmp / "old-copy.age"
        self.copy.write_bytes(self.enc.read_bytes())

    def opens(self, path, ident) -> bool:
        try:
            return agefmt.decrypt_bytes(path.read_bytes(), [ident]) == self.data
        except SealError as exc:
            self.assertEqual(exc.code, "wrong_key")
            return False

    def test_rewrap_changes_locks_but_not_content_bytes(self):
        out = self.tmp / "rewrapped.age"
        res = agefmt.rewrap(self.enc, out, [self.old], [self.new.recipient, self.master.recipient])
        self.assertFalse(self.opens(out, self.old))       # 舊鑰匙打不開新檔
        self.assertTrue(self.opens(out, self.new))
        self.assertTrue(self.opens(out, self.master))     # 保留的萬用鎖仍可開
        old_payload = self.enc.read_bytes()[agefmt.inspect(self.enc).header_size:]
        new_payload = out.read_bytes()[agefmt.inspect(out).header_size:]
        self.assertEqual(new_payload, old_payload)        # 內容位元組原封不動
        self.assertEqual(res.payload_sha256, hashlib.sha256(old_payload).hexdigest())
        self.assertEqual(res.payload_size, len(old_payload))
        self.assertTrue(res.payload_verified)
        self.assertNotEqual(out.read_bytes()[:200], self.enc.read_bytes()[:200])
        # 誠實的限制：舊檔案的副本仍然可以被舊鑰匙打開
        self.assertTrue(self.opens(self.copy, self.old))

    def test_rewrap_using_the_master_key(self):
        out = self.tmp / "r.age"
        res = agefmt.rewrap(self.enc, out, [self.master], [self.new.recipient])
        self.assertIn(self.master.public_key, res.matched)
        self.assertTrue(self.opens(out, self.new))
        self.assertFalse(self.opens(out, self.master))

    def test_rewrap_armored_and_in_place(self):
        armored = self.tmp / "a.age"
        agefmt.rewrap(self.enc, armored, [self.old], [self.old.recipient], armor=True)
        self.assertTrue(agefmt.inspect(armored).armored)
        out = self.tmp / "b.age"
        res = agefmt.rewrap(armored, out, [self.old], [self.new.recipient])   # 沿用來源的 armor
        self.assertTrue(res.armored)
        self.assertTrue(self.opens(out, self.new))
        with self.assertRaises(SealError) as caught:
            agefmt.rewrap(out, out, [self.new], [self.master.recipient])
        self.assertEqual(caught.exception.code, "output_exists")
        agefmt.rewrap(out, out, [self.new], [self.master.recipient], overwrite=True)
        self.assertTrue(self.opens(out, self.master))
        self.assertFalse(self.opens(out, self.new))
        self.assertEqual(leftovers(self.tmp), [])

    def test_rewrap_refuses_corrupt_payload(self):
        blob = bytearray(self.enc.read_bytes())
        blob[-1] ^= 1
        bad = self.tmp / "bad.age"
        bad.write_bytes(bytes(blob))
        out = self.tmp / "r.age"
        with self.assertRaises(SealError) as caught:
            agefmt.rewrap(bad, out, [self.old], [self.new.recipient])
        self.assertEqual(caught.exception.code, "corrupt")
        self.assertFalse(out.exists())
        self.assertEqual(leftovers(self.tmp), [])

    def test_rewrap_wrong_key(self):
        with self.assertRaises(SealError) as caught:
            agefmt.rewrap(self.enc, self.tmp / "r.age", [self.new], [self.new.recipient])
        self.assertEqual(caught.exception.code, "wrong_key")

    def test_rewrap_passphrase_rules(self):
        with self.assertRaises(SealError) as caught:
            agefmt.rewrap(self.enc, self.tmp / "r.age", [self.old], [agefmt.passphrase_recipient("pw", LOW)])
        self.assertEqual(caught.exception.code, "bad_input")
        self.assertEqual(caught.exception.detail, "rewrap-to-scrypt")
        # 換密語（來源本來就只有密語）是允許的
        p1 = self.tmp / "p1.age"
        agefmt.rekey(self.enc, p1, [self.old], [agefmt.passphrase_recipient("first", LOW)])
        p2 = self.tmp / "p2.age"
        agefmt.rewrap(p1, p2, [agefmt.passphrase_identity("first")], [agefmt.passphrase_recipient("second", LOW)])
        self.assertTrue(self.opens(p2, agefmt.passphrase_identity("second")))
        self.assertFalse(self.opens(p2, agefmt.passphrase_identity("first")))

    def test_rekey_reencrypts_everything(self):
        out = self.tmp / "rekeyed.age"
        res = agefmt.rekey(self.enc, out, [self.old], [self.new.recipient, self.master.recipient])
        self.assertEqual(res.plaintext_size, len(self.data))
        self.assertTrue(self.opens(out, self.new))
        self.assertTrue(self.opens(out, self.master))
        self.assertFalse(self.opens(out, self.old))
        old_payload = self.enc.read_bytes()[agefmt.inspect(self.enc).header_size:]
        new_payload = out.read_bytes()[agefmt.inspect(out).header_size:]
        self.assertEqual(len(new_payload), len(old_payload))
        self.assertNotEqual(new_payload[:16], old_payload[:16])   # 新 nonce
        self.assertNotEqual(new_payload[16:64], old_payload[16:64])
        self.assertTrue(self.opens(self.copy, self.old))          # 舊副本不受影響（誠實的限制）

    def test_rekey_corrupt_source_leaves_nothing(self):
        blob = bytearray(self.enc.read_bytes())
        blob[-40] ^= 1
        bad = self.tmp / "bad.age"
        bad.write_bytes(bytes(blob))
        out = self.tmp / "r.age"
        with self.assertRaises(SealError) as caught:
            agefmt.rekey(bad, out, [self.old], [self.new.recipient])
        self.assertEqual(caught.exception.code, "corrupt")
        self.assertFalse(out.exists())
        self.assertEqual(leftovers(self.tmp), [])


class _Synthetic:
    """產生 size 位元組的合成資料（重複一塊隨機資料再混入位置），同時算 SHA-256。"""

    def __init__(self, size: int, block: bytes):
        self.left = size
        self.block = block
        self.pos = 0
        self.hash = hashlib.sha256()

    def read(self, n: int) -> bytes:
        n = min(n, self.left, len(self.block))
        if n <= 0:
            return b""
        start = self.pos % (len(self.block) - n + 1)
        out = self.block[start:start + n]
        self.pos += 7919
        self.left -= n
        self.hash.update(out)
        return out


class _HashSink:
    def __init__(self):
        self.hash = hashlib.sha256()
        self.n = 0

    def write(self, data):
        self.hash.update(data)
        self.n += len(data)


class StreamingMemoryTests(Case):
    def _round_trip(self, size: int, block: bytes, ident) -> tuple[int, float]:
        enc = self.tmp / f"big-{size}.age"
        tracemalloc.start()
        t0 = time.monotonic()
        try:
            src = _Synthetic(size, block)
            with open(enc, "wb") as fh:
                agefmt.encrypt_stream(src, fh, [ident.recipient])
            sink = _HashSink()
            with open(enc, "rb") as fh:
                res = agefmt.decrypt_stream(fh, sink, [ident])
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(sink.n, size)
        self.assertEqual(res.plaintext_size, size)
        self.assertEqual(sink.hash.hexdigest(), src.hash.hexdigest())
        enc.unlink()
        return peak, time.monotonic() - t0

    def test_memory_does_not_grow_with_size(self):
        block = os.urandom(1 << 20)
        ident = agefmt.generate_identity()
        small_peak, _ = self._round_trip(2 * 1024 * 1024, block, ident)
        big_peak, seconds = self._round_trip(55 * 1024 * 1024, block, ident)
        print(f"\n[age streaming] peak 2 MiB={small_peak / 1024:.0f} KiB, "
              f"55 MiB={big_peak / 1024:.0f} KiB, 55 MiB round trip {seconds:.1f}s")
        self.assertLess(big_peak, 2 * 1024 * 1024)          # 遠小於 55 MiB
        self.assertLess(big_peak, small_peak + 512 * 1024)  # 不隨大小成長

    def test_decrypt_file_streams_too(self):
        ident = agefmt.generate_identity()
        src = self.tmp / "big.bin"
        block = os.urandom(1 << 20)
        with open(src, "wb") as fh:
            for i in range(8):
                fh.write(block[i:] + block[:i])
        enc = self.tmp / "big.age"
        out = self.tmp / "big.out"
        tracemalloc.start()
        try:
            agefmt.encrypt_file(src, enc, [ident.recipient], armor=True)
            agefmt.decrypt_file(enc, out, [ident])
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 2 * 1024 * 1024)
        with open(src, "rb") as a, open(out, "rb") as b:
            self.assertEqual(hashlib.sha256(a.read()).digest(), hashlib.sha256(b.read()).digest())


if __name__ == "__main__":
    unittest.main()
