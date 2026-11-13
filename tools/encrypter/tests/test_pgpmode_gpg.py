"""PGP 模式實際呼叫 gpg 的測試：金鑰產生、多收件人、收件人＋密語、armor、錯誤分類、
竄改與截斷、祕密不外洩、不碰預設金鑰環、不留下 gpg-agent 與暫存資料夾。

全部離線；金鑰在測試開始時產生（假的 uid，example.invalid）。找不到 gpg 時整組略過。
跑一次大約兩三分鐘（每次 gpg 操作都要啟動一個新的 gpg-agent）。
"""

import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from _support import Case, SealError

from crypto_tool import pgpmode
from crypto_tool.pgpmode import _gpg, ops

KEY_PASS = "KeyPass-Marker-91c2e7-私鑰密語"
FILE_PASS = "FilePass-Marker-4d8b0a-檔案密語"
WRONG = "Wrong-Marker-55e1f9-錯的"
MARKERS = ("Marker-91c2e7", "Marker-4d8b0a", "Marker-55e1f9")

try:
    GPG = pgpmode.find_gpg()
    SKIP = ""
except SealError as exc:
    GPG = None
    SKIP = f"找不到可用的 gpg（{exc.reason}），PGP 整合測試全部略過"

_real_run = subprocess.run
_RECORDED: list[tuple[list[str], dict]] = []   # 每次 subprocess.run 的 (argv, env)
_STATE: dict = {}


def _recording_run(argv, *args, **kwargs):
    _RECORDED.append(([str(a) for a in argv], dict(kwargs.get("env") or {})))
    return _real_run(argv, *args, **kwargs)


def _default_keyrings() -> list[Path]:
    dirs = [Path.home() / ".gnupg"]
    if os.environ.get("APPDATA"):
        dirs.append(Path(os.environ["APPDATA"]) / "gnupg")
    return dirs


def _snapshot() -> dict:
    """預設金鑰環資料夾的檔名、大小、修改時間（只看中繼資料，不讀內容）。"""
    snap = {}
    for folder in _default_keyrings():
        if not folder.is_dir():
            snap[str(folder)] = None
            continue
        entries = {}
        for root, _dirs, files in os.walk(folder):
            for name in files:
                p = Path(root) / name
                try:
                    st = p.stat()
                    entries[str(p.relative_to(folder))] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    pass
        snap[str(folder)] = entries
    return snap


def setUpModule():
    if SKIP:
        return
    _STATE["before"] = _snapshot()
    base = Path(tempfile.mkdtemp(prefix="pgpm-"))
    _STATE["base"] = base
    _STATE["home_prefix"] = _gpg.home_argument(GPG, base)
    patchers = [
        mock.patch.dict(os.environ, {_gpg.ENV_TMPDIR: str(base)}),
        mock.patch.object(_gpg.subprocess, "run", _recording_run),
    ]
    for p in patchers:
        p.start()
    _STATE["patchers"] = patchers
    keys = base.parent / (base.name + "-keys")
    keys.mkdir()
    _STATE["keys"] = keys
    try:
        _make_keys(keys)
    except BaseException:
        tearDownModule()   # setUpModule 失敗時 unittest 不會呼叫 tearDownModule
        raise


def _make_keys(keys: Path) -> None:
    _STATE["A"] = pgpmode.generate_keypair(
        "Test A", "a@example.invalid", out_public=keys / "a.pub.asc", out_secret=keys / "a.sec.asc")
    _STATE["B"] = pgpmode.generate_keypair(
        "測試 B", "b@example.invalid", out_public=keys / "b.pub.asc", out_secret=keys / "b.sec.asc",
        passphrase=KEY_PASS)
    _STATE["C"] = pgpmode.generate_keypair(
        "Test C", None, out_public=keys / "c.pub.asc", out_secret=keys / "c.sec.asc",
        out_revocation=keys / "c.rev")


def tearDownModule():
    for p in reversed(_STATE.get("patchers", [])):
        p.stop()
    for key in ("base", "keys"):
        if key in _STATE:
            shutil.rmtree(_STATE[key], ignore_errors=True)


@unittest.skipIf(GPG is None, SKIP)
class GpgCase(Case):
    def setUp(self):
        super().setUp()
        self.keys = _STATE["keys"]
        self.plain = self.tmp / "plain.bin"
        self.plain.write_bytes(os.urandom(50_000) + "結尾的中文\n".encode("utf-8"))

    def pub(self, who):
        return self.keys / f"{who.lower()}.pub.asc"

    def sec(self, who):
        return self.keys / f"{who.lower()}.sec.asc"

    def assert_no_partials(self, folder=None):
        names = [p.name for p in (folder or self.tmp).iterdir()]
        self.assertFalse([n for n in names if ".partial-" in n], names)

    def decrypt_ok(self, src, **kw):
        out = self.tmp / f"out-{len(list(self.tmp.iterdir()))}.bin"
        result = pgpmode.decrypt_file(src, out, **kw)
        self.assertEqual(out.read_bytes(), self.plain.read_bytes())
        return result

    def decrypt_fails(self, src, **kw):
        out = self.tmp / "should-not-exist.bin"
        code = self.code_of(pgpmode.decrypt_file, src, out, **kw)
        self.assertFalse(out.exists())
        self.assert_no_partials()
        return code

    def packet_listing(self, path):
        with _gpg.GpgSession() as s:
            return s.run(["--list-packets", str(path)]).output


class KeygenTests(GpgCase):
    def test_generated_files_and_protection_flag(self):
        a, b = _STATE["A"], _STATE["B"]
        for r in (a, b, _STATE["C"]):
            self.assertRegex(r["fingerprint"], r"^[0-9A-F]{40}$")
        self.assertEqual(a["uid"], "Test A <a@example.invalid>")
        self.assertEqual(b["uid"], "測試 B <b@example.invalid>")
        self.assertEqual(_STATE["C"]["uid"], "Test C")
        self.assertFalse(a["protected"])
        self.assertIn("warning", a)
        self.assertTrue(b["protected"])
        self.assertNotIn("warning", b)
        self.assertTrue(self.pub("A").read_text().startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----"))
        sec_a = self.sec("A").read_text()
        self.assertTrue(sec_a.startswith("-----BEGIN PGP PRIVATE KEY BLOCK-----"))
        self.assertIn("Comment: " + ops.UNPROTECTED_COMMENT, sec_a)
        self.assertNotIn(ops.UNPROTECTED_COMMENT, self.sec("B").read_text())
        self.assertIn("BEGIN PGP PUBLIC KEY BLOCK", (self.keys / "c.rev").read_text())
        self.assertEqual(pgpmode.pgp_kind(self.pub("A").read_bytes()), "public_key")
        self.assertEqual(pgpmode.pgp_kind(self.sec("B").read_bytes()), "secret_key")

    def test_keys_do_not_advertise_aead(self):
        for who in ("A", "B"):
            listing = self.packet_listing(self.pub(who))
            self.assertIn("features: 01", listing)          # 只有 MDC（SEIPD v1）
            self.assertNotIn("pref-aead-algos", listing)
            self.assertIn("cv25519", listing)              # 有加密用子金鑰

    def test_existing_key_files_are_refused(self):
        before = self.sec("A").read_bytes()
        code = self.code_of(pgpmode.generate_keypair, "Other", out_public=self.tmp / "new.pub.asc",
                            out_secret=self.sec("A"))
        self.assertEqual(code, "output_exists")
        self.assertEqual(self.sec("A").read_bytes(), before)
        self.assertFalse((self.tmp / "new.pub.asc").exists())


class RoundTripTests(GpgCase):
    def test_single_recipient_binary(self):
        dst = self.tmp / "plain.bin.gpg"
        r = pgpmode.encrypt_file(self.plain, dst, recipient_key_files=[self.pub("A")])
        self.assertEqual(r["data_packet"], "seipd_v1")
        self.assertEqual(r["recipient_count"], 1)
        self.assertEqual(pgpmode.pgp_kind(dst.read_bytes()[:64]), "message")
        info = pgpmode.inspect(dst)
        self.assertFalse(info["armor"])
        self.assertEqual(info["recipient_count"], 1)
        self.assertRegex(info["recipients"][0]["key_id"], r"^[0-9A-F]{16}$")
        self.assertEqual(info["recipients"][0]["algo_name"], "ECDH")
        self.assertFalse(info["has_passphrase"])
        self.assertEqual(info["data_packet"], "seipd_v1")
        self.assertTrue(info["integrity_protected"] and info["interoperable"])
        self.assertEqual(self.decrypt_ok(dst, secret_key_files=[self.sec("A")])["used"], "key")
        self.assert_no_partials()

    def test_relative_paths_work_although_gpg_runs_in_its_own_folder(self):
        # gpg 的工作目錄是暫時 home；使用者打的相對路徑要先轉成絕對路徑（打包後的冒煙測試抓到的）
        old = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, old)
        shutil.copy(self.pub("A"), "a.pub.asc")
        shutil.copy(self.sec("A"), "a.sec.asc")
        shutil.copy(self.plain, "rel.bin")
        pgpmode.encrypt_file("rel.bin", "rel.gpg", recipient_key_files=["a.pub.asc"])
        self.assertEqual(pgpmode.inspect("rel.gpg")["recipient_count"], 1)
        pgpmode.decrypt_file("rel.gpg", "back.bin", secret_key_files=["a.sec.asc"])
        self.assertEqual(Path("back.bin").read_bytes(), self.plain.read_bytes())

    def test_multiple_recipients_any_key_opens(self):
        dst = self.tmp / "multi.gpg"
        pgpmode.encrypt_file(self.plain, dst, recipient_key_files=[self.pub("A"), self.pub("B")])
        info = pgpmode.inspect(dst)
        self.assertEqual(info["recipient_count"], 2)
        self.assertEqual(len({r["key_id"] for r in info["recipients"]}), 2)
        self.decrypt_ok(dst, secret_key_files=[self.sec("A")])
        self.decrypt_ok(dst, secret_key_files=[self.sec("B")], key_passphrase=KEY_PASS)
        # 多給一把不相干的私鑰也沒關係
        self.decrypt_ok(dst, secret_key_files=[self.sec("C"), self.sec("A")])

    def test_recipient_plus_passphrase_both_open(self):
        dst = self.tmp / "both.gpg"
        r = pgpmode.encrypt_file(self.plain, dst, recipient_key_files=[self.pub("A")],
                                 passphrase=FILE_PASS)
        self.assertTrue(r["passphrase"])
        info = pgpmode.inspect(dst)
        self.assertEqual(info["recipient_count"], 1)
        self.assertEqual(info["passphrase_packets"], 1)
        self.assertTrue(info["has_passphrase"])
        self.assertEqual(self.decrypt_ok(dst, secret_key_files=[self.sec("A")])["used"], "key")
        self.assertEqual(self.decrypt_ok(dst, passphrase=FILE_PASS)["used"], "passphrase")
        # 私鑰不是收件人時，退回用密語
        self.assertEqual(self.decrypt_ok(dst, secret_key_files=[self.sec("C")],
                                         passphrase=FILE_PASS)["used"], "passphrase")

    def test_passphrase_only_armor(self):
        dst = self.tmp / "text.asc"
        r = pgpmode.encrypt_file(self.plain, dst, passphrase=FILE_PASS, armor=True)
        self.assertTrue(r["armor"])
        self.assertTrue(dst.read_text(encoding="ascii").startswith("-----BEGIN PGP MESSAGE-----"))
        info = pgpmode.inspect(dst)
        self.assertTrue(info["armor"])
        self.assertEqual(info["recipient_count"], 0)
        self.assertTrue(info["has_passphrase"])
        self.assertEqual(info["data_packet"], "seipd_v1")
        self.decrypt_ok(dst, passphrase=FILE_PASS)

    def test_non_ascii_paths(self):
        folder = self.tmp / "子資料夾 含空白"
        folder.mkdir()
        src = folder / "測試 資料.txt"
        src.write_bytes(self.plain.read_bytes())
        dst = folder / "測試 資料.txt.gpg"
        pgpmode.encrypt_file(src, dst, recipient_key_files=[self.pub("B")], passphrase=FILE_PASS)
        out = folder / "解開.txt"
        pgpmode.decrypt_file(dst, out, secret_key_files=[self.sec("B")], key_passphrase=KEY_PASS)
        self.assertEqual(out.read_bytes(), src.read_bytes())

    def test_existing_output_and_overwrite(self):
        dst = self.tmp / "o.gpg"
        dst.write_text("old")
        self.assertEqual(self.code_of(pgpmode.encrypt_file, self.plain, dst, passphrase=FILE_PASS),
                         "output_exists")
        self.assertEqual(dst.read_text(), "old")
        pgpmode.encrypt_file(self.plain, dst, passphrase=FILE_PASS, overwrite=True)
        out = self.tmp / "o.out"
        out.write_text("old")
        self.assertEqual(self.code_of(pgpmode.decrypt_file, dst, out, passphrase=FILE_PASS),
                         "output_exists")
        self.assertEqual(out.read_text(), "old")
        pgpmode.decrypt_file(dst, out, passphrase=FILE_PASS, overwrite=True)
        self.assertEqual(out.read_bytes(), self.plain.read_bytes())

    def test_aead_recipient_key_still_gets_seipd_v1(self):
        """對方的金鑰宣告 AEAD（GnuPG 2.4 在 compliance=gnupg 時的預設）也照樣產生 SEIPD v1。"""
        aead_pub = self.tmp / "aead.pub.asc"
        with _gpg.GpgSession() as s:
            res = s.run(["--compliance=gnupg", "--rfc4880bis", "--quick-generate-key",
                         "AEAD <aead@example.invalid>", "ed25519", "cert", "never"], passphrase="")
            fpr = [a[1] for a in res.args_of("KEY_CREATED")][0]
            s.run(["--compliance=gnupg", "--rfc4880bis", "--quick-add-key", fpr, "cv25519", "encr",
                   "never"], passphrase="")
            s.run(["--armor", "-o", str(aead_pub), "--export", fpr])
            listing = s.run(["--list-packets", str(aead_pub)]).output
            if "pref-aead-algos" not in listing:
                self.skipTest("這版 gpg 產生不出宣告 AEAD 的金鑰")
            # 對照組：gpg 照自己的預設（compliance=gnupg）會用 OCB
            plain = s.folder / "p.txt"
            plain.write_text("x")
            s.run(["--compliance=gnupg", "-o", str(s.folder / "ocb.gpg"), "--encrypt",
                   "--recipient", fpr, str(plain)])
            control = ops._parse_packets(
                s.run(["--list-only", "--list-packets", str(s.folder / "ocb.gpg")]).output)
        self.assertEqual(control["data_packet"], "aead_ocb")
        dst = self.tmp / "to-aead.gpg"
        r = pgpmode.encrypt_file(self.plain, dst, recipient_key_files=[aead_pub])
        self.assertEqual(r["data_packet"], "seipd_v1")
        self.assertTrue(pgpmode.inspect(dst)["interoperable"])


class FailureTests(GpgCase):
    def _encrypted(self, name="enc.gpg", **kw):
        dst = self.tmp / name
        pgpmode.encrypt_file(self.plain, dst, **kw)
        return dst

    def test_wrong_secret_key(self):
        src = self._encrypted(recipient_key_files=[self.pub("A")])
        self.assertEqual(self.decrypt_fails(src, secret_key_files=[self.sec("C")]), "wrong_key")

    def test_wrong_passphrase(self):
        src = self._encrypted(passphrase=FILE_PASS)
        self.assertEqual(self.decrypt_fails(src, passphrase=WRONG), "wrong_key")

    def test_passphrase_for_key_only_file(self):
        src = self._encrypted(recipient_key_files=[self.pub("A")])
        with self.assertRaises(SealError) as caught:
            pgpmode.decrypt_file(src, self.tmp / "x", passphrase=FILE_PASS)
        self.assertEqual(caught.exception.code, "wrong_key")
        self.assertIn("私鑰", caught.exception.reason)

    def test_wrong_or_missing_key_passphrase(self):
        src = self._encrypted(recipient_key_files=[self.pub("B")])
        for kw in ({"key_passphrase": WRONG}, {}):
            with self.assertRaises(SealError) as caught:
                pgpmode.decrypt_file(src, self.tmp / "x", secret_key_files=[self.sec("B")], **kw)
            self.assertEqual(caught.exception.code, "wrong_key")
            self.assertIn("密語", caught.exception.reason)
            self.assertFalse((self.tmp / "x").exists())

    def test_both_routes_wrong(self):
        src = self._encrypted(recipient_key_files=[self.pub("A")], passphrase=FILE_PASS)
        self.assertEqual(self.decrypt_fails(src, secret_key_files=[self.sec("C")], passphrase=WRONG),
                         "wrong_key")

    def test_tampered_ciphertext_is_rejected(self):
        for kw in ({"recipient_key_files": [self.pub("A")]}, {"passphrase": FILE_PASS}):
            src = self._encrypted(**kw)
            data = bytearray(src.read_bytes())
            data[len(data) - 30] ^= 0x01
            src.write_bytes(bytes(data))
            code = self.decrypt_fails(src, secret_key_files=[self.sec("A")], passphrase=FILE_PASS)
            self.assertEqual(code, "corrupt")
            src.unlink()

    def test_tampered_armor_is_rejected(self):
        src = self._encrypted("enc.asc", recipient_key_files=[self.pub("A")], armor=True)
        lines = src.read_text(encoding="ascii").splitlines()
        body = [i for i, line in enumerate(lines) if line and not line.startswith(("-----", "="))
                and ":" not in line]
        target = body[len(body) // 2]
        chars = list(lines[target])
        chars[10] = "A" if chars[10] != "A" else "B"
        lines[target] = "".join(chars)
        src.write_text("\n".join(lines) + "\n", encoding="ascii")
        self.assertEqual(self.decrypt_fails(src, secret_key_files=[self.sec("A")]), "corrupt")

    def test_truncated_file_is_rejected(self):
        src = self._encrypted(recipient_key_files=[self.pub("A")])
        data = src.read_bytes()
        for cut in (20, len(data) // 2, len(data) - 120):
            src.write_bytes(data[:-cut])
            self.assertEqual(self.decrypt_fails(src, secret_key_files=[self.sec("A")]), "corrupt", cut)
        sym = self._encrypted("sym.gpg", passphrase=FILE_PASS)
        data = sym.read_bytes()
        sym.write_bytes(data[: len(data) // 2])
        self.assertEqual(self.decrypt_fails(sym, passphrase=FILE_PASS), "corrupt")

    def test_bad_key_files(self):
        src = self._encrypted(recipient_key_files=[self.pub("A")])
        # 公鑰檔當私鑰用
        self.assertEqual(self.decrypt_fails(src, secret_key_files=[self.pub("A")]), "bad_key_format")
        garbage = self.tmp / "garbage.asc"
        garbage.write_text("not a key at all\n")
        self.assertEqual(self.code_of(pgpmode.encrypt_file, self.plain, self.tmp / "g.gpg",
                                      recipient_key_files=[garbage]), "bad_key_format")
        self.assertFalse((self.tmp / "g.gpg").exists())
        self.assert_no_partials()

    def test_inspect_key_file_and_not_encrypted(self):
        info = pgpmode.inspect(self.pub("A"))
        self.assertEqual(info["kind"], "public_key")
        self.assertFalse(info["encrypted"])
        self.assertTrue(info["armor"])


class SafetyTests(GpgCase):
    """祕密不外洩、只用暫時 home、不碰預設金鑰環、不留殘留。"""

    def test_secrets_never_leak(self):
        texts = []
        src = self.tmp / "s.gpg"
        texts.append(str(pgpmode.encrypt_file(self.plain, src, recipient_key_files=[self.pub("B")],
                                              passphrase=FILE_PASS)))
        texts.append(str(pgpmode.decrypt_file(src, self.tmp / "ok1", passphrase=FILE_PASS)))
        texts.append(str(pgpmode.decrypt_file(src, self.tmp / "ok2", secret_key_files=[self.sec("B")],
                                              key_passphrase=KEY_PASS)))
        texts.append(str(pgpmode.inspect(src)))
        for kw in ({"passphrase": WRONG}, {"secret_key_files": [self.sec("B")], "key_passphrase": WRONG},
                   {"secret_key_files": [self.sec("B")], "key_passphrase": WRONG, "passphrase": WRONG}):
            with self.assertRaises(SealError) as caught:
                pgpmode.decrypt_file(src, self.tmp / "bad", **kw)
            err = caught.exception
            texts += [str(err), repr(err), str(err.to_dict())]
        texts.append(str(_STATE["B"]))
        for text in texts:
            for marker in MARKERS:
                self.assertNotIn(marker, text)
        # 包含 setUpModule 裡用 KEY_PASS 產生 B 的那幾次呼叫
        self.assertTrue(_RECORDED)
        for argv, env in _RECORDED:
            joined = "\n".join(argv) + "\n" + "\n".join(f"{k}={v}" for k, v in env.items())
            for marker in MARKERS:
                self.assertNotIn(marker, joined)
        # 明文也不該出現在任何錯誤或回傳裡：檔案內容是亂數，取一段特徵檢查
        tail = "結尾的中文"
        for text in texts:
            self.assertNotIn(tail, text)

    def test_every_gpg_call_uses_a_temporary_home(self):
        prefix = _STATE["home_prefix"]
        gpg_calls = [(a, e) for a, e in _RECORDED
                     if Path(a[0]).name.lower().startswith(("gpg", "gpgconf"))]
        self.assertGreater(len(gpg_calls), 20)
        defaults = [os.path.normcase(str(p)) for p in _default_keyrings()]
        for argv, env in gpg_calls:
            self.assertIn("--homedir", argv, argv[:3])
            home = argv[argv.index("--homedir") + 1]
            self.assertTrue(home.startswith(prefix + ("/" if GPG.msys else os.sep)), home)
            self.assertEqual(env.get("GNUPGHOME"), home)
            self.assertNotIn(os.path.normcase(home), defaults)

    def test_default_keyring_untouched(self):
        pgpmode.inspect(self.pub("A"))   # 至少再跑一次
        self.assertEqual(_snapshot(), _STATE["before"])

    def test_no_leftover_homes_or_agents(self):
        src = self.tmp / "x.gpg"
        pgpmode.encrypt_file(self.plain, src, passphrase=FILE_PASS)
        pgpmode.decrypt_file(src, self.tmp / "x.out", passphrase=FILE_PASS)
        base = _STATE["base"]
        self.assertEqual([p.name for p in base.iterdir()], [])
        needles = {_STATE["home_prefix"].lower(), str(base).lower()}
        deadline = time.time() + 15
        while True:
            lines = _agent_command_lines()
            mine = [line for line in lines if any(n in line.lower() for n in needles)]
            if not mine or time.time() > deadline:
                break
            time.sleep(1)
        self.assertEqual(mine, [])


def _agent_command_lines() -> list[str]:
    """目前所有 gpg-agent／dirmngr／keyboxd 行程的命令列（只用來找屬於測試 home 的）。"""
    if os.name == "nt":
        script = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match "
                  "'^(gpg-agent|dirmngr|keyboxd)(\\.exe)?$' } | ForEach-Object { $_.CommandLine }")
        argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    else:
        argv = ["ps", "-eo", "args"]
    try:
        proc = _real_run(argv, capture_output=True, timeout=60,
                         creationflags=0x08000000 if os.name == "nt" else 0)
    except (OSError, subprocess.SubprocessError):
        return []
    text = proc.stdout.decode("utf-8", "replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if os.name != "nt":
        lines = [line for line in lines if re.search(r"(gpg-agent|dirmngr|keyboxd)", line)]
    return lines


if __name__ == "__main__":
    unittest.main()
