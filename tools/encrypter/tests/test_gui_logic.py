"""新介面的邏輯層（gui/logic.py）：不需要 tkinter、不開視窗。"""

import os
import subprocess
import sys
from unittest import mock

from _support import TOOL_DIR, Case

from crypto_tool import agefmt
from crypto_tool.gui import logic, texts as T
from crypto_tool.sealed import keys, ops, settings, workflow
from crypto_tool.sealed.errors import SealError, all_codes


class LogicCase(Case):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"TOOLZOO_DATA_DIR": str(self.tmp / "cfg")})
        env.start()
        self.addCleanup(env.stop)
        for name in settings.KEYS:
            os.environ.pop(name, None)
        self.patch(workflow, "AGE_SCRYPT_WORK_FACTOR", 10)

    def identity(self, name, passphrase=None):
        ident = agefmt.generate_identity()
        path = self.tmp / f"{name}.key"
        agefmt.write_identity_file(path, [ident], passphrase=passphrase, work_factor=10)
        return path, ident.public_key


class PureHelperTests(LogicCase):
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

    def test_dropped_lists(self):
        self.assertEqual(logic.first_dropped(()), ("", 0))
        self.assertEqual(logic.first_dropped(("C:/a b/檔 案.txt", "C:/other")), ("C:/a b/檔 案.txt", 1))
        self.assertEqual(logic.dropped(("a", " ", "b", "a")), ["a", "b"])
        self.assertEqual(logic.split_recipients(" age1a, age1b；age1c\nage1d "), ["age1a", "age1b", "age1c", "age1d"])

    def test_suggest_output(self):
        tmp = self.tmp
        (tmp / "dir").mkdir()
        self.assertEqual(logic.suggest_output("encrypt", str(tmp / "a.pdf")), str(tmp / "a.pdf.age"))
        self.assertEqual(logic.suggest_output("encrypt", str(tmp / "a.pdf"), mode="pgp"), str(tmp / "a.pdf.gpg"))
        self.assertEqual(logic.suggest_output("encrypt", str(tmp / "a.pdf"), mode="pgp", armor=True),
                         str(tmp / "a.pdf.asc"))
        self.assertEqual(logic.suggest_output("encrypt", str(tmp / "dir")), str(tmp / "dir.tar.age"))
        self.assertEqual(logic.suggest_output("encrypt", [str(tmp / "a"), str(tmp / "b")]),
                         str(tmp / "bundle.tar.age"))
        self.assertEqual(logic.suggest_output("decrypt", str(tmp / "a.pdf.age")), str(tmp / "a.pdf"))
        self.assertEqual(logic.suggest_output("decrypt", str(tmp / "dir.tar.age")), str(tmp / "dir"))
        self.assertEqual(logic.suggest_output("decrypt", str(tmp / "dir.tar.age"), keep_tar=True),
                         str(tmp / "dir.tar"))
        self.assertEqual(logic.suggest_output("decrypt", str(tmp / "old.isd2")), str(tmp / "old"))
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

    def test_describe_inputs(self):
        (self.tmp / "f.bin").write_bytes(b"x" * 2048)
        self.assertEqual(logic.describe_input(str(self.tmp / "f.bin")), f"{T.KIND_FILE}・2.0 KB")
        self.assertEqual(logic.describe_input(str(self.tmp)), T.KIND_FOLDER)
        self.assertEqual(logic.describe_input(str(self.tmp / "nope")), T.PROBLEM_INPUT_GONE)
        self.assertEqual(logic.describe_inputs([str(self.tmp / "f.bin"), str(self.tmp)]),
                         T.MANY_INPUTS.format(n=2))


class ValidationTests(LogicCase):
    def test_encrypt_form_problems(self):
        self.assertEqual(logic.validate(logic.JobForm()), [
            T.PROBLEM_NO_INPUT["encrypt"], T.PROBLEM_NO_LOCK, T.PROBLEM_NO_OUTPUT])
        src = self.tmp / "a.txt"
        src.write_bytes(b"x")
        form = logic.JobForm(inputs=[str(src)], output_path=str(src) + ".age", use_passphrase=True,
                             passphrase="one passphrase", passphrase_confirm="another one")
        self.assertEqual(logic.validate(form), [T.PROBLEM_MISMATCH])
        form.passphrase_confirm = "one passphrase"
        self.assertEqual(logic.validate(form), [])
        form.recipients = ["age1something"]
        self.assertEqual(logic.validate(form), [T.PROBLEM_AGE_MIX])     # age 不能密語＋金鑰
        form.mode = logic.MODE_PGP
        self.assertEqual(logic.validate(form), [])                      # PGP 可以
        self.assertEqual(logic.validate(form, gpg=False), [T.PROBLEM_PGP_UNAVAILABLE])
        form.use_passphrase = False
        form.recipients = []
        form.with_master = True
        self.assertEqual(logic.validate(form), [])

    def test_decrypt_form_problems(self):
        src = self.tmp / "a.age"
        src.write_bytes(b"x")
        gone = logic.JobForm(action="decrypt", inputs=[str(self.tmp / "gone.age")], output_path="x",
                             passphrase="p")
        self.assertEqual(logic.validate(gone), [T.PROBLEM_INPUT_GONE])
        nokey = logic.JobForm(action="decrypt", inputs=[str(src)], output_path="x")
        self.assertEqual(logic.validate(nokey), [T.PROBLEM_NO_DECRYPT_KEY])
        ok = logic.JobForm(action="decrypt", inputs=[str(src)], output_path="x", key_files=["k"])
        self.assertEqual(logic.validate(ok), [])


class JobTests(LogicCase):
    def test_key_roundtrip_with_master_progress_and_messages(self):
        tmp = self.tmp
        alice, alice_pub = self.identity("alice")
        master, master_pub = self.identity("master")
        settings.set_value(settings.MASTER_RECIPIENT, master_pub)
        self.assertEqual(logic.master_for(logic.MODE_AGE), master_pub)
        src = tmp / "data.bin"
        src.write_bytes(os.urandom(2_500_000))
        seen = []
        form = logic.JobForm(inputs=[str(src)], output_path=str(src) + ".age",
                             recipients=[alice_pub], with_master=True)
        done = logic.run_job_safely(form, progress=lambda d, t: seen.append(logic.progress_view(d, t)[0]))
        self.assertEqual((done.kind, done.title), ("success", T.SUCCESS_TITLE["encrypt"]), done.lines)
        self.assertIn(T.SUCCESS_WHO.format(who=T.WHO_KEYS.format(n=2) + T.WHO_MASTER), done.lines)
        self.assertIn(T.SUCCESS_BACKUP, done.lines)
        self.assertEqual(seen[-1], 100)
        self.assertEqual(seen, sorted(seen))

        text, info, problem = logic.inspect_sealed(str(src) + ".age")
        self.assertIsNone(problem)
        self.assertIn(T.LOCK_KEYS.format(n=2), text)

        again = logic.run_job_safely(form)  # 目標已存在
        self.assertEqual((again.kind, again.code), ("warning", "output_exists"))
        self.assertNotIn(T.ERROR_NOTHING_WRITTEN, again.lines)

        out = tmp / "back.bin"
        back = logic.run_job_safely(logic.JobForm(
            action="decrypt", inputs=[str(src) + ".age"], output_path=str(out), key_files=[str(master)]))
        self.assertEqual(back.kind, "success", back.lines)
        self.assertIn(T.SUCCESS_USED_MASTER, back.lines)
        self.assertEqual(out.read_bytes(), src.read_bytes())
        self.assertNotIn(T.SUCCESS_BACKUP, back.lines)

    def test_identity_file_as_recipient_and_protected_identity_needs_its_passphrase(self):
        locked, locked_pub = self.identity("locked", passphrase="id pass")
        plain, _ = self.identity("plain")
        src = self.tmp / "a.txt"
        src.write_bytes(b"hello")
        ok = logic.run_job_safely(logic.JobForm(inputs=[str(src)], output_path=str(self.tmp / "a.age"),
                                                recipients=[str(plain), locked_pub]))
        self.assertEqual(ok.kind, "success", ok.lines)
        refused = logic.run_job_safely(logic.JobForm(inputs=[str(src)], output_path=str(self.tmp / "b.age"),
                                                     recipients=[str(locked)]))
        self.assertEqual(refused.code, "bad_key_format")
        missing = logic.run_job_safely(logic.JobForm(action="decrypt", inputs=[str(self.tmp / "a.age")],
                                                     output_path=str(self.tmp / "o1"), key_files=[str(locked)]))
        self.assertEqual(missing.code, "key_missing")
        good = logic.run_job_safely(logic.JobForm(action="decrypt", inputs=[str(self.tmp / "a.age")],
                                                  output_path=str(self.tmp / "o2"), key_files=[str(locked)],
                                                  key_passphrase="id pass"))
        self.assertEqual(good.kind, "success", good.lines)

    def test_wrong_passphrase_message_is_plain_language(self):
        src = self.tmp / "a.txt"
        src.write_bytes(b"hello")
        sealed = str(src) + ".age"
        ok = logic.run_job_safely(logic.JobForm(
            inputs=[str(src)], output_path=sealed, use_passphrase=True,
            passphrase="right passphrase", passphrase_confirm="right passphrase"))
        self.assertEqual(ok.kind, "success")
        self.assertIn(T.LOCK_PASSPHRASE, logic.inspect_sealed(sealed)[0])
        bad = logic.run_job_safely(logic.JobForm(
            action="decrypt", inputs=[sealed], output_path=str(self.tmp / "o.txt"), passphrase="wrong passphrase"))
        self.assertEqual((bad.kind, bad.code, bad.title), ("danger", "wrong_key", T.ERROR_TITLES["wrong_key"]))
        self.assertIn(T.ERROR_NOTHING_WRITTEN, bad.lines)
        self.assertNotIn("wrong passphrase", " ".join(bad.lines))
        self.assertFalse((self.tmp / "o.txt").exists())

    def test_all_layers_partial_result_is_a_warning_with_the_layer(self):
        alice, alice_pub = self.identity("alice")
        _bob, bob_pub = self.identity("bob")
        inner = self.tmp / "inner.txt"
        inner.write_bytes(b"inner")
        logic.run_job(logic.JobForm(inputs=[str(inner)], output_path=str(self.tmp / "inner.txt.age"),
                                    recipients=[bob_pub]))
        side = self.tmp / "side.txt"
        side.write_bytes(b"side")
        logic.run_job(logic.JobForm(inputs=[str(self.tmp / "inner.txt.age"), str(side)],
                                    output_path=str(self.tmp / "outer.age"), recipients=[alice_pub]))
        msg = logic.run_job_safely(logic.JobForm(action="decrypt", inputs=[str(self.tmp / "outer.age")],
                                                 output_path=str(self.tmp / "out"), key_files=[str(alice)],
                                                 all_layers=True))
        self.assertEqual((msg.kind, msg.title), ("warning", T.LAYERS_STOPPED_TITLE))
        self.assertIn(T.LAYERS_STOP.format(depth=2, path="inner.txt.age", lock=T.LOCK_KEYS.format(n=1)),
                      msg.lines)

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

    def test_inspect_legacy_preview_and_foreign_files(self):
        legacy = self.tmp / "old.isd"
        legacy.write_text('CONTENT="""QUJD"""\nNOTE="""{"mode": "layered"}"""', encoding="utf-8")
        text, info, problem = logic.inspect_sealed(str(legacy))
        self.assertEqual((text, problem, info["format"]), (T.SEALED_LEGACY, None, "isd-legacy"))
        keyfile = self.tmp / "old.env"
        keys.generate_key_file(keyfile)
        src = self.tmp / "p.txt"
        src.write_bytes(b"preview")
        ops.encrypt_path(src, self.tmp / "p.isd2", keys.load_key_file(keyfile))
        text, info, problem = logic.inspect_sealed(str(self.tmp / "p.isd2"))
        self.assertIn("ISD2 預覽格式（已停用）", text)
        back = logic.run_job_safely(logic.JobForm(action="decrypt", inputs=[str(self.tmp / "p.isd2")],
                                                  output_path=str(self.tmp / "p.out"), key_files=[str(keyfile)]))
        self.assertEqual(back.kind, "success", back.lines)
        self.assertIn(T.SUCCESS_DEPRECATED, back.lines)
        other = self.tmp / "x.txt"
        other.write_bytes(b"plain text file")
        text, info, problem = logic.inspect_sealed(str(other))
        self.assertIsNone(info)
        self.assertEqual(problem.code, "unsupported_format")
        self.assertEqual(logic.inspect_sealed(str(self.tmp / "typing-in-progr")),
                         (T.PROBLEM_INPUT_GONE, None, None))


class KeyTabTests(LogicCase):
    def test_age_identity_never_reveals_or_overwrites(self):
        path = self.tmp / ".decryption_code.env"
        first = logic.create_age_identity(str(path), "", "", set_default=True)
        self.assertEqual(first.kind, "success", first.lines)
        secret = agefmt.load_identity_file(path)[0].secret_key_string()
        shown = " ".join([first.title, *first.lines])
        self.assertNotIn(secret, shown)
        self.assertIn(agefmt.load_identity_file(path)[0].public_key, shown)
        self.assertEqual(settings.identity_file(), path.resolve())
        self.assertEqual(logic.default_key_files(), [str(path.resolve())])
        second = logic.create_age_identity(str(path))
        self.assertEqual(second.code, "output_exists")
        self.assertEqual(agefmt.load_identity_file(path)[0].secret_key_string(), secret)
        self.assertEqual(logic.create_age_identity("  ").kind, "warning")
        self.assertEqual(logic.create_age_identity(str(self.tmp / "x"), "a", "b").lines, [T.PROBLEM_MISMATCH])
        locked = logic.create_age_identity(str(self.tmp / "locked.key"), "lock pass", "lock pass")
        self.assertIn(T.KEYS_PROTECTED, locked.lines)

    def test_master_settings_and_key_checks(self):
        ident_path, pub = self.identity("master")
        self.assertEqual(logic.public_key_from_identity(str(ident_path)), pub)
        saved = logic.save_master(pub, "")
        self.assertEqual(saved.kind, "success")
        self.assertEqual(settings.master_recipient(), pub)
        self.assertEqual(logic.save_master("age1notvalid", "").code, "bad_key_format")
        self.assertEqual(settings.master_recipient(), pub)                 # 壞的值沒有寫進去
        self.assertEqual(logic.save_master(pub, str(ident_path)).code, "bad_key_format")   # 不是 PGP 公鑰
        self.assertEqual(logic.save_master("", "").kind, "info")
        self.assertIsNone(settings.master_recipient())

        checked = logic.check_key_file(str(ident_path))
        self.assertIn(pub, checked.lines[0])
        self.assertNotIn("AGE-SECRET-KEY", " ".join(checked.lines))
        locked, _ = self.identity("locked", passphrase="x pass")
        self.assertEqual(logic.check_key_file(str(locked)).lines, [T.KEYS_CHECK_AGE_LOCKED])
        listing = self.tmp / "people.txt"
        listing.write_text(pub + "\n", encoding="utf-8")
        self.assertEqual(logic.check_key_file(str(listing)).kind, "info")
        old = self.tmp / "old.env"
        keys.generate_key_file(old)
        self.assertIn("ISD2", logic.check_key_file(str(old)).lines[0])
        self.assertEqual(logic.check_key_file(str(self.tmp / "missing")).code, "key_missing")
        self.assertEqual(logic.check_key_file("").kind, "warning")
