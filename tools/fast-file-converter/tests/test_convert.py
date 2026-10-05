"""實際轉檔：用程式產生的小檔案跑一輪快速拖放的轉換規則（影片相關需要 ffmpeg）。

    .\\tools\\fast-file-converter\\.venv\\Scripts\\python.exe -m unittest discover -s tools\\fast-file-converter\\tests -v
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ffmpeg_utils import check_ffmpeg, get_ffmpeg_path  # noqa: E402
from core.quick import PRESETS, convert_single  # noqa: E402


class ConvertTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def preset(self, name_start):
        return PRESETS[next(n for n in PRESETS if n.startswith(name_start))]

    def test_images(self):
        from PIL import Image

        src = self.dir / "logo.png"
        Image.new("RGBA", (300, 200), (255, 0, 0, 128)).save(src)
        for start, ext in (("圖片 → ICO", ".ico"), ("圖片 → JPEG", ".jpg"), ("圖片 → PDF", ".pdf")):
            out = convert_single(str(src), self.preset(start), overwrite=False)
            self.assertEqual(Path(out[0]).suffix, ext)
            self.assertGreater(os.path.getsize(out[0]), 0)
        again = convert_single(str(src), self.preset("圖片 → JPEG"), overwrite=False)
        self.assertNotEqual(Path(again[0]).name, "logo.jpg")           # 不覆蓋時加後綴

    @unittest.skipUnless(check_ffmpeg(), "需要 ffmpeg")
    def test_video(self):
        src = self.dir / "clip.mp4"
        subprocess.run([get_ffmpeg_path(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest", str(src)],
                       check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for start in ("影片 → MP3", "影片 → GIF"):
            out = convert_single(str(src), self.preset(start), overwrite=True)
            self.assertGreater(os.path.getsize(out[0]), 0, start)

    def test_tables(self):
        import pandas as pd

        xlsx = self.dir / "data.xlsx"
        with pd.ExcelWriter(xlsx) as w:
            pd.DataFrame({"名稱": ["甲", "乙"], "數量": [1, 2]}).to_excel(w, sheet_name="一月", index=False)
            pd.DataFrame({"名稱": ["丙"], "數量": [3]}).to_excel(w, sheet_name="二月", index=False)
        csvs = convert_single(str(xlsx), PRESETS["Excel → CSV"], overwrite=False)
        self.assertEqual(len(csvs), 2)
        back = convert_single(csvs[0], PRESETS["CSV/Parquet → Excel"], overwrite=False)
        self.assertTrue(back and os.path.exists(back[0]))

    def test_pdf_to_text(self):
        import fitz

        pdf = self.dir / "doc.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "Hello converter")
        doc.save(pdf)
        doc.close()
        out = convert_single(str(pdf), PRESETS["PDF → TXT"], overwrite=False)
        self.assertIn("Hello converter", Path(out[0]).read_text(encoding="utf-8"))


class WindowTest(unittest.TestCase):
    def test_single_window_has_all_tabs(self):
        from gui.main_window import MainWindow

        app = MainWindow()
        app.root.withdraw()
        try:
            notebook = next(w for w in app.root.winfo_children() if w.winfo_class() == "TNotebook")
            labels = [notebook.tab(t, "text").strip() for t in notebook.tabs()]
            self.assertEqual(len(labels), 7)
            self.assertIn("快速拖放", labels[0])
        finally:
            app.root.destroy()


if __name__ == "__main__":
    unittest.main()
