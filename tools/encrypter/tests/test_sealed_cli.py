"""命令列：退出碼、--json 的格式、目標已存在、以及「祕密不外洩」。

大部分在同一個行程裡呼叫 main()（快）；另外有幾個真的開子行程跑 ``python -m crypto_tool``。
金鑰與密語都是測試時臨時產生的。
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from crypto_tool.sealed import cli, keys
from crypto_tool.sealed.errors import all_codes

TOOL_DIR = Path(__file__).resolve().parents[1]


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


def run_json(*argv, stdin_text=""):
    code, out, err = run(*argv, "--json", stdin_text=stdin_text)
    lines = out.splitlines()
    assert len(lines) == 1 and err == "", (out, err)
    return code, json.loads(lines[0])


@pytest.fixture
def keyfile(tmp_path):
    path = tmp_path / ".decryption_code.env"
    keys.generate_key_file(path)
    return path


@pytest.fixture
def plain(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_bytes(b"PLAINTEXT-MARKER-0123456789 " * 20)
    return path


def test_encrypt_decrypt_info_json(tmp_path, keyfile, plain):
    code, body = run_json("encrypt", plain, "--key-file", keyfile)
    assert code == 0 and body["ok"] is True
    data = body["data"]
    sealed = tmp_path / "notes.txt.isd2"
    assert data["output"] == str(sealed) and data["payload"] == "file"
    assert data["cipher"] == "aes-256-gcm" and data["kdf"] == "raw-key"

    code, body = run_json("info", sealed)
    assert code == 0 and body["data"]["format"] == "isd2"

    out = tmp_path / "back.txt"
    code, body = run_json("decrypt", sealed, "-o", out, "--key-file", keyfile)
    assert code == 0 and body["data"]["output"] == str(out)
    assert out.read_bytes() == plain.read_bytes()


def test_folder_via_cli(tmp_path, keyfile):
    src = tmp_path / "docs"
    (src / "inner").mkdir(parents=True)
    (src / "inner" / "x.txt").write_bytes(b"x")
    code, body = run_json("encrypt", src, "--key-file", keyfile)
    assert code == 0 and body["data"]["payload"] == "folder" and body["data"]["files"] == 1
    code, body = run_json("decrypt", tmp_path / "docs.isd2", "-o", tmp_path / "docs2",
                          "--key-file", keyfile)
    assert code == 0 and (tmp_path / "docs2" / "inner" / "x.txt").read_bytes() == b"x"


def test_target_exists_exit_code_and_force(tmp_path, keyfile, plain):
    target = tmp_path / "notes.txt.isd2"
    target.write_bytes(b"keep me")
    code, body = run_json("encrypt", plain, "--key-file", keyfile)
    assert code == 2 and body["ok"] is False
    assert body["error"]["code"] == "output_exists"
    assert body["error"]["reason"] and body["error"]["remedy"]["action"]
    assert target.read_bytes() == b"keep me"
    code, _ = run_json("encrypt", plain, "--key-file", keyfile, "--force")
    assert code == 0 and target.read_bytes() != b"keep me"


def test_wrong_key_and_corrupt_exit_codes(tmp_path, keyfile, plain):
    run("encrypt", plain, "--key-file", keyfile)
    sealed = tmp_path / "notes.txt.isd2"
    other = tmp_path / "other.env"
    keys.generate_key_file(other)
    code, body = run_json("decrypt", sealed, "-o", tmp_path / "o1", "--key-file", other)
    assert (code, body["error"]["code"]) == (5, "wrong_key")

    blob = bytearray(sealed.read_bytes())
    blob[-1] ^= 1
    sealed.write_bytes(bytes(blob))
    code, body = run_json("decrypt", sealed, "-o", tmp_path / "o2", "--key-file", keyfile)
    assert (code, body["error"]["code"]) == (6, "corrupt")

    sealed.write_bytes(bytes(blob[:100]))
    code, body = run_json("decrypt", sealed, "-o", tmp_path / "o3", "--key-file", keyfile)
    assert (code, body["error"]["code"]) == (6, "corrupt")
    assert not any((tmp_path / n).exists() for n in ("o1", "o2", "o3"))


def test_usage_and_missing_things_are_exit_2(tmp_path, keyfile, plain):
    for argv in (
        ["encrypt", plain],                                   # 沒給金鑰來源
        ["encrypt", plain, "--key-file", keyfile, "--key-env", "X"],
        ["frobnicate"],
        [],
        ["encrypt", tmp_path / "missing", "--key-file", keyfile],
        ["encrypt", plain, "--key-file", tmp_path / "missing.env"],
        ["encrypt", plain, "--key-env", "CRYPTO_TOOL_TEST_UNSET_VARIABLE"],
        ["encrypt", plain, "--key-env", "X", "--key-name", "Y"],
        ["decrypt", plain, "-o", tmp_path / "o", "--key-file", keyfile],   # 不是加密檔
    ):
        code, body = run_json(*argv)
        assert code == 2 and body["ok"] is False, argv
        assert set(body["error"]) == {"code", "reason", "retryable", "remedy", "detail"}
        assert body["error"]["code"] in all_codes()


def test_there_is_no_way_to_pass_a_passphrase_as_an_argument():
    parser = cli.build_parser()
    for sub in ("encrypt", "decrypt"):
        action = next(a for a in parser._subparsers._group_actions[0].choices[sub]._actions
                      if "--passphrase-stdin" in a.option_strings)
        assert action.nargs == 0  # 是開關，不收值
    code, body = run_json("encrypt", "x", "--passphrase", "hunter2")
    assert code == 2 and "hunter2" not in json.dumps(body)
    code, body = run_json("encrypt", "x", "--passphrase-stdin=hunter2")
    assert code == 2 and "hunter2" not in json.dumps(body)


def test_passphrase_from_stdin_and_short_warning(tmp_path, plain):
    code, body = run_json("encrypt", plain, "--passphrase-stdin", stdin_text="短密語\n")
    assert code == 0 and body["data"]["kdf"] == "scrypt"
    assert body["data"]["warnings"] == ["passphrase_short"]
    out = tmp_path / "o.txt"
    code, _ = run_json("decrypt", tmp_path / "notes.txt.isd2", "-o", out,
                       "--passphrase-stdin", stdin_text="短密語\r\n")
    assert code == 0 and out.read_bytes() == plain.read_bytes()
    code, body = run_json("decrypt", tmp_path / "notes.txt.isd2", "-o", tmp_path / "o2",
                          "--passphrase-stdin", stdin_text="")
    assert (code, body["error"]["code"]) == (2, "key_missing")


def test_keygen_cli(tmp_path):
    path = tmp_path / "k.env"
    code, body = run_json("keygen", "-o", path)
    assert code == 0 and body["data"]["path"] == str(path)
    secret = keys.load_key_file(path)
    assert secret.raw.hex() not in json.dumps(body)
    code, body = run_json("keygen", "-o", path)
    assert (code, body["error"]["code"]) == (2, "output_exists")
    code, out, _ = run("keygen", "-o", tmp_path / "k2.env")
    assert code == 0 and "備份" in out


def _secret_forms(path):
    text = path.read_text(encoding="ascii")
    value = text.strip().splitlines()[-1].split("=", 1)[1]
    raw = keys.load_key_file(path).raw
    return [value, value.removeprefix("b64:"), raw.hex()]


def test_nothing_secret_is_ever_printed(tmp_path, keyfile, plain):
    """把各種成功與失敗的輸出全部收集起來，裡面不可以出現金鑰、密語或明文。"""
    passphrase = "correct-horse-battery-staple-9431"
    other = tmp_path / "other.env"
    keys.generate_key_file(other)
    sealed = tmp_path / "notes.txt.isd2"
    captured = []

    def both(*argv, stdin_text=""):
        for extra in ([], ["--json"]):
            captured.extend(run(*argv, *extra, stdin_text=stdin_text)[1:])

    both("encrypt", plain, "--key-file", keyfile, "--force")
    both("info", sealed)
    both("decrypt", sealed, "-o", tmp_path / "d1", "--key-file", keyfile, "--force")
    both("decrypt", sealed, "-o", tmp_path / "d2", "--key-file", other)
    both("encrypt", plain, "-o", tmp_path / "p.isd2", "--passphrase-stdin", "--force",
         stdin_text=passphrase + "\n")
    both("decrypt", tmp_path / "p.isd2", "-o", tmp_path / "d3", "--passphrase-stdin",
         stdin_text="wrong-" + passphrase + "\n")
    both("decrypt", tmp_path / "p.isd2", "-o", tmp_path / "d4", "--key-file", keyfile)
    both("keygen", "-o", tmp_path / "fresh.env", "--force")
    bad = tmp_path / "bad.env"
    bad.write_text("CRYPTO_TOOL_KEY=b64:SECRETISHvalueThatIsNotValid\n", encoding="ascii")
    both("encrypt", plain, "-o", tmp_path / "x.isd2", "--key-file", bad)

    everything = "\n".join(captured)
    forbidden = (_secret_forms(keyfile) + _secret_forms(other) + _secret_forms(tmp_path / "fresh.env")
                 + [passphrase, "PLAINTEXT-MARKER", "SECRETISHvalue"])
    for item in forbidden:
        assert item not in everything


def test_unexpected_error_reports_type_only(tmp_path, keyfile, plain, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("message with SECRET-DETAIL inside")
    monkeypatch.setattr(cli, "encrypt_path", boom)
    code, body = run_json("encrypt", plain, "--key-file", keyfile)
    assert (code, body["error"]["code"]) == (1, "internal_bug")
    assert "SECRET-DETAIL" not in json.dumps(body)


# ── 真的開子行程 ────────────────────────────────────────────────────────

def _spawn(args, **kwargs):
    env = dict(os.environ, PYTHONUTF8="1")
    env.update(kwargs.pop("env", {}))
    return subprocess.run([sys.executable, *map(str, args)], cwd=TOOL_DIR, env=env,
                          capture_output=True, timeout=120, **kwargs)


def test_module_entry_with_key_from_environment(tmp_path, plain):
    key_hex = os.urandom(32).hex()
    env = {"CRYPTO_TOOL_TEST_KEY": key_hex}
    done = _spawn(["-m", "crypto_tool", "encrypt", plain, "--key-env", "CRYPTO_TOOL_TEST_KEY",
                   "--json"], env=env)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["ok"] is True
    assert key_hex.encode() not in done.stdout + done.stderr

    out = tmp_path / "o.txt"
    done = _spawn(["-m", "crypto_tool", "decrypt", tmp_path / "notes.txt.isd2", "-o", out,
                   "--key-env", "CRYPTO_TOOL_TEST_KEY", "--json"], env=env)
    assert done.returncode == 0 and out.read_bytes() == plain.read_bytes()

    done = _spawn(["-m", "crypto_tool", "decrypt", tmp_path / "notes.txt.isd2", "-o",
                   tmp_path / "o2.txt", "--key-env", "CRYPTO_TOOL_TEST_KEY", "--json"],
                  env={"CRYPTO_TOOL_TEST_KEY": os.urandom(32).hex()})
    assert done.returncode == 5
    assert json.loads(done.stdout)["error"]["code"] == "wrong_key"


def test_directory_entry_and_piped_passphrase(tmp_path, plain):
    """``python <crypto_tool 資料夾>``：不必先切到工具資料夾也能呼叫。"""
    package = TOOL_DIR / "crypto_tool"
    secret = "piped passphrase 密語 8842"
    done = subprocess.run(
        [sys.executable, str(package), "encrypt", str(plain), "--passphrase-stdin", "--json"],
        input=(secret + "\n").encode("utf-8"), cwd=tmp_path, capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert secret.encode("utf-8") not in done.stdout + done.stderr
    out = tmp_path / "o.txt"
    done = subprocess.run(
        [sys.executable, str(package), "decrypt", str(tmp_path / "notes.txt.isd2"),
         "-o", str(out), "--passphrase-stdin"],
        input=(secret + "\n").encode("utf-8"), cwd=tmp_path, capture_output=True, timeout=120)
    assert done.returncode == 0 and out.read_bytes() == plain.read_bytes()


def test_cli_does_not_import_gui_or_legacy_crypto():
    done = _spawn(["-c", "import sys; sys.argv=['x','info','nope','--json'];"
                         "import runpy\n"
                         "try:\n runpy.run_module('crypto_tool', run_name='__main__')\n"
                         "except SystemExit: pass\n"
                         "bad=[m for m in sys.modules if m.split('.')[0] in "
                         "('tkinter','ttkbootstrap','tkinterdnd2','Crypto')]\n"
                         "print('LOADED', bad)"])
    assert b"LOADED []" in done.stdout, done.stdout + done.stderr
