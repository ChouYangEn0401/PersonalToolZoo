"""畫面（main.py）走一遍：加資料夾 → 規則 → 預覽 → 套用 → 關掉重開還能復原 → 規則組。

資料夾用 TOOLZOO_DATA_DIR 隔離，不會碰到工具真正的 data\\。
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

DATA = tempfile.mkdtemp(prefix="file-renamer-test-")
os.environ["TOOLZOO_DATA_DIR"] = DATA      # 必須在 import main 之前


def tearDownModule():
    shutil.rmtree(DATA, ignore_errors=True)   # 測試完把隔離用的資料夾清掉，不在 %TEMP% 留東西
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tkinterdnd2 import TkinterDnD  # noqa: E402

import main  # noqa: E402
from renamer import MODE_NAME_HASH, Rule  # noqa: E402


class GuiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        for name in ("[1080p] 影集 S01E01.mp4", "sub/[720p] 影集 S01E02.mkv", "readme.txt"):
            p = self.dir / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(name.encode("utf-8"))
        for f in (main.SETTINGS_FILE, main.PRESETS_FILE, main.LAST_BATCH_FILE):
            if f.exists():
                f.unlink()

    def new_app(self):
        root = TkinterDnD.Tk()
        root.withdraw()

        def cleanup():
            try:
                root.destroy()
            except Exception:  # noqa: BLE001 — app.close() 已經關掉了
                pass

        self.addCleanup(cleanup)
        return main.FileRenamerApp(root, confirm=lambda *a, **k: True)

    def files(self):
        return sorted(str(p.relative_to(self.dir)) for p in self.dir.rglob("*") if p.is_file())

    def test_folder_rules_apply_and_undo_after_restart(self):
        self.assertTrue(str(main.DATA).startswith(DATA))
        app = self.new_app()
        app.recursive.set(True)
        app.name_filter.set("*.mp4;*.mkv")
        app.add_paths([str(self.dir)])
        self.assertEqual(len(app.paths), 2)                      # readme.txt 被篩掉

        app.rules = [Rule(r"\[(1080p|720p)\]\s*", ""), Rule(r"S(\d+)E(\d+)", "第$1季第$2集")]
        app._show_rules(select=0)
        app.refresh()
        self.assertEqual(sorted(r.new_name for r in app.rows), ["影集 第01季第01集.mp4", "影集 第01季第02集.mkv"])

        app._show_rules(select=1)                                 # 編輯區改的是選取的那一條規則
        app.replace_var.set("S$1-E$2")
        self.assertEqual(app.rules[1].replace, "S$1-E$2")
        app.replace_var.set("第$1季第$2集")

        app.apply()
        self.assertEqual(self.files(), ["readme.txt", os.path.join("sub", "影集 第01季第02集.mkv"),
                                        "影集 第01季第01集.mp4"])
        self.assertTrue(main.LAST_BATCH_FILE.exists())
        app.close()

        again = self.new_app()                                    # 關掉重開：規則還在，也還能復原
        self.assertEqual([r.find for r in again.rules], [r"\[(1080p|720p)\]\s*", r"S(\d+)E(\d+)"])
        self.assertEqual(str(again.undo_btn.cget("state")), "normal")
        again.undo()
        self.assertEqual(self.files(), ["[1080p] 影集 S01E01.mp4", "readme.txt",
                                        os.path.join("sub", "[720p] 影集 S01E02.mkv")])
        self.assertFalse(main.LAST_BATCH_FILE.exists())

    def test_presets_and_hash_mode(self):
        app = self.new_app()
        app.rules = [Rule(r"\s+", "_")]
        app.save_preset("空白變底線")
        app.rules = [Rule()]
        app.preset_var.set("空白變底線")
        app.load_preset()
        self.assertEqual([(r.find, r.replace) for r in app.rules], [(r"\s+", "_")])

        app.add_paths([str(self.dir / "readme.txt")])
        app.mode.set(MODE_NAME_HASH)
        app._mode_changed()
        app.refresh()
        self.assertTrue(app.rows[0].ok)
        self.assertTrue(app.rows[0].new_name.endswith(".txt"))


if __name__ == "__main__":
    unittest.main()
