"""PGP 模式中不需要 gpg 的部分：格式辨識、路徑轉換、找 gpg 的降級訊息、密語只走 stdin。

全部離線、用假資料；gpg 用 mock 取代，所以這台電腦有沒有裝 gpg 都會跑。
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _support import Case, SealError

from crypto_tool import pgpmode
from crypto_tool.pgpmode import _gpg, ops

SECRET = "SeCrEt-Marker-7f3a9c-密語"


def _fake_info(path="C:/fake/gpg.exe", msys=True, version=(2, 4, 9)):
    return _gpg.GpgInfo(path=path, version=".".join(map(str, version)), version_tuple=version,
                        msys=msys, gpgconf="C:/fake/gpgconf.exe", source="common")


class DetectTests(unittest.TestCase):
    def test_armor_kinds(self):
        self.assertEqual(pgpmode.pgp_kind(b"-----BEGIN PGP MESSAGE-----\n\nhQ"), "message")
        self.assertEqual(pgpmode.pgp_kind(b"\xef\xbb\xbf\r\n  -----BEGIN PGP MESSAGE-----"), "message")
        self.assertEqual(pgpmode.pgp_kind(b"-----BEGIN PGP PUBLIC KEY BLOCK-----"), "public_key")
        self.assertEqual(pgpmode.pgp_kind(b"-----BEGIN PGP PRIVATE KEY BLOCK-----"), "secret_key")
        self.assertEqual(pgpmode.pgp_kind(b"-----BEGIN PGP SIGNATURE-----"), "signature")
        self.assertTrue(pgpmode.is_pgp(b"-----BEGIN PGP MESSAGE-----"))

    def test_binary_packets(self):
        # 舊格式 PKESK（tag 1，1 位元組長度，版本 3）——gpg 2.4 的實際輸出開頭
        self.assertEqual(pgpmode.pgp_kind(bytes([0x84, 0x5E, 0x03]) + b"\x00" * 20), "message")
        # 舊格式 SKESK（tag 3，版本 4）
        self.assertEqual(pgpmode.pgp_kind(bytes([0x8C, 0x0D, 0x04, 0x09])), "message")
        # 新格式 SEIPD（tag 18，版本 1）
        self.assertEqual(pgpmode.pgp_kind(bytes([0xD2, 0x46, 0x01]) + b"\x00" * 10), "message")
        # 新格式部分長度的 SEIPD
        self.assertEqual(pgpmode.pgp_kind(bytes([0xD2, 0xE5, 0x01])), "message")
        # 公鑰（舊格式 tag 6，2 位元組長度，版本 4）
        self.assertEqual(pgpmode.pgp_kind(bytes([0x99, 0x00, 0x33, 0x04])), "public_key")
        # 私鑰（舊格式 tag 5）
        self.assertEqual(pgpmode.pgp_kind(bytes([0x94, 0x86, 0x04])), "secret_key")

    def test_not_pgp(self):
        for head in (b"", b"\x00" * 64, b"age-encryption.org/v1\n-> X25519 abc",
                     b"ISD2\x01\x02", b"PK\x03\x04", b"hello world",
                     bytes([0x84, 0x5E, 0x09]),           # PKESK 但版本不對
                     bytes([0x84]),                        # 太短
                     bytes([0xC1, 0xE5, 0x03]),            # 部分長度用在不允許的封包
                     b"-----BEGIN PGP NONSENSE-----"):
            self.assertFalse(pgpmode.is_pgp(head), head)

    def test_parse_packets(self):
        listing = (
            "# off=0 ctb=84 tag=1 hlen=2 plen=94\n"
            ":pubkey enc packet: version 3, algo 18, keyid 31DD615E94821FE6\n"
            "\tdata: [263 bits]\n"
            "# off=96 ctb=84 tag=1 hlen=2 plen=94\n"
            ":pubkey enc packet: version 3, algo 1, keyid 0000000000000000\n"
            "# off=192 ctb=8c tag=3 hlen=2 plen=46\n"
            ":symkey enc packet: version 4, cipher 9, aead 0, s2k 3, hash 10, seskey 256 bits\n"
            "# off=240 ctb=d2 tag=18 hlen=2 plen=70 new-ctb\n"
            ":encrypted data packet:\n\tlength: 70\n\tmdc_method: 2\n"
        )
        info = ops._parse_packets(listing)
        self.assertEqual(info["recipient_count"], 2)
        self.assertEqual(info["recipients"][0], {"key_id": "31DD615E94821FE6", "algo": 18,
                                                 "algo_name": "ECDH"})
        self.assertEqual(info["hidden_recipients"], 1)
        self.assertEqual(info["passphrase_packets"], 1)
        self.assertEqual(info["data_packet"], "seipd_v1")
        self.assertTrue(info["interoperable"])
        aead = ops._parse_packets("# off=0 ctb=d4 tag=20 hlen=2 plen=9\n"
                                  ":aead encrypted packet: cipher=9 aead=2 cb=16\n")
        self.assertEqual(aead["data_packet"], "aead_ocb")
        self.assertFalse(aead["interoperable"])
        sed = ops._parse_packets("# off=0 ctb=a4 tag=9 hlen=2 plen=9\n:encrypted data packet:\n")
        self.assertEqual(sed["data_packet"], "sed")
        self.assertFalse(sed["integrity_protected"])


class PathTests(Case):
    def test_msys_path(self):
        if os.name != "nt":
            self.skipTest("只在 Windows 上有磁碟機代號")
        self.assertEqual(_gpg.msys_path(r"C:\Users\x\data\g\1a2b"), "/c/Users/x/data/g/1a2b")
        self.assertEqual(_gpg.msys_path(r"D:\a b\c"), "/d/a b/c")
        self.assertEqual(_gpg.msys_path(r"\\server\share\x"), "//server/share/x")

    def test_home_argument_depends_on_msys(self):
        folder = self.tmp / "h"
        native = _gpg.home_argument(_fake_info(msys=False), folder)
        self.assertEqual(native, os.path.abspath(folder))
        if os.name == "nt":
            self.assertTrue(_gpg.home_argument(_fake_info(msys=True), folder).startswith("/"))

    def test_home_bases_order_and_override(self):
        with mock.patch.dict(os.environ, {_gpg.ENV_TMPDIR: str(self.tmp)}):
            bases = _gpg.home_bases()
        self.assertEqual(bases[0], self.tmp)
        self.assertEqual(bases[1].name, "g")                 # 工具的 data/g
        self.assertEqual(bases[2].name, "egpg")              # 系統暫存（最後才用）
        with mock.patch.dict(os.environ, {"TOOLZOO_DATA_DIR": str(self.tmp)}):
            os.environ.pop(_gpg.ENV_TMPDIR, None)
            self.assertEqual(_gpg.home_bases()[0], self.tmp / "encrypter" / "g")

    def test_long_base_is_skipped(self):
        deep = self.tmp / ("x" * 120)
        short = Path(tempfile.mkdtemp(prefix="e"))        # 系統暫存底下：夠短
        self.addCleanup(shutil.rmtree, short, True)
        with mock.patch.object(_gpg, "home_bases", lambda: [deep, short]):
            folder, arg = _gpg.make_home(_fake_info(msys=False))
        self.assertEqual(folder.parent, short)
        self.assertEqual(len(arg), _gpg.HOME_LEN)              # 名稱補長到固定長度
        self.assertLessEqual(len(arg), _gpg.MAX_HOME_LEN)
        self.assertFalse(deep.exists())
        self.assertTrue(_gpg.remove_tree(folder))

    def test_home_lengths_sit_in_the_measured_range(self):
        # 實測 home 參數 55～74 個字元時，單把匯入的 Curve25519 私鑰都正常（見 _gpg.py 的說明）
        self.assertEqual(_gpg.HOME_LEN_CHOICES[0], _gpg.HOME_LEN)
        self.assertTrue(all(55 <= n <= 74 for n in _gpg.HOME_LEN_CHOICES))
        self.assertEqual(len(set(_gpg.HOME_LEN_CHOICES)), len(_gpg.HOME_LEN_CHOICES))
        self.assertGreaterEqual(_gpg.MAX_HOME_LEN, max(_gpg.HOME_LEN_CHOICES))

    def test_key_conversion_failure_retries_in_a_home_of_another_length(self):
        lengths = []

        def fake_import(session, keys, *, secret):
            lengths.append(len(session.home))
            return ["F" * 40]

        def fake_warm(session, fprs, pw):   # 前兩個長度轉換失敗，第三個成功
            return {fprs[0]: "failed" if len(lengths) < 3 else "ok"}

        self.patch(ops, "_import_keys", fake_import)
        self.patch(ops, "_warm_up", fake_warm)
        self.patch(_gpg.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b"", b""))
        short = Path(tempfile.mkdtemp(prefix="e"))
        self.addCleanup(shutil.rmtree, short, True)
        with mock.patch.dict(os.environ, {_gpg.ENV_TMPDIR: str(short)}):
            session, fprs, states = ops._session_with_keys(_fake_info(msys=False), [Path("k.asc")], "")
        session.close()
        self.assertEqual(lengths, list(_gpg.HOME_LEN_CHOICES[:3]))
        self.assertEqual(states, {"F" * 40: "ok"})
        self.assertEqual([p for p in short.iterdir()], [])       # 失敗的 home 都刪掉了
        # 解密重來時從不同的長度開始
        lengths.clear()
        with mock.patch.dict(os.environ, {_gpg.ENV_TMPDIR: str(short)}):
            ops._session_with_keys(_fake_info(msys=False), [Path("k.asc")], "", start=1)[0].close()
        self.assertEqual(lengths[0], _gpg.HOME_LEN_CHOICES[1])

    def test_no_usable_base(self):
        deep = self.tmp / ("x" * 120)
        with mock.patch.object(_gpg, "home_bases", lambda: [deep]):
            with self.assertRaises(SealError) as caught:
                _gpg.make_home(_fake_info(msys=False))
        self.assertEqual(caught.exception.code, "io_error")
        self.assertIn(_gpg.ENV_TMPDIR, caught.exception.action)


class FindGpgTests(Case):
    def setUp(self):
        super().setUp()
        _gpg._cache.clear()
        self.addCleanup(_gpg._cache.clear)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(_gpg.ENV_GPG, None)

    def test_env_points_nowhere(self):
        os.environ[_gpg.ENV_GPG] = str(self.tmp / "no-gpg.exe")
        with self.assertRaises(Exception) as caught:
            pgpmode.find_gpg()
        err = caught.exception
        self.assertEqual(err.code, "dependency_missing")
        self.assertIn(_gpg.ENV_GPG, err.reason)
        self.assertEqual(err.exit_code, 3)

    def test_nothing_installed(self):
        self.patch(_gpg, "_candidates", lambda: [])
        with self.assertRaises(Exception) as caught:
            pgpmode.find_gpg()
        err = caught.exception
        self.assertEqual(err.code, "dependency_missing")
        self.assertIn("Gpg4win", err.action)
        self.assertIn("Git for Windows", err.action)
        self.assertIn(_gpg.ENV_GPG, err.action)
        self.assertEqual(err.remedy_kind, "needs_config")

    def _fake_exe(self, version_line, home="/c/Users/someone/.gnupg"):
        exe = self.tmp / "gpg.exe"
        exe.write_bytes(b"")
        out = f"{version_line}\nlibgcrypt 1.10\n\nHome: {home}\n".encode()

        def fake_run(argv, **kwargs):
            # 探測時一定要指定一個不存在的 home，不能讓 gpg 碰預設金鑰環
            self.assertEqual(argv[1:3], ["--homedir", _gpg._PROBE_HOME])
            self.assertEqual(kwargs["env"]["GNUPGHOME"], _gpg._PROBE_HOME)
            return subprocess.CompletedProcess(argv, 0, out, b"")
        self.patch(_gpg.subprocess, "run", fake_run)
        self.patch(_gpg, "_candidates", lambda: [("common", exe)])
        return exe

    def test_too_old_is_rejected(self):
        self._fake_exe("gpg (GnuPG) 2.0.30")
        with self.assertRaises(Exception) as caught:
            pgpmode.find_gpg()
        self.assertEqual(caught.exception.code, "dependency_missing")
        self.assertIn("2.0.30", caught.exception.detail)

    def test_found_and_msys_detected_from_home_line(self):
        exe = self._fake_exe("gpg (GnuPG) 2.4.9")
        info = pgpmode.find_gpg()
        self.assertEqual(info.path, str(exe))
        self.assertEqual(info.version, "2.4.9")
        self.assertEqual(info.version_tuple, (2, 4, 9))
        self.assertEqual(info.msys, os.name == "nt")
        self.assertIs(pgpmode.find_gpg(), info)                  # 快取

    def test_native_build_is_not_msys(self):
        self._fake_exe("gpg (GnuPG) 2.2.41", home="C:/Users/someone/AppData/Roaming/gnupg")
        self.assertFalse(pgpmode.find_gpg().msys)

    def test_operations_report_missing_gpg(self):
        def missing(**_kw):
            raise SealError("dependency_missing", "找不到 gpg")
        self.patch(ops, "find_gpg", missing)
        src = self.tmp / "a.txt"
        src.write_text("x")
        self.assertEqual(self.code_of(pgpmode.encrypt_file, src, self.tmp / "a.gpg",
                                      passphrase="pw-123456"), "dependency_missing")
        self.assertFalse((self.tmp / "a.gpg").exists())
        self.assertEqual(self.code_of(pgpmode.generate_keypair, "Test",
                                      out_public=self.tmp / "p.asc", out_secret=self.tmp / "s.asc"),
                         "dependency_missing")


class ArgumentTests(Case):
    """不需要執行 gpg 就能擋下的錯誤。"""

    def test_encrypt_needs_recipient_or_passphrase(self):
        src = self.tmp / "a.txt"
        src.write_text("x")
        self.assertEqual(self.code_of(pgpmode.encrypt_file, src, self.tmp / "a.gpg"), "bad_input")
        self.assertEqual(self.code_of(pgpmode.encrypt_file, src, self.tmp / "a.gpg",
                                      recipient_key_files=[self.tmp / "none.asc"]), "key_missing")
        self.assertEqual(self.code_of(pgpmode.encrypt_file, self.tmp / "missing", self.tmp / "b.gpg",
                                      passphrase="pw-123456"), "input_missing")
        self.assertEqual(self.code_of(pgpmode.encrypt_file, self.tmp, self.tmp / "c.gpg",
                                      passphrase="pw-123456"), "bad_input")
        self.assertEqual(self.code_of(pgpmode.encrypt_file, src, src, passphrase="pw-123456"),
                         "bad_input")
        self.assertEqual(self.code_of(pgpmode.encrypt_file, src, self.tmp / "d.gpg",
                                      passphrase="two\nlines"), "bad_input")

    def test_existing_output_is_refused(self):
        src = self.tmp / "a.txt"
        src.write_text("x")
        dst = self.tmp / "a.gpg"
        dst.write_text("keep me")
        self.assertEqual(self.code_of(pgpmode.encrypt_file, src, dst, passphrase="pw-123456"),
                         "output_exists")
        self.assertEqual(dst.read_text(), "keep me")
        pub, sec = self.tmp / "p.asc", self.tmp / "s.asc"
        sec.write_text("old secret")
        self.assertEqual(self.code_of(pgpmode.generate_keypair, "Test",
                                      out_public=pub, out_secret=sec), "output_exists")
        self.assertFalse(pub.exists())
        self.assertEqual(sec.read_text(), "old secret")

    def test_decrypt_rejects_non_pgp_before_running_gpg(self):
        src = self.tmp / "x.bin"
        src.write_bytes(b"age-encryption.org/v1\n")
        self.patch(ops, "find_gpg", mock.Mock(side_effect=AssertionError("不該執行 gpg")))
        self.assertEqual(self.code_of(pgpmode.decrypt_file, src, self.tmp / "o",
                                      passphrase="pw-123456"), "unsupported_format")
        self.assertEqual(self.code_of(pgpmode.inspect, src), "unsupported_format")
        key = self.tmp / "k.asc"
        key.write_text("-----BEGIN PGP PUBLIC KEY BLOCK-----\n\nxx\n")
        self.assertEqual(self.code_of(pgpmode.decrypt_file, key, self.tmp / "o",
                                      passphrase="pw-123456"), "unsupported_format")
        self.assertEqual(self.code_of(pgpmode.decrypt_file, key, self.tmp / "o"), "bad_input")

    def test_keygen_input_checks(self):
        kw = {"out_public": self.tmp / "p.asc", "out_secret": self.tmp / "s.asc"}
        self.assertEqual(self.code_of(pgpmode.generate_keypair, "", **kw), "bad_input")
        self.assertEqual(self.code_of(pgpmode.generate_keypair, "A <b>", **kw), "bad_input")
        self.assertEqual(self.code_of(pgpmode.generate_keypair, "A", "not-an-email", **kw), "bad_input")
        self.assertEqual(self.code_of(pgpmode.generate_keypair, "A", key_type="dsa", **kw), "bad_input")
        self.assertEqual(self.code_of(pgpmode.generate_keypair, "A", out_public=self.tmp / "same",
                                      out_secret=self.tmp / "same"), "bad_input")


class PassphrasePlumbingTests(Case):
    """密語只能經過 stdin（--passphrase-fd 0），不能出現在命令列或環境變數。"""

    def test_run_sends_passphrase_on_stdin_only(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, b"[GNUPG:] DECRYPTION_OKAY\nplain\n", b"")

        self.patch(_gpg.subprocess, "run", fake_run)
        with mock.patch.dict(os.environ, {_gpg.ENV_TMPDIR: str(self.tmp)}):
            with _gpg.GpgSession(_fake_info()) as session:
                res = session.run(["--decrypt", "x.gpg"], passphrase=SECRET)
                home, folder = session.home, session.folder
        self.assertTrue(res.has("DECRYPTION_OKAY"))
        self.assertEqual(res.output, "plain")
        self.assertFalse(folder.exists())                     # 用完就刪
        argv, kwargs = calls[0]
        self.assertEqual(argv[1:3], ["--homedir", home])
        self.assertIn("--passphrase-fd", argv)
        self.assertEqual(argv[argv.index("--passphrase-fd") + 1], "0")
        self.assertEqual(kwargs["input"], SECRET.encode("utf-8") + b"\n")
        self.assertEqual(kwargs["env"]["GNUPGHOME"], home)
        self.assertNotIn("shell", kwargs)
        self.assertIn("timeout", kwargs)
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"], 0x08000000)
        for argv, kwargs in calls:                            # 包含最後的 gpgconf --kill
            self.assertFalse(any(SECRET in a for a in argv))
            self.assertFalse(any(SECRET in v for v in kwargs["env"].values()))
            self.assertIn("--homedir", argv)
            self.assertEqual(argv[argv.index("--homedir") + 1], home)
        self.assertTrue(any("--kill" in argv for argv, _ in calls))
        for flag in ("--batch", "--no-tty", "--disable-dirmngr", "--no-auto-key-retrieve",
                     "--no-auto-key-locate", "--trust-model"):
            self.assertIn(flag, calls[0][0])

    def test_summary_hides_secrets(self):
        res = _gpg.GpgResult(2, [("ERROR", ["x", "11"])], "", f"gpg: oops {SECRET}\n")
        self.assertNotIn(SECRET, res.summary((SECRET,)))

    def test_timeout_becomes_seal_error(self):
        def slow(argv, **kwargs):
            if "--kill" in argv:
                return subprocess.CompletedProcess(argv, 0, b"", b"")
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        self.patch(_gpg.subprocess, "run", slow)
        with mock.patch.dict(os.environ, {_gpg.ENV_TMPDIR: str(self.tmp)}):
            with _gpg.GpgSession(_fake_info()) as session:
                with self.assertRaises(Exception) as caught:
                    session.run(["--version"], passphrase=SECRET)
        self.assertEqual(caught.exception.code, "io_error")
        self.assertNotIn(SECRET, str(caught.exception.to_dict()))
        self.assertEqual(list(Path(self.tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
