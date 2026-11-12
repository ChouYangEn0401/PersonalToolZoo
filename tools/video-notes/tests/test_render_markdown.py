"""Markdown 輸出 adapter：版面、跳脫（惡意字串）、很長的字串、降級提醒、合併標頭。完全離線。"""

import copy
import sys
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs"), str(TOOL / "tests")]

from video_notes import analysis  # noqa: E402
from video_notes.adapters import render, render_markdown  # noqa: E402
from video_notes.adapters.render_markdown import esc, esc_line, safe_url  # noqa: E402

CTX = render.RenderContext(profile_name="📰 新聞快訊", modifier_names=["時間軸"])


def sample(**over) -> dict:
    data = analysis.new_analysis(
        title="台積電漲太多？", mode={"profile": "news", "modifiers": ["timeline"], "focus": ""}, language="zh",
        sources=[analysis.source_entry(platform="youtube", video_id="abcdefghijk", url="https://youtu.be/abcdefghijk",
                                       title="台積電漲太多？", channel="某頻道", duration=1520, date="2026-10-01")])
    data.update({
        "summary": "主持人認為台積電短線過熱。",
        "overview": "第一段概述。\n\n第二段概述。",
        "sections": [
            {"title": "台積電", "summary": "先進封裝", "points": ["產能翻倍", "毛利率 58%"], "start": 62,
             "children": [{"title": "風險", "summary": "", "points": ["匯率"], "start": None,
                           "children": [{"title": "更深一層", "summary": "", "points": ["地緣政治"],
                                         "start": 3700, "children": []}]}]},
            {"title": "鴻海", "summary": "", "points": ["AI 伺服器毛利低"], "start": None, "children": []},
        ],
        "key_points": ["重點甲"],
        "timeline": [{"time": 62, "label": "法說會", "detail": "重點"}, {"time": None, "label": "結尾", "detail": ""}],
        "terms": [{"term": "CoWoS", "definition": "先進封裝"}],
        "actions": ["追蹤法說會"],
        "quotes": [{"text": "不要追高", "speaker": "主持人", "time": 95}],
        "perspectives": [{"who": "主持人", "stance": "過熱"}],
        "caveats": ["不構成投資建議"],
        "tags": ["台積電", "AI"],
    })
    data.update(over)
    return analysis.normalize(data)


def md(data, ctx=CTX) -> str:
    return render_markdown.MarkdownRenderer().render(data, ctx)


class LayoutTest(unittest.TestCase):
    def test_registered_under_fixed_name(self):
        self.assertIn("markdown", render.REGISTRY)
        r = render.REGISTRY.create("markdown")
        self.assertEqual((r.name, r.extension, r.binary), ("markdown", ".md", False))
        self.assertEqual(r.capabilities()["group"], "notes")
        self.assertIsNone(r.check())

    def test_header_matches_old_format(self):
        text = md(sample())
        self.assertTrue(text.startswith(
            "# 台積電漲太多？\n\n> 🔗 https://youtu.be/abcdefghijk · 📺 某頻道 · ⏱ 25:20 · 📅 2026-10-01 · "
            "📰 新聞快訊 + 時間軸\n\n---\n"), text[:200])

    def test_focus_in_header(self):
        data = sample()
        data["mode"]["focus"] = "毛利率"
        self.assertIn("（關注：毛利率）", md(data))

    def test_body_blocks(self):
        text = md(sample())
        for expected in ("**摘要**：主持人認為台積電短線過熱。", "第二段概述。", "## 台積電（01:02）", "先進封裝",
                         "- 產能翻倍", "### 風險", "- **更深一層**（1:01:40）", "  - 地緣政治", "## 鴻海",
                         "## 關鍵重點", "## 時間軸", "- **01:02** 法說會：重點", "- 結尾", "## 名詞解釋",
                         "- **CoWoS**：先進封裝", "## 行動清單", "- [ ] 追蹤法說會", "## 金句",
                         "> 不要追高 —— 主持人 01:35", "## 各方說法", "- **主持人**：過熱", "## 注意事項",
                         "標籤：台積電、AI"):
            self.assertIn(expected, text)

    def test_empty_blocks_are_omitted(self):
        text = md(sample(timeline=[], terms=[], actions=[], quotes=[], perspectives=[], caveats=[], key_points=[]))
        for title in ("時間軸", "名詞解釋", "行動清單", "金句", "各方說法", "注意事項", "關鍵重點"):
            self.assertNotIn(f"## {title}", text)

    def test_collection_header_lists_sources(self):
        data = sample(kind="collection", title="本週財經")
        data["sources"].append(analysis.source_entry(platform="youtube", video_id="zzzzzzzzzzz",
                                                     url="https://youtu.be/zzzzzzzzzzz", title="第二支", channel="乙"))
        text = md(data)
        self.assertIn("> 📚 合併 2 支影片", text)
        self.assertIn("## 來源影片", text)
        self.assertIn("- 第二支 · 乙 · https://youtu.be/zzzzzzzzzzz", text)
        self.assertNotIn("🔗", text.split("---")[0])

    def test_flags_add_a_warning_line(self):
        data = sample()
        analysis.add_flag(data, "schema_repair_failed")
        analysis.add_flag(data, "stt_fallback_local")
        analysis.add_flag(data, "estimated_cost")     # 這個不用提醒
        head = md(data).split("---")[0]
        self.assertIn("> ⚠ ", head)
        self.assertIn("簡化版本", head)
        self.assertIn("本機模型", head)
        self.assertNotIn("估計", head)
        self.assertNotIn("⚠", md(sample()))

    def test_fallback_header_helper(self):
        data = sample()
        analysis.add_flag(data, "schema_repair_failed")
        head = "\n".join(render_markdown.header(data, CTX))
        self.assertIn("簡化版本", head)


class EscapingTest(unittest.TestCase):
    def test_line_start_syntax_is_escaped(self):
        self.assertEqual(esc("# 假標題"), "\\# 假標題")
        self.assertEqual(esc("- 假清單"), "\\- 假清單")
        self.assertEqual(esc("1. 假編號"), "\\1. 假編號")
        self.assertEqual(esc("2) 假編號"), "\\2) 假編號")
        self.assertEqual(esc("> 假引言"), "\\> 假引言")
        self.assertEqual(esc("=== 底線"), "\\=== 底線")
        self.assertEqual(esc("---"), "\\---")
        self.assertEqual(esc("| a | b |"), "\\| a | b |")

    def test_inline_syntax_is_escaped(self):
        self.assertEqual(esc("<script>alert(1)</script>"), "\\<script\\>alert(1)\\</script\\>")
        self.assertEqual(esc("[點我](javascript:alert(1))"), "\\[點我\\](javascript:alert(1))")
        self.assertEqual(esc("![x](http://e/x.png)"), "!\\[x\\](http://e/x.png)")
        self.assertEqual(esc("a *b* `c` ~d~"), "a \\*b\\* \\`c\\` \\~d\\~")
        self.assertEqual(esc("反斜線 \\ 結尾"), "反斜線 \\\\ 結尾")

    def test_malicious_strings_everywhere(self):
        evil = "# <script>alert(1)</script>\n[x](javascript:alert(1))"
        data = sample(title=evil, summary=evil, overview=evil, key_points=[evil], caveats=[evil], tags=[evil])
        data["sections"] = [{"title": evil, "summary": evil, "points": [evil], "start": None,
                             "children": [{"title": evil, "summary": "", "points": [evil], "start": None,
                                           "children": []}]}]
        data["timeline"] = [{"time": 1, "label": evil, "detail": evil}]
        data["terms"] = [{"term": evil, "definition": evil}]
        data["actions"] = [evil]
        data["quotes"] = [{"text": evil, "speaker": evil, "time": 1}]
        data["perspectives"] = [{"who": evil, "stance": evil}]
        data["sources"][0]["channel"] = evil
        text = md(data)
        self.assertNotIn("<script>", text)
        self.assertNotIn("</script>", text)
        self.assertNotRegex(text, r"(?m)^#(?! |#)")                    # 沒有被偽造的標頭以外的 #
        self.assertEqual(len([ln for ln in text.splitlines() if ln.startswith("# ")]), 1)   # 只有程式產生的標題
        self.assertNotRegex(text, r"(?<!\\)\[x\]\(javascript")         # 沒有可點的 javascript 連結
        for line in text.splitlines():
            self.assertFalse(line.lstrip().startswith("<"), line)

    def test_multiline_overview_each_line_escaped(self):
        text = md(sample(overview="第一行\n# 假標題\n- 假清單"))
        self.assertIn("第一行\n\\# 假標題\n\\- 假清單", text)

    def test_urls_only_http(self):
        self.assertEqual(safe_url("https://a.com/x?y=1"), "https://a.com/x?y=1")
        self.assertEqual(safe_url("javascript:alert(1)"), "")
        self.assertEqual(safe_url("file:///c:/secret"), "")
        self.assertEqual(safe_url(""), "")
        self.assertEqual(safe_url("https://a.com/a)<x>"), "https://a.com/a%29%3Cx%3E")
        self.assertEqual(safe_url("https://a.com/a b"), "")
        data = sample()
        data["sources"][0]["url"] = "javascript:alert(1)"
        text = md(data)
        self.assertNotIn("javascript", text)
        self.assertNotIn("🔗", text)

    def test_very_long_strings_are_clipped(self):
        long = "字" * 200000
        data = sample(summary=long, overview=long, title=long)
        data["sections"][0]["points"] = [long] * 3 + ["正常"] * 5
        text = md(data)
        self.assertLess(len(text), 40000)
        self.assertIn("…", text)
        self.assertIn("- 正常", text)
        self.assertLess(len(esc_line("a" * 10)), 20)

    def test_huge_lists_are_capped(self):
        data = sample(key_points=[f"點{i}" for i in range(5000)])
        text = md(data)
        self.assertLess(text.count("\n- 點"), 600)

    def test_does_not_mutate_input(self):
        data = sample()
        before = copy.deepcopy(data)
        md(data)
        self.assertEqual(data, before)

    def test_minimal_analysis_renders(self):
        data = analysis.new_analysis(title="空的")
        text = md(data, render.RenderContext())
        self.assertTrue(text.startswith("# 空的\n"))


if __name__ == "__main__":
    unittest.main()
