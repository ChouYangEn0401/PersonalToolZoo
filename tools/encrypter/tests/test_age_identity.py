"""金鑰與身分檔：產生、公鑰解讀、age-keygen 格式、.env 風格、密語保護的身分檔、祕密不外洩。"""

import io
import pickle
import re
import unittest

from _support import Case

from crypto_tool import agefmt
from crypto_tool.sealed.errors import SealError

LOW = 10
CANARY = "CANARY-pass-7f3e9c1d-DO-NOT-LEAK"


def everything_said(exc: SealError) -> str:
    return " ".join([str(exc), repr(exc), str(exc.to_dict()), exc.reason, exc.action, exc.detail])


class KeyTests(Case):
    def test_generate_and_round_trip_strings(self):
        ident = agefmt.generate_identity()
        secret = ident.secret_key_string()
        self.assertRegex(secret, r"^AGE-SECRET-KEY-1[0-9A-Z]{58}$")
        self.assertRegex(ident.public_key, r"^age1[0-9a-z]{58}$")
        self.assertEqual(agefmt.parse_identity(secret), ident)
        self.assertEqual(agefmt.parse_recipient(ident.public_key), ident.recipient)
        self.assertEqual(str(agefmt.parse_recipient("  " + ident.public_key + "\n")), ident.public_key)
        self.assertNotEqual(agefmt.generate_identity(), ident)

    def test_secret_never_in_repr_str_or_pickle(self):
        ident = agefmt.generate_identity()
        secret = ident.secret_key_string()
        for text in (repr(ident), str(ident), f"{ident}", repr([ident])):
            self.assertNotIn(secret, text)
            self.assertNotIn(secret.lower(), text.lower())
            self.assertIn(ident.public_key, text)
        with self.assertRaises(TypeError):
            pickle.dumps(ident)
        for obj in (agefmt.passphrase_recipient(CANARY, LOW), agefmt.passphrase_identity(CANARY)):
            self.assertNotIn(CANARY, repr(obj) + str(obj))
            with self.assertRaises(TypeError):
                pickle.dumps(obj)

    def test_parse_recipient_errors_do_not_echo_input(self):
        ident = agefmt.generate_identity()
        secret = ident.secret_key_string()
        good = ident.public_key
        cases = {
            secret: "bad_key_format",                       # 把私鑰當公鑰
            good[:-1] + ("q" if good[-1] != "q" else "p"): "bad_key_format",   # 檢查碼錯
            good[:-5]: "bad_key_format",
            good.upper(): "bad_key_format",
            "age1pq1" + "q" * 60: "unsupported_format",
            "ssh-ed25519 AAAAC3Nza": "unsupported_format",
            "": "key_missing",
        }
        for text, code in cases.items():
            with self.subTest(text=text[:12]):
                with self.assertRaises(SealError) as caught:
                    agefmt.parse_recipient(text)
                self.assertEqual(caught.exception.code, code)
                if text:
                    self.assertNotIn(text, everything_said(caught.exception))
        with self.assertRaises(SealError) as caught:
            agefmt.parse_recipient(secret)
        self.assertNotIn(secret[16:40], everything_said(caught.exception))

    def test_parse_identity_errors_do_not_echo_input(self):
        secret = agefmt.generate_identity().secret_key_string()
        broken = secret[:-3] + ("AAA" if secret[-3:] != "AAA" else "QQQ")
        for text, code in ((broken, "bad_key_format"), (secret.lower()[:-1], "bad_key_format"),
                           ("AGE-SECRET-KEY-PQ-1" + "Q" * 60, "unsupported_format"),
                           ("AGE-PLUGIN-YUBIKEY-1QQQQ", "unsupported_format")):
            with self.subTest(text=text[:20]):
                with self.assertRaises(SealError) as caught:
                    agefmt.parse_identity(text)
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(text[15:], everything_said(caught.exception))

    def test_parse_recipients_list(self):
        a, b = agefmt.generate_identity(), agefmt.generate_identity()
        text = f"# team\n{a.public_key}\n\n{b.public_key}\n{a.public_key}\n"
        self.assertEqual(agefmt.parse_recipients(text), [a.recipient, b.recipient])


class IdentityFileTests(Case):
    def test_age_keygen_format(self):
        a, b = agefmt.generate_identity(), agefmt.generate_identity()
        text = agefmt.format_identity_file([a, b], created="2026-01-02T15:04:05+08:00")
        lines = text.splitlines()
        self.assertEqual(lines[0], "# created: 2026-01-02T15:04:05+08:00")
        self.assertEqual(lines[1], f"# public key: {a.public_key}")
        self.assertEqual(lines[2], a.secret_key_string())
        self.assertEqual(lines[3], "")
        self.assertEqual(lines[6], b.secret_key_string())
        self.assertEqual(agefmt.parse_identity_file(text), [a, b])
        stamp = agefmt.format_identity_file(a).splitlines()[0]
        self.assertRegex(stamp, r"^# created: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d([+-]\d\d:\d\d|Z)$")

    def test_env_style_lines_crlf_and_bom(self):
        a, b = agefmt.generate_identity(), agefmt.generate_identity()
        text = (
            "\ufeff# keys for the tool\r\n"
            f"export AGE_KEY=\"{a.secret_key_string()}\"\r\n"
            "ENCRYPTER_MASTER_RECIPIENT=" + b.public_key + "\r\n"
            "OTHER_SETTING = some value\r\n"
            f"SECOND='{b.secret_key_string()}'\r\n"
            f"{a.secret_key_string()}\r\n"
        )
        self.assertEqual(agefmt.parse_identity_file(text), [a, b])
        self.assertEqual(agefmt.parse_identity_file(text.encode("utf-8")), [a, b])

    def test_bad_lines(self):
        secret = agefmt.generate_identity().secret_key_string()
        broken = secret[:-2] + ("AA" if secret[-2:] != "AA" else "QQ")
        for text, code, line_no in (
            (f"# ok\n{broken}\n", "bad_key_format", 2),
            ("just some words\n", "bad_key_format", 1),
            ("# only comments\n\n", "key_missing", None),
            ("AGE-SECRET-KEY-PQ-1" + "Q" * 60 + "\n", "unsupported_format", 1),
            (b"\xff\xfe\x00bad", "bad_key_format", None),
        ):
            with self.subTest(code=code, line=line_no):
                with self.assertRaises(SealError) as caught:
                    agefmt.parse_identity_file(text)
                self.assertEqual(caught.exception.code, code)
                said = everything_said(caught.exception)
                if line_no:
                    self.assertIn(f"第 {line_no} 行", said)
                self.assertNotIn(broken[15:], said)

    def test_passphrase_protected_identity_file(self):
        a, b = agefmt.generate_identity(), agefmt.generate_identity()
        for armor in (True, False):
            path = self.tmp / f"keys-{armor}.env"
            agefmt.write_identity_file(path, [a, b], passphrase=CANARY, armor=armor, work_factor=LOW)
            data = path.read_bytes()
            self.assertTrue(agefmt.is_encrypted_identity_file(data))
            self.assertNotIn(a.secret_key_string().encode(), data)
            self.assertEqual(data.startswith(b"-----BEGIN AGE ENCRYPTED FILE-----"), armor)
            # 標準做法：內容就是 scrypt 收件人的 age 檔
            info = agefmt.inspect(path)
            self.assertEqual(info.stanza_types, ("scrypt",))
            with self.subTest(armor=armor):
                self.assertEqual(agefmt.load_identity_file(path, lambda: CANARY), [a, b])
                self.assertEqual(agefmt.parse_identity_file(data, lambda: CANARY), [a, b])
                with self.assertRaises(SealError) as caught:
                    agefmt.load_identity_file(path)
                self.assertEqual(caught.exception.code, "key_missing")
                wrong = CANARY + "-wrong"
                with self.assertRaises(SealError) as caught:
                    agefmt.load_identity_file(path, lambda: wrong)
                self.assertEqual(caught.exception.code, "wrong_key")
                self.assertNotIn(CANARY, everything_said(caught.exception))
        # 文字封裝的版本可以當成一般文字讀進來再解讀
        text = (self.tmp / "keys-True.env").read_text(encoding="ascii")
        self.assertEqual(agefmt.parse_identity_file(text, lambda: CANARY), [a, b])

    def test_plain_identity_file_written_and_protected_from_overwrite(self):
        a = agefmt.generate_identity()
        path = self.tmp / ".decryption_code.env"
        agefmt.write_identity_file(path, a)
        self.assertEqual(agefmt.load_identity_file(path), [a])
        with self.assertRaises(SealError) as caught:
            agefmt.write_identity_file(path, agefmt.generate_identity())
        self.assertEqual(caught.exception.code, "output_exists")
        self.assertEqual(agefmt.load_identity_file(path), [a])
        self.assertEqual([p.name for p in self.tmp.iterdir()], [path.name])

    def test_identity_file_used_for_decryption(self):
        a = agefmt.generate_identity()
        blob = agefmt.encrypt_bytes(b"payload", [a.recipient])
        ids = agefmt.parse_identity_file(agefmt.format_identity_file(a))
        self.assertEqual(agefmt.decrypt_bytes(blob, ids), b"payload")


class SecretLeakTests(Case):
    """特徵明顯的假密語、私鑰，不可以出現在任何例外或回傳值裡。"""

    def test_passphrase_never_appears(self):
        src = self.tmp / "plain.txt"
        src.write_bytes(b"some plaintext")
        dst = self.tmp / "plain.txt.age"
        res = agefmt.encrypt_file(src, dst, [agefmt.passphrase_recipient(CANARY, LOW)])
        self.assertNotIn(CANARY, repr(res) + str(res.to_dict()))
        self.assertNotIn(CANARY.encode(), dst.read_bytes())
        info = agefmt.inspect(dst)
        self.assertNotIn(CANARY, repr(info))
        wrong = "WRONG-" + CANARY
        for ids in ([agefmt.passphrase_identity(wrong)], [agefmt.passphrase_identity(wrong, max_work_factor=5)]):
            with self.assertRaises(SealError) as caught:
                agefmt.decrypt_file(dst, self.tmp / "out.txt", ids)
            said = everything_said(caught.exception)
            self.assertNotIn(CANARY, said)
            self.assertNotIn("some plaintext", said)
        ok = agefmt.decrypt_file(dst, self.tmp / "out.txt", [agefmt.passphrase_identity(CANARY)])
        self.assertNotIn(CANARY, repr(ok) + str(ok.to_dict()))
        self.assertNotIn("some plaintext", repr(ok))

    def test_secret_key_never_appears(self):
        a = agefmt.generate_identity()
        secret = a.secret_key_string()
        blob = agefmt.encrypt_bytes(b"x", [a.recipient])
        out = io.BytesIO()
        res = agefmt.decrypt_stream(io.BytesIO(blob), out, [a])
        self.assertNotIn(secret, repr(res) + str(res.to_dict()))
        self.assertIn(a.public_key, res.matched)
        with self.assertRaises(SealError) as caught:
            agefmt.decrypt_bytes(blob + b"junk", [a])
        self.assertNotIn(secret, everything_said(caught.exception))
        self.assertIsNone(re.search(r"AGE-SECRET-KEY-1[0-9A-Z]{20}", everything_said(caught.exception)))


if __name__ == "__main__":
    unittest.main()
