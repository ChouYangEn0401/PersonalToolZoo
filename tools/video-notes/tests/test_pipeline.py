"""流程（沿用 / 重做）、分析 → 輸出、重新分析、只轉格式、socket 模式。用假的 LLM／來源／語音辨識，完全離線。"""

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes import analysis  # noqa: E402
from video_notes.adapters import render  # noqa: E402
from video_notes.config import Settings  # noqa: E402
from video_notes.errors import ToolError  # noqa: E402
from video_notes.naming import Artifacts, classify, new_folder  # noqa: E402
from video_notes.notify import post_result  # noqa: E402
from video_notes.pipeline import STAGES, JobOptions, Locks, Pipeline  # noqa: E402
from video_notes.profiles import PromptLibrary  # noqa: E402
from video_notes.summarize import NoteWriter, VideoContext, clean_body, split_chunks  # noqa: E402
from video_notes.transcribe import Segment, Transcript  # noqa: E402

LIB = PromptLibrary(TOOL / "prompts")
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

VALID_AI = {
    "summary": "記者在動物園的大象前面做了一段簡短的介紹。",
    "overview": "影片很短，只有一段開場與結尾。",
    "sections": [{"title": "發生什麼事", "summary": "", "points": ["動物園的大象。", "沒有其他內容。"],
                  "start": 0, "children": []}],
    "key_points": ["大象很長的鼻子"],
    "timeline": [{"time": 0, "label": "開場", "detail": ""}],
    "terms": [], "actions": [], "quotes": [], "perspectives": [], "caveats": [], "tags": ["動物園"],
    "layout_hint": {"template": "sheet", "tree_depth": 2},
}


class FakeLLM:
    """記錄每次呼叫；依 system prompt 回不同東西。

    analysis_replies：分析（及修復）呼叫依序要回的文字；用完後回合格的 JSON。
    """

    provider, model = "fake", "fake-1"

    def __init__(self, analysis_replies=None):
        self.calls = []
        self.analysis_replies = list(analysis_replies or [])

    def stream(self, system, user, temperature=None, final=None):
        self.calls.append((system, user))
        if "影片分類助手" in system:
            text = '{"profile": "news", "reason": "記者在報導事件"}'
        elif "只處理其中一段" in system:
            text = f"- 第 {len(self.calls)} 段的重點"
        elif "專業的影片筆記整理員" in system:      # 舊的 Markdown 寫法（降級用）
            text = "```markdown\n# 模型自己加的標題\n## 發生什麼事\n- 動物園的大象。\n```"
        elif self.analysis_replies:
            text = self.analysis_replies.pop(0)
        else:
            text = json.dumps(VALID_AI, ensure_ascii=False)
        for piece in (text[:5], text[5:]):
            yield piece
        if final is not None:
            final["text"] = text


class FakeSource:
    name = "fake"

    def __init__(self):
        self.calls = []

    def matches(self, url):
        return True

    def fetch_info(self, url):
        self.calls.append("fetch_info")
        return {"title": "Me at the zoo", "uploader": "jawed", "duration": 19, "upload_date": "20050424"}

    def download(self, url, folder, *, keep_video, on_progress=None, cancel=None):
        self.calls.append("download")
        (folder / "media.m4a").write_bytes(b"fake")
        if on_progress:
            on_progress(1.0, "done")


class FakeStt:
    name, model = "fake-stt", "tiny"

    def __init__(self, fell_back=False):
        self.fell_back = fell_back
        self.calls = 0

    def describe(self):
        return "fake stt"

    def transcribe(self, wav, *, language=None, on_progress=None, cancel=None):
        self.calls += 1
        return Transcript("en", 19, [Segment(0, 5, "Alright, so here we are, in front of the elephants.")])


def make_done_video(root: Path, segments=None) -> Artifacts:
    """做出一個「已經下載、轉錄完」的影片資料夾，讓流程不用連網。"""
    ref = classify(URL)
    folder = new_folder(root, ref, "Me at the zoo")
    folder.mkdir(parents=True)
    art = Artifacts(folder)
    (folder / "media.m4a").write_bytes(b"fake")
    art.audio.write_bytes(b"fake")
    art.info.write_text(json.dumps({"url": URL, "platform": ref.platform, "id": ref.video_id, "kind": ref.kind,
                                    "video": {"title": "Me at the zoo", "uploader": "jawed", "duration": 19,
                                              "upload_date": "20050424"}}), encoding="utf-8")
    segments = segments or [Segment(0, 5, "Alright, so here we are, in front of the elephants."),
                            Segment(17, 19, "And that's pretty much all there is to say.")]
    Transcript("en", 19, segments).save(art.transcript_txt, art.transcript_srt, art.transcript_json)
    return art


class _TextRenderer:
    name, label, extension, binary = "fake-tree", "假樹狀圖", ".txt", False

    def capabilities(self):
        return {}

    def check(self):
        return None

    def render(self, data, ctx):
        return "\n".join(s["title"] for s in data["sections"])


class _BoomRenderer(_TextRenderer):
    name = "boom"

    def render(self, data, ctx):
        raise ValueError("壞掉了")


def _fail_if_called(*_a, **_k):
    raise AssertionError("不該被呼叫")


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.art = make_done_video(self.root)
        self.llm = FakeLLM()
        self.settings = Settings()
        # 已經做完的影片不該碰來源與語音辨識
        self.pipeline = Pipeline(self.settings, LIB, llm_factory=lambda _s: self.llm,
                                 source_factory=_fail_if_called, stt_factory=_fail_if_called)
        for cls in (_TextRenderer, _BoomRenderer):
            render.REGISTRY.register(cls.name, lambda *a, _c=cls, **k: _c(), label=cls.label)

    def run_pipeline(self, plan, redo=frozenset(), **kw):
        events = []
        result = self.pipeline.run(URL, JobOptions(plan=plan, output_root=self.root, redo=redo, **kw),
                                   emit=lambda n, d: events.append((n, d)))
        return result, {d["stage"]: d["state"] for n, d in events if n == "stage"}

    def test_stages_include_outputs(self):
        self.assertIn("outputs", STAGES)
        self.assertLess(STAGES.index("notes"), STAGES.index("outputs"))

    def test_auto_classifies_once_then_reuses_everything(self):
        result, states = self.run_pipeline(LIB.plan())
        self.assertEqual([states[s] for s in ("download", "audio", "transcribe")], ["reused"] * 3)
        self.assertEqual(states["notes"], "done")
        self.assertEqual(result["profile"], "news")
        self.assertEqual(len(self.llm.calls), 2)                 # 分類 + 分析
        info = json.loads(self.art.info.read_text(encoding="utf-8"))
        self.assertEqual(info["auto_profile"], "news")
        notes = Path(result["notes_file"])
        self.assertEqual(notes.name, "notes.news.md")
        text = notes.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Me at the zoo\n"))   # 標題由程式產生
        self.assertIn("動物園的大象", text)
        self.assertIn("📅 2005-04-24", text)
        self.assertNotIn("```", text)

        data = analysis.load(Path(result["analysis_file"]))
        self.assertEqual(Path(result["analysis_file"]).name, "analysis.news.json")
        self.assertEqual(data["mode"]["profile"], "news")
        self.assertEqual(data["provenance"]["analyzer"], {"provider": "fake", "model": "fake-1"})
        self.assertEqual(data["provenance"]["prompt_version"], "news@1")
        self.assertIn("estimated_cost", data["quality_flags"])
        self.assertEqual(result["outputs"], {"markdown": str(notes)})

        result2, states2 = self.run_pipeline(LIB.plan())
        self.assertEqual(states2["notes"], "reused")
        self.assertEqual(len(self.llm.calls), 2)                 # 第二次完全沒有呼叫 LLM
        self.assertEqual(result2["notes"], text)

    def test_redo_notes_calls_llm_again_but_keeps_classification(self):
        self.run_pipeline(LIB.plan())
        self.run_pipeline(LIB.plan(), redo=frozenset({"notes"}))
        self.assertEqual(len(self.llm.calls), 3)                 # 只多一次分析，分類沿用

    def test_different_plan_writes_a_separate_file(self):
        self.run_pipeline(LIB.plan("knowledge"))
        self.run_pipeline(LIB.plan("knowledge", ["timeline"]))
        self.assertEqual(sorted(p.name for p in self.art.all_notes()),
                         ["notes.knowledge+timeline.md", "notes.knowledge.md"])
        self.assertEqual(sorted(p.name for p in self.art.all_analyses()),
                         ["analysis.knowledge+timeline.json", "analysis.knowledge.json"])
        system, user = self.llm.calls[-1]
        self.assertIn("[00:00]", user)                           # 逐字稿帶時間碼
        self.assertIn("`timeline` 欄位", system)                 # 時間軸加料 → 寫進 timeline 欄位

    def test_without_notes_never_touches_llm(self):
        self.run_pipeline(LIB.plan())
        self.llm.calls.clear()
        self.pipeline.run(URL, JobOptions(plan=LIB.plan(), output_root=self.root, notes=False))
        self.assertEqual(self.llm.calls, [])

    def test_legacy_folder_with_only_notes_is_reused_without_tokens(self):
        legacy = self.art.notes("knowledge")
        legacy.write_text("# 舊筆記\n\n舊的內容\n", encoding="utf-8")
        result, states = self.run_pipeline(LIB.plan("knowledge"))
        self.assertEqual(states["notes"], "reused")
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(result["notes"], "# 舊筆記\n\n舊的內容\n")
        self.assertEqual(result["analysis_file"], "")
        # 要其他輸出就得先分析（舊筆記不會被當成 analysis）
        result2, _ = self.run_pipeline(LIB.plan("knowledge"), outputs=("fake-tree",))
        self.assertEqual(len(self.llm.calls), 1)
        self.assertIn("fake-tree", result2["outputs"])

    def test_extra_outputs_and_a_failing_one_does_not_fail_the_video(self):
        result, states = self.run_pipeline(LIB.plan("knowledge"), outputs=("fake-tree", "boom", "markdown"))
        self.assertEqual(states["outputs"], "done")
        out = Path(result["outputs"]["fake-tree"])
        self.assertEqual(out, self.art.outputs_dir / "knowledge.fake-tree.txt")
        self.assertEqual(out.read_text(encoding="utf-8"), "發生什麼事")
        self.assertNotIn("boom", result["outputs"])
        self.assertIn("壞掉了", result["output_errors"]["boom"])
        self.assertTrue(Path(result["notes_file"]).exists())

    def test_default_outputs_come_from_settings(self):
        self.settings.outputs = ["fake-tree"]
        result, _ = self.run_pipeline(LIB.plan("knowledge"))
        self.assertIn("fake-tree", result["outputs"])

    def test_render_reads_analysis_only(self):
        self.run_pipeline(LIB.plan("knowledge"))
        calls = len(self.llm.calls)
        paths = self.pipeline.render(self.art.folder, "knowledge", ["fake-tree", "markdown"])
        self.assertEqual(len(self.llm.calls), calls)             # 不呼叫 AI
        self.assertTrue(Path(paths["fake-tree"]).exists())
        self.assertEqual(Path(paths["markdown"]).name, "notes.knowledge.md")

    def test_render_without_analysis_says_to_reanalyze(self):
        with self.assertRaises(ToolError) as cm:
            self.pipeline.render(self.art.folder, "knowledge", ["markdown"])
        self.assertEqual(cm.exception.code, "bad_input")
        self.assertIn("重新分析", cm.exception.remedy.action)

    def test_reanalyze_reuses_transcript_without_download(self):
        self.run_pipeline(LIB.plan("knowledge"))
        calls = len(self.llm.calls)
        result = self.pipeline.reanalyze(self.art.folder, LIB.plan("knowledge"), outputs=("fake-tree",))
        self.assertEqual(len(self.llm.calls), calls + 1)         # 只多一次分析
        self.assertIn("fake-tree", result["outputs"])
        self.assertEqual(result["title"], "Me at the zoo")
        self.assertTrue(result["notes"].startswith("# Me at the zoo"))

    def test_reanalyze_without_transcript_fails_clearly(self):
        empty = self.root / "空資料夾 [video-aaaaaaaaaaa]"
        empty.mkdir()
        with self.assertRaises(ToolError) as cm:
            self.pipeline.reanalyze(empty, LIB.plan("knowledge"))
        self.assertEqual(cm.exception.code, "bad_input")

    def test_corrupt_analysis_file_is_redone(self):
        self.run_pipeline(LIB.plan("knowledge"))
        self.art.analysis("knowledge").write_text("{壞掉", encoding="utf-8")
        self.run_pipeline(LIB.plan("knowledge"))
        analysis.load(self.art.analysis("knowledge"))            # 又是好的了


class FreshDownloadTest(unittest.TestCase):
    """從零開始：來源與語音辨識都走注入的假 adapter。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def run_fresh(self, stt):
        source, llm = FakeSource(), FakeLLM()
        pipeline = Pipeline(Settings(), LIB, llm_factory=lambda _s: llm, source_factory=lambda _u, _s: source,
                            stt_factory=lambda _s: stt)

        def fake_audio(media_file, wav, ffmpeg):
            wav.write_bytes(b"wav")

        with mock.patch("video_notes.pipeline.media.extract_audio", fake_audio):
            result = pipeline.run(URL, JobOptions(plan=LIB.plan("knowledge"), output_root=self.root))
        return result, source, llm

    def test_source_and_stt_adapters_are_used(self):
        stt = FakeStt()
        result, source, _ = self.run_fresh(stt)
        self.assertEqual(source.calls, ["fetch_info", "download"])
        self.assertEqual(stt.calls, 1)
        data = analysis.load(Path(result["analysis_file"]))
        self.assertEqual(data["provenance"]["stt"], {"adapter": "fake-stt", "model": "tiny"})
        self.assertNotIn("stt_fallback_local", data["quality_flags"])
        self.assertEqual(data["provenance"]["source_hash"], analysis.source_hash("youtube", "jNQXAC9IVRw"))

    def test_stt_fallback_is_flagged_in_analysis(self):
        result, _, _ = self.run_fresh(FakeStt(fell_back=True))
        data = analysis.load(Path(result["analysis_file"]))
        self.assertIn("stt_fallback_local", data["quality_flags"])
        # 之後沿用逐字稿重新分析，旗標還在（記在 info.json）
        pipeline = Pipeline(Settings(), LIB, llm_factory=lambda _s: FakeLLM(),
                            source_factory=_fail_if_called, stt_factory=_fail_if_called)
        again = pipeline.reanalyze(result["folder"], LIB.plan("knowledge"))
        self.assertIn("stt_fallback_local", analysis.load(Path(again["analysis_file"]))["quality_flags"])


class LocksTest(unittest.TestCase):
    def test_download_limit_follows_settings(self):
        locks = Locks.from_settings(Settings(max_parallel_downloads=1))
        self.assertTrue(locks.download.acquire(blocking=False))
        self.assertFalse(locks.download.acquire(blocking=False))
        locks = Locks.from_settings(Settings(max_parallel_downloads=3))
        self.assertEqual(sum(locks.download.acquire(blocking=False) for _ in range(5)), 3)


class SummarizeTest(unittest.TestCase):
    def test_split_chunks_keeps_paragraphs_whole(self):
        paras = ["甲" * 40, "乙" * 40, "丙" * 40]
        chunks = split_chunks(paras, limit=90)
        self.assertEqual(chunks, ["甲" * 40 + "\n\n" + "乙" * 40, "丙" * 40])

    def test_long_transcript_is_mapped_then_reduced(self):
        segs = [Segment(i * 10, i * 10 + 5, f"第{i}句" + "內容" * 50) for i in range(12)]
        llm = FakeLLM()
        writer = NoteWriter(llm, LIB, long_chars=500)
        ctx = VideoContext(url=URL, kind="video", title="長影片")
        notes = writer.write(LIB.plan("general"), "general", Transcript("zh", 120, segs), ctx)
        systems = [s for s, _ in llm.calls]
        self.assertGreater(sum("只處理其中一段" in s for s in systems), 0)
        self.assertIn("<partial_notes>", llm.calls[-1][1])
        self.assertTrue(notes.startswith("# 長影片"))

    def test_clean_body(self):
        self.assertEqual(clean_body("```md\n# 標題\n## 重點\n- a\n```"), "## 重點\n- a\n")

    def test_video_info_block(self):
        ctx = VideoContext(url=URL, kind="short", title="T", uploader="U", duration=75, upload_date="20260110",
                           description="d" * 3000, chapters=[{"start_time": 65, "title": "結論"}])
        block = ctx.block()
        self.assertIn("類型：短影音", block)
        self.assertIn("長度：01:15", block)
        self.assertIn("- 01:05 結論", block)
        self.assertIn("以下省略", block)


class NotifyTest(unittest.TestCase):
    def test_post_result_sends_json(self):
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.handle_request, daemon=True).start()
        ok, message = post_result(f"http://127.0.0.1:{server.server_address[1]}/hook",
                                  {"title": "影片", "notes": "# 筆記", "files": {}}, config={"timeout": 5})
        server.server_close()
        self.assertTrue(ok, message)
        self.assertEqual(received["body"]["event"], "video-notes.completed")
        self.assertEqual(received["body"]["notes"], "# 筆記")

    def test_unreachable_target_does_not_raise(self):
        ok, message = post_result("http://127.0.0.1:9/nothing", {"files": {}}, config={"timeout": 2})
        self.assertFalse(ok)
        self.assertIn("連不上", message)

    def test_result_keeps_old_keys_and_adds_new_ones(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        make_done_video(Path(tmp.name))
        pipeline = Pipeline(Settings(), LIB, llm_factory=lambda _s: FakeLLM(),
                            source_factory=_fail_if_called, stt_factory=_fail_if_called)
        result = pipeline.run(URL, JobOptions(plan=LIB.plan("news"), output_root=Path(tmp.name)))
        for key in ("notes", "notes_file", "profile", "profile_reason", "analysis_file", "outputs"):
            self.assertIn(key, result)
        json.dumps(result)   # 要能序列化成 JSON 才能 POST


if __name__ == "__main__":
    unittest.main()
