"""查詢解析、檔名比對、內容搜尋（只用標準庫）。

    python -m unittest discover -s tools\\better-file-finder\\tests -v
"""

import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import Query, content_hit, name_score, parse_patterns, search  # noqa: E402


class QueryTest(unittest.TestCase):
    def test_parse(self):
        q = Query.parse('報告 +2024 "季度 總結" -草稿')
        self.assertEqual((q.words, q.phrases, q.excludes), (["報告", "2024"], ["季度 總結"], ["草稿"]))
        self.assertTrue(Query.parse("-只有排除").empty)

    def test_patterns(self):
        self.assertEqual(parse_patterns("txt, .md; *.py"), ["*.txt", "*.md", "*.py"])
        self.assertEqual(parse_patterns(""), [])

    def test_name_score(self):
        q = Query.parse("報告 2024")
        self.assertGreater(name_score("2024年度報告.docx", q, False), 0)
        self.assertEqual(name_score("報告.docx", q, False), 0)                   # 少一個詞
        self.assertEqual(name_score("2024報告-草稿.docx", Query.parse("報告 -草稿"), False), 0)   # 舊版這裡寫反了
        self.assertGreater(name_score("report.txt", Query.parse("repotr"), True), 0)  # 模糊：打錯字
        self.assertEqual(name_score("abc.txt", Query.parse("xyz"), True), 0)       # 舊版門檻 > 0 什麼都會中
        self.assertGreater(name_score("報告.txt", Query.parse("報告"), False),
                           name_score("期末報告.txt", Query.parse("報告"), False))  # 完全相同排前面


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "sub").mkdir()
        (root / "node_modules").mkdir()
        (root / "notes.md").write_text("第一行\n會議的結論是延期\n", encoding="utf-8")
        (root / "sub" / "plan.txt").write_text("plan", encoding="utf-8")
        (root / "sub" / "big5.txt").write_bytes("中文會議紀錄".encode("cp950"))
        (root / "image.bin").write_bytes(b"\x00\x01" + "會議".encode("utf-8"))
        (root / "node_modules" / "會議.txt").write_text("x", encoding="utf-8")
        self.root = str(root)

    def run_search(self, text, **kw):
        hits = []
        search(self.root, Query.parse(text), parse_patterns(kw.pop("patterns", "")),
               emit=lambda e: e[0] == "hit" and hits.append(e[1]), **kw)
        return sorted(Path(h[1]).name for h in hits)

    def test_names_and_skip_dirs(self):
        self.assertEqual(self.run_search("plan"), ["plan.txt"])
        self.assertEqual(self.run_search("會議"), [])                  # node_modules 會被略過

    def test_contents(self):
        self.assertEqual(self.run_search("會議", contents=True), ["big5.txt", "notes.md"])   # 二進位檔不算
        self.assertEqual(content_hit(str(Path(self.root) / "notes.md"), Query.parse("結論")), "會議的結論是延期")

    def test_extension_only_and_folders(self):
        self.assertEqual(self.run_search("", patterns="txt"), ["big5.txt", "plan.txt"])
        self.assertIn("sub", self.run_search("sub", folders=True))

    def test_cancel(self):
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(search(self.root, Query.parse("plan"), [], cancel=cancel), 0)


if __name__ == "__main__":
    unittest.main()
