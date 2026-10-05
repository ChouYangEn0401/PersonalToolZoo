"""同一個種子要產生跟舊版一模一樣的圖示。

參考值是 2026-10-05 用舊版 GeneratedImageExporter.py（Pillow 12.3）以種子 596481 產生的 9 個 .ico，
重新讀回來後 RGBA 像素的 SHA-256 前 16 碼。

    .\\tools\\random-icon-maker\\.venv\\Scripts\\python.exe -m unittest discover -s tools\\random-icon-maker\\tests -v
"""

import hashlib
import io
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from icon_algorithms import ALGORITHMS, generate_all  # noqa: E402

REFERENCE_596481 = {
    "algo1": "4e8267038ac44f97", "algo2": "c7c6517563f16b56", "algo3": "77aea591c9de6254",
    "algo4": "78e56015719c5e58", "algo5": "adc3191e662333c5", "algo6": "6b7793bfa8a286d0",
    "algo7": "2fecef5dca6d6297", "algo8": "bdc6fa7cd570b463", "algo9": "4fb8489925a01dad",
}


def ico_pixels_hash(img):
    buf = io.BytesIO()
    img.save(buf, format="ICO")
    buf.seek(0)
    return hashlib.sha256(Image.open(buf).convert("RGBA").tobytes()).hexdigest()[:16]


class AlgorithmTest(unittest.TestCase):
    def test_same_icons_as_the_old_script(self):
        for key, _name, img in generate_all(596481, 64):
            self.assertEqual(ico_pixels_hash(img), REFERENCE_596481[key], key)

    def test_deterministic_and_sized(self):
        a = [img.tobytes() for _, _, img in generate_all(42, 32)]
        b = [img.tobytes() for _, _, img in generate_all(42, 32)]
        self.assertEqual(a, b)
        self.assertEqual(len(a), len(ALGORITHMS))
        self.assertTrue(all(img.size == (128, 128) for _, _, img in generate_all(7, 128)))


if __name__ == "__main__":
    unittest.main()
