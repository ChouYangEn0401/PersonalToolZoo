"""流程（沿用 / 重做）、筆記組裝、socket 模式。用假的 LLM，完全離線。"""

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes.config import Settings  # noqa: E402
from video_notes.naming import Artifacts, classify, new_folder  # noqa: E402
from video_notes.notify import post_result  # noqa: E402
from video_notes.pipeline import JobOptions, Pipeline  # noqa: E402
from video_notes.profiles import PromptLibrary  # noqa: E402
from video_notes.summarize import NoteWriter, VideoContext, clean_body, split_chunks  # noqa: E402
from video_notes.transcribe import Segment, Transcript  # noqa: E402

LIB = PromptLibrary(TOOL / "prompts")
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


class FakeLLM:
    """記錄每次呼叫；分類問題回 JSON，其他回一份「筆記」。"""

    provider, model = "fake", "fake-1"

    def __init__(self):
        self.calls = []

    def stream(self, system, user, temperature=None, final=None):
        self.calls.append((system, user))
        if "影片分類助手" in system:
            text = '{"profile": "news", "reason": "記者在報導事件"}'
        elif "只處理其中一段" in system:
            text = f"- 第 {len(self.calls)} 段的重點"
        else:
            text = "```markdown\n# 模型自己加的標題\n## 發生什麼事\n動物園的大象。\n```"
        for piece in (text[:5], text[5:]):
            yield piece
        if final is not None:
            final["text"] = text


def make_done_video(root: Path, segments=None) -> Artifacts:
    """做出一個「已經下載、轉錄完」的影片資料夾，讓流程不用連網。"""
    ref = classify(URL)
    folder = new_folder(root, ref, "Me at the zoo")
    folder.mkdir(parents=True)
    art = Artifacts(folder)
    (folder / "media.m4a").write_bytes(b"fake")
    art.audio.write_bytes(b"fake")
    art.info.write_text(json.dumps({"video": {"title": "Me at the zoo", "uploader": "jawed", "duration": 19,
                                              "upload_date": "20050424"}}), encoding="utf-8")
    segments = segments or [Segment(0, 5, "Alright, so here we are, in front of the elephants."),
                            Segment(17, 19, "And that's pretty much all there is to say.")]
    Transcript("en", 19, segments).save(art.transcript_txt, art.transcript_srt, art.transcript_json)
    return art


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.art = make_done_video(self.root)
        self.llm = FakeLLM()
        self.pipeline = Pipeline(Settings(), LIB, llm_factory=lambda _s: self.llm)

    def run_pipeline(self, plan, redo=frozenset()):
        events = []
        result = self.pipeline.run(URL, JobOptions(plan=plan, output_root=self.root, redo=redo),
                                   emit=lambda n, d: events.append((n, d)))
        return result, {d["stage"]: d["state"] for n, d in events if n == "stage"}

    def test_auto_classifies_once_then_reuses_everything(self):
        result, states = self.run_pipeline(LIB.plan())
        self.assertEqual([states[s] for s in ("download", "audio", "transcribe")], ["reused"] * 3)
        self.assertEqual(states["notes"], "done")
        self.assertEqual(result["profile"], "news")
        self.assertEqual(len(self.llm.calls), 2)                 # 分類 + 筆記
        info = json.loads(self.art.info.read_text(encoding="utf-8"))
        self.assertEqual(info["auto_profile"], "news")
        notes = Path(result["notes_file"])
        self.assertEqual(notes.name, "notes.news.md")
        text = notes.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Me at the zoo\n"))   # 標題由程式產生
        self.assertNotIn("模型自己加的標題", text)
        self.assertNotIn("```", text)
        self.assertIn("📅 2005-04-24", text)

        result2, states2 = self.run_pipeline(LIB.plan())
        self.assertEqual(states2["notes"], "reused")
        self.assertEqual(len(self.llm.calls), 2)                 # 第二次完全沒有呼叫 LLM
        self.assertEqual(result2["notes"], text)

    def test_redo_notes_calls_llm_again_but_keeps_classification(self):
        self.run_pipeline(LIB.plan())
        self.run_pipeline(LIB.plan(), redo=frozenset({"notes"}))
        self.assertEqual(len(self.llm.calls), 3)                 # 只多一次筆記，分類沿用

    def test_different_plan_writes_a_separate_file(self):
        self.run_pipeline(LIB.plan("knowledge"))
        self.run_pipeline(LIB.plan("knowledge", ["timeline"]))
        names = sorted(p.name for p in self.art.all_notes())
        self.assertEqual(names, ["notes.knowledge+timeline.md", "notes.knowledge.md"])
        # 時間軸加料 → 逐字稿帶時間碼
        self.assertIn("[00:00]", self.llm.calls[-1][1])

    def test_without_notes_never_touches_llm(self):
        result, states = self.run_pipeline(LIB.plan())
        self.llm.calls.clear()
        self.pipeline.run(URL, JobOptions(plan=LIB.plan(), output_root=self.root, notes=False))
        self.assertEqual(self.llm.calls, [])


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


if __name__ == "__main__":
    unittest.main()
