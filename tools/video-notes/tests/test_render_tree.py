"""樹狀圖輸出（tree-md／mermaid／opml／freemind／xmind）。完全離線。"""

import io
import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes.adapters import render_tree  # noqa: E402
from video_notes.adapters.render import REGISTRY, RenderContext  # noqa: E402

CTX = RenderContext(profile_name="財經", modifier_names=["時間軸"], tool_version="0.0.0-test")
NAMES = ["tree-md", "tree-mermaid", "tree-opml", "tree-freemind", "tree-xmind"]


def sample(**over) -> dict:
    data = {
        "schema_version": 1, "kind": "video", "title": "台積電漲太多？鴻海卻漲不動",
        "summary": "台積電短線漲多但基本面強。", "overview": "節目比較兩檔權值股。",
        "sections": [
            {"title": "台積電", "summary": "先進封裝是重點", "points": ["產能翻倍", "毛利率 58%"], "start": 62,
             "children": [{"title": "風險", "summary": "", "points": ["匯率", "地緣政治"], "start": None,
                           "children": []}]},
            {"title": "鴻海", "summary": "", "points": ["AI 伺服器毛利低"], "start": 410, "children": []},
        ],
        "key_points": ["重點一", "重點二"],
        "terms": [{"term": "CoWoS", "definition": "先進封裝技術"}],
        "actions": ["追蹤法說會"], "caveats": ["不構成投資建議"],
        "sources": [{"id": "youtube:x", "url": "https://youtu.be/x", "title": "原片"}],
        "layout_hint": {"template": "longform", "tree_depth": 2},
    }
    data.update(over)
    return data


def evil() -> dict:
    s = "<script>alert(1)</script>"
    return sample(
        title=s,
        summary='x ]]> "quote" \'q\' & more\nnewline',
        sections=[{"title": s + '"]\n  injected["x', "summary": "]]>", "points": [
            "javascript:alert(1)", "- # [x](javascript:alert(1)) `code` *b* _i_ |t| 1. a", "\x00\x01控制字元\ud800",
            "長" * 5000], "start": None, "children": []}],
        kind="collection",
        sources=[{"id": "a", "url": "javascript:alert(1)", "title": "bad"},
                 {"id": "b", "url": "https://ok.example/a b)", "title": "space"},
                 {"id": "c", "url": "https://ok.example/path?q=1&r=2", "title": "good"}],
        terms=[{"term": "#quot;", "definition": "%% comment"}],
    )


def render(name, analysis):
    r = REGISTRY.create(name)
    return r.render(analysis, CTX)


class Registration(unittest.TestCase):
    def test_all_registered_with_protocol_attrs(self):
        for n in NAMES:
            r = REGISTRY.create(n)
            self.assertEqual(r.name, n)
            self.assertTrue(r.extension.startswith("."))
            self.assertIsNone(r.check())
            self.assertEqual(r.capabilities()["group"], "tree")
            self.assertFalse(r.capabilities()["needs_network"])
        self.assertEqual({n: REGISTRY.create(n).extension for n in NAMES},
                         {"tree-md": ".md", "tree-mermaid": ".mmd", "tree-opml": ".opml",
                          "tree-freemind": ".mm", "tree-xmind": ".xmind"})

    def test_binary_matches_return_type(self):
        for n in NAMES:
            r = REGISTRY.create(n)
            self.assertIsInstance(r.render(sample(), CTX), bytes if r.binary else str, n)


class Tree(unittest.TestCase):
    def test_node_count(self):
        # 根1 + 台積電(1+2點+風險(1+2)) + 鴻海(1+1) + 重點(1+2) + 名詞(1+1+1) + 行動(1+1) + 注意(1+1)
        self.assertEqual(render_tree.build_tree(sample()).count(), 1 + 6 + 2 + 3 + 3 + 2 + 2)

    def test_root_falls_back_to_summary(self):
        self.assertEqual(render_tree.build_tree(sample(title="")).text, "台積電短線漲多但基本面強。")

    def test_collection_has_sources_branch(self):
        t = render_tree.build_tree(sample(kind="collection"))
        self.assertIn("來源影片", [c.text for c in t.children])
        t = render_tree.build_tree(sample())
        self.assertNotIn("來源影片", [c.text for c in t.children])

    def test_malformed_input_does_not_crash(self):
        for n in NAMES:
            render(n, {"title": None, "sections": "oops", "key_points": [1, None], "terms": ["x"]})


class Markdown(unittest.TestCase):
    def test_structure(self):
        out = render("tree-md", sample())
        lines = out.splitlines()
        self.assertEqual(lines[0], "# 台積電漲太多？鴻海卻漲不動")
        self.assertIn("- 台積電", lines)
        self.assertIn("  - 毛利率 58%", lines)
        self.assertIn("  - 風險", lines)
        self.assertIn("    - 匯率", lines)

    def test_escape(self):
        out = render("tree-md", evil())
        self.assertNotIn("<script>", out)
        self.assertIn("\\<script\\>", out)
        self.assertNotIn("\x00", out)
        self.assertIsNone(re.search(r"(?<!\\)\]\(javascript", out))   # 括號前的 ] 已跳脫，不會變成連結
        self.assertIn("[good](https://ok.example/path?q=1&r=2)", out)
        self.assertIn("- space\n", out)               # 含空白的網址不當連結
        # 行首符號被跳脫：不會變成標題／清單／有序清單
        self.assertIn("  - \\- # ", out)   # 只有行首的 - 需要跳脫

    def test_long_text_truncated_without_breaking_escape(self):
        out = render("tree-md", evil())
        for line in out.splitlines():
            self.assertLess(len(line), 700)


class Mermaid(unittest.TestCase):
    def test_structure(self):
        out = render("tree-mermaid", sample())
        lines = out.splitlines()
        self.assertEqual(lines[0], "mindmap")
        self.assertTrue(lines[1].startswith('  root(("'))
        self.assertEqual(sum(1 for l in lines if l.startswith("  ") and not l.startswith("   ")), 1)  # 只有一個根
        self.assertIn('    n1["台積電"]', lines)
        depths = [(len(l) - len(l.lstrip())) // 2 for l in lines[1:]]
        for a, b in zip(depths, depths[1:]):
            self.assertLessEqual(b, a + 1)   # 不跳層

    def test_escape(self):
        out = render("tree-mermaid", evil())
        body = out.split("\n", 1)[1]
        self.assertNotIn("<", body)
        self.assertNotIn("\\", body)
        self.assertNotIn("%", body)
        self.assertNotIn("`", body)
        for line in body.splitlines():
            s = line.strip()
            self.assertTrue(s.endswith('"]') or s.endswith('"))'), s)
            inner = s.split('"', 1)[1].rsplit('"', 1)[0]
            self.assertNotIn('"', inner)          # 引號都已換成 #quot;
            self.assertNotIn("\x00", s)
        self.assertEqual(len(body.splitlines()), render_tree.build_tree(evil()).count())  # 換行不會多出節點
        self.assertIn("#35;quot;", out)           # 使用者寫的「#quot;」不會被當成實體


class Xml(unittest.TestCase):
    def test_opml(self):
        root = ET.fromstring(render("tree-opml", sample()))
        self.assertEqual(root.tag, "opml")
        self.assertEqual(root.get("version"), "2.0")
        outlines = root.find("body").findall(".//outline")
        self.assertEqual(len(outlines), render_tree.build_tree(sample()).count())
        top = root.find("body").find("outline")
        self.assertEqual(top.get("text"), "台積電漲太多？鴻海卻漲不動")
        self.assertIn("先進封裝是重點", [o.get("_note") for o in outlines])

    def test_freemind(self):
        root = ET.fromstring(render("tree-freemind", sample()))
        self.assertEqual(root.tag, "map")
        nodes = root.findall(".//node")
        self.assertEqual(len(nodes), render_tree.build_tree(sample()).count())
        top = root.find("node")
        self.assertEqual(top.get("TEXT"), "台積電漲太多？鴻海卻漲不動")
        # tree_depth=2：第 2 層有子節點的會折疊；第 1 層不會
        by_text = {n.get("TEXT"): n for n in nodes}
        self.assertEqual(by_text["台積電"].get("FOLDED"), None)
        self.assertEqual(by_text["風險"].get("FOLDED"), "true")
        self.assertIsNotNone(by_text["台積電"].find("richcontent"))

    def test_evil_parses_and_has_no_bad_links(self):
        for n in ("tree-opml", "tree-freemind"):
            data = render(n, evil())
            self.assertNotIn(b"\x00", data)
            root = ET.fromstring(data)
            text = data.decode("utf-8")
            self.assertNotIn("<script>", text)         # 都已被跳脫
            self.assertNotIn("javascript:alert(1)\"", text.replace("TEXT=\"javascript:alert(1)\"", "")
                             .replace('text="javascript:alert(1)"', ""))
            links = [e.get("url") or e.get("LINK") for e in root.iter() if e.get("url") or e.get("LINK")]
            for u in links:
                self.assertTrue(u.startswith("https://"), u)
            self.assertIn("https://ok.example/path?q=1&r=2", links)
            self.assertNotIn("https://ok.example/a b)", links)   # 含空白的網址不放

    def test_long_title_truncated_but_full_text_in_note(self):
        root = ET.fromstring(render("tree-opml", evil()))
        long_ = [o for o in root.iter("outline") if o.get("text", "").endswith("…") and o.get("text").startswith("長")]
        self.assertEqual(len(long_), 1)
        self.assertLessEqual(len(long_[0].get("text")), render_tree.TreeOpml.LIMIT)
        self.assertTrue(long_[0].get("_note").startswith("長" * 100))


class Xmind(unittest.TestCase):
    def _open(self, analysis):
        z = zipfile.ZipFile(io.BytesIO(render("tree-xmind", analysis)))
        self.assertIsNone(z.testzip())
        return z

    @staticmethod
    def _count(t):
        return 1 + sum(Xmind._count(c) for c in t.get("children", {}).get("attached", []))

    def test_files_and_content(self):
        z = self._open(sample())
        self.assertEqual(sorted(z.namelist()), ["content.json", "manifest.json", "metadata.json"])
        content = json.loads(z.read("content.json"))
        self.assertEqual(len(content), 1)
        sheet = content[0]
        self.assertEqual(sheet["class"], "sheet")
        root = sheet["rootTopic"]
        self.assertEqual(root["class"], "topic")
        self.assertEqual(root["title"], "台積電漲太多？鴻海卻漲不動")
        self.assertEqual(self._count(root), render_tree.build_tree(sample()).count())
        ids = []

        def collect(t):
            ids.append(t["id"])
            for c in t.get("children", {}).get("attached", []):
                collect(c)
        collect(root)
        self.assertEqual(len(ids), len(set(ids)))
        manifest = json.loads(z.read("manifest.json"))
        self.assertEqual(set(manifest["file-entries"]), {"content.json", "metadata.json"})
        meta = json.loads(z.read("metadata.json"))
        self.assertEqual(meta["activeSheetId"], sheet["id"])
        self.assertEqual(root["children"]["attached"][0]["notes"]["plain"]["content"], "先進封裝是重點")

    def test_folding_and_determinism(self):
        z = self._open(sample())
        root = json.loads(z.read("content.json"))[0]["rootTopic"]
        tsmc = root["children"]["attached"][0]
        self.assertNotIn("branch", tsmc)
        self.assertEqual(tsmc["children"]["attached"][-1]["branch"], "folded")   # 風險：第 2 層、有子節點
        self.assertEqual(render("tree-xmind", sample()), render("tree-xmind", sample()))

    def test_evil(self):
        z = self._open(evil())
        text = z.read("content.json").decode("utf-8")
        content = json.loads(text)
        self.assertEqual(content[0]["rootTopic"]["title"], "<script>alert(1)</script>")  # JSON 字串，不是可執行內容
        hrefs = []

        def walk(t):
            if "href" in t:
                hrefs.append(t["href"])
            for c in t.get("children", {}).get("attached", []):
                walk(c)
        walk(content[0]["rootTopic"])
        self.assertEqual(hrefs, ["https://ok.example/path?q=1&r=2"])


if __name__ == "__main__":
    unittest.main()
