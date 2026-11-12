"""新介面的邏輯層（gui/logic.py）：不需要 tkinter、不開視窗。"""

import os
import sys

import pytest

from crypto_tool.gui import logic, texts as T
from crypto_tool.sealed import keys
from crypto_tool.sealed.errors import SealError, all_codes


def test_logic_and_texts_do_not_import_tkinter():
    import subprocess
    done = subprocess.run(
        [sys.executable, "-c",
         "import sys, crypto_tool.gui.logic; "
         "print([m for m in sys.modules if m.split('.')[0] in "
         "('tkinter', 'ttkbootstrap', 'tkinterdnd2', 'Crypto')])"],
        cwd=os.path.dirname(os.path.dirname(__file__)), capture_output=True, text=True)
    assert done.stdout.strip() == "[]", done.stdout + done.stderr


def test_human_size():
    assert logic.human_size(0) == "0 bytes"
    assert logic.human_size(1023) == "1023 bytes"
    assert logic.human_size(1536) == "1.5 KB"
    assert logic.human_size(5 * 1024 ** 3) == "5.0 GB"
    assert logic.human_size(5000 * 1024 ** 3) == "5000.0 GB"


def test_first_dropped():
    assert logic.first_dropped(()) == ("", 0)
    assert logic.first_dropped(("C:/a b/檔 案.txt", "C:/other")) == ("C:/a b/檔 案.txt", 1)


def test_suggest_output(tmp_path):
    src = tmp_path / "a.pdf"
    assert logic.suggest_output("encrypt", str(src)) == str(tmp_path / "a.pdf.isd2")
    assert logic.suggest_output("decrypt", str(tmp_path / "a.pdf.isd2")) == str(src)
    assert logic.suggest_output("decrypt", str(tmp_path / "dir.isd2"), keep_tar=True) == str(
        tmp_path / "dir.tar")
    assert logic.suggest_output("decrypt", str(tmp_path / "odd.bin")) == ""
    assert logic.suggest_output("encrypt", "") == ""


def test_passphrase_strength_levels():
    assert logic.passphrase_strength("")[0] == 0
    assert logic.passphrase_strength("short")[0] == 1
    assert logic.passphrase_strength("twelve chars")[0] == 2
    assert logic.passphrase_strength("Sixteen-Chars-01")[0] == 3
    assert logic.passphrase_strength("a much longer sentence here")[0] == 3
    for level in range(4):
        assert isinstance(T.STRENGTH_LABELS[level], str)


def test_validate_lists_every_problem(tmp_path):
    form = logic.JobForm()
    assert logic.validate(form) == [
        T.PROBLEM_NO_INPUT["encrypt"], T.PROBLEM_NO_PASSPHRASE, T.PROBLEM_NO_OUTPUT]
    src = tmp_path / "a.txt"
    src.write_bytes(b"x")
    form = logic.JobForm(input_path=str(src), output_path=str(src) + ".isd2",
                         passphrase="one passphrase", passphrase_confirm="another one")
    assert logic.validate(form) == [T.PROBLEM_MISMATCH]
    form.passphrase_confirm = "one passphrase"
    assert logic.validate(form) == []
    form.key_mode = logic.KEY_FILE
    assert logic.validate(form) == [T.PROBLEM_NO_KEYFILE]
    gone = logic.JobForm(action="decrypt", input_path=str(tmp_path / "gone.isd2"),
                         output_path="x", passphrase="p")
    assert logic.validate(gone) == [T.PROBLEM_INPUT_GONE]
    # 解密不需要再輸入一次
    ok = logic.JobForm(action="decrypt", input_path=str(src), output_path="x", passphrase="p")
    assert logic.validate(ok) == []


def test_keyfile_job_roundtrip_with_progress_and_messages(tmp_path):
    keyfile = tmp_path / "k.env"
    created = logic.create_key_file(str(keyfile))
    assert created.kind == "success" and T.KEYS_BACKUP_WARNING in created.lines
    src = tmp_path / "data.bin"
    src.write_bytes(os.urandom(2_500_000))
    seen = []
    form = logic.JobForm(input_path=str(src), output_path=str(src) + ".isd2",
                         key_mode=logic.KEY_FILE, key_file=str(keyfile))
    done = logic.run_job_safely(form, progress=lambda d, t: seen.append(logic.progress_view(d, t)))
    assert done.kind == "success" and done.title == T.SUCCESS_TITLE["encrypt"]
    assert T.SUCCESS_BACKUP in done.lines and T.SUCCESS_ORIGINAL_KEPT in done.lines
    assert seen[-1][0] == 100 and [p for p, _ in seen] == sorted(p for p, _ in seen)

    text, info, problem = logic.inspect_sealed(str(src) + ".isd2")
    assert problem is None and "AES-256-GCM" in text and T.SEALED_KEY["raw-key"] in text
    assert logic.key_mode_for(info) == logic.KEY_FILE

    again = logic.run_job_safely(form)  # 目標已存在
    assert (again.kind, again.code) == ("warning", "output_exists")
    assert T.ERROR_NOTHING_WRITTEN not in again.lines

    out = tmp_path / "back.bin"
    back = logic.run_job_safely(logic.JobForm(
        action="decrypt", input_path=str(src) + ".isd2", output_path=str(out),
        key_mode=logic.KEY_FILE, key_file=str(keyfile)))
    assert back.kind == "success" and out.read_bytes() == src.read_bytes()
    assert T.SUCCESS_BACKUP not in back.lines


def test_wrong_passphrase_message_is_plain_language(tmp_path, monkeypatch):
    # 測試不需要真的跑高成本的 scrypt
    real = logic.encrypt_path
    monkeypatch.setattr(logic, "encrypt_path",
                        lambda *a, **k: real(*a, scrypt_log_n=10, **k))
    src = tmp_path / "a.txt"
    src.write_bytes(b"hello")
    sealed = str(src) + ".isd2"
    ok = logic.run_job_safely(logic.JobForm(
        input_path=str(src), output_path=sealed,
        passphrase="right passphrase", passphrase_confirm="right passphrase"))
    assert ok.kind == "success"
    assert logic.key_mode_for(logic.inspect_sealed(sealed)[1]) == logic.KEY_PASSPHRASE
    bad = logic.run_job_safely(logic.JobForm(
        action="decrypt", input_path=sealed, output_path=str(tmp_path / "o.txt"),
        passphrase="wrong passphrase"))
    assert (bad.kind, bad.code, bad.title) == ("danger", "wrong_key", T.ERROR_TITLES["wrong_key"])
    assert T.ERROR_NOTHING_WRITTEN in bad.lines
    assert "wrong passphrase" not in " ".join(bad.lines)
    assert not (tmp_path / "o.txt").exists()


def test_every_error_code_has_a_title_and_unexpected_errors_stay_quiet(monkeypatch):
    for code in all_codes():
        assert code in T.ERROR_TITLES
        message = logic.error_message(SealError(code, "原因"))
        assert message.title and message.lines[0] == "原因"

    def boom(*_a, **_k):
        raise RuntimeError("SECRET-DETAIL in exception text")
    monkeypatch.setattr(logic, "run_job", boom)
    message = logic.run_job_safely(logic.JobForm())
    assert message.code == "internal_bug"
    assert "SECRET-DETAIL" not in " ".join(message.lines)


def test_inspect_legacy_and_foreign_files(tmp_path):
    legacy = tmp_path / "old.isd"
    legacy.write_text('CONTENT="""QUJD"""\nNOTE="""{"mode": "layered"}"""', encoding="utf-8")
    text, info, problem = logic.inspect_sealed(str(legacy))
    assert text == T.SEALED_LEGACY and problem is None and logic.key_mode_for(info) is None
    other = tmp_path / "x.txt"
    other.write_bytes(b"plain text file")
    text, info, problem = logic.inspect_sealed(str(other))
    assert info is None and problem.code == "unsupported_format"
    text, info, problem = logic.inspect_sealed(str(tmp_path / "typing-in-progr"))
    assert (text, info, problem) == (T.PROBLEM_INPUT_GONE, None, None)


def test_describe_input(tmp_path):
    (tmp_path / "f.bin").write_bytes(b"x" * 2048)
    assert logic.describe_input(str(tmp_path / "f.bin")) == f"{T.KIND_FILE}・2.0 KB"
    assert logic.describe_input(str(tmp_path)) == T.KIND_FOLDER
    assert logic.describe_input(str(tmp_path / "nope")) == T.PROBLEM_INPUT_GONE


def test_key_tab_helpers_never_reveal_or_overwrite(tmp_path):
    path = tmp_path / ".decryption_code.env"
    first = logic.create_key_file(str(path))
    raw = keys.load_key_file(path).raw
    shown = " ".join([first.title, *first.lines])
    assert raw.hex() not in shown and path.read_text().split("b64:")[1].strip() not in shown
    second = logic.create_key_file(str(path))
    assert second.code == "output_exists" and keys.load_key_file(path).raw == raw
    assert logic.create_key_file("  ").kind == "warning"

    checked = logic.check_key_file(str(path))
    assert checked.kind == "success" and keys.key_id(raw) in checked.lines[0]
    assert raw.hex() not in checked.lines[0]
    words = tmp_path / "words.env"
    words.write_text("CODE=some words that are a passphrase\n", encoding="utf-8")
    info = logic.check_key_file(str(words))
    assert info.kind == "info" and "some words" not in " ".join(info.lines)
    assert logic.check_key_file(str(tmp_path / "missing")).code == "key_missing"
    assert logic.check_key_file("").kind == "warning"


def test_progress_view():
    assert logic.progress_view(0, 0) == (0, "")
    assert logic.progress_view(512, 1024)[0] == 50
    assert logic.progress_view(5000, 1024)[0] == 100
