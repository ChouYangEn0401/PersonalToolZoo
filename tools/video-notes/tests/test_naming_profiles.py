"""網址判斷、檔名、提示詞庫（不需要網路、GPU 或 API）。

    .\\tools\\video-notes\\.venv\\Scripts\\python.exe -m unittest discover -s tools\\video-notes\\tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes.naming import Artifacts, classify, find_folder, new_folder, safe_title  # noqa: E402
from video_notes.profiles import AUTO, PromptLibrary  # noqa: E402

LIB = PromptLibrary(TOOL / "prompts")


class ClassifyTest(unittest.TestCase):
    def check(self, url, platform, vid, kind):
        ref = classify(url)
        self.assertEqual((ref.platform, ref.video_id, ref.kind), (platform, vid, kind), url)

    def test_youtube_forms(self):
        self.check("https://www.youtube.com/watch?v=knWPw9_a5qY&t=42s&list=PL1", "youtube", "knWPw9_a5qY", "video")
        self.check("youtu.be/jNQXAC9IVRw?si=abc", "youtube", "jNQXAC9IVRw", "video")
        self.check("https://m.youtube.com/shorts/ZLCFg03KCmM", "youtube", "ZLCFg03KCmM", "short")
        self.check("https://www.youtube.com/live/ULl5Jp87061", "youtube", "ULl5Jp87061", "video")

    def test_other_platforms(self):
        self.check("https://www.tiktok.com/@someone/video/7312345678901234567", "tiktok", "7312345678901234567", "short")
        self.check("https://www.instagram.com/reel/C1AbCdEfGh/", "instagram", "C1AbCdEfGh", "short")
        self.check("https://www.bilibili.com/video/BV1xx411c7mD/", "bilibili", "BV1xx411c7mD", "video")

    def test_unknown_site_is_stable(self):
        a, b = classify("https://example.com/v/123"), classify("https://example.com/v/123")
        self.assertEqual(a, b)
        self.assertTrue(a.video_id.startswith("h"))
        self.assertNotEqual(a.video_id, classify("https://example.com/v/124").video_id)


class FolderTest(unittest.TestCase):
    def test_safe_title(self):
        self.assertEqual(safe_title('台積電漲太多？鴻海卻漲不動 "杜大師" a/b:c.'), "台積電漲太多？鴻海卻漲不動 杜大師 a b c")
        self.assertEqual(safe_title(""), "untitled")
        self.assertLessEqual(len(safe_title("字" * 300)), 80)

    def test_found_by_tag_even_if_title_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = classify("https://youtu.be/jNQXAC9IVRw")
            folder = new_folder(root, ref, "舊標題")
            folder.mkdir()
            self.assertEqual(find_folder(root, classify("https://www.youtube.com/watch?v=jNQXAC9IVRw")), folder)
            self.assertIsNone(find_folder(root, classify("https://youtu.be/knWPw9_a5qY")))

    def test_status_ignores_partial_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            art = Artifacts(Path(tmp))
            (art.folder / "media.webm.part").write_bytes(b"x")
            self.assertFalse(art.status()["media"])
            (art.folder / "media.m4a").write_bytes(b"x")
            (art.folder / "notes.news+brief.md").write_text("n", encoding="utf-8")
            status = art.status()
            self.assertTrue(status["media"])
            self.assertEqual(status["notes"], ["news+brief"])


class LibraryTest(unittest.TestCase):
    def test_bundled_prompts_load(self):
        self.assertTrue({"knowledge", "news", "podcast", "quick", "finance", "general"} <= set(LIB.profiles))
        self.assertTrue({"timeline", "actions", "brief", "english"} <= set(LIB.modifiers))
        for p in LIB.profiles.values():
            self.assertTrue(p.goal and p.format, p.id)

    def test_preset_expands_and_explicit_options_win(self):
        plan = LIB.plan(preset="stock-show")
        self.assertEqual((plan.profile, set(plan.modifiers)), ("finance", {"actions", "timeline"}))
        plan = LIB.plan(profile="news", modifiers=["brief"], preset="stock-show", focus="AI 伺服器")
        self.assertEqual(plan.profile, "news")
        self.assertEqual(plan.modifiers, ("actions", "timeline", "brief"))
        self.assertEqual(plan.focus, "AI 伺服器")

    def test_unknown_names_are_rejected(self):
        with self.assertRaises(KeyError):
            LIB.plan(profile="nope")
        with self.assertRaises(KeyError):
            LIB.plan(modifiers=["nope"])

    def test_slug_is_order_independent_and_focus_aware(self):
        a = LIB.plan("news", ["brief", "timeline"]).slug()
        b = LIB.plan("news", ["timeline", "brief"]).slug()
        self.assertEqual(a, b)
        self.assertNotEqual(LIB.plan("news", focus="甲").slug(), LIB.plan("news", focus="乙").slug())
        self.assertEqual(LIB.plan(AUTO).slug("news"), "news")

    def test_compose(self):
        c = LIB.compose("finance", ["timeline", "english"], focus="AI", short=True)
        self.assertIn("<format>", c.system)
        self.assertIn("</format>", c.system)
        self.assertIn("## 時間軸", c.system)
        self.assertIn("全部用 English 撰寫", c.system)
        self.assertIn("「AI」", c.system)
        self.assertIn("短影音", c.system)
        self.assertTrue(c.needs_timestamps)
        self.assertNotIn("繁體中文與台灣慣用語", c.system)

    def test_parse_classification(self):
        self.assertEqual(LIB.parse_classification('{"profile": "news", "reason": "記者報導"}'), ("news", "記者報導"))
        self.assertEqual(LIB.parse_classification('好的：```json\n{"profile":"finance"}\n```')[0], "finance")
        self.assertEqual(LIB.parse_classification("podcast")[0], "podcast")
        self.assertEqual(LIB.parse_classification("我不確定")[0], "general")

    def test_user_folder_overrides_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "profiles").mkdir()
            (Path(tmp) / "profiles" / "news.toml").write_text(
                'name = "我的新聞"\ngoal = "只要標題"\nformat = "- 標題"\n', encoding="utf-8")
            lib = PromptLibrary(TOOL / "prompts", Path(tmp))
            self.assertEqual(lib.profiles["news"].name, "我的新聞")
            self.assertIn("knowledge", lib.profiles)


if __name__ == "__main__":
    unittest.main()
