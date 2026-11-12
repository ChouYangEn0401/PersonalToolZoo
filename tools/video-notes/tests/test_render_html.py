"""HTML 範本輸出（html-sheet／html-longform／html-tabs／tree-html）。完全離線。"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes.adapters import render_html  # noqa: E402
from video_notes.adapters.render import REGISTRY, RenderContext  # noqa: E402
from video_notes.errors import ToolError  # noqa: E402

NAMES = {"html-sheet": "sheet.html", "html-longform": "longform.html", "html-tabs": "tabs.html",
         "tree-html": "tree.html"}
CTX = RenderContext(profile_name="財經", modifier_names=["時間軸"], tool_version="9.9.9")
MIN_TEMPLATE = ('<!doctype html><meta charset="utf-8"><title>t</title>'
                '<script type="application/json" id="vn-data">__VN_DATA__</script><body>hi</body>')
DATA_RE = re.compile(r'<script type="application/json" id="vn-data">(.*?)</script>', re.S)


def evil() -> dict:
    s = "</script><script>alert(1)</script><!-- &amp;"
    return {
        "title": s, "summary": "]]> \"q\"     'x'", "kind": "video",
        "sections": [{"title": s, "summary": "", "points": ["javascript:alert(1)", "長" * 5000],
                      "start": None, "children": []}],
        "sources": [{"id": "a", "url": "javascript:alert(1)", "title": "bad"},
                    {"id": "b", "url": "https://ok.example/x", "title": "good"}],
    }


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self._old = render_html.TEMPLATE_DIRS
        render_html.TEMPLATE_DIRS = [self.dir]
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(lambda: setattr(render_html, "TEMPLATE_DIRS", self._old))

    def put(self, filename, text=MIN_TEMPLATE):
        (self.dir / filename).write_text(text, encoding="utf-8")


class Fill(Base):
    def test_all_four_render(self):
        for name, fn in NAMES.items():
            self.put(fn)
            r = REGISTRY.create(name)
            self.assertEqual((r.extension, r.binary), (".html", False))
            self.assertIsNone(r.check())
            out = r.render({"title": "標題", "summary": "s", "sections": []}, CTX)
            self.assertIsInstance(out, str)
            self.assertNotIn("__VN_DATA__", out)
            payload = json.loads(DATA_RE.search(out).group(1))
            self.assertEqual(payload["analysis"]["title"], "標題")
            meta = payload["meta"]
            self.assertEqual(meta["profile_name"], "財經")
            self.assertEqual(meta["modifier_names"], ["時間軸"])
            self.assertEqual(meta["tool_version"], "9.9.9")
            self.assertRegex(meta["generated_at"], r"^\d{4}-\d\d-\d\dT")

    def test_tool_version_falls_back_to_version_py(self):
        self.put("sheet.html")
        out = REGISTRY.create("html-sheet").render({"title": "x"}, RenderContext())
        v = json.loads(DATA_RE.search(out).group(1))["meta"]["tool_version"]
        self.assertRegex(v, r"^\d+\.\d+\.\d+")

    def test_groups(self):
        self.assertEqual(REGISTRY.create("tree-html").capabilities()["group"], "tree")
        self.assertEqual(REGISTRY.create("html-tabs").capabilities()["group"], "html")

    def test_evil_data_cannot_close_script(self):
        self.put("sheet.html")
        out = REGISTRY.create("html-sheet").render(evil(), CTX)
        m = DATA_RE.search(out)
        data_region = m.group(1)
        for bad in ("</", "<script", "<!--", "&amp;", " ", " ", ">"):
            self.assertNotIn(bad, data_region, bad)
        self.assertEqual(out.count("</script>"), 1)          # 只有範本自己那一個
        parsed = json.loads(data_region)                       # 還原後內容完全一樣
        self.assertEqual(parsed["analysis"]["title"], evil()["title"])
        self.assertEqual(parsed["analysis"]["summary"], evil()["summary"])

    def test_bad_source_urls_are_blanked(self):
        self.put("sheet.html")
        out = REGISTRY.create("html-sheet").render(evil(), CTX)
        srcs = json.loads(DATA_RE.search(out).group(1))["analysis"]["sources"]
        self.assertEqual([s["url"] for s in srcs], ["", "https://ok.example/x"])

    def test_does_not_mutate_input(self):
        self.put("sheet.html")
        a = evil()
        REGISTRY.create("html-sheet").render(a, CTX)
        self.assertEqual(a["sources"][0]["url"], "javascript:alert(1)")

    def test_data_containing_placeholder_is_harmless(self):
        self.put("sheet.html")
        out = REGISTRY.create("html-sheet").render({"title": "__VN_DATA__"}, CTX)
        self.assertEqual(json.loads(DATA_RE.search(out).group(1))["analysis"]["title"], "__VN_DATA__")


class Errors(Base):
    def test_missing_template(self):
        r = REGISTRY.create("html-sheet")
        err = r.check()
        self.assertIsInstance(err, ToolError)
        self.assertEqual(err.code, "dependency_missing")
        with self.assertRaises(ToolError) as cm:
            r.render({"title": "x"}, CTX)
        self.assertEqual(cm.exception.code, "dependency_missing")

    def test_placeholder_count(self):
        for text in ("<body>no placeholder</body>", MIN_TEMPLATE + MIN_TEMPLATE):
            self.put("sheet.html", text)
            with self.assertRaises(ToolError) as cm:
                REGISTRY.create("html-sheet").render({"title": "x"}, CTX)
            self.assertEqual(cm.exception.code, "config_invalid")

    def test_user_template_overrides_bundle(self):
        user, bundle = self.dir / "user", self.dir / "bundle"
        user.mkdir()
        bundle.mkdir()
        (bundle / "sheet.html").write_text(MIN_TEMPLATE.replace("hi", "BUNDLE"), encoding="utf-8")
        render_html.TEMPLATE_DIRS = [user, bundle]
        out = REGISTRY.create("html-sheet").render({"title": "x"}, CTX)
        self.assertIn("BUNDLE", out)
        (user / "sheet.html").write_text(MIN_TEMPLATE.replace("hi", "USER"), encoding="utf-8")
        out = REGISTRY.create("html-sheet").render({"title": "x"}, CTX)
        self.assertIn("USER", out)
        self.assertNotIn("BUNDLE", out)


class RealTemplates(unittest.TestCase):
    """templates/*.html 存在才跑（設計師做的範本）；用真檔確認契約。"""

    def test_real_templates_fill(self):
        real = TOOL / "templates"
        old = render_html.TEMPLATE_DIRS
        render_html.TEMPLATE_DIRS = [real]
        try:
            found = [(n, f) for n, f in NAMES.items() if (real / f).is_file()]
            if not found:
                self.skipTest("templates/*.html 還沒有")
            for name, _ in found:
                with self.subTest(name):
                    out = REGISTRY.create(name).render(evil(), CTX)
                    data = DATA_RE.search(out)
                    self.assertIsNotNone(data)
                    json.loads(data.group(1))
                    self.assertNotIn("__VN_DATA__", out)
        finally:
            render_html.TEMPLATE_DIRS = old


if __name__ == "__main__":
    unittest.main()
