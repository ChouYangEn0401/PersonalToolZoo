"""cover.py：圖片轉 ico、套用與移除資料夾圖示（在暫存資料夾實際呼叫 Windows API）。

    .\\tools\\folder-cover\\.venv\\Scripts\\python.exe -m unittest discover -s tools\\folder-cover\\tests -v
"""

import ctypes
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cover  # noqa: E402


def attrs(path: Path) -> int:
    return ctypes.windll.kernel32.GetFileAttributesW(str(path))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / "相簿 2026"
        self.folder.mkdir()

    def cleanup(self):
        # 測試會把檔案設成隱藏／系統、資料夾設成唯讀；清掉前先還原，暫存資料夾才刪得掉
        for p in self.root.rglob("*"):
            ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x80)
        self.tmp.cleanup()

    def image(self, name="photo.png", size=(300, 200), color=(200, 30, 30, 255)):
        path = self.folder / name
        Image.new("RGBA", size, color).save(path)
        return path


class IconTest(Base):
    def test_crop_and_fit_make_square_multi_size_icons(self):
        src = self.image(size=(300, 120))
        ico = cover.make_icon(src, self.root / "a.ico", cover.MODE_CROP)
        with Image.open(ico) as im:
            self.assertEqual(sorted(im.info["sizes"]), sorted(cover.ICON_SIZES))
            im.size = (256, 256)
            self.assertEqual(im.load()[0, 0][3], 255)               # 裁切：角落是原圖（不透明）
        fit = cover.make_icon(src, self.root / "b.ico", cover.MODE_FIT)
        with Image.open(fit) as im:
            im.size = (256, 256)
            self.assertEqual(im.load()[0, 0][3], 0)                 # 補邊：上方角落是透明的

    def test_find_images_prefers_cover_names(self):
        for name in ("b.jpg", "a.png", "cover.webp", "note.txt"):
            (self.folder / name).write_bytes(b"x")
        self.assertEqual([p.name for p in cover.find_images(self.folder)], ["cover.webp", "a.png", "b.jpg"])


class ApplyTest(Base):
    def test_apply_writes_relative_icon_and_attributes_then_remove_restores(self):
        cover.apply_cover(self.folder, self.image())
        ini = self.folder / "desktop.ini"
        icon = self.folder / cover.ICON_NAME
        self.assertTrue(ini.exists() and icon.exists())
        self.assertTrue(cover.current_cover(self.folder).lower().startswith(cover.ICON_NAME))   # 相對路徑
        self.assertTrue(attrs(ini) & cover.FILE_ATTRIBUTE_HIDDEN and attrs(ini) & cover.FILE_ATTRIBUTE_SYSTEM)
        self.assertTrue(attrs(icon) & cover.FILE_ATTRIBUTE_HIDDEN)
        self.assertTrue(attrs(self.folder) & (cover.FILE_ATTRIBUTE_READONLY | cover.FILE_ATTRIBUTE_SYSTEM))

        cover.apply_cover(self.folder, self.image("other.png", color=(0, 0, 255, 255)))   # 再換一張也可以
        self.assertTrue(icon.exists())

        cover.remove_cover(self.folder)
        self.assertFalse(ini.exists() or icon.exists())
        self.assertFalse(attrs(self.folder) & (cover.FILE_ATTRIBUTE_READONLY | cover.FILE_ATTRIBUTE_SYSTEM))
        self.assertEqual(cover.current_cover(self.folder), "")

    def test_remove_keeps_other_desktop_ini_settings(self):
        cover.apply_cover(self.folder, self.image())
        ini = self.folder / "desktop.ini"
        ctypes.windll.kernel32.WritePrivateProfileStringW(".ShellClassInfo", "InfoTip", "我的相簿", str(ini))
        cover.remove_cover(self.folder)
        self.assertTrue(ini.exists())                                       # 其他設定還在，檔案留著
        self.assertEqual(cover.current_cover(self.folder), "")
        self.assertEqual(cover._read_ini(ini, "InfoTip"), "我的相簿")

    def test_not_a_folder(self):
        with self.assertRaises(cover.CoverError):
            cover.apply_cover(self.root / "沒有這個資料夾", self.image())


if __name__ == "__main__":
    unittest.main()
