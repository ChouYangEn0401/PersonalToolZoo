"""toolzoo.appdirs：資料與 .env 放在工具旁邊，不寫到使用者資料夾。

用暫存資料夾假造一個 repo，模擬「從原始碼執行」「exe 在 repo 的 dist\\ 裡」「exe 被拿到 repo 外」三種情況。
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolzoo import appdirs  # noqa: E402
from toolzoo.ai import keys  # noqa: E402


class AppDirsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "scripts" / "tool.spec").write_text("# marker", encoding="utf-8")
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("TOOLZOO_DATA_DIR", None)
        appdirs.loaded_from.clear()

    def frozen(self, exe: Path):
        exe.parent.mkdir(parents=True, exist_ok=True)
        patches = [mock.patch.object(sys, "frozen", True, create=True),
                   mock.patch.object(sys, "executable", str(exe))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_source_run_uses_the_tool_folder_and_repo_env(self):
        with mock.patch.object(appdirs, "_source_repo", return_value=self.repo):
            self.assertEqual(appdirs.tool_data_dir("video-notes"), self.repo / "tools" / "video-notes" / "data")
            self.assertEqual(appdirs.env_files(), [self.repo / ".env"])
            self.assertEqual(appdirs.env_file(), self.repo / ".env")

    def test_exe_inside_repo_reads_its_own_env_then_the_repo_env(self):
        exe = self.repo / "dist" / "video-notes" / "VideoNotes(v2.0.0).exe"
        self.frozen(exe)
        self.assertEqual(appdirs.tool_data_dir("video-notes"), exe.parent / "data")
        self.assertEqual(appdirs.env_files(), [exe.parent / ".env", self.repo / ".env"])
        self.assertEqual(appdirs.env_file(), self.repo / ".env")

    def test_exe_outside_repo_keeps_everything_next_to_itself(self):
        exe = self.base / "Desktop" / "tools" / "HashMyFile.exe"
        self.frozen(exe)
        self.assertIsNone(appdirs.repo_root())
        self.assertEqual(appdirs.tool_data_dir("hash-my-file"), exe.parent / "data")
        self.assertEqual(appdirs.env_files(), [exe.parent / ".env"])
        self.assertEqual(appdirs.env_file(), exe.parent / ".env")

    def test_override_moves_data_and_env(self):
        os.environ["TOOLZOO_DATA_DIR"] = str(self.base / "sandbox")
        self.assertEqual(appdirs.tool_data_dir("x"), self.base / "sandbox" / "x")
        self.assertEqual(appdirs.env_files(), [self.base / "sandbox" / ".env"])

    def test_load_env_skips_placeholders_and_existing_variables(self):
        os.environ["TOOLZOO_DATA_DIR"] = str(self.base / "sandbox")
        env = appdirs.env_file()
        env.write_text("A_PARAM=1\nOPENAI_API_KEY=sk-proj-......\nKEEP=from-file\n# comment\n", encoding="utf-8")
        os.environ["KEEP"] = "from-environment"
        os.environ.pop("A_PARAM", None)
        os.environ.pop("OPENAI_API_KEY", None)
        loaded = appdirs.load_env()
        self.assertEqual(os.environ["A_PARAM"], "1")
        self.assertNotIn("OPENAI_API_KEY", os.environ)
        self.assertEqual(os.environ["KEEP"], "from-environment")
        self.assertEqual(loaded, {"A_PARAM": env})

    def test_key_loaded_from_env_file_reports_the_file(self):
        os.environ["TOOLZOO_DATA_DIR"] = str(self.base / "sandbox")
        for names in keys.KEY_NAMES.values():
            for name in names:
                os.environ.pop(name, None)
        appdirs.env_file().write_text("OPENAI_API_KEY=sk-real-value\n", encoding="utf-8")
        appdirs.load_env()
        self.assertEqual(keys.find_key("openai"), ("sk-real-value", str(appdirs.env_file())))


if __name__ == "__main__":
    unittest.main()
