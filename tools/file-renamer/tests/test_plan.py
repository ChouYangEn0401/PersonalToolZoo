"""改名規劃（plan_renames）與套用 / 復原。

    .\\tools\\file-renamer\\.venv\\Scripts\\python.exe -m unittest discover -s tools\\file-renamer\\tests -v
"""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import MODE_CONTENT_HASH, MODE_NAME_HASH, MODE_REGEX, plan_renames  # noqa: E402


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.files = []
        for name, data in (("IMG_001.jpg", b"a"), ("IMG_002.jpg", b"b"), ("note.txt", b"a")):
            p = self.dir / name
            p.write_bytes(data)
            self.files.append(str(p))

    def test_regex_with_groups(self):
        plan = plan_renames(self.files, MODE_REGEX, r"^IMG_(\d+)", r"照片_\1")
        self.assertEqual([(os.path.basename(p), n, e) for p, n, e in plan],
                         [("IMG_001.jpg", "照片_001.jpg", ""), ("IMG_002.jpg", "照片_002.jpg", ""),
                          ("note.txt", "note.txt", "不變")])

    def test_bad_regex_and_illegal_names(self):
        self.assertTrue(all(e.startswith("規則錯誤") for _, _, e in plan_renames(self.files, MODE_REGEX, "(")))
        plan = plan_renames(self.files[:1], MODE_REGEX, "IMG", "a/b")
        self.assertEqual(plan[0][2], "新檔名不合法")

    def test_conflicts(self):
        plan = plan_renames(self.files[:2], MODE_REGEX, r"_\d+", "")          # 兩個都變成 IMG.jpg
        self.assertEqual(plan[0][2], "")
        self.assertIn("重複", plan[1][2])
        (self.dir / "已存在.txt").write_bytes(b"x")
        plan = plan_renames(self.files[2:], MODE_REGEX, "note", "已存在")
        self.assertEqual(plan[0][2], "目標檔名已存在")

    def test_hash_modes(self):
        name_plan = plan_renames(self.files[:1], MODE_NAME_HASH)
        self.assertEqual(name_plan[0][1], hashlib.sha256(b"IMG_001.jpg").hexdigest() + ".jpg")
        content = plan_renames([self.files[0], self.files[2]], MODE_CONTENT_HASH)
        self.assertEqual(content[0][1], hashlib.sha256(b"a").hexdigest() + ".jpg")
        self.assertEqual(content[1][1], hashlib.sha256(b"a").hexdigest() + ".txt")   # 內容相同、副檔名不同不衝突

    def test_apply_and_undo_through_the_app(self):
        from tkinterdnd2 import TkinterDnD

        from main import FileRenamerApp

        root = TkinterDnD.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        app = FileRenamerApp(root)
        app._add_paths(self.files)
        app.pattern.set(r"^IMG_(\d+)")
        app.replacement.set(r"P\1")
        import main
        main.messagebox.askyesno = lambda *a, **k: True
        app._apply()
        self.assertEqual(sorted(os.listdir(self.dir)), ["P001.jpg", "P002.jpg", "note.txt"])
        app._undo()
        self.assertEqual(sorted(os.listdir(self.dir)), ["IMG_001.jpg", "IMG_002.jpg", "note.txt"])


if __name__ == "__main__":
    unittest.main()
