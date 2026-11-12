"""命令列（0.4.0）：每個指令的成功與失敗、--json 合約、退出碼、祕密不外洩、
--all-layers 剝洋蔥＋萬用鎖、rewrap／rekey、ISD2 預覽格式只能解不能產生。

大部分在同一個行程裡呼叫 main()（快）；另外有幾個真的開子行程跑 ``python -m crypto_tool``。
金鑰與密語都是測試時臨時產生的；設定（.env）用 TOOLZOO_DATA_DIR 導到暫存資料夾，不會讀到 repo 的 .env。
PGP 模式的測試要系統上有 gpg，找不到就整組略過。
"""

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import unittest
from pathlib import Path
from unittest import mock

from _support import TOOL_DIR, Case

from crypto_tool import agefmt, pgpmode
from crypto_tool.sealed import cli, keys, ops, settings, workflow
from crypto_tool.sealed.container import KeyMaterial
from crypto_tool.sealed.errors import all_codes

PLAIN_MARK = b"PLAINTEXT-MARKER-0123456789 "


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


def payload_sha(path: Path) -> str:
    """age 檔標頭之後的位元組（nonce＋密文）的 SHA-256。"""
    blob = path.read_bytes()
    end = blob.index(b"\n---") + 1
    end = blob.index(b"\n", end) + 1
    return hashlib.sha256(blob[end:]).hexdigest()


class CliCase(Case):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"TOOLZOO_DATA_DIR": str(self.tmp / "cfg")})
        env.start()
        self.addCleanup(env.stop)
        for name in list(os.environ):
            if name.startswith("ENCRYPTER_") and name not in ("ENCRYPTER_GPG", "ENCRYPTER_GPG_TMPDIR"):
                os.environ.pop(name)
        self.patch(workflow, "AGE_SCRYPT_WORK_FACTOR", 10)   # 測試不需要真的花 256 MB 算 scrypt
        self.plain = self.tmp / "notes.txt"
        self.plain.write_bytes(PLAIN_MARK * 20)
        self.ids = {}

    def identity(self, name: str, passphrase: str | None = None) -> Path:
        ident = agefmt.generate_identity()
        path = self.tmp / f"{name}.key"
        agefmt.write_identity_file(path, [ident], passphrase=passphrase, work_factor=10)
        self.ids[name] = ident
        return path

    def pub(self, name: str) -> str:
        return self.ids[name].public_key

    def run_json(self, *argv, stdin_text=""):
        code, out, err = run(*argv, "--json", stdin_text=stdin_text)
        lines = out.splitlines()
        self.assertEqual((len(lines), err), (1, ""), (out, err))
        return code, json.loads(lines[0])

    def ok(self, *argv, stdin_text=""):
        code, body = self.run_json(*argv, stdin_text=stdin_text)
        self.assertEqual((code, body["ok"]), (0, True), body)
        return body["data"]

    def assert_error(self, result, exit_code, code):
        self.assertEqual((result[0], result[1]["ok"], result[1]["error"]["code"]),
                         (exit_code, False, code), result[1])
        self.assertEqual(set(result[1]["error"]), {"code", "reason", "retryable", "remedy", "detail"})

    def set_master(self, value: str):
        cfg = self.tmp / "cfg"
        cfg.mkdir(exist_ok=True)
        settings.set_value(settings.MASTER_RECIPIENT, value)


class EncryptDecryptTests(CliCase):
    def test_age_file_roundtrip_with_default_names(self):
        alice = self.identity("alice")
        data = self.ok("encrypt", self.plain, "-r", self.pub("alice"))
        sealed = self.tmp / "notes.txt.age"
        self.assertEqual((data["output"], data["format"], data["payload"]), (str(sealed), "age", "file"))
        self.assertEqual(data["recipients"], {"keys": 1, "passphrase": False, "master": False})
        self.assertTrue(sealed.read_bytes().startswith(b"age-encryption.org/v1\n"))
        self.plain.rename(self.tmp / "original.txt")
        back = self.ok("decrypt", sealed, "-i", alice)
        self.assertEqual((back["output"], back["payload"]), (str(self.plain), "file"))
        self.assertEqual(self.plain.read_bytes(), (self.tmp / "original.txt").read_bytes())

    def test_several_inputs_and_folders_become_one_archive(self):
        alice = self.identity("alice")
        folder = self.tmp / "photos"
        (folder / "trip").mkdir(parents=True)
        (folder / "trip" / "a.jpg").write_bytes(os.urandom(3000))
        (folder / "empty").mkdir()
        data = self.ok("encrypt", self.plain, folder, "-o", self.tmp / "bundle.age", "-r", self.pub("alice"))
        self.assertEqual((data["payload"], data["files"]), ("tar", 2))
        out = self.ok("decrypt", self.tmp / "bundle.age", "-i", alice)
        restored = self.tmp / "bundle"
        self.assertEqual((out["output"], out["payload"], out["files"]), (str(restored), "folder", 2))
        self.assertEqual((restored / "notes.txt").read_bytes(), self.plain.read_bytes())
        self.assertEqual((restored / "photos" / "trip" / "a.jpg").read_bytes(),
                         (folder / "trip" / "a.jpg").read_bytes())
        self.assertTrue((restored / "photos" / "empty").is_dir())
        # 單一資料夾：預設檔名 photos.tar.age，解開還原成 photos2（指定的名字）
        self.ok("encrypt", folder, "-r", self.pub("alice"))
        self.assertTrue((self.tmp / "photos.tar.age").is_file())
        self.ok("decrypt", self.tmp / "photos.tar.age", "-o", self.tmp / "photos2", "-i", alice)
        self.assertTrue((self.tmp / "photos2" / "trip" / "a.jpg").is_file())
        # --keep-tar：得到標準 tar
        kept = self.ok("decrypt", self.tmp / "photos.tar.age", "-o", self.tmp / "p.tar", "-i", alice,
                       "--keep-tar")
        self.assertEqual(kept["payload"], "tar")
        with tarfile.open(self.tmp / "p.tar") as tar:
            self.assertIn("trip/a.jpg", tar.getnames())
            self.assertTrue(all(m.uname == "" for m in tar.getmembers()))
        # 多個輸入一定要 -o；名字重複拒絕
        self.assert_error(self.run_json("encrypt", self.plain, folder, "-r", self.pub("alice")), 2, "bad_input")
        other = self.tmp / "x"
        other.mkdir()
        (other / "notes.txt").write_bytes(b"x")
        self.assert_error(self.run_json("encrypt", self.plain, other / "notes.txt", "-o", self.tmp / "dup.age",
                                        "-r", self.pub("alice")), 2, "bad_input")

    def test_armor_and_recipients_file(self):
        alice = self.identity("alice")
        self.identity("bob")
        listing = self.tmp / "people.txt"
        listing.write_text(f"# team\n{self.pub('alice')}\n\n{self.pub('bob')}\n", encoding="utf-8")
        data = self.ok("encrypt", self.plain, "-o", self.tmp / "n.age", "-R", listing, "--armor")
        self.assertEqual((data["armored"], data["recipients"]["keys"]), (True, 2))
        self.assertTrue((self.tmp / "n.age").read_bytes().startswith(b"-----BEGIN AGE ENCRYPTED FILE-----"))
        info = self.ok("inspect", self.tmp / "n.age")
        self.assertEqual((info["format"], info["armored"], info["stanza_counts"]), ("age", True, {"X25519": 2}))
        self.ok("decrypt", self.tmp / "n.age", "-o", self.tmp / "back.txt", "-i", alice)
        self.assertEqual((self.tmp / "back.txt").read_bytes(), self.plain.read_bytes())

    def test_passphrase_from_stdin_short_warning_and_wrong_passphrase(self):
        data = self.ok("encrypt", self.plain, "--passphrase-stdin", stdin_text="短密語\n")
        self.assertEqual(data["recipients"], {"keys": 0, "passphrase": True, "master": False})
        self.assertEqual(data["warnings"], ["passphrase_short"])
        sealed = self.tmp / "notes.txt.age"
        self.assertEqual(self.ok("inspect", sealed)["stanza_counts"], {"scrypt": 1})
        out = self.tmp / "o.txt"
        self.ok("decrypt", sealed, "-o", out, "--passphrase", stdin_text="短密語\r\n")
        self.assertEqual(out.read_bytes(), self.plain.read_bytes())
        self.assert_error(self.run_json("decrypt", sealed, "-o", self.tmp / "o2", "--passphrase-stdin",
                                        stdin_text="不對的密語\n"), 5, "wrong_key")
        self.assert_error(self.run_json("decrypt", sealed, "-o", self.tmp / "o3", "--passphrase-stdin",
                                        stdin_text=""), 2, "key_missing")
        self.assertFalse((self.tmp / "o2").exists() or (self.tmp / "o3").exists())

    def test_age_refuses_passphrase_with_other_recipients_before_asking(self):
        self.identity("alice")
        # 標準輸入是空的：如果先問密語會變成 key_missing；應該在問之前就拒絕
        code, body = self.run_json("encrypt", self.plain, "-r", self.pub("alice"), "--passphrase-stdin")
        self.assert_error((code, body), 2, "bad_input")
        self.assertEqual(body["error"]["detail"], "scrypt-not-alone")
        self.assertIn("PGP", body["error"]["remedy"]["action"])
        self.assertFalse((self.tmp / "notes.txt.age").exists())

    def test_mode_specific_options_are_checked(self):
        self.identity("alice")
        self.assert_error(self.run_json("encrypt", self.plain, "--pgp-recipient", self.plain), 2, "bad_input")
        self.assert_error(self.run_json("encrypt", self.plain, "--mode", "pgp", "-r", self.pub("alice")),
                          2, "bad_input")
        self.assert_error(self.run_json("encrypt", self.plain), 2, "key_missing")
        self.assert_error(self.run_json("encrypt", self.plain, "-r", "age1notakey"), 2, "bad_key_format")

    def test_output_exists_force_wrong_key_and_corrupt(self):
        alice = self.identity("alice")
        bob = self.identity("bob")
        sealed = self.tmp / "notes.txt.age"
        sealed.write_bytes(b"keep me")
        result = self.run_json("encrypt", self.plain, "-r", self.pub("alice"))
        self.assert_error(result, 2, "output_exists")
        self.assertTrue(result[1]["error"]["remedy"]["action"])
        self.assertEqual(sealed.read_bytes(), b"keep me")
        self.ok("encrypt", self.plain, "-r", self.pub("alice"), "--force")
        self.assert_error(self.run_json("decrypt", sealed, "-o", self.tmp / "o1", "-i", bob), 5, "wrong_key")
        blob = bytearray(sealed.read_bytes())
        blob[-1] ^= 1
        sealed.write_bytes(bytes(blob))
        self.assert_error(self.run_json("decrypt", sealed, "-o", self.tmp / "o2", "-i", alice), 6, "corrupt")
        sealed.write_bytes(bytes(blob[:-40]))
        self.assert_error(self.run_json("decrypt", sealed, "-o", self.tmp / "o3", "-i", alice), 6, "corrupt")
        self.assertFalse(any((self.tmp / n).exists() for n in ("o1", "o2", "o3")))
        self.assertEqual([p.name for p in self.tmp.iterdir() if "partial" in p.name], [])

    def test_unknown_and_legacy_files(self):
        alice = self.identity("alice")
        self.assert_error(self.run_json("decrypt", self.plain, "-o", self.tmp / "o", "-i", alice),
                          2, "unsupported_format")
        self.assert_error(self.run_json("inspect", self.plain), 2, "unsupported_format")
        legacy = self.tmp / "old.isd"
        legacy.write_text('CONTENT="""QUJD"""\nNOTE="""{"mode": "layered"}"""', encoding="utf-8")
        self.assert_error(self.run_json("decrypt", legacy, "-o", self.tmp / "o", "-i", alice), 2, "legacy_format")
        self.assertEqual(self.ok("info", legacy)["format"], "isd-legacy")
        odd = self.tmp / "sealed.bin"
        self.ok("encrypt", self.plain, "-o", odd, "-r", self.pub("alice"))
        self.assert_error(self.run_json("decrypt", odd, "-i", alice), 2, "bad_input")   # 猜不出輸出檔名

    def test_usage_errors_are_exit_2_with_the_json_contract(self):
        for argv in (["frobnicate"], [], ["encrypt"], ["decrypt"], ["rewrap", self.plain],
                     ["encrypt", self.plain, "--cipher", "aes-256-gcm"],
                     ["encrypt", self.plain, "--key-file", self.plain],
                     ["decrypt", self.plain, "--passphrase", "--passphrase-stdin"],
                     ["--check", "extra"]):
            with self.subTest(argv=[str(a) for a in argv[:2]]):
                code, body = self.run_json(*argv)
                self.assertEqual((code, body["ok"]), (2, False))
                self.assertIn(body["error"]["code"], all_codes())


class MasterLockTests(CliCase):
    def test_with_master_needs_configuration_then_master_opens_everything(self):
        self.identity("alice")
        master = self.identity("master")
        self.assert_error(self.run_json("encrypt", self.plain, "-r", self.pub("alice"), "--with-master"),
                          2, "key_missing")
        self.set_master(self.pub("master"))
        data = self.ok("encrypt", self.plain, "-r", self.pub("alice"), "--with-master")
        self.assertEqual(data["recipients"], {"keys": 2, "passphrase": False, "master": True})
        back = self.ok("decrypt", self.tmp / "notes.txt.age", "-o", self.tmp / "m.txt", "-i", master)
        self.assertTrue(back["used_master"])
        # 萬用鎖＋密語在簡單模式不行，訊息建議 PGP 模式
        code, body = self.run_json("encrypt", self.plain, "-o", self.tmp / "x.age", "--with-master",
                                   "--passphrase-stdin", stdin_text="whatever passphrase\n")
        self.assert_error((code, body), 2, "bad_input")
        self.assertIn("PGP", body["error"]["remedy"]["action"])

    def test_default_identity_from_settings_and_private_key_is_refused_there(self):
        alice = self.identity("alice")
        self.ok("encrypt", self.plain, "-r", self.pub("alice"))
        settings.set_value(settings.IDENTITY_FILE, str(alice))
        self.ok("decrypt", self.tmp / "notes.txt.age", "-o", self.tmp / "d.txt")   # 沒給 -i：用設定的身分檔
        self.assertEqual((self.tmp / "d.txt").read_bytes(), self.plain.read_bytes())
        env = settings.env_file_for_writing()
        env.write_text(env.read_text(encoding="utf-8")
                       + f"{settings.MASTER_RECIPIENT}={self.ids['alice'].secret_key_string()}\n",
                       encoding="utf-8")
        code, body = self.run_json("encrypt", self.plain, "-o", self.tmp / "y.age", "--with-master")
        self.assert_error((code, body), 2, "bad_key_format")
        self.assertNotIn(self.ids["alice"].secret_key_string(), json.dumps(body))

    def test_rewrap_old_key_fails_master_still_opens_and_payload_is_unchanged(self):
        alice = self.identity("alice")
        bob = self.identity("bob")
        master = self.identity("master")
        self.set_master(self.pub("master"))
        self.ok("encrypt", self.plain, "-o", self.tmp / "a.age", "-r", self.pub("alice"), "--with-master")
        data = self.ok("rewrap", self.tmp / "a.age", "-o", self.tmp / "b.age", "-i", master,
                       "-r", self.pub("bob"), "--with-master")
        self.assertEqual(data["new_recipient_count"], 2)
        self.assertEqual(payload_sha(self.tmp / "a.age"), payload_sha(self.tmp / "b.age"))
        self.assert_error(self.run_json("decrypt", self.tmp / "b.age", "-o", self.tmp / "x", "-i", alice),
                          5, "wrong_key")
        self.ok("decrypt", self.tmp / "b.age", "-o", self.tmp / "by_bob", "-i", bob)
        self.ok("decrypt", self.tmp / "b.age", "-o", self.tmp / "by_master", "-i", master)
        # 誠實限制：舊檔副本還是打得開
        self.ok("decrypt", self.tmp / "a.age", "-o", self.tmp / "old_copy", "-i", alice)
        # 沒有能開的鑰匙就不能換鎖
        self.assert_error(self.run_json("rewrap", self.tmp / "b.age", "-o", self.tmp / "c.age", "-i", alice,
                                        "-r", self.pub("alice")), 5, "wrong_key")

    def test_rekey_changes_the_file_key(self):
        alice = self.identity("alice")
        bob = self.identity("bob")
        self.ok("encrypt", self.plain, "-o", self.tmp / "a.age", "-r", self.pub("alice"))
        self.ok("rekey", self.tmp / "a.age", "-o", self.tmp / "b.age", "-i", alice, "-r", self.pub("bob"))
        self.assertNotEqual(payload_sha(self.tmp / "a.age"), payload_sha(self.tmp / "b.age"))
        self.assert_error(self.run_json("decrypt", self.tmp / "b.age", "-o", self.tmp / "x", "-i", alice),
                          5, "wrong_key")
        self.ok("decrypt", self.tmp / "b.age", "-o", self.tmp / "y", "-i", bob)
        self.assertEqual((self.tmp / "y").read_bytes(), self.plain.read_bytes())
        # rekey 到密語
        self.ok("rekey", self.tmp / "b.age", "-o", self.tmp / "c.age", "-i", bob, "--new-passphrase",
                stdin_text="new passphrase for c\n")
        self.ok("decrypt", self.tmp / "c.age", "-o", self.tmp / "z", "--passphrase-stdin",
                stdin_text="new passphrase for c\n")


class OnionTests(CliCase):
    """三層洋蔥，每層都有萬用鎖，每層夾帶旁邊的檔案。"""

    def setUp(self):
        super().setUp()
        for name in ("alice", "bob", "carol", "master"):
            self.identity(name)
        self.set_master(self.pub("master"))
        inner = self.tmp / "secret.txt"
        inner.write_bytes(PLAIN_MARK + b"innermost")
        self.ok("encrypt", inner, "-o", self.tmp / "secret.txt.age", "-r", self.pub("carol"), "--with-master")
        (self.tmp / "side2.txt").write_bytes(b"side two")
        self.ok("encrypt", self.tmp / "secret.txt.age", self.tmp / "side2.txt", "-o", self.tmp / "L2.tar.age",
                "-r", self.pub("bob"), "--with-master")
        (self.tmp / "side1.txt").write_bytes(b"side one")
        self.ok("encrypt", self.tmp / "L2.tar.age", self.tmp / "side1.txt", "-o", self.tmp / "L1.age",
                "-r", self.pub("alice"), "--with-master")

    def test_master_peels_every_layer(self):
        out = self.tmp / "owner"
        data = self.ok("decrypt", self.tmp / "L1.age", "-o", out, "-i", self.tmp / "master.key", "--all-layers")
        self.assertTrue(data["complete"])
        self.assertEqual((data["depth"], data["stopped"]), (3, []))
        self.assertEqual([layer["depth"] for layer in data["layers"]], [1, 2, 3])
        self.assertEqual((out / "side1.txt").read_bytes(), b"side one")
        self.assertEqual((out / "L2" / "side2.txt").read_bytes(), b"side two")
        self.assertEqual((out / "L2" / "secret.txt").read_bytes(), PLAIN_MARK + b"innermost")
        self.assertFalse((out / "L2.tar.age").exists() or (out / "L2" / "secret.txt.age").exists())
        code, text, _ = run("decrypt", self.tmp / "L1.age", "-o", self.tmp / "again", "-i",
                            self.tmp / "master.key", "--all-layers")
        self.assertEqual(code, 0)
        self.assertIn("已經解到底", text)

    def test_someone_with_only_one_layer_key_stops_at_the_right_layer(self):
        out = self.tmp / "alice_view"
        data = self.ok("decrypt", self.tmp / "L1.age", "-o", out, "-i", self.tmp / "alice.key", "--all-layers")
        self.assertFalse(data["complete"])
        self.assertEqual(len(data["stopped"]), 1)
        stop = data["stopped"][0]
        self.assertEqual((stop["depth"], stop["path"], stop["reason"], stop["code"]),
                         (2, "L2.tar.age", "needs_other_key", "wrong_key"))
        self.assertEqual(stop["lock"]["recipient_types"], {"X25519": 2})
        self.assertTrue((out / "L2.tar.age").is_file())      # 解不開的那層原封不動留著
        self.assertEqual((out / "side1.txt").read_bytes(), b"side one")
        code, text, _ = run("decrypt", self.tmp / "L1.age", "-o", self.tmp / "alice2", "-i",
                            self.tmp / "alice.key", "--all-layers")
        self.assertEqual(code, 0)
        self.assertIn("第 2 層需要別的鑰匙", text)
        # 中間那層的人：從 L2 開始，停在 secret.txt.age
        bob = self.ok("decrypt", self.tmp / "L2.tar.age", "-o", self.tmp / "bob_view", "-i",
                      self.tmp / "bob.key", "--all-layers")
        self.assertEqual([(s["depth"], s["path"]) for s in bob["stopped"]], [(2, "secret.txt.age")])
        # 外層解不開就是一般的錯誤
        self.assert_error(self.run_json("decrypt", self.tmp / "L1.age", "-o", self.tmp / "nope", "-i",
                                        self.tmp / "bob.key", "--all-layers"), 5, "wrong_key")

    def test_depth_limit_and_single_file_layers(self):
        # 一個檔案連包三層（每層只有萬用鎖）：結果是同一個名字的檔案
        layer = self.tmp / "deep0"
        layer.write_bytes(b"core")
        for i in range(1, 4):
            nxt = self.tmp / f"deep{i}"
            self.ok("encrypt", layer, "-o", nxt, "--with-master")
            layer = nxt
        out = self.tmp / "core.out"
        data = self.ok("decrypt", layer, "-o", out, "-i", self.tmp / "master.key", "--all-layers")
        self.assertEqual((data["depth"], data["complete"], out.read_bytes()), (3, True, b"core"))
        limited = workflow.decrypt_all_layers(
            layer, self.tmp / "core.limited", workflow.Keyring(age_identities=[self.ids["master"]]),
            max_layers=2)
        self.assertEqual([(s["depth"], s["reason"]) for s in limited["stopped"]], [(3, "depth_limit")])


class KeygenAndInspectTests(CliCase):
    def test_keygen_default_name_format_and_no_secret_in_output(self):
        old = os.getcwd()   # 預設檔名落在工作目錄：切到暫存資料夾
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, old)
        data = self.ok("keygen")
        path = self.tmp / ".decryption_code.env"
        self.assertEqual((data["path"], data["protected"]), (".decryption_code.env", False))
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("# created: "))
        self.assertEqual(lines[1], "# public key: " + data["public_key"])
        self.assertTrue(lines[2].startswith("AGE-SECRET-KEY-1"))
        code, out, _ = run("keygen", "-o", self.tmp / "k2.key")
        self.assertEqual(code, 0)
        self.assertIn("備份", out)
        self.assertNotIn("AGE-SECRET-KEY", out + json.dumps(data))
        self.assert_error(self.run_json("keygen"), 2, "output_exists")
        self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_protected_identity_needs_its_passphrase(self):
        data = self.ok("keygen", "-o", self.tmp / "locked.key", "--protect", stdin_text="identity pass 123\n")
        self.assertTrue(data["protected"])
        locked = self.tmp / "locked.key"
        self.assertTrue(locked.read_bytes().startswith(b"-----BEGIN AGE ENCRYPTED FILE-----"))
        self.assertNotIn(b"AGE-SECRET-KEY", locked.read_bytes())
        self.ok("encrypt", self.plain, "-r", data["public_key"])
        sealed = self.tmp / "notes.txt.age"
        self.ok("decrypt", sealed, "-o", self.tmp / "a.txt", "-i", locked, stdin_text="identity pass 123\n")
        self.assertEqual((self.tmp / "a.txt").read_bytes(), self.plain.read_bytes())
        self.assert_error(self.run_json("decrypt", sealed, "-o", self.tmp / "b.txt", "-i", locked,
                                        stdin_text="wrong\n"), 5, "wrong_key")
        self.assert_error(self.run_json("decrypt", sealed, "-o", self.tmp / "c.txt", "-i", locked),
                          2, "key_missing")
        # 兩個密語：先身分檔、再檔案密語（照文件寫的順序）
        alice = self.identity("alice", passphrase="alice id pass")
        self.ok("encrypt", self.plain, "-o", self.tmp / "p.age", "--passphrase-stdin", stdin_text="file pass\n")
        self.ok("decrypt", self.tmp / "p.age", "-o", self.tmp / "d.txt", "-i", alice, "--passphrase-stdin",
                stdin_text="alice id pass\nfile pass\n")

    def test_check_reports_modes(self):
        data = self.ok("--check")
        self.assertTrue(data["ok"] and data["age_roundtrip"] and data["age_passphrase_roundtrip"])
        self.assertIn("available", data["gpg"])
        self.assertEqual(data["modes"]["age"], True)
        code, out, _ = run("--check")
        self.assertEqual(code, 0)
        self.assertIn("簡單模式", out)
        self.assertTrue(self.ok("--version")["version"])


class Isd2PreviewTests(CliCase):
    """ISD2 預覽格式（已停用）：只能解，不能產生。"""

    def make_isd2(self, material, name="old.isd2"):
        path = self.tmp / name
        ops.encrypt_path(self.plain, path, material, scrypt_log_n=10)
        return path

    def test_preview_files_still_decrypt(self):
        keyfile = self.tmp / "old.env"
        keys.generate_key_file(keyfile)
        sealed = self.make_isd2(keys.load_key_file(keyfile))
        info = self.ok("inspect", sealed)
        self.assertEqual((info["format"], info["deprecated"]), ("isd2-preview", True))
        data = self.ok("decrypt", sealed, "-o", self.tmp / "a.txt", "--key-file", keyfile)
        self.assertEqual((data["format"], data["deprecated"]), ("isd2-preview", True))
        self.assertEqual((self.tmp / "a.txt").read_bytes(), self.plain.read_bytes())
        code, out, _ = run("decrypt", sealed, "-o", self.tmp / "b.txt", "--key-file", keyfile)
        self.assertIn("已停用", out)
        pw = self.make_isd2(keys.passphrase_material("old preview pass"), "pw.isd2")
        self.ok("decrypt", pw, "-o", self.tmp / "c.txt", "--passphrase-stdin", stdin_text="old preview pass\n")
        self.assert_error(self.run_json("decrypt", sealed, "-o", self.tmp / "d.txt"), 2, "key_missing")
        self.assert_error(self.run_json("rewrap", sealed, "-o", self.tmp / "e", "--key-file", keyfile,
                                        "-r", agefmt.generate_identity().public_key), 2, "bad_input")

    def test_there_is_no_way_to_produce_the_preview_format(self):
        parser = cli.build_parser()
        enc = parser._subparsers._group_actions[0].choices["encrypt"]
        options = {o for a in enc._actions for o in a.option_strings}
        for gone in ("--key-file", "--key-env", "--cipher", "--key-name"):
            self.assertNotIn(gone, options)
        gen = parser._subparsers._group_actions[0].choices["keygen"]
        self.assertNotIn("--format", {o for a in gen._actions for o in a.option_strings})
        self.assertNotIn("isd2", workflow.MODES)


class SecretHandlingTests(CliCase):
    def test_there_is_no_way_to_pass_a_passphrase_as_an_argument(self):
        parser = cli.build_parser()
        for sub, sp in parser._subparsers._group_actions[0].choices.items():
            for action in sp._actions:
                if any("passphrase" in o for o in action.option_strings):
                    self.assertEqual(action.nargs, 0, (sub, action.option_strings))   # 都是開關，不收值
        for argv in (["encrypt", "x", "--passphrase=hunter2"],
                     ["encrypt", "x", "--passphrase-stdin=hunter2"],
                     ["decrypt", "x", "--passphrase", "hunter2"],
                     ["keygen", "--protect=hunter2"],
                     ["rekey", "x", "-o", "y", "--new-passphrase", "hunter2"]):
            code, body = self.run_json(*argv)
            self.assertEqual(code, 2)
            self.assertNotIn("hunter2", json.dumps(body))   # 誤放的密語不會被轉述回去
            code, out, err = run(*argv)
            self.assertNotIn("hunter2", out + err)

    def test_nothing_secret_is_ever_printed(self):
        """把各種成功與失敗的輸出全部收集起來，裡面不可以出現私鑰、密語或明文。"""
        tmp, plain = self.tmp, self.plain
        alice = self.identity("alice")
        bob = self.identity("bob")
        locked = self.identity("locked", passphrase="identity-secret-7781")
        master = self.identity("master")
        self.set_master(self.pub("master"))
        passphrase = "correct-horse-battery-staple-9431"
        captured = []

        def both(*argv, stdin_text=""):
            for extra in ([], ["--json"]):
                captured.extend(run(*argv, *extra, stdin_text=stdin_text)[1:])

        both("encrypt", plain, "-r", self.pub("alice"), "--with-master", "--force")
        sealed = tmp / "notes.txt.age"
        both("inspect", sealed)
        both("decrypt", sealed, "-o", tmp / "d1", "-i", alice, "--force")
        both("decrypt", sealed, "-o", tmp / "d2", "-i", bob)
        both("decrypt", sealed, "-o", tmp / "d3", "-i", locked, stdin_text="identity-secret-7781\n")
        both("decrypt", sealed, "-o", tmp / "d4", "-i", locked, stdin_text="wrong-identity-secret\n")
        both("encrypt", plain, "-o", tmp / "p.age", "--passphrase-stdin", "--force", stdin_text=passphrase + "\n")
        both("decrypt", tmp / "p.age", "-o", tmp / "d5", "--passphrase-stdin", stdin_text="wrong-" + passphrase + "\n")
        both("decrypt", tmp / "p.age", "-o", tmp / "d6", "--passphrase-stdin", "--force",
             stdin_text=passphrase + "\n")
        both("rewrap", sealed, "-o", tmp / "r.age", "-i", master, "-r", self.pub("bob"), "--force")
        both("rekey", sealed, "-o", tmp / "k.age", "-i", master, "--new-passphrase", "--force",
             stdin_text=passphrase + "\n")
        both("decrypt", tmp / "r.age", "-o", tmp / "d7", "-i", master, "--all-layers", "--force")
        both("keygen", "-o", tmp / "fresh.key", "--force")
        both("keygen", "-o", tmp / "fresh2.key", "--protect", "--force", stdin_text=passphrase + "\n")
        bad = tmp / "bad.key"
        bad.write_text("AGE-SECRET-KEY-1SECRETISHVALUETHATISNOTVALID\n", encoding="ascii")
        both("decrypt", sealed, "-o", tmp / "d8", "-i", bad)
        both("--check")

        everything = "\n".join(captured)
        self.assertGreater(len(everything), 2000)
        forbidden = [i.secret_key_string() for i in self.ids.values()]
        forbidden += [agefmt.load_identity_file(tmp / "fresh.key")[0].secret_key_string(),
                      passphrase, "identity-secret-7781", "wrong-identity-secret",
                      PLAIN_MARK.decode(), "SECRETISHVALUE"]
        for item in forbidden:
            self.assertNotIn(item, everything)

    def test_unexpected_error_reports_type_only(self):
        self.identity("alice")

        def boom(*_args, **_kwargs):
            raise RuntimeError("message with SECRET-DETAIL inside")
        self.patch(workflow, "encrypt", boom)
        result = self.run_json("encrypt", self.plain, "-r", self.pub("alice"))
        self.assert_error(result, 1, "internal_bug")
        self.assertEqual(result[1]["error"]["detail"], "RuntimeError")
        self.assertNotIn("SECRET-DETAIL", json.dumps(result[1]))


class SubprocessTests(CliCase):
    """真的開子行程（用頂層的 sealed／agefmt 載入，跟視窗程式一樣）。"""

    def spawn(self, args, env=None, **kwargs):
        full_env = dict(os.environ, PYTHONUTF8="1")
        full_env.update(env or {})
        kwargs.setdefault("cwd", TOOL_DIR)
        return subprocess.run([sys.executable, *map(str, args)], env=full_env,
                              capture_output=True, timeout=120, **kwargs)

    def test_module_entry_roundtrip_and_isd2_key_from_environment(self):
        alice = self.identity("alice")
        done = self.spawn(["-m", "crypto_tool", "encrypt", self.plain, "-r", self.pub("alice"), "--json"])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(json.loads(done.stdout)["ok"])
        out = self.tmp / "o.txt"
        done = self.spawn(["-m", "crypto_tool", "decrypt", self.tmp / "notes.txt.age", "-o", out,
                           "-i", alice, "--json"])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(out.read_bytes(), self.plain.read_bytes())
        # ISD2 預覽格式的舊檔：--key-env 只剩解密用
        key_hex = os.urandom(32).hex()
        old = self.tmp / "old.isd2"
        ops.encrypt_path(self.plain, old, KeyMaterial(raw=bytes.fromhex(key_hex)))
        done = self.spawn(["-m", "crypto_tool", "decrypt", old, "-o", self.tmp / "o2.txt",
                           "--key-env", "CRYPTO_TOOL_TEST_KEY", "--json"], env={"CRYPTO_TOOL_TEST_KEY": key_hex})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn(key_hex.encode(), done.stdout + done.stderr)
        done = self.spawn(["-m", "crypto_tool", "decrypt", old, "-o", self.tmp / "o3.txt",
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
        done = self.spawn([package, "decrypt", self.tmp / "notes.txt.age", "-o", out, "--passphrase-stdin"],
                          input=piped, cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(out.read_bytes(), self.plain.read_bytes())

    def test_gui_entry_script_dispatches_to_cli(self):
        """run.bat 會執行 GUI__Encrypter.py 並把參數傳給它；帶參數時要走命令列，不開視窗。"""
        entry = TOOL_DIR / "crypto_tool" / "GUI__Encrypter.py"
        done = self.spawn([entry, "inspect", self.tmp / "nope.age", "--json"])
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertEqual(json.loads(done.stdout)["error"]["code"], "input_missing")
        done = self.spawn([entry, "--check", "--json"])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(json.loads(done.stdout)["data"]["age_roundtrip"])

    def test_cli_does_not_import_gui_or_legacy_crypto(self):
        done = self.spawn(["-c", "import sys; sys.argv=['x','inspect','nope','--json'];"
                                 "import runpy\n"
                                 "try:\n runpy.run_module('crypto_tool', run_name='__main__')\n"
                                 "except SystemExit: pass\n"
                                 "bad=[m for m in sys.modules if m.split('.')[0] in "
                                 "('tkinter','ttkbootstrap','tkinterdnd2','Crypto')]\n"
                                 "print('LOADED', bad)"])
        self.assertIn(b"LOADED []", done.stdout, done.stdout + done.stderr)


class PgpModeCliTests(CliCase):
    """PGP 模式（實際呼叫 gpg；找不到就略過）。每次操作都用暫時的 GNUPGHOME，不碰任何金鑰環。"""

    @classmethod
    def setUpClass(cls):
        try:
            pgpmode.find_gpg()
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"找不到可用的 gpg：{type(exc).__name__}")

    def test_pgp_keygen_recipients_master_passphrase_inspect_and_rekey(self):
        tmp = self.tmp
        user = self.ok("keygen", "--mode", "pgp", "-o", tmp / "user", "--name", "Test User",
                       "--email", "user@example.invalid")
        self.assertEqual((user["mode"], user["protected"]), ("pgp", False))
        self.assertTrue(Path(user["public_key"]).is_file() and Path(user["secret_key"]).is_file())
        master = self.ok("keygen", "--mode", "pgp", "-o", tmp / "master", "--name", "Test Master",
                         "--protect", stdin_text="master key pass\n")
        self.assertTrue(master["protected"])
        settings.set_value(settings.MASTER_PGP_KEY, master["public_key"])

        data = self.ok("encrypt", self.plain, "--mode", "pgp", "--pgp-recipient", user["public_key"],
                       "--with-master", "--passphrase-stdin", stdin_text="shared file pass\n")
        sealed = tmp / "notes.txt.gpg"
        self.assertEqual((data["format"], data["output"]), ("openpgp", str(sealed)))
        self.assertEqual(data["recipients"], {"keys": 2, "passphrase": True, "master": True})
        info = self.ok("inspect", sealed)
        self.assertEqual((info["format"], info["recipient_count"], info["has_passphrase"]), ("openpgp", 2, True))

        # -i 認得 OpenPGP 私鑰；萬用鎖私鑰有密語
        self.ok("decrypt", sealed, "-o", tmp / "u.txt", "-i", user["secret_key"])
        self.assertEqual((tmp / "u.txt").read_bytes(), self.plain.read_bytes())
        self.ok("decrypt", sealed, "-o", tmp / "m.txt", "--pgp-secret", master["secret_key"],
                "--pgp-key-passphrase", stdin_text="master key pass\n")
        self.ok("decrypt", sealed, "-o", tmp / "p.txt", "--passphrase-stdin", stdin_text="shared file pass\n")
        self.assert_error(self.run_json("decrypt", sealed, "-o", tmp / "w.txt", "--passphrase-stdin",
                                        stdin_text="not it\n"), 5, "wrong_key")
        self.assert_error(self.run_json("rewrap", sealed, "-o", tmp / "r.gpg", "-i", user["secret_key"],
                                        "-r", agefmt.generate_identity().public_key), 2, "unsupported_format")
        # rekey：只剩萬用鎖
        self.ok("rekey", sealed, "-o", tmp / "k.asc", "-i", user["secret_key"], "--with-master", "--armor")
        self.assertTrue((tmp / "k.asc").read_bytes().startswith(b"-----BEGIN PGP MESSAGE-----"))
        self.assert_error(self.run_json("decrypt", tmp / "k.asc", "-o", tmp / "k1.txt", "-i", user["secret_key"]),
                          5, "wrong_key")
        self.ok("decrypt", tmp / "k.asc", "-o", tmp / "k2.txt", "-i", master["secret_key"],
                "--pgp-key-passphrase", stdin_text="master key pass\n")
        self.assertEqual((tmp / "k2.txt").read_bytes(), self.plain.read_bytes())
        # 公鑰不能拿來解密；私鑰檔內容不會出現在輸出
        self.assert_error(self.run_json("decrypt", sealed, "-o", tmp / "x.txt", "-i", user["public_key"]),
                          2, "bad_key_format")


if __name__ == "__main__":
    unittest.main()
