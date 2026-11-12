"""health 接進 pipeline：失敗記帳、連續失敗後不再叫來源、成功清帳。完全離線，記帳檔放在暫存資料夾。"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes.config import Settings  # noqa: E402
from video_notes.errors import Remedy, ToolError  # noqa: E402
from video_notes.health import DEGRADED_AFTER, HealthBook  # noqa: E402
from video_notes.pipeline import JobOptions, Pipeline  # noqa: E402
from video_notes.profiles import PromptLibrary  # noqa: E402

from test_pipeline import (URL, FakeLLM, FakeSource, FakeStt, make_done_video,  # noqa: E402
                           _fail_if_called)

LIB = PromptLibrary(TOOL / "prompts")


class _OutdatedSource(FakeSource):
    def fetch_info(self, url):
        self.calls.append("fetch_info")
        raise ToolError("dependency_outdated", "yt-dlp 太舊", source="yt-dlp",
                        remedy=Remedy("needs_update", "升級 yt-dlp"))


class HealthWiringTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "out"
        self.root.mkdir()
        self.book = HealthBook(Path(self.tmp.name) / "health.json")      # 不碰真的 data\health.json
        self.version = mock.patch("video_notes.pipeline.ytdlp.version", lambda: "2026.1.1")
        self.version.start()
        self.addCleanup(self.version.stop)

    def pipeline(self, **kw) -> Pipeline:
        return Pipeline(Settings(), LIB, health=self.book, **kw)

    def opts(self, **kw) -> JobOptions:
        return JobOptions(plan=LIB.plan(), output_root=self.root, **kw)

    def test_fourth_run_raises_degraded_without_calling_the_source(self):
        source = _OutdatedSource()
        made = []

        def factory(url, settings):
            made.append(url)
            return source

        pipeline = self.pipeline(source_factory=factory)
        for _ in range(DEGRADED_AFTER):
            with self.assertRaises(ToolError) as ctx:
                pipeline.run(URL, self.opts())
            self.assertEqual(ctx.exception.code, "dependency_outdated")
        self.assertEqual(len(source.calls), DEGRADED_AFTER)
        entry = self.book.entries()["yt-dlp"]
        self.assertEqual((entry["state"], entry["count"], entry["version"]), ("degraded", 3, "2026.1.1"))

        with self.assertRaises(ToolError) as ctx:       # 第 4 次：直接丟，來源連建都不建
            pipeline.run(URL, self.opts())
        err = ctx.exception
        self.assertEqual((err.code, err.source, err.retryable), ("dependency_outdated", "yt-dlp", False))
        self.assertEqual(err.remedy.kind, "needs_update")
        self.assertEqual(len(made), DEGRADED_AFTER)
        self.assertEqual(len(source.calls), DEGRADED_AFTER)

    def test_new_ytdlp_version_gives_it_another_chance(self):
        pipeline = self.pipeline(source_factory=lambda u, s: _OutdatedSource())
        for _ in range(DEGRADED_AFTER):
            with self.assertRaises(ToolError):
                pipeline.run(URL, self.opts())
        with mock.patch("video_notes.pipeline.ytdlp.version", lambda: "2026.2.2"):
            with self.assertRaises(ToolError):
                pipeline.run(URL, self.opts())      # 版本變了 → 解除，又真的去叫來源一次
        self.assertEqual(self.book.entries()["yt-dlp"]["count"], 1)

    def test_clear_lets_it_try_again(self):
        source = _OutdatedSource()
        pipeline = self.pipeline(source_factory=lambda u, s: source)
        for _ in range(DEGRADED_AFTER):
            with self.assertRaises(ToolError):
                pipeline.run(URL, self.opts())
        self.book.clear()
        with self.assertRaises(ToolError):
            pipeline.run(URL, self.opts())
        self.assertEqual(len(source.calls), DEGRADED_AFTER + 1)

    def test_bad_input_is_not_recorded(self):
        class BadUrl(FakeSource):
            def fetch_info(self, url):
                raise ToolError("bad_input", "影片不存在")

        pipeline = self.pipeline(source_factory=lambda u, s: BadUrl())
        for _ in range(DEGRADED_AFTER + 1):
            with self.assertRaises(ToolError):
                pipeline.run(URL, self.opts())
        self.assertEqual(self.book.entries(), {})

    def test_successful_download_clears_earlier_failures(self):
        self.book.record_failure("yt-dlp", ToolError("rate_limited", "x"), "2026.1.1")
        art = make_done_video(self.root)
        art.media().unlink()                                    # 要重新下載
        art.audio.unlink()
        pipeline = self.pipeline(llm_factory=lambda s: FakeLLM(), source_factory=lambda u, s: FakeSource(),
                                 stt_factory=lambda s: FakeStt())
        with mock.patch("video_notes.pipeline.media.extract_audio", lambda m, a, f: a.write_bytes(b"x")):
            pipeline.run(URL, self.opts(notes=False))
        self.assertNotIn("yt-dlp", self.book.entries())

    def test_stt_failure_is_recorded_under_its_provider(self):
        class BoomStt(FakeStt):
            def transcribe(self, *a, **k):
                raise ToolError("auth_required", "沒有金鑰", source="stt:openai")

        art = make_done_video(self.root)
        art.transcript_json.unlink()
        pipeline = Pipeline(Settings(stt_provider="openai"), LIB, health=self.book, stt_factory=lambda s: BoomStt(),
                            source_factory=_fail_if_called)
        with self.assertRaises(ToolError):
            pipeline.run(URL, self.opts(notes=False))
        self.assertEqual(self.book.entries()["stt:openai"]["code"], "auth_required")

    def test_cloud_stt_fallback_records_the_cloud_failure(self):
        class Fallback(FakeStt):
            fallback_error = ToolError("rate_limited", "OpenAI 限流", source="stt:openai")

        art = make_done_video(self.root)
        art.transcript_json.unlink()
        pipeline = Pipeline(Settings(stt_provider="openai"), LIB, health=self.book,
                            stt_factory=lambda s: Fallback(fell_back=True), source_factory=_fail_if_called)
        pipeline.run(URL, self.opts(notes=False))
        self.assertEqual(self.book.entries()["stt:openai"]["code"], "rate_limited")

    def test_llm_failure_is_recorded_and_success_clears(self):
        class BoomLLM(FakeLLM):
            def stream(self, *a, **k):
                raise ToolError("rate_limited", "被限流", source="llm:fake")
                yield   # pragma: no cover

        make_done_video(self.root)
        pipeline = self.pipeline(llm_factory=lambda s: BoomLLM(), source_factory=_fail_if_called,
                                 stt_factory=_fail_if_called)
        with self.assertRaises(ToolError):
            pipeline.run(URL, self.opts())
        self.assertEqual(self.book.entries()["llm:fake"]["code"], "rate_limited")

        ok = self.pipeline(llm_factory=lambda s: FakeLLM(), source_factory=_fail_if_called,
                           stt_factory=_fail_if_called)
        ok.run(URL, self.opts())
        self.assertNotIn("llm:fake", self.book.entries())

    def test_default_pipeline_uses_the_module_book(self):
        from video_notes import health

        self.assertIs(Pipeline(Settings(), LIB).health, health.default())


if __name__ == "__main__":
    unittest.main()
