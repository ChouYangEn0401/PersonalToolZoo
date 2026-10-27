"""畫面（main.py）走一遍：加資料夾 → 選圖 → 套用 → 移除；自動套用時沒有圖片的資料夾會被略過。"""

import ctypes
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tkinterdnd2 import TkinterDnD  # noqa: E402

import main  # noqa: E402


class GuiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.tmp.name)
        self.addCleanup(self.cleanup)
        self.album = self.root_dir / "相簿"
        self.empty = self.root_dir / "空的"
        self.album.mkdir()
        self.empty.mkdir()
        Image.new("RGB", (320, 200), (10, 160, 90)).save(self.album / "b.jpg")
        Image.new("RGB", (200, 320), (160, 10, 90)).save(self.album / "folder.png")
        root = TkinterDnD.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        self.app = main.FolderCoverApp(root, confirm=lambda *a, **k: True, notify=lambda *a, **k: None)

    def cleanup(self):
        for p in self.root_dir.rglob("*"):
            ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x80)
        self.tmp.cleanup()

    def test_pick_apply_and_remove(self):
        self.app.add_folders([self.album])
        self.assertEqual([p.name for p in self.app.images], ["folder.png", "b.jpg"])   # folder.* 排第一
        self.app.image_list.selection_clear(0, "end")
        self.app.image_list.selection_set(1)
        self.app._pick_from_list()
        self.app.apply_selected()
        self.assertTrue((self.album / "desktop.ini").exists())
        self.assertIn("b.jpg", self.app.tree.item("0", "values")[2])
        self.assertEqual(self.app.tree.item("0", "values")[1], "自訂")
        self.app.remove_selected_cover()
        self.assertFalse((self.album / "desktop.ini").exists())
        self.assertEqual(self.app.tree.item("0", "values")[1], "預設")

    def test_apply_all_skips_folders_without_images(self):
        self.app.add_folders([self.album, self.empty])
        self.app.apply_all()
        self.assertTrue((self.album / main.cover.ICON_NAME).exists())
        self.assertIn("folder.png", self.app.tree.item("0", "values")[2])
        self.assertIn("沒有圖片", self.app.tree.item("1", "values")[2])
        self.assertFalse((self.empty / "desktop.ini").exists())


if __name__ == "__main__":
    unittest.main()
