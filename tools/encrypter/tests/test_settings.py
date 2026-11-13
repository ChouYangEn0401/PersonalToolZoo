"""設定（.env）：讀哪個檔、環境變數優先、相對路徑、只改一行、不收私鑰。"""

import os
from unittest import mock

from _support import Case

from crypto_tool.sealed import settings

AGE_PUB = "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p"   # age 規格裡的範例公鑰


class SettingsTests(Case):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"TOOLZOO_DATA_DIR": str(self.tmp)})
        env.start()
        self.addCleanup(env.stop)
        for name in settings.KEYS:
            os.environ.pop(name, None)
        self.env = self.tmp / ".env"

    def test_env_file_location_and_placeholders(self):
        self.assertEqual(settings.env_files(), [self.env])
        self.assertEqual(settings.master_recipients(), [])
        self.env.write_text(f"OTHER_TOOL_KEY=sk-123\n{settings.MASTER_RECIPIENT}=age1......\n", encoding="utf-8")
        self.assertEqual(settings.master_recipients(), [])          # 範本佔位不算
        self.env.write_text(f'export {settings.MASTER_RECIPIENT}="{AGE_PUB}"\n', encoding="utf-8")
        self.assertEqual(settings.master_recipients(), [AGE_PUB])
        with mock.patch.dict(os.environ, {settings.MASTER_RECIPIENT: "age1fromenv"}):
            self.assertEqual(settings.master_recipients(), ["age1fromenv"])   # 環境變數優先

    def test_several_master_locks_in_one_setting(self):
        other = "age1zvkyg2lqzraa2lnjvqej32nkuu0ues2s82hzrye869xeexvn73equnujwj"   # 另一個格式正確的公鑰字串
        self.env.write_text(f"{settings.MASTER_RECIPIENT}={AGE_PUB}, {other} ,{AGE_PUB}\n", encoding="utf-8")
        self.assertEqual(settings.master_recipients(), [AGE_PUB, other])        # 逗號分開、重複只算一次
        with mock.patch.dict(os.environ, {settings.MASTER_RECIPIENT: f"{other}\n{AGE_PUB}"}):
            self.assertEqual(settings.master_recipients(), [other, AGE_PUB])    # 環境變數可以用換行
        self.env.write_text(f"{settings.MASTER_PGP_KEY}=keys/a b.asc; {self.tmp / 'c,d.asc'}\n", encoding="utf-8")
        self.assertEqual(settings.master_pgp_keys(), [self.tmp / "keys" / "a b.asc", self.tmp / "c,d.asc"])
        self.assertEqual(settings.describe()[settings.MASTER_PGP_KEY]["count"], 2)

    def test_relative_paths_resolve_next_to_the_env_file(self):
        self.env.write_text(f"{settings.IDENTITY_FILE}=keys/me.key\n", encoding="utf-8")
        self.assertEqual(settings.identity_file(), self.tmp / "keys" / "me.key")
        absolute = self.tmp / "elsewhere.key"
        self.env.write_text(f"{settings.IDENTITY_FILE}={absolute}\n", encoding="utf-8")
        self.assertEqual(settings.identity_file(), absolute)

    def test_set_value_changes_one_line_and_keeps_the_rest(self):
        self.env.write_text("# comment\nOTHER_TOOL_KEY=keep-me\n"
                            f"{settings.MASTER_RECIPIENT}=age1old\nLAST=1\n", encoding="utf-8")
        path = settings.set_value(settings.MASTER_RECIPIENT, AGE_PUB)
        self.assertEqual(path, self.env)
        self.assertEqual(self.env.read_text(encoding="utf-8"),
                         f"# comment\nOTHER_TOOL_KEY=keep-me\n{settings.MASTER_RECIPIENT}={AGE_PUB}\nLAST=1\n")
        settings.set_value(settings.IDENTITY_FILE, "C:/keys/me.key")
        self.assertTrue(self.env.read_text(encoding="utf-8").endswith(f"{settings.IDENTITY_FILE}=C:/keys/me.key\n"))
        settings.set_value(settings.MASTER_RECIPIENT, "")
        self.assertNotIn(settings.MASTER_RECIPIENT, self.env.read_text(encoding="utf-8"))
        self.assertIn("OTHER_TOOL_KEY=keep-me", self.env.read_text(encoding="utf-8"))
        self.assertEqual([p.name for p in self.tmp.iterdir() if "partial" in p.name], [])

    def test_private_keys_are_refused(self):
        secret = "AGE-SECRET-KEY-1QYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGP"
        self.assertEqual(self.code_of(settings.set_value, settings.MASTER_RECIPIENT, secret), "bad_key_format")
        self.assertEqual(self.code_of(settings.set_value, "SOMETHING_ELSE", "x"), "bad_input")
        self.assertEqual(self.code_of(settings.set_value, settings.IDENTITY_FILE, "a\nb"), "bad_input")
        self.env.write_text(f"{settings.MASTER_RECIPIENT}={secret}\n", encoding="utf-8")
        with self.assertRaises(settings.SealError) as caught:
            settings.master_recipients()
        self.assertNotIn(secret, str(caught.exception.to_dict()))
        self.assertEqual(settings.describe()[settings.MASTER_RECIPIENT], {"set": True, "valid": False})

    def test_load_into_environ_only_takes_this_tools_keys(self):
        self.env.write_text(f"OTHER_TOOL_KEY=sk-should-not-load\n{settings.MASTER_RECIPIENT}={AGE_PUB}\n"
                            "ENCRYPTER_GPG=C:/gpg/gpg.exe\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {}):
            os.environ.pop("OTHER_TOOL_KEY", None)
            os.environ.pop("ENCRYPTER_GPG", None)
            settings.load_into_environ()
            self.assertNotIn("OTHER_TOOL_KEY", os.environ)
            self.assertEqual(os.environ["ENCRYPTER_GPG"], "C:/gpg/gpg.exe")
            self.assertEqual(os.environ[settings.MASTER_RECIPIENT], AGE_PUB)
