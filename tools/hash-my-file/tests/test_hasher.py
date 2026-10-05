"""FileHasher：四種雜湊、資料夾展開、比對貼上的雜湊值。

    .\\tools\\hash-my-file\\.venv\\Scripts\\python.exe -m unittest discover -s tools\\hash-my-file\\tests -v
"""

import hashlib
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from HashMyFile import FileHasher  # noqa: E402


class HasherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / "a.bin"
        self.data = b"hello" * 30000          # 比 64 KB 的讀取區塊大，測分段讀取
        self.file.write_bytes(self.data)

    def test_all_hashes(self):
        h = FileHasher.get_hashes(str(self.file))
        self.assertEqual(h["MD5"], hashlib.md5(self.data).hexdigest())
        self.assertEqual(h["SHA1"], hashlib.sha1(self.data).hexdigest())
        self.assertEqual(h["SHA256"], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(h["CRC32"], format(zlib.crc32(self.data) & 0xFFFFFFFF, "08x"))
        self.assertIsNone(FileHasher.get_hashes(str(self.root)))

    def test_expand_folders(self):
        (self.root / "sub").mkdir()
        (self.root / "sub" / "b.txt").write_text("b")
        found = sorted(Path(p).name for p in FileHasher.expand([str(self.root)]))
        self.assertEqual(found, ["a.bin", "b.txt"])

    def test_match(self):
        h = FileHasher.get_hashes(str(self.file))
        self.assertEqual(FileHasher.match(h["SHA256"].upper(), h), "SHA256")
        self.assertEqual(FileHasher.match(f"  {h['CRC32']} \n", h), "CRC32")
        spaced = ":".join(h["MD5"][i:i + 2] for i in range(0, 32, 2))   # 有些網站用冒號分隔
        self.assertEqual(FileHasher.match(spaced, h), "MD5")
        self.assertIsNone(FileHasher.match("deadbeef", h))
        self.assertIsNone(FileHasher.match("   ", h))


if __name__ == "__main__":
    unittest.main()
