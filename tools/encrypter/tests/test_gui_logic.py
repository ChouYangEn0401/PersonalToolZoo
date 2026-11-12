"""新介面的邏輯層（gui/logic.py）：不需要 tkinter、不開視窗。"""

import os
import subprocess
import sys
import unittest

from _support import TOOL_DIR, Case

from crypto_tool.gui import logic, texts as T
from crypto_tool.sealed import keys
from crypto_tool.sealed.errors import SealError, all_codes


class PureHelperTests(Case):
    def test_logic_and_texts_do_not_import_tkinter(self):
        done = subprocess.run(
            [sys.executable, "-c",
             "import sys, crypto_tool.gui.logic; "
             "print([m for m in sys.modules if m.split('.')[0] in "
             "('tkinter', 'ttkbootstrap', 'tkinterdnd2', 'Crypto')])"],
            cwd=TOOL_DIR, capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), "[]", done.stdout + done.stderr)

    def test_human_size(self):
        self.assertEqual(logic.human_size(0), "0 bytes")
        self.assertEqual(logic.human_size(1023), "1023 bytes")
        self.assertEqual(logic.human_size(1536), "1.5 KB")
        self.assertEqual(logic.human_size(5 * 1024 ** 3), "5.0 GB")
        self.assertEqual(logic.human_size(5000 * 1024 ** 3), "5000.0 GB")

    def test_first_dropped(self):
        self.assertEqual(logic.first_dropped(()), ("", 0))
        self.assertEqual(logic.first_dropped(("C:/a b/檔 案.txt", "C:/other")),
                         ("C:/a b/檔 案.txt", 1))

    def test_suggest_output(self):
        tmp = self.tmp
        self.assertEqual(logic.suggest_output("encrypt", str(tmp / "a.pdf")),
                         str(tmp / "a.pdf.isd2"))
        self.assertEqual(logic.suggest_output("decrypt", str(tmp / "a.pdf.isd2")),
                         str(tmp / "a.pdf"))
        self.assertEqual(logic.suggest_output("decrypt", str(tmp / "dir.isd2"), keep_tar=True),
                         str(tmp / "dir.tar"))
        self.assertEqual(logic.suggest_output("decrypt", str(tmp / "odd.bin")), "")
        self.assertEqual(logic.suggest_output("encrypt", ""), "")

    def test_passphrase_strength_levels(self):
        for text, level in (("", 0), ("short", 1), ("twelve chars", 2),
                            ("Sixteen-Chars-01", 3), ("a much longer sentence here", 3)):
            self.assertEqual(logic.passphrase_strength(text), (level, T.STRENGTH_LABELS[level]))

    def test_progress_view(self):
        self.assertEqual(logic.progress_view(0, 0), (0, ""))
        self.assertEqual(logic.progress_view(512, 1024)[0], 50)
        self.assertEqual(logic.progress_view(5000, 1024)[0], 100)

    def test_describe_input(self):
        (self.tmp / "f.bin").write_bytes(b"x" * 2048)
        self.assertEqual(logic.describe_input(str(self.tmp / "f.bin")), f"{T.KIND_FILE}・2.0 KB")
        self.assertEqual(logic.describe_input(str(self.tmp)), T.KIND_FOLDER)
        self.assertEqual(logic.describe_input(str(self.tmp / "nope")), T.PROBLEM_INPUT_GONE)


class ValidationTests(Case):
    def test_validate_lists_every_problem(self):
        self.assertEqual(logic.validate(logic.JobForm()), [
            T.PROBLEM_NO_INPUT["encrypt"], T.PROBLEM_NO_PASSPHRASE, T.PROBLEM_NO_OUTPUT])
        src = self.tmp / "a.txt"
        src.write_bytes(b"x")
        form = logic.JobForm(input_path=str(src), output_path=str(src) + ".isd2",
                             passphrase="one passphrase", passphrase_confirm="another one")
        self.assertEqual(logic.validate(form), [T.PROBLEM_MISMATCH])
        form.passphrase_confirm = "one passphrase"
        self.assertEqual(logic.validate(form), [])
        form.key_mode = logic.KEY_FILE
        self.assertEqual(logic.validate(form), [T.PROBLEM_NO_KEYFILE])
        gone = logic.JobForm(action="decrypt", input_path=str(self.tmp / "gone.isd2"),
                             output_path="x", passphrase="p")
        self.assertEqual(logic.validate(gone), [T.PROBLEM_INPUT_GONE])
        # 解密不需要再輸入一次
        ok = logic.JobForm(action="decrypt", input_path=str(src), output_path="x",
                           passphrase="p")
        self.assertEqual(logic.validate(ok), [])


class JobTests(Case):
    def test_keyfile_job_roundtrip_with_progress_and_messages(self):
        tmp = self.tmp
        keyfile = tmp / "k.env"
        created = logic.create_key_file(str(keyfile))
        self.assertEqual(created.kind, "success")
        self.assertIn(T.KEYS_BACKUP_WARNING, created.lines)
        src = tmp / "data.bin"
        src.write_bytes(os.urandom(2_500_000))
        seen = []
        form = logic.JobForm(input_path=str(src), output_path=str(src) + ".isd2",
                             key_mode=logic.KEY_FILE, key_file=str(keyfile))
        done = logic.run_job_safely(
            form, progress=lambda d, t: seen.append(logic.progress_view(d, t)[0]))
        self.assertEqual((done.kind, done.title), ("success", T.SUCCESS_TITLE["encrypt"]))
        self.assertIn(T.SUCCESS_BACKUP, done.lines)
        self.assertIn(T.SUCCESS_ORIGINAL_KEPT, done.lines)
        self.assertEqual(seen[-1], 100)
        self.assertEqual(seen, sorted(seen))

        text, info, problem = logic.inspect_sealed(str(src) + ".isd2")
        self.assertIsNone(problem)
        self.assertIn("AES-256-GCM", text)
        self.assertIn(T.SEALED_KEY["raw-key"], text)
        self.assertEqual(logic.key_mode_for(info), logic.KEY_FILE)

        again = logic.run_job_safely(form)  # 目標已存在
        self.assertEqual((again.kind, again.code), ("warning", "output_exists"))
        self.assertNotIn(T.ERROR_NOTHING_WRITTEN, again.lines)

        out = tmp / "back.bin"
        back = logic.run_job_safely(logic.JobForm(
            action="decrypt", input_path=str(src) + ".isd2", output_path=str(out),
            key_mode=logic.KEY_FILE, key_file=str(keyfile)))
        self.assertEqual(back.kind, "success")
        self.assertEqual(out.read_bytes(), src.read_bytes())
        self.assertNotIn(T.SUCCESS_BACKUP, back.lines)

    def test_wrong_passphrase_message_is_plain_language(self):
        real = logic.encrypt_path   # 測試不需要真的跑高成本的 scrypt
        self.patch(logic, "encrypt_path", lambda *a, **k: real(*a, scrypt_log_n=10, **k))
        src = self.tmp / "a.txt"
        src.write_bytes(b"hello")
        sealed = str(src) + ".isd2"
        ok = logic.run_job_safely(logic.JobForm(
            input_path=str(src), output_path=sealed,
            passphrase="right passphrase", passphrase_confirm="right passphrase"))
        self.assertEqual(ok.kind, "success")
        self.assertEqual(logic.key_mode_for(logic.inspect_sealed(sealed)[1]), logic.KEY_PASSPHRASE)
        bad = logic.run_job_safely(logic.JobForm(
            action="decrypt", input_path=sealed, output_path=str(self.tmp / "o.txt"),
            passphrase="wrong passphrase"))
        self.assertEqual((bad.kind, bad.code, bad.title),
                         ("danger", "wrong_key", T.ERROR_TITLES["wrong_key"]))
        self.assertIn(T.ERROR_NOTHING_WRITTEN, bad.lines)
        self.assertNotIn("wrong passphrase", " ".join(bad.lines))
        self.assertFalse((self.tmp / "o.txt").exists())

    def test_every_error_code_has_a_title_and_unexpected_errors_stay_quiet(self):
        for code in all_codes():
            self.assertIn(code, T.ERROR_TITLES)
            message = logic.error_message(SealError(code, "原因"))
            self.assertTrue(message.title)
            self.assertEqual(message.lines[0], "原因")

        def boom(*_a, **_k):
            raise RuntimeError("SECRET-DETAIL in exception text")
        self.patch(logic, "run_job", boom)
        message = logic.run_job_safely(logic.JobForm())
        self.assertEqual(message.code, "internal_bug")
        self.assertNotIn("SECRET-DETAIL", " ".join(message.lines))

    def test_inspect_legacy_and_foreign_files(self):
        legacy = self.tmp / "old.isd"
        legacy.write_text('CONTENT="""QUJD"""\nNOTE="""{"mode": "layered"}"""', encoding="utf-8")
        text, info, problem = logic.inspect_sealed(str(legacy))
        self.assertEqual((text, problem, logic.key_mode_for(info)), (T.SEALED_LEGACY, None, None))
        other = self.tmp / "x.txt"
        other.write_bytes(b"plain text file")
        text, info, problem = logic.inspect_sealed(str(other))
        self.assertIsNone(info)
        self.assertEqual(problem.code, "unsupported_format")
        self.assertEqual(logic.inspect_sealed(str(self.tmp / "typing-in-progr")),
                         (T.PROBLEM_INPUT_GONE, None, None))


class KeyTabTests(Case):
    def test_helpers_never_reveal_or_overwrite(self):
        path = self.tmp / ".decryption_code.env"
        first = logic.create_key_file(str(path))
        raw = keys.load_key_file(path).raw
        shown = " ".join([first.title, *first.lines])
        self.assertNotIn(raw.hex(), shown)
        self.assertNotIn(path.read_text().split("b64:")[1].strip(), shown)
        second = logic.create_key_file(str(path))
        self.assertEqual(second.code, "output_exists")
        self.assertEqual(keys.load_key_file(path).raw, raw)
        self.assertEqual(logic.create_key_file("  ").kind, "warning")

        checked = logic.check_key_file(str(path))
        self.assertEqual(checked.kind, "success")
        self.assertIn(keys.key_id(raw), checked.lines[0])
        self.assertNotIn(raw.hex(), checked.lines[0])
        words = self.tmp / "words.env"
        words.write_text("CODE=some words that are a passphrase\n", encoding="utf-8")
        info = logic.check_key_file(str(words))
        self.assertEqual(info.kind, "info")
        self.assertNotIn("some words", " ".join(info.lines))
        self.assertEqual(logic.check_key_file(str(self.tmp / "missing")).code, "key_missing")
        self.assertEqual(logic.check_key_file("").kind, "warning")


if __name__ == "__main__":
    unittest.main()
