"""改名引擎（renamer.py）：規則、預覽、衝突、兩段式套用與復原、掃描資料夾、存檔。

    .\\tools\\file-renamer\\.venv\\Scripts\\python.exe -m unittest discover -s tools\\file-renamer\\tests -v
"""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import renamer  # noqa: E402
from renamer import (MODE_CONTENT_HASH, MODE_NAME_HASH, SCOPE_FULL, STATUS_NO_MATCH, STATUS_SAME, Rule,  # noqa: E402
                     RuleError)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def make(self, *names, data=b"x"):
        paths = []
        for name in names:
            p = self.dir / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if isinstance(data, bytes) else data[name])
            paths.append(str(p))
        return paths

    def names(self, rows):
        return [(os.path.basename(r.path), r.new_name, r.status) for r in rows]

    def listing(self):
        return sorted(os.listdir(self.dir))


class RulesTest(Base):
    def test_rules_apply_in_order_and_keep_the_extension(self):
        files = self.make("[1080p] 影片 S01E02 [字幕].mp4", "note.txt")
        rules = [Rule(r"\[(1080p|720p)\]\s*", ""), Rule(r"\s*\[字幕\]", ""), Rule(r"S(\d+)E(\d+)", r"第$1季第$2集")]
        rows = renamer.plan(files, rules=rules)
        self.assertEqual(self.names(rows), [("[1080p] 影片 S01E02 [字幕].mp4", "影片 第01季第02集.mp4", ""),
                                            ("note.txt", "note.txt", STATUS_NO_MATCH)])
        self.assertEqual(rows[0].hits, 3)

    def test_extension_untouched_unless_full_scope(self):
        files = self.make("a.mp4.mp4")
        self.assertEqual(renamer.plan(files, rules=[Rule(r"\.mp4", "")])[0].new_name, "a.mp4")
        self.assertEqual(renamer.plan(files, rules=[Rule(r"\.mp4$", ".mkv")], scope=SCOPE_FULL)[0].new_name,
                         "a.mp4.mkv")

    def test_disabled_rule_ignore_case_and_dollar_syntax(self):
        files = self.make("IMG_0012.JPG")
        rows = renamer.plan(files, rules=[Rule("img_", "照片_", ignore_case=True), Rule("照片", "X", enabled=False)])
        self.assertEqual(rows[0].new_name, "照片_0012.JPG")
        self.assertEqual(renamer.to_python_replacement(r"$1-${name}-$$-\2"), r"\g<1>-\g<name>-$-\2")

    def test_bad_rule_reports_which_one(self):
        files = self.make("a.txt")
        rows = renamer.plan(files, rules=[Rule("a", "b"), Rule("(", "x")])
        self.assertIn("第 2 條規則", rows[0].status)
        with self.assertRaises(RuleError):
            renamer.compile_rules([Rule("(a)", r"\3")])      # 引用不存在的群組也要在預覽時擋下

    def test_hash_modes(self):
        files = self.make("IMG_001.jpg", "copy.txt", data={"IMG_001.jpg": b"a", "copy.txt": b"a"})
        self.assertEqual(renamer.plan(files[:1], MODE_NAME_HASH)[0].new_name,
                         hashlib.sha256(b"IMG_001.jpg").hexdigest() + ".jpg")
        rows = renamer.plan(files, MODE_CONTENT_HASH)
        self.assertEqual([r.new_name for r in rows], [hashlib.sha256(b"a").hexdigest() + ".jpg",
                                                      hashlib.sha256(b"a").hexdigest() + ".txt"])
        self.assertTrue(all(r.ok for r in rows))        # 內容相同、副檔名不同不算衝突


class ConflictTest(Base):
    def test_duplicates_existing_illegal_and_reserved(self):
        files = self.make("IMG_1.jpg", "IMG_2.jpg", "note.txt", "keep.txt")
        rows = renamer.plan(files[:2], rules=[Rule(r"_\d+", "")])                # 兩個都變成 IMG.jpg
        self.assertTrue(rows[0].ok)
        self.assertIn("重複", rows[1].status)
        self.assertEqual(renamer.plan(files[2:3], rules=[Rule("note", "keep")])[0].status, "目標檔名已經有別的檔案")
        self.assertIn("不能用的字元", renamer.plan(files[2:3], rules=[Rule("note", "a?b")])[0].status)
        self.assertIn("保留的名稱", renamer.plan(files[2:3], rules=[Rule("note", "CON")])[0].status)
        self.assertIn("結尾", renamer.plan(files[2:3], rules=[Rule(r"\.txt$", ".")], scope=SCOPE_FULL)[0].status)

    def test_blocked_file_also_blocks_whoever_wanted_its_name(self):
        # a→b 會撞到「不會改名」的 b（b 因為規則沒命中留在原地），所以 a 也要擋下
        files = self.make("a.txt", "b.txt")
        rows = renamer.plan(files, rules=[Rule("^a$", "b")])
        self.assertEqual(rows[0].status, "目標檔名已經有別的檔案")
        self.assertEqual(rows[1].status, STATUS_NO_MATCH)

    def test_unchanged_name(self):
        rows = renamer.plan(self.make("a.txt"), rules=[Rule("a", "a")])
        self.assertEqual(rows[0].status, STATUS_SAME)


class ApplyTest(Base):
    def test_chain_and_swap_do_not_collide(self):
        self.make("1.txt", "2.txt", "3.txt", data={"1.txt": b"one", "2.txt": b"two", "3.txt": b"three"})
        files = [str(self.dir / n) for n in ("1.txt", "2.txt", "3.txt")]
        rows = renamer.plan(files, rules=[Rule("^3$", "4"), Rule("^2$", "3"), Rule("^1$", "2")])
        self.assertTrue(all(r.ok for r in rows), self.names(rows))
        pairs = renamer.apply(rows)
        self.assertEqual(self.listing(), ["2.txt", "3.txt", "4.txt"])
        self.assertEqual((self.dir / "2.txt").read_bytes(), b"one")
        renamer.undo(pairs)
        self.assertEqual((self.dir / "1.txt").read_bytes(), b"one")
        self.assertEqual(self.listing(), ["1.txt", "2.txt", "3.txt"])

        swap = renamer.plan(files[:2], rules=[Rule("^1$", "@"), Rule("^2$", "1"), Rule("^@$", "2")])
        renamer.apply(swap)
        self.assertEqual((self.dir / "1.txt").read_bytes(), b"two")
        self.assertEqual((self.dir / "2.txt").read_bytes(), b"one")

    def test_case_only_rename(self):
        files = self.make("photo.JPG")
        rows = renamer.plan(files, rules=[Rule(r"\.JPG$", ".jpg")], scope=SCOPE_FULL)
        self.assertTrue(rows[0].ok)
        renamer.apply(rows)
        self.assertEqual(self.listing(), ["photo.jpg"])

    def test_failure_rolls_back_the_whole_batch(self):
        files = self.make("a.txt", "b.txt")
        rows = renamer.plan(files, rules=[Rule("^(.)$", r"new_\1")])
        real_rename = os.rename
        calls = []

        def flaky(src, dst):
            calls.append((src, dst))
            if len(calls) == 4:            # 第二段的第二個檔案失敗
                raise PermissionError("檔案被別的程式開著")
            real_rename(src, dst)

        with mock.patch.object(renamer.os, "rename", flaky):
            with self.assertRaises(renamer.RenameError):
                renamer.apply(rows)
        self.assertEqual(self.listing(), ["a.txt", "b.txt"])

    def test_undo_refuses_when_a_file_is_gone(self):
        files = self.make("a.txt")
        pairs = renamer.apply(renamer.plan(files, rules=[Rule("a", "b")]))
        (self.dir / "b.txt").unlink()
        with self.assertRaises(renamer.RenameError):
            renamer.undo(pairs)


class ScanAndStorageTest(Base):
    def test_scan_folder_recursive_with_filter(self):
        self.make("a.mp4", "b.MKV", "c.txt", "sub/d.mp4", ".git/e.mp4", "desktop.ini")
        all_files = [os.path.relpath(p, self.dir) for p in renamer.scan_folder(self.dir)]
        self.assertEqual(sorted(all_files), sorted(["a.mp4", "b.MKV", "c.txt", os.path.join("sub", "d.mp4")]))
        videos = [os.path.basename(p) for p in renamer.scan_folder(self.dir, recursive=False, name_filter="*.mp4; *.mkv")]
        self.assertEqual(videos, ["a.mp4", "b.MKV"])

    def test_rules_round_trip(self):
        rules = [Rule(r"\s+", "_", ignore_case=True), Rule("x", "", enabled=False)]
        path = self.dir / "data" / "presets.json"
        renamer.save_json(path, {"空白變底線": renamer.rules_to_data(rules)})
        loaded = renamer.rules_from_data(renamer.load_json(path, {})["空白變底線"])
        self.assertEqual(loaded, rules)
        self.assertEqual(renamer.load_json(self.dir / "missing.json", {"a": 1}), {"a": 1})


if __name__ == "__main__":
    unittest.main()
