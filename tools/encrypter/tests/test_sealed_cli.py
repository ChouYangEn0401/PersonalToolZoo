"""命令列：退出碼、--json 的格式、目標已存在、以及「祕密不外洩」。

大部分在同一個行程裡呼叫 main()（快）；另外有幾個真的開子行程跑 ``python -m crypto_tool``。
金鑰與密語都是測試時臨時產生的。
"""

import io
import json
import os
import subprocess
import sys
import unittest

from _support import TOOL_DIR, Case

from crypto_tool.sealed import cli, keys
from crypto_tool.sealed.errors import all_codes


class FakeStdin(io.BytesIO):
    """模擬被導向的標準輸入（不是終端機）。"""

    def __init__(self, text: str = ""):
        super().__init__(text.encode("utf-8"))
        self.buffer = self

    def isatty(self):
        return False


def run(*argv, stdin_text=""):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main([str(a) for a in argv], stdin=FakeStdin(stdin_text), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class CliCase(Case):
    def setUp(self):
        super().setUp()
        self.keyfile = self.tmp / ".decryption_code.env"
        keys.generate_key_file(self.keyfile)
        self.plain = self.tmp / "notes.txt"
        self.plain.write_bytes(b"PLAINTEXT-MARKER-0123456789 " * 20)
        self.sealed = self.tmp / "notes.txt.isd2"

    def run_json(self, *argv, stdin_text=""):
        code, out, err = run(*argv, "--json", stdin_text=stdin_text)
        lines = out.splitlines()
        self.assertEqual((len(lines), err), (1, ""), (out, err))
        return code, json.loads(lines[0])

    def assert_error(self, result, exit_code, code):
        self.assertEqual((result[0], result[1]["ok"], result[1]["error"]["code"]),
                         (exit_code, False, code))


class CommandTests(CliCase):
    def test_encrypt_decrypt_info_json(self):
        code, body = self.run_json("encrypt", self.plain, "--key-file", self.keyfile)
        self.assertEqual((code, body["ok"]), (0, True))
        data = body["data"]
        self.assertEqual(data["output"], str(self.sealed))
        self.assertEqual((data["payload"], data["cipher"], data["kdf"]),
                         ("file", "aes-256-gcm", "raw-key"))

        code, body = self.run_json("info", self.sealed)
        self.assertEqual((code, body["data"]["format"]), (0, "isd2"))

        out = self.tmp / "back.txt"
        code, body = self.run_json("decrypt", self.sealed, "-o", out, "--key-file", self.keyfile)
        self.assertEqual((code, body["data"]["output"]), (0, str(out)))
        self.assertEqual(out.read_bytes(), self.plain.read_bytes())

    def test_folder_via_cli(self):
        src = self.tmp / "docs"
        (src / "inner").mkdir(parents=True)
        (src / "inner" / "x.txt").write_bytes(b"x")
        code, body = self.run_json("encrypt", src, "--key-file", self.keyfile)
        self.assertEqual((code, body["data"]["payload"], body["data"]["files"]), (0, "folder", 1))
        code, _ = self.run_json("decrypt", self.tmp / "docs.isd2", "-o", self.tmp / "docs2",
                                "--key-file", self.keyfile)
        self.assertEqual(code, 0)
        self.assertEqual((self.tmp / "docs2" / "inner" / "x.txt").read_bytes(), b"x")

    def test_target_exists_exit_code_and_force(self):
        self.sealed.write_bytes(b"keep me")
        result = self.run_json("encrypt", self.plain, "--key-file", self.keyfile)
        self.assert_error(result, 2, "output_exists")
        self.assertTrue(result[1]["error"]["reason"])
        self.assertTrue(result[1]["error"]["remedy"]["action"])
        self.assertEqual(self.sealed.read_bytes(), b"keep me")
        code, _ = self.run_json("encrypt", self.plain, "--key-file", self.keyfile, "--force")
        self.assertEqual(code, 0)
        self.assertNotEqual(self.sealed.read_bytes(), b"keep me")

    def test_wrong_key_and_corrupt_exit_codes(self):
        run("encrypt", self.plain, "--key-file", self.keyfile)
        other = self.tmp / "other.env"
        keys.generate_key_file(other)
        self.assert_error(self.run_json("decrypt", self.sealed, "-o", self.tmp / "o1",
                                        "--key-file", other), 5, "wrong_key")
        blob = bytearray(self.sealed.read_bytes())
        blob[-1] ^= 1
        self.sealed.write_bytes(bytes(blob))
        self.assert_error(self.run_json("decrypt", self.sealed, "-o", self.tmp / "o2",
                                        "--key-file", self.keyfile), 6, "corrupt")
        self.sealed.write_bytes(bytes(blob[:100]))
        self.assert_error(self.run_json("decrypt", self.sealed, "-o", self.tmp / "o3",
                                        "--key-file", self.keyfile), 6, "corrupt")
        self.assertFalse(any((self.tmp / n).exists() for n in ("o1", "o2", "o3")))

    def test_usage_and_missing_things_are_exit_2(self):
        plain, keyfile, tmp = self.plain, self.keyfile, self.tmp
        for argv in (
            ["encrypt", plain],                                   # 沒給金鑰來源
            ["encrypt", plain, "--key-file", keyfile, "--key-env", "X"],
            ["frobnicate"],
            [],
            ["encrypt", tmp / "missing", "--key-file", keyfile],
            ["encrypt", plain, "--key-file", tmp / "missing.env"],
            ["encrypt", plain, "--key-env", "CRYPTO_TOOL_TEST_UNSET_VARIABLE"],
            ["encrypt", plain, "--key-env", "X", "--key-name", "Y"],
            ["decrypt", plain, "-o", tmp / "o", "--key-file", keyfile],   # 不是加密檔
        ):
            with self.subTest(argv=[str(a) for a in argv[:2]]):
                code, body = self.run_json(*argv)
                self.assertEqual((code, body["ok"]), (2, False))
                self.assertEqual(set(body["error"]),
                                 {"code", "reason", "retryable", "remedy", "detail"})
                self.assertIn(body["error"]["code"], all_codes())

    def test_keygen_cli(self):
        path = self.tmp / "k.env"
        code, body = self.run_json("keygen", "-o", path)
        self.assertEqual((code, body["data"]["path"]), (0, str(path)))
        self.assertNotIn(keys.load_key_file(path).raw.hex(), json.dumps(body))
        self.assert_error(self.run_json("keygen", "-o", path), 2, "output_exists")
        code, out, _ = run("keygen", "-o", self.tmp / "k2.env")
        self.assertEqual(code, 0)
        self.assertIn("備份", out)

    def test_human_output_goes_to_stdout_and_errors_to_stderr(self):
        code, out, err = run("encrypt", self.plain, "--key-file", self.keyfile)
        self.assertEqual((code, err), (0, ""))
        self.assertIn(str(self.sealed), out)
        code, out, err = run("encrypt", self.plain, "--key-file", self.keyfile)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("output_exists", err)


class SecretHandlingTests(CliCase):
    def test_there_is_no_way_to_pass_a_passphrase_as_an_argument(self):
        parser = cli.build_parser()
        for sub in ("encrypt", "decrypt"):
            subparser = parser._subparsers._group_actions[0].choices[sub]
            action = next(a for a in subparser._actions
                          if "--passphrase-stdin" in a.option_strings)
            self.assertEqual(action.nargs, 0)  # 是開關，不收值
        for argv in (["encrypt", "x", "--passphrase", "hunter2"],
                     ["encrypt", "x", "--passphrase-stdin=hunter2"],
                     ["encrypt", "x", "--passphrase-stdin", "hunter2"]):
            code, body = self.run_json(*argv)
            self.assertEqual(code, 2)
            self.assertNotIn("hunter2", json.dumps(body))   # 誤放的密語不會被轉述回去
            code, out, err = run(*argv)
            self.assertNotIn("hunter2", out + err)

    def test_passphrase_from_stdin_and_short_warning(self):
        code, body = self.run_json("encrypt", self.plain, "--passphrase-stdin",
                                   stdin_text="短密語\n")
        self.assertEqual((code, body["data"]["kdf"]), (0, "scrypt"))
        self.assertEqual(body["data"]["warnings"], ["passphrase_short"])
        out = self.tmp / "o.txt"
        code, _ = self.run_json("decrypt", self.sealed, "-o", out, "--passphrase-stdin",
                                stdin_text="短密語\r\n")
        self.assertEqual(code, 0)
        self.assertEqual(out.read_bytes(), self.plain.read_bytes())
        self.assert_error(self.run_json("decrypt", self.sealed, "-o", self.tmp / "o2",
                                        "--passphrase-stdin", stdin_text=""), 2, "key_missing")

    def _secret_forms(self, path):
        value = path.read_text(encoding="ascii").strip().splitlines()[-1].split("=", 1)[1]
        return [value, value[len("b64:"):], keys.load_key_file(path).raw.hex()]

    def test_nothing_secret_is_ever_printed(self):
        """把各種成功與失敗的輸出全部收集起來，裡面不可以出現金鑰、密語或明文。"""
        tmp, plain, keyfile, sealed = self.tmp, self.plain, self.keyfile, self.sealed
        passphrase = "correct-horse-battery-staple-9431"
        other = tmp / "other.env"
        keys.generate_key_file(other)
        captured = []

        def both(*argv, stdin_text=""):
            for extra in ([], ["--json"]):
                captured.extend(run(*argv, *extra, stdin_text=stdin_text)[1:])

        both("encrypt", plain, "--key-file", keyfile, "--force")
        both("info", sealed)
        both("decrypt", sealed, "-o", tmp / "d1", "--key-file", keyfile, "--force")
        both("decrypt", sealed, "-o", tmp / "d2", "--key-file", other)
        both("encrypt", plain, "-o", tmp / "p.isd2", "--passphrase-stdin", "--force",
             stdin_text=passphrase + "\n")
        both("decrypt", tmp / "p.isd2", "-o", tmp / "d3", "--passphrase-stdin",
             stdin_text="wrong-" + passphrase + "\n")
        both("decrypt", tmp / "p.isd2", "-o", tmp / "d4", "--key-file", keyfile)
        both("keygen", "-o", tmp / "fresh.env", "--force")
        bad = tmp / "bad.env"
        bad.write_text("CRYPTO_TOOL_KEY=b64:SECRETISHvalueThatIsNotValid\n", encoding="ascii")
        both("encrypt", plain, "-o", tmp / "x.isd2", "--key-file", bad)

        everything = "\n".join(captured)
        self.assertGreater(len(everything), 500)
        forbidden = (self._secret_forms(keyfile) + self._secret_forms(other)
                     + self._secret_forms(tmp / "fresh.env")
                     + [passphrase, "PLAINTEXT-MARKER", "SECRETISHvalue"])
        for item in forbidden:
            self.assertNotIn(item, everything)

    def test_unexpected_error_reports_type_only(self):
        def boom(*_args, **_kwargs):
            raise RuntimeError("message with SECRET-DETAIL inside")
        self.patch(cli, "encrypt_path", boom)
        result = self.run_json("encrypt", self.plain, "--key-file", self.keyfile)
        self.assert_error(result, 1, "internal_bug")
        self.assertNotIn("SECRET-DETAIL", json.dumps(result[1]))


class SubprocessTests(CliCase):
    """真的開子行程。"""

    def spawn(self, args, env=None, **kwargs):
        full_env = dict(os.environ, PYTHONUTF8="1")
        full_env.update(env or {})
        kwargs.setdefault("cwd", TOOL_DIR)
        return subprocess.run([sys.executable, *map(str, args)], env=full_env,
                              capture_output=True, timeout=120, **kwargs)

    def test_module_entry_with_key_from_environment(self):
        key_hex = os.urandom(32).hex()
        env = {"CRYPTO_TOOL_TEST_KEY": key_hex}
        done = self.spawn(["-m", "crypto_tool", "encrypt", self.plain,
                           "--key-env", "CRYPTO_TOOL_TEST_KEY", "--json"], env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(json.loads(done.stdout)["ok"])
        self.assertNotIn(key_hex.encode(), done.stdout + done.stderr)

        out = self.tmp / "o.txt"
        done = self.spawn(["-m", "crypto_tool", "decrypt", self.sealed, "-o", out,
                           "--key-env", "CRYPTO_TOOL_TEST_KEY", "--json"], env=env)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(out.read_bytes(), self.plain.read_bytes())

        done = self.spawn(["-m", "crypto_tool", "decrypt", self.sealed, "-o", self.tmp / "o2.txt",
                           "--key-env", "CRYPTO_TOOL_TEST_KEY", "--json"],
                          env={"CRYPTO_TOOL_TEST_KEY": os.urandom(32).hex()})
        self.assertEqual(done.returncode, 5)
        self.assertEqual(json.loads(done.stdout)["error"]["code"], "wrong_key")

    def test_directory_entry_and_piped_passphrase(self):
        """``python <crypto_tool 資料夾>``：不必先切到工具資料夾也能呼叫。"""
        package = TOOL_DIR / "crypto_tool"
        secret = "piped passphrase 密語 8842"
        piped = (secret + "\n").encode("utf-8")
        done = self.spawn([package, "encrypt", self.plain, "--passphrase-stdin", "--json"],
                          input=piped, cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn(secret.encode("utf-8"), done.stdout + done.stderr)
        out = self.tmp / "o.txt"
        done = self.spawn([package, "decrypt", self.sealed, "-o", out, "--passphrase-stdin"],
                          input=piped, cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(out.read_bytes(), self.plain.read_bytes())

    def test_gui_entry_script_dispatches_to_cli(self):
        """run.bat 會執行 GUI__Encrypter.py 並把參數傳給它；帶參數時要走命令列，不開視窗。"""
        entry = TOOL_DIR / "crypto_tool" / "GUI__Encrypter.py"
        done = self.spawn([entry, "info", self.tmp / "nope.isd2", "--json"])
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertEqual(json.loads(done.stdout)["error"]["code"], "input_missing")

    def test_cli_does_not_import_gui_or_legacy_crypto(self):
        done = self.spawn(["-c", "import sys; sys.argv=['x','info','nope','--json'];"
                                 "import runpy\n"
                                 "try:\n runpy.run_module('crypto_tool', run_name='__main__')\n"
                                 "except SystemExit: pass\n"
                                 "bad=[m for m in sys.modules if m.split('.')[0] in "
                                 "('tkinter','ttkbootstrap','tkinterdnd2','Crypto')]\n"
                                 "print('LOADED', bad)"])
        self.assertIn(b"LOADED []", done.stdout, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
