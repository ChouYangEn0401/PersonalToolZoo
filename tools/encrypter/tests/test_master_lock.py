"""萬用鎖的四個問題，各用測試證明（README「萬用鎖」一節的依據）：

1. 能不能同時綁**好幾把**萬用鎖（兩台電腦各一把、主＋備）？——可以：設定用逗號分開，或命令列重複 ``--master``；
   每一把都能單獨打開，其他人的鑰匙也照樣能開。
2. 擁有者能不能**自己生成很多把**萬用鎖？——可以：``keygen`` 每次產生一把新的，可以 ``--protect`` 用密語保護私鑰。
3. **自訂密碼的萬用鎖**：簡單模式（age 規格）密語必須是唯一的鎖，所以改用「密語保護的身分檔」當萬用鎖；
   PGP 模式可以真的在同一個檔案上放「別人的公鑰＋擁有者自訂的密語」（要系統有 gpg，找不到就略過）。
4. 加萬用鎖會不會讓檔案變兩倍？——不會：1 MiB 的檔案，每多一把鎖只多一小段固定大小的標頭。

全部離線；金鑰都是測試時臨時產生的；設定用 TOOLZOO_DATA_DIR 導到暫存資料夾。
"""

import unittest

from test_sealed_cli import CliCase

from crypto_tool import agefmt, pgpmode
from crypto_tool.gui import logic
from crypto_tool.sealed import settings

MiB = 1024 * 1024


class SeveralMasterLocksTests(CliCase):
    def test_two_master_locks_from_settings_each_open_the_file_alone(self):
        alice = self.identity("alice")
        laptop = self.identity("laptop")
        desktop = self.identity("desktop")
        self.set_master(f"{self.pub('laptop')}, {self.pub('desktop')}")
        data = self.ok("encrypt", self.plain, "-r", self.pub("alice"), "--with-master")
        self.assertEqual(data["recipients"], {"keys": 3, "passphrase": False, "master": True, "masters": 2})
        sealed = self.tmp / "notes.txt.age"
        self.assertEqual(self.ok("inspect", sealed)["stanza_counts"], {"X25519": 3})
        for name, key in (("alice", alice), ("laptop", laptop), ("desktop", desktop)):
            with self.subTest(key=name):
                back = self.ok("decrypt", sealed, "-o", self.tmp / f"{name}.txt", "-i", key)
                self.assertEqual((self.tmp / f"{name}.txt").read_bytes(), self.plain.read_bytes())
                self.assertEqual(back["used_master"], name != "alice")
        # 其中一把格式不對：整個停下，不會悄悄少一把
        self.set_master(f"{self.pub('laptop')}, age1notvalid")
        self.assert_error(self.run_json("encrypt", self.plain, "-o", self.tmp / "x.age", "--with-master"),
                          2, "bad_key_format")
        self.assertFalse((self.tmp / "x.age").exists())

    def test_repeated_master_option_without_any_settings(self):
        self.identity("alice")
        main = self.identity("main")
        spare = self.identity("spare")
        listing = self.tmp / "spare.pub"                       # --master 也接受公鑰清單檔
        listing.write_text(self.pub("spare") + "\n", encoding="utf-8")
        data = self.ok("encrypt", self.plain, "-o", self.tmp / "a.age", "-r", self.pub("alice"),
                       "--master", self.pub("main"), "--master", listing, "--master", self.pub("main"))
        self.assertEqual(data["recipients"], {"keys": 3, "passphrase": False, "master": True, "masters": 2})
        for name, key in (("main", main), ("spare", spare)):
            with self.subTest(key=name):
                self.ok("decrypt", self.tmp / "a.age", "-o", self.tmp / f"{name}.txt", "-i", key)
                self.assertEqual((self.tmp / f"{name}.txt").read_bytes(), self.plain.read_bytes())
        # 設定的＋這次指定的：合在一起，重複的只算一次
        self.set_master(self.pub("main"))
        data = self.ok("encrypt", self.plain, "-o", self.tmp / "b.age", "--with-master", "--master", self.pub("spare"),
                       "--master", self.pub("main"))
        self.assertEqual(data["recipients"]["masters"], 2)
        self.assertEqual(self.ok("inspect", self.tmp / "b.age")["stanza_counts"], {"X25519": 2})
        # 簡單模式的萬用鎖跟密語不能並存（age 規格）；PGP 模式不收 age1 公鑰
        self.assert_error(self.run_json("encrypt", self.plain, "-o", self.tmp / "c.age", "--master", self.pub("main"),
                                        "--passphrase-stdin", stdin_text="whatever passphrase\n"), 2, "bad_input")
        self.assert_error(self.run_json("encrypt", self.plain, "--mode", "pgp", "--master", self.pub("main")),
                          2, "bad_input")

    def test_rewrap_can_add_a_second_master_later(self):
        alice = self.identity("alice")
        old_master = self.identity("old_master")
        new_master = self.identity("new_master")
        self.ok("encrypt", self.plain, "-o", self.tmp / "a.age", "-r", self.pub("alice"),
                "--master", self.pub("old_master"))
        self.ok("rewrap", self.tmp / "a.age", "-o", self.tmp / "b.age", "-i", old_master, "-r", self.pub("alice"),
                "--master", self.pub("old_master"), "--master", self.pub("new_master"))
        for key in (alice, old_master, new_master):
            with self.subTest(key=key.name):
                self.ok("decrypt", self.tmp / "b.age", "-o", self.tmp / f"{key.stem}.txt", "-i", key)


class MakeYourOwnMasterLocksTests(CliCase):
    def test_keygen_makes_a_new_key_every_time(self):
        publics = set()
        for i in range(5):
            data = self.ok("keygen", "-o", self.tmp / f"master{i}.key")
            self.assertTrue(data["public_key"].startswith("age1"))
            publics.add(data["public_key"])
        self.assertEqual(len(publics), 5)
        # 不小心再產生到同一個檔名：不覆蓋（舊的萬用鎖不會被弄丟）
        before = (self.tmp / "master0.key").read_bytes()
        self.assert_error(self.run_json("keygen", "-o", self.tmp / "master0.key"), 2, "output_exists")
        self.assertEqual((self.tmp / "master0.key").read_bytes(), before)

    def test_passphrase_protected_identity_works_as_a_custom_password_master_lock(self):
        """簡單模式要「自訂密碼的萬用鎖」：用密語保護的身分檔當萬用鎖（age 標準做法，age -d -i 也認得）。"""
        self.identity("alice")
        data = self.ok("keygen", "-o", self.tmp / "master.key", "--protect",
                       stdin_text="my own master password\n")
        self.assertTrue(data["protected"])
        blob = (self.tmp / "master.key").read_bytes()
        self.assertTrue(agefmt.is_encrypted_identity_file(blob))
        self.assertNotIn(b"AGE-SECRET-KEY-", blob.upper())          # 私鑰本身不以明文出現在檔案裡
        self.ok("encrypt", self.plain, "-o", self.tmp / "a.age", "-r", self.pub("alice"),
                "--master", data["public_key"])
        self.ok("decrypt", self.tmp / "a.age", "-o", self.tmp / "m.txt", "-i", self.tmp / "master.key",
                stdin_text="my own master password\n")
        self.assertEqual((self.tmp / "m.txt").read_bytes(), self.plain.read_bytes())
        self.assert_error(self.run_json("decrypt", self.tmp / "a.age", "-o", self.tmp / "w.txt",
                                        "-i", self.tmp / "master.key", stdin_text="wrong password\n"),
                          5, "wrong_key")
        self.assertFalse((self.tmp / "w.txt").exists())


class SizeOverheadTests(CliCase):
    def test_master_locks_add_a_small_fixed_header_not_a_second_copy(self):
        """1 MiB 的檔案：每多一把 age 鎖固定多一段約 100 bytes 的標頭，內容只加密一次。"""
        self.plain.write_bytes(bytes(range(256)) * (MiB // 256))
        self.identity("alice")
        for name in ("m1", "m2", "m3"):
            self.identity(name)
        sizes = []
        for n in range(4):
            masters = [x for name in ("m1", "m2", "m3")[:n] for x in ("--master", self.pub(name))]
            out = self.tmp / f"n{n}.age"
            data = self.ok("encrypt", self.plain, "-o", out, "-r", self.pub("alice"), *masters)
            self.assertEqual((data["bytes_in"], data["bytes_out"]), (MiB, out.stat().st_size))
            sizes.append(out.stat().st_size)
        steps = {b - a for a, b in zip(sizes, sizes[1:])}
        self.assertEqual(len(steps), 1, sizes)                 # 每多一把鎖，增加的量都一樣
        self.assertLess(steps.pop(), 200)
        self.assertLess(sizes[0] - MiB, 1024 * 1.01)           # 原本的額外量（標頭＋每 64 KiB 16 bytes 的驗證碼）
        self.assertLess(sizes[-1], MiB * 1.01)                 # 三把萬用鎖之後也遠小於兩倍


class GuiMasterSettingsTests(CliCase):
    def test_keys_tab_saves_and_shows_several_master_locks(self):
        first = self.identity("first")
        self.identity("second")
        text = f"{self.pub('first')}，{self.pub('second')}"          # 全形逗號也可以
        message = logic.save_master(text, "")
        self.assertEqual(message.kind, "success")
        self.assertEqual(settings.master_recipients(), [self.pub("first"), self.pub("second")])
        self.assertEqual(logic.master_for(logic.MODE_AGE), f"{self.pub('first')}, {self.pub('second')}")
        self.assertTrue(logic.master_summary(logic.MODE_AGE).startswith("2 "))
        # 「從身分檔讀…」接在後面，不是取代；重複的不加
        self.assertEqual(logic.add_master_value(self.pub("first"), logic.public_key_from_identity(str(first))),
                         self.pub("first"))
        self.assertEqual(logic.add_master_value("", self.pub("second")), self.pub("second"))
        # 一把不對：整個不寫
        self.assertEqual(logic.save_master(f"{self.pub('first')}, age1bad", "").code, "bad_key_format")
        self.assertEqual(len(settings.master_recipients()), 2)


class PgpCustomPasswordMasterTests(CliCase):
    """PGP 模式：同一個檔案，別人用自己的私鑰開、擁有者用自己訂的密語開（實際呼叫 gpg；找不到就略過）。"""

    @classmethod
    def setUpClass(cls):
        try:
            pgpmode.find_gpg()
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"找不到可用的 gpg：{type(exc).__name__}")

    def test_someone_elses_public_key_plus_owner_password_and_two_pgp_masters(self):
        tmp = self.tmp
        bob = self.ok("keygen", "--mode", "pgp", "-o", tmp / "bob", "--name", "Test Bob")
        m1 = self.ok("keygen", "--mode", "pgp", "-o", tmp / "m1", "--name", "Test Master One")
        m2 = self.ok("keygen", "--mode", "pgp", "-o", tmp / "m2", "--name", "Test Master Two")
        self.plain.write_bytes(bytes(range(256)) * (MiB // 256))
        plain_only = self.ok("encrypt", self.plain, "--mode", "pgp", "-o", tmp / "base.gpg",
                             "--pgp-recipient", bob["public_key"])
        data = self.ok("encrypt", self.plain, "--mode", "pgp", "-o", tmp / "all.gpg",
                       "--pgp-recipient", bob["public_key"], "--master", m1["public_key"],
                       "--master", m2["public_key"], "--passphrase-stdin",
                       stdin_text="owner custom password\n")
        self.assertEqual(data["recipients"], {"keys": 3, "passphrase": True, "master": True, "masters": 2})
        info = self.ok("inspect", tmp / "all.gpg")
        self.assertEqual((info["recipient_count"], info["has_passphrase"]), (3, True))
        # 檔案沒有變兩倍：三把公鑰＋一個密語只多幾百 bytes
        extra = (tmp / "all.gpg").stat().st_size - (tmp / "base.gpg").stat().st_size
        self.assertLess(extra, 2048, (plain_only.get("bytes_out"), data.get("bytes_out")))
        opened = {
            "bob": ("-i", bob["secret_key"]),
            "m1": ("-i", m1["secret_key"]),
            "m2": ("-i", m2["secret_key"]),
        }
        for name, args in opened.items():
            with self.subTest(key=name):
                self.ok("decrypt", tmp / "all.gpg", "-o", tmp / f"{name}.bin", *args)
                self.assertEqual((tmp / f"{name}.bin").read_bytes(), self.plain.read_bytes())
        self.ok("decrypt", tmp / "all.gpg", "-o", tmp / "pw.bin", "--passphrase-stdin",
                stdin_text="owner custom password\n")
        self.assertEqual((tmp / "pw.bin").read_bytes(), self.plain.read_bytes())
        self.assert_error(self.run_json("decrypt", tmp / "all.gpg", "-o", tmp / "no.bin", "--passphrase-stdin",
                                        stdin_text="not the password\n"), 5, "wrong_key")
        # 設定也可以放好幾個 PGP 萬用鎖公鑰檔（用分號分開）
        settings.set_value(settings.MASTER_PGP_KEY, f"{m1['public_key']}; {m2['public_key']}")
        data = self.ok("encrypt", self.plain, "--mode", "pgp", "-o", tmp / "cfg.gpg",
                       "--pgp-recipient", bob["public_key"], "--with-master")
        self.assertEqual(data["recipients"]["masters"], 2)
        self.ok("decrypt", tmp / "cfg.gpg", "-o", tmp / "cfg2.bin", "-i", m2["secret_key"])


if __name__ == "__main__":
    unittest.main()
