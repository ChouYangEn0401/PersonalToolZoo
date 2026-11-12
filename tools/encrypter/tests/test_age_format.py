"""age 格式本身：往返、多收件人、竄改、截斷／加料／對調、錯金鑰、密語規則、work factor 上限。
金鑰都在測試裡臨時產生；密語用低成本（2^10）以免太慢。"""

import io
import os
import time
import tracemalloc
import unittest
from unittest import mock

from _support import Case

from crypto_tool import agefmt
from crypto_tool.agefmt import _common, recipients as rmod, stream as smod
from crypto_tool.agefmt.header import Source, Stanza, parse_header, seal_header
from crypto_tool.sealed.errors import SealError

LOW = 10  # 測試用的密語運算成本


def enc(data, recips, armor=False):
    return agefmt.encrypt_bytes(data, recips, armor=armor)


def dec(blob, ids, armor=None):
    return agefmt.decrypt_bytes(blob, ids, armor=armor)


def split(blob):
    """回傳 (標頭位元組, nonce, 內容分塊串)。"""
    src = Source(io.BytesIO(blob))
    parse_header(src)
    head_len = src.consumed
    return blob[:head_len], blob[head_len:head_len + 16], blob[head_len + 16:]


class RoundTripTests(Case):
    def setUp(self):
        super().setUp()
        self.a = agefmt.generate_identity()
        self.b = agefmt.generate_identity()
        self.master = agefmt.generate_identity()

    def test_sizes_and_armor(self):
        sizes = [0, 1, 1000, 65535, 65536, 65537, 2 * 65536, 2 * 65536 + 1, 3 * 65536 - 1]
        for n in sizes:
            data = os.urandom(n)
            for armor in (False, True):
                with self.subTest(size=n, armor=armor):
                    blob = enc(data, [self.a.recipient], armor=armor)
                    self.assertEqual(agefmt.detect(blob), "armor" if armor else "binary")
                    self.assertEqual(dec(blob, [self.a]), data)
                    if not armor:
                        _, _, payload = split(blob)
                        chunks = max(1, -(-n // 65536))
                        self.assertEqual(len(payload), n + 16 * chunks)

    def test_every_recipient_can_open_the_same_ciphertext(self):
        """萬用鎖：同一份密文，任一把鑰匙都能開；每多一把只多一個約 100 位元組的區塊。"""
        data = os.urandom(70000)
        one = enc(data, [self.a.recipient])
        three = enc(data, [self.a.recipient, self.b.recipient, self.master.recipient])
        for ident in (self.a, self.b, self.master):
            self.assertEqual(dec(three, [ident]), data)
        extra = len(three) - len(one)
        self.assertLess(extra, 2 * 130)
        self.assertEqual(split(three)[0].count(b"\n-> X25519 "), 3)

    def test_recipient_strings_and_identities_are_accepted(self):
        data = b"hello"
        blob = enc(data, [self.a.public_key, self.b])  # 公鑰字串，或直接給身分（取其公鑰）
        self.assertEqual(dec(blob, [self.b.secret_key_string()]), data)
        self.assertEqual(dec(blob, [self.a]), data)

    def test_duplicate_recipients_are_collapsed(self):
        blob = enc(b"x", [self.a.recipient, self.a.public_key, self.a])
        self.assertEqual(split(blob)[0].count(b"-> X25519 "), 1)

    def test_passphrase_round_trip(self):
        data = os.urandom(5000)
        blob = enc(data, [agefmt.passphrase_recipient("correct horse", LOW)], armor=True)
        self.assertEqual(dec(blob, [agefmt.passphrase_identity("correct horse")]), data)
        head = split(enc(data, [agefmt.passphrase_recipient("p", LOW)]))[0]
        self.assertIn(b"-> scrypt ", head)
        self.assertIn(b" 10\n", head)

    def test_header_format_details(self):
        blob = enc(b"abc", [self.a.recipient])
        head = split(blob)[0]
        lines = head.split(b"\n")
        self.assertEqual(lines[0], b"age-encryption.org/v1")
        self.assertTrue(lines[1].startswith(b"-> X25519 "))
        self.assertEqual(len(lines[1].split(b" ")[2]), 43)   # 32 位元組、無 padding
        self.assertEqual(len(lines[2]), 43)                   # 本體 32 位元組 → 43 字（短行結束）
        self.assertTrue(lines[3].startswith(b"--- "))
        self.assertNotIn(b"=", head)

    def test_long_stanza_body_wraps_at_64_columns(self):
        """本體剛好 48 位元組的倍數時，要多一個空行（最後一行必須短於 64 字）。"""
        for size, expect_lines in ((48, [64, 0]), (49, [64, 2]), (96, [64, 64, 0]), (0, [0])):
            body = os.urandom(size)
            raw = Stanza("test", ("a",), body).marshal().split(b"\n")[1:-1]
            self.assertEqual([len(x) for x in raw], expect_lines, size)
            src = Source(io.BytesIO(b"age-encryption.org/v1\n" + Stanza("test", ("a",), body).marshal()
                                    + b"--- " + b"A" * 43 + b"\n"))
            self.assertEqual(parse_header(src).stanzas[0].body, body)

    def test_unknown_stanzas_are_ignored(self):
        """grease：不認得的區塊要略過。"""
        file_key = os.urandom(16)
        stanzas = [Stanza("example.com/grease", ("x", "y"), os.urandom(70)),
                   self.a.recipient.wrap(file_key)]
        header = seal_header(file_key, stanzas)
        nonce = os.urandom(16)
        payload = io.BytesIO()
        smod.encrypt_payload(io.BytesIO(b"grease ok").read, payload.write, smod.payload_key(file_key, nonce))
        blob = header.marshal() + nonce + payload.getvalue()
        self.assertEqual(dec(blob, [self.a]), b"grease ok")


class FailureTests(Case):
    def setUp(self):
        super().setUp()
        self.a = agefmt.generate_identity()
        self.b = agefmt.generate_identity()
        self.data = os.urandom(3 * 65536 + 123)   # 4 塊
        self.blob = enc(self.data, [self.a.recipient, self.b.recipient])

    def fails(self, blob, ids=None, codes=("corrupt",)):
        out = io.BytesIO()
        with self.assertRaises(SealError) as caught:
            agefmt.decrypt_stream(io.BytesIO(blob), out, ids or [self.a])
        self.assertIn(caught.exception.code, codes)
        return caught.exception, out.getvalue()

    def test_wrong_key(self):
        err, out = self.fails(self.blob, [agefmt.generate_identity()], ("wrong_key",))
        self.assertEqual(out, b"")
        err, _ = self.fails(self.blob, [agefmt.passphrase_identity("nope")], ("wrong_key",))
        self.assertIn("金鑰", err.reason)

    def test_every_header_byte_is_protected(self):
        """改標頭的任何一個位元組都必須失敗，而且不輸出任何東西。"""
        head = split(self.blob)[0]
        for i in range(len(head)):
            for flip in (0x01, 0x80):
                tampered = bytearray(self.blob)
                tampered[i] ^= flip
                with self.subTest(offset=i, flip=flip):
                    _, out = self.fails(bytes(tampered), codes=("corrupt", "wrong_key", "unsupported_format"))
                    self.assertEqual(out, b"")

    def test_mac_region_failures(self):
        head, _, _ = split(self.blob)
        mac_line = head.rsplit(b"\n", 2)[-2]
        cases = {
            "mac-changed": head.replace(mac_line, mac_line[:-1] + (b"A" if mac_line[-1:] != b"A" else b"B")),
            "mac-missing": head.replace(mac_line + b"\n", b"---\n"),
            "mac-extra-space": head.replace(mac_line, mac_line.replace(b"--- ", b"---  ")),
            "mac-trailing-space": head.replace(mac_line, mac_line + b" "),
        }
        for name, new_head in cases.items():
            with self.subTest(case=name):
                err, _ = self.fails(new_head + self.blob[len(head):])
                self.assertTrue(err.detail == "hmac" or err.detail.startswith("header:"), err.detail)

    def test_payload_tampering(self):
        head, nonce, payload = split(self.blob)
        base = len(head)
        for name, offset in (("nonce", base), ("first-chunk", base + 16 + 10),
                             ("first-tag", base + 16 + 65536 + 5), ("middle", base + 16 + 65552 + 999),
                             ("last-chunk", len(self.blob) - 30), ("last-tag", len(self.blob) - 1)):
            tampered = bytearray(self.blob)
            tampered[offset] ^= 0x40
            with self.subTest(case=name):
                err, _ = self.fails(bytes(tampered))
                self.assertTrue(err.detail.startswith("payload:"), err.detail)

    def test_truncation_extension_and_reordering(self):
        head, nonce, payload = split(self.blob)
        enc_chunk = 65552
        chunks = [payload[i:i + enc_chunk] for i in range(0, len(payload), enc_chunk)]
        self.assertEqual(len(chunks), 4)
        cases = {
            "no-payload": head,
            "half-nonce": head + nonce[:8],
            "nonce-only": head + nonce,
            "cut-at-chunk-boundary": head + nonce + chunks[0],
            "cut-two-chunks": head + nonce + b"".join(chunks[:2]),
            "cut-inside-last": self.blob[:-5],
            "cut-one-byte": self.blob[:-1],
            "extra-byte": self.blob + b"\x00",
            "extra-chunk": self.blob + chunks[-1],
            "swap-chunks": head + nonce + chunks[1] + chunks[0] + b"".join(chunks[2:]),
            "drop-middle": head + nonce + chunks[0] + b"".join(chunks[2:]),
            "duplicate-chunk": head + nonce + chunks[0] + chunks[0] + b"".join(chunks[1:]),
        }
        for name, blob in cases.items():
            with self.subTest(case=name):
                err, out = self.fails(blob)
                self.assertTrue(err.detail.startswith(("payload:", "header:")), err.detail)
                self.assertTrue(self.data.startswith(out), "只能釋出已驗證的前段")
        self.assertEqual(len(head) + 16 + sum(map(len, chunks)), len(self.blob))

    def test_empty_final_chunk_is_rejected(self):
        """除了整個內容是空的，最後一塊不能是空塊。"""
        file_key = os.urandom(16)
        header = seal_header(file_key, [self.a.recipient.wrap(file_key)])
        nonce = os.urandom(16)
        aead = _common.chacha(smod.payload_key(file_key, nonce))
        body = aead.encrypt(smod._nonce(0, False), b"x" * 65536, None) + aead.encrypt(smod._nonce(1, True), b"", None)
        err, out = self.fails(header.marshal() + nonce + body)
        self.assertEqual(err.detail, "payload:empty-final-chunk")
        self.assertEqual(out, b"x" * 65536)

    def test_not_age_and_other_versions(self):
        for blob, code in ((b"", "unsupported_format"), (b"hello world\n", "unsupported_format"),
                           (b"age-encryption.org/v2\n-> X\n\n--- x\n", "unsupported_format"),
                           (b"age-encryption.org/v1", "corrupt")):
            with self.subTest(blob=blob[:20]):
                self.fails(blob, codes=(code,))

    def test_bad_armor(self):
        armored = enc(b"data", [self.a.recipient], armor=True)
        lines = armored.split(b"\n")
        cases = {
            "garbage-before": b"garbage\n" + armored,
            "garbage-after": armored + b"garbage\n",
            "lowercase-label": armored.replace(b"BEGIN AGE", b"BEGIN age"),
            "missing-end": b"\n".join(lines[:-2]) + b"\n",
            "long-line": armored.replace(lines[1], lines[1] + b"AAAA"),
            "header-line": armored.replace(lines[0] + b"\n", lines[0] + b"\nVersion: 1\n"),
        }
        for name, blob in cases.items():
            with self.subTest(case=name):
                # 開頭就有雜訊時自動辨識認不出是 armor，會當成「不是 age 檔」
                codes = ("unsupported_format",) if name == "garbage-before" else ("corrupt",)
                err, _ = self.fails(blob, codes=codes)
                self.assertTrue(err.detail.startswith(("armor:", "header:")), err.detail)
        with self.assertRaises(SealError) as caught:  # 明確指定 armor 時，一律是 armor 錯誤
            agefmt.decrypt_stream(io.BytesIO(cases["garbage-before"]), io.BytesIO(), [self.a], armor=True)
        self.assertEqual(caught.exception.detail, "armor:invalid-first-line")
        # 前後空白與 CRLF 是允許的
        ok = b"  \r\n" + armored.replace(b"\n", b"\r\n") + b"\r\n \n"
        self.assertEqual(dec(ok, [self.a]), b"data")

    def test_low_order_recipient_is_rejected_when_encrypting(self):
        with self.assertRaises(SealError) as caught:
            enc(b"x", [rmod.X25519Recipient(b"\x00" * 32)])
        self.assertEqual(caught.exception.code, "bad_key_format")


class PassphraseRuleTests(Case):
    def setUp(self):
        super().setUp()
        self.a = agefmt.generate_identity()

    def test_encrypt_refuses_mixing_passphrase_with_others(self):
        p = agefmt.passphrase_recipient("pw", LOW)
        for recips in ([p, self.a.recipient], [self.a.recipient, p],
                       [p, agefmt.passphrase_recipient("other", LOW)]):
            with self.assertRaises(SealError) as caught:
                enc(b"x", recips)
            self.assertEqual(caught.exception.code, "bad_input")
            self.assertEqual(caught.exception.detail, "scrypt-not-alone")

    def test_decrypt_refuses_mixed_header_even_for_key_holders(self):
        file_key = os.urandom(16)
        stanzas = [self.a.recipient.wrap(file_key), agefmt.passphrase_recipient("pw", LOW).wrap(file_key)]
        header = seal_header(file_key, stanzas)
        nonce = os.urandom(16)
        payload = io.BytesIO()
        smod.encrypt_payload(io.BytesIO(b"x").read, payload.write, smod.payload_key(file_key, nonce))
        blob = header.marshal() + nonce + payload.getvalue()
        for ids in ([self.a], [agefmt.passphrase_identity("pw")]):
            with self.assertRaises(SealError) as caught:
                dec(blob, ids)
            self.assertEqual(caught.exception.detail, "header:scrypt-not-alone")

    def test_default_work_factor_is_18_like_age(self):
        """不真的跑 2^18（256 MiB）：把 scrypt 換成假的，只檢查標頭寫的參數。"""
        seen = []

        def fake(passphrase, salt, log_n):
            seen.append(log_n)
            return b"\x00" * 32

        with mock.patch.object(rmod, "scrypt_key", fake):
            stanza = agefmt.passphrase_recipient("pw").wrap(os.urandom(16))
        self.assertEqual(agefmt.DEFAULT_SCRYPT_WORK_FACTOR, 18)
        self.assertEqual(stanza.args[1], "18")
        self.assertEqual(seen, [18])

    def _scrypt_file(self, work_factor_text):
        file_key = os.urandom(16)
        stanza = Stanza("scrypt", (_common.b64_encode_raw(os.urandom(16)).decode(), work_factor_text),
                        os.urandom(32))
        header = seal_header(file_key, [stanza])
        return header.marshal() + os.urandom(16) + os.urandom(40)

    def test_work_factor_cap_rejects_without_using_memory(self):
        self.assertEqual(agefmt.MAX_SCRYPT_WORK_FACTOR, 22)
        for wf in ("23", "30", "64", "99999999999999999999"):
            blob = self._scrypt_file(wf)
            tracemalloc.start()
            t0 = time.monotonic()
            try:
                with self.assertRaises(SealError) as caught:
                    dec(blob, [agefmt.passphrase_identity("pw")])
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            with self.subTest(work_factor=wf):
                self.assertEqual(caught.exception.code, "unsupported_format")
                self.assertEqual(caught.exception.detail, "header:scrypt-work-factor-too-large")
                self.assertLess(time.monotonic() - t0, 2.0)
                self.assertLess(peak, 4 * 1024 * 1024)

    def test_work_factor_encoding_rules(self):
        for wf in ("010", "0", "-1", "+5", "0x10", "1e1", "5 "):
            with self.subTest(work_factor=wf):
                try:
                    blob = self._scrypt_file(wf)
                except ValueError:  # 帶空白的引數根本寫不出來
                    continue
                with self.assertRaises(SealError) as caught:
                    dec(blob, [agefmt.passphrase_identity("pw")])
                self.assertTrue(caught.exception.detail.startswith("header:"))

    def test_custom_lower_cap(self):
        blob = enc(b"secret", [agefmt.passphrase_recipient("pw", 12)])
        with self.assertRaises(SealError) as caught:
            dec(blob, [agefmt.passphrase_identity("pw", max_work_factor=11)])
        self.assertEqual(caught.exception.code, "unsupported_format")
        self.assertEqual(dec(blob, [agefmt.passphrase_identity("pw")]), b"secret")

    def test_wrong_passphrase(self):
        blob = enc(b"secret", [agefmt.passphrase_recipient("right", LOW)])
        with self.assertRaises(SealError) as caught:
            dec(blob, [agefmt.passphrase_identity("wrong")])
        self.assertEqual(caught.exception.code, "wrong_key")
        with self.assertRaises(SealError) as caught:
            dec(blob, [self.a])
        self.assertEqual(caught.exception.code, "wrong_key")
        self.assertIn("密語", caught.exception.reason)

    def test_empty_passphrase_is_refused(self):
        for make in (agefmt.passphrase_recipient, agefmt.passphrase_identity):
            with self.assertRaises(SealError) as caught:
                make("")
            self.assertEqual(caught.exception.code, "key_missing")


class DetectionTests(Case):
    def test_is_age(self):
        a = agefmt.generate_identity()
        binary = enc(b"x", [a.recipient])
        armored = enc(b"x", [a.recipient], armor=True)
        self.assertTrue(agefmt.is_age(binary[:64]))
        self.assertTrue(agefmt.is_age(armored[:64]))
        self.assertTrue(agefmt.is_age(b"\r\n   \n" + armored[:64]))
        self.assertTrue(agefmt.is_age(b"age-encryption.org/v2\n"))
        for other in (b"", b"PK\x03\x04", b"-----BEGIN PGP MESSAGE-----\n", b"ISD2", b"age"):
            self.assertFalse(agefmt.is_age(other), other)


class NoMissingKeysTests(Case):
    def test_no_identities(self):
        blob = enc(b"x", [agefmt.generate_identity().recipient])
        with self.assertRaises(SealError) as caught:
            dec(blob, [])
        self.assertEqual(caught.exception.code, "key_missing")
        with self.assertRaises(SealError) as caught:
            enc(b"x", [])
        self.assertEqual(caught.exception.code, "key_missing")


if __name__ == "__main__":
    unittest.main()
