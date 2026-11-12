"""語音辨識 adapter：註冊、退路、切段時間碼、錯誤轉換。完全離線：假 SDK client、假 ffmpeg，不載入模型。"""

import math
import os
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes.adapters import stt, stt_chunk  # noqa: E402
from video_notes.adapters.stt_gemini import GeminiStt  # noqa: E402
from video_notes.adapters.stt_local import LocalStt  # noqa: E402
from video_notes.adapters.stt_openai import OpenAIStt  # noqa: E402
from video_notes.config import Settings  # noqa: E402
from video_notes.errors import ToolError  # noqa: E402
from video_notes.transcribe import Cancelled, Segment, Transcript  # noqa: E402

SECRET = "sk-testkey1234567890abcdefXYZ"
KEY_ENV = ("OPENAI_API_KEY", "CHATGPT_API_KEY", "OPENAI_KEY", "OPENAI_APIKEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")


def make_wav(path: Path, seconds: int) -> Path:
    """假裝 seconds 秒長的 wav：取樣率設成 100 Hz，檔案很小，wav_duration 讀到的秒數正確。"""
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(100)
        fh.writeframes(b"\x00\x00" * 100 * seconds)
    return path


def fake_ffmpeg_run(calls=None, fail=False):
    """取代 subprocess.run：依 -segment_time 在輸出資料夾寫出假的 mp3 段落。"""
    def run(cmd, **kwargs):
        if calls is not None:
            calls.append(cmd)
        if fail:
            return SimpleNamespace(returncode=1, stderr="boom", stdout="")
        seg = int(cmd[cmd.index("-segment_time") + 1])
        src = Path(cmd[cmd.index("-i") + 1])
        with wave.open(str(src), "rb") as fh:
            total = fh.getnframes() / fh.getframerate()
        out = Path(cmd[-1]).parent
        for i in range(math.ceil(total / seg)):
            (out / f"chunk_{i:04d}.mp3").write_bytes(b"ID3fake")
        return SimpleNamespace(returncode=0, stderr="", stdout="")
    return run


class ApiError(Exception):
    def __init__(self, msg, status_code=None, body=None):
        super().__init__(msg)
        self.status_code = status_code
        self.body = body


class FakeTranscriptions:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.handler(len(self.calls), kwargs)


def openai_client(handler):
    trans = FakeTranscriptions(handler)
    return SimpleNamespace(audio=SimpleNamespace(transcriptions=trans)), trans


def gemini_client(handler):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return handler(len(calls), kwargs)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), calls


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        env = {k: "" for k in KEY_ENV}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for target in ("toolzoo.ai.keys.env_files",):
            p = mock.patch(target, return_value=[])
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(stt_chunk.subprocess, "run", side_effect=fake_ffmpeg_run())
        self.run_mock = p.start()
        self.addCleanup(p.stop)
        self.settings = Settings(traditional=False)

    def set_key(self, name="OPENAI_API_KEY", value=SECRET):
        os.environ[name] = value

    def leftovers(self):
        return [p for p in self.dir.iterdir() if p.name.startswith("stt-chunks-")]


class RegistryTests(Base):
    def test_builtin_registered_local_first(self):
        stt.load_builtin()
        names = stt.REGISTRY.names()
        self.assertEqual(names[0], "local")
        self.assertIn("openai", names)
        self.assertIn("gemini", names)

    def test_build_local_has_no_fallback_wrapper(self):
        adapter = stt.build_stt(Settings(stt_provider="local", stt_fallback_local=True))
        self.assertIsInstance(adapter, LocalStt)
        self.assertFalse(getattr(adapter, "fell_back", False))

    def test_build_cloud_wraps_only_when_fallback_enabled(self):
        wrapped = stt.build_stt(Settings(stt_provider="openai", stt_fallback_local=True))
        self.assertIsInstance(wrapped, stt.FallbackStt)
        self.assertIsInstance(wrapped.primary, OpenAIStt)
        self.assertIsInstance(wrapped.local, LocalStt)
        plain = stt.build_stt(Settings(stt_provider="gemini", stt_fallback_local=False))
        self.assertIsInstance(plain, GeminiStt)

    def test_unknown_provider_is_config_invalid(self):
        with self.assertRaises(ToolError) as ctx:
            stt.build_stt(Settings(stt_provider="nope"))
        self.assertEqual(ctx.exception.code, "config_invalid")

    def test_capabilities_and_describe(self):
        for adapter, privacy in ((LocalStt(self.settings), "local"), (OpenAIStt(self.settings), "cloud"),
                                 (GeminiStt(self.settings), "cloud")):
            caps = adapter.capabilities()
            self.assertEqual(caps["privacy"], privacy)
            self.assertEqual(caps["needs_network"], privacy == "cloud")
            self.assertTrue(adapter.describe())
        self.assertEqual(OpenAIStt(self.settings).model, "gpt-4o-transcribe")
        self.assertEqual(OpenAIStt(Settings(stt_model="whisper-1")).model, "whisper-1")

    def test_local_check_uses_find_spec_without_loading(self):
        with mock.patch("importlib.util.find_spec", return_value=None):
            err = LocalStt(self.settings).check()
        self.assertEqual(err.code, "dependency_missing")
        with mock.patch("importlib.util.find_spec", return_value=object()):
            self.assertIsNone(LocalStt(self.settings).check())

    def test_cloud_check_needs_key(self):
        self.assertEqual(OpenAIStt(self.settings).check().code, "auth_required")
        self.assertEqual(GeminiStt(self.settings).check().code, "auth_required")
        self.set_key()
        self.assertIsNone(OpenAIStt(self.settings).check())


class ChunkTests(Base):
    def test_spread_text_proportional(self):
        segs = stt_chunk.spread_text("第一句。第二句比較長一點。", 100.0, 110.0)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].start, 100.0)
        self.assertEqual(segs[-1].end, 110.0)
        self.assertEqual(segs[0].end, segs[1].start)
        self.assertLess(segs[0].end - segs[0].start, segs[1].end - segs[1].start)
        self.assertEqual(stt_chunk.spread_text("   ", 0, 5), [])

    def test_whisper1_segment_timestamps_are_offset(self):
        self.set_key()
        wav = make_wav(self.dir / "audio.wav", 1500)   # 600 秒一段 → 3 段

        def handler(n, kw):
            return SimpleNamespace(text="x", language="english", segments=[
                {"start": 1.0, "end": 2.0, "text": f"chunk{n}-a"}, {"start": 5.0, "end": 6.5, "text": f"chunk{n}-b"}])
        client, trans = openai_client(handler)
        adapter = OpenAIStt(Settings(stt_model="whisper-1", traditional=False), client_factory=lambda k: client,
                            ffmpeg="ffmpeg")
        seen = []
        result = adapter.transcribe(wav, on_progress=lambda p, t: seen.append(p))
        starts = [(s.start, s.text) for s in result.segments]
        self.assertEqual(starts, [(1.0, "chunk1-a"), (5.0, "chunk1-b"), (601.0, "chunk2-a"), (605.0, "chunk2-b"),
                                  (1201.0, "chunk3-a"), (1205.0, "chunk3-b")])
        self.assertEqual(result.segments[-1].end, 1206.5)
        self.assertEqual(result.duration, 1500.0)
        self.assertEqual(result.language, "en")
        self.assertEqual(trans.calls[0]["response_format"], "verbose_json")
        self.assertEqual(seen[-1], 1.0)
        self.assertEqual(self.leftovers(), [])   # 暫存清乾淨

    def test_text_only_model_spreads_within_each_chunk(self):
        self.set_key()
        wav = make_wav(self.dir / "audio.wav", 1000)   # 600 + 400

        def handler(n, kw):
            return SimpleNamespace(text="你好。今天天氣很好。" if n == 1 else "第二段。")
        client, trans = openai_client(handler)
        adapter = OpenAIStt(self.settings, client_factory=lambda k: client, ffmpeg="ffmpeg")
        result = adapter.transcribe(wav, language="zh")
        self.assertEqual(trans.calls[0]["response_format"], "json")
        self.assertEqual(trans.calls[0]["language"], "zh")
        first = [s for s in result.segments if s.start < 600]
        second = [s for s in result.segments if s.start >= 600]
        self.assertEqual(first[0].start, 0.0)
        self.assertEqual(first[-1].end, 600.0)
        self.assertEqual(second[0].start, 600.0)
        self.assertEqual(second[-1].end, 1000.0)
        self.assertEqual(result.language, "zh")

    def test_traditional_conversion_for_chinese(self):
        from video_notes.transcribe import _opencc
        if _opencc() is None:
            self.skipTest("沒有 opencc")
        self.set_key()
        wav = make_wav(self.dir / "audio.wav", 30)
        client, _ = openai_client(lambda n, kw: SimpleNamespace(text="软件开发很有意思。"))
        on = OpenAIStt(Settings(traditional=True), client_factory=lambda k: client, ffmpeg="ffmpeg")
        off = OpenAIStt(Settings(traditional=False), client_factory=lambda k: client, ffmpeg="ffmpeg")
        self.assertNotIn("软", on.transcribe(wav, language="zh").plain_text())
        self.assertIn("软", off.transcribe(wav, language="zh").plain_text())

    def test_gemini_sends_input_audio_and_uses_chunks(self):
        self.set_key("GEMINI_API_KEY", "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE123")
        wav = make_wav(self.dir / "audio.wav", 700)   # 300 秒一段 → 3 段
        client, calls = gemini_client(lambda n, kw: SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=f"第{n}段內容。"))]))
        adapter = GeminiStt(self.settings, client_factory=lambda k: client, ffmpeg="ffmpeg")
        result = adapter.transcribe(wav)
        self.assertEqual(len(calls), 3)
        audio = calls[0]["messages"][0]["content"][1]
        self.assertEqual(audio["type"], "input_audio")
        self.assertEqual(audio["input_audio"]["format"], "mp3")
        self.assertEqual([s.start for s in result.segments], [0.0, 300.0, 600.0])
        self.assertEqual(result.segments[-1].end, 700.0)

    def test_cancel_raises_cancelled_and_cleans_up(self):
        self.set_key()
        wav = make_wav(self.dir / "audio.wav", 1500)
        cancel = threading.Event()

        def handler(n, kw):
            cancel.set()
            return SimpleNamespace(text="a。")
        client, trans = openai_client(handler)
        adapter = OpenAIStt(self.settings, client_factory=lambda k: client, ffmpeg="ffmpeg")
        with self.assertRaises(Cancelled):
            adapter.transcribe(wav, cancel=cancel)
        self.assertEqual(len(trans.calls), 1)
        self.assertEqual(self.leftovers(), [])

    def test_ffmpeg_missing_and_failure(self):
        self.set_key()
        wav = make_wav(self.dir / "audio.wav", 30)
        client, _ = openai_client(lambda n, kw: SimpleNamespace(text="a"))
        with mock.patch("toolzoo.ytdlp.find_ffmpeg", return_value=None):
            with self.assertRaises(ToolError) as ctx:
                OpenAIStt(self.settings, client_factory=lambda k: client).transcribe(wav)
        self.assertEqual(ctx.exception.code, "dependency_missing")
        self.run_mock.side_effect = fake_ffmpeg_run(fail=True)
        with self.assertRaises(ToolError) as ctx:
            OpenAIStt(self.settings, client_factory=lambda k: client, ffmpeg="ffmpeg").transcribe(wav)
        self.assertEqual(ctx.exception.code, "bad_input")
        self.assertEqual(self.leftovers(), [])


class ErrorTests(Base):
    def run_with(self, exc, cls=OpenAIStt):
        self.set_key()
        self.set_key("GEMINI_API_KEY", SECRET)
        wav = make_wav(self.dir / "audio.wav", 30)

        def boom(n, kw):
            raise exc
        if cls is OpenAIStt:
            client, _ = openai_client(boom)
        else:
            client, _ = gemini_client(boom)
        with self.assertRaises(ToolError) as ctx:
            cls(self.settings, client_factory=lambda k: client, ffmpeg="ffmpeg").transcribe(wav)
        return ctx.exception

    def test_status_codes_map_to_codes(self):
        cases = [(401, "auth_expired"), (403, "auth_required"), (404, "config_invalid"), (429, "rate_limited"),
                 (400, "bad_input"), (413, "bad_input"), (503, "network_unreachable")]
        for status, code in cases:
            with self.subTest(status=status):
                err = self.run_with(ApiError(f"HTTP {status} key={SECRET}", status))
                self.assertEqual(err.code, code)
                self.assertTrue(err.remedy.action or err.remedy.kind == "none")

    def test_quota_and_network(self):
        err = self.run_with(ApiError("quota", 429, {"error": {"code": "insufficient_quota"}}))
        self.assertEqual(err.code, "resource_exhausted")
        self.assertFalse(err.retryable)
        err = self.run_with(type("APIConnectionError", (Exception,), {})("Connection error."))
        self.assertEqual(err.code, "network_unreachable")
        self.assertTrue(err.retryable)

    def test_unknown_error_is_internal_not_swallowed(self):
        err = self.run_with(ValueError("weird"))
        self.assertEqual(err.code, "internal_bug")

    def test_gemini_errors_too(self):
        err = self.run_with(ApiError("bad", 401), cls=GeminiStt)
        self.assertEqual(err.code, "auth_expired")
        self.assertIn("GEMINI_API_KEY", err.remedy.action)

    def test_key_never_in_error_text(self):
        for status in (401, 429, 500, 400, None):
            err = self.run_with(ApiError(f"failed with Authorization: Bearer {SECRET} and key {SECRET}", status))
            blob = str(err) + repr(err.to_dict())
            self.assertNotIn(SECRET, blob)
            self.assertNotIn("testkey1234567890", blob)

    def test_plain_unknown_key_is_scrubbed_by_literal(self):
        odd = "my-odd-compat-token"
        err = stt_chunk.to_tool_error(ApiError(f"nope {odd}", 500), source="x", service="S", key=odd)
        self.assertNotIn(odd, repr(err.to_dict()))

    def test_missing_key_raises_auth_required_before_any_work(self):
        wav = make_wav(self.dir / "audio.wav", 30)
        with self.assertRaises(ToolError) as ctx:
            OpenAIStt(self.settings, ffmpeg="ffmpeg").transcribe(wav)
        self.assertEqual(ctx.exception.code, "auth_required")
        self.run_mock.assert_not_called()


class FakeEngine:
    def __init__(self, name, result=None, error=None, check_error=None):
        self.name, self.model = name, f"{name}-model"
        self.result, self.error, self._check = result, error, check_error
        self.calls = 0

    def capabilities(self):
        return {"privacy": "x"}

    def check(self):
        return self._check

    def describe(self):
        return self.name

    def transcribe(self, wav, *, language=None, on_progress=None, cancel=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


T_CLOUD = Transcript("en", 1.0, [Segment(0, 1, "cloud")])
T_LOCAL = Transcript("en", 1.0, [Segment(0, 1, "local")])


class FallbackTests(unittest.TestCase):
    def test_cloud_ok_no_fallback(self):
        cloud, local = FakeEngine("openai", T_CLOUD), FakeEngine("local", T_LOCAL)
        fb = stt.FallbackStt(cloud, local)
        self.assertIs(fb.transcribe(Path("x.wav")), T_CLOUD)
        self.assertFalse(fb.fell_back)
        self.assertEqual((fb.name, local.calls), ("openai", 0))

    def test_cloud_tool_error_falls_back_to_local(self):
        err = ToolError("rate_limited", "限流")
        cloud, local = FakeEngine("openai", error=err), FakeEngine("local", T_LOCAL)
        fb = stt.FallbackStt(cloud, local)
        self.assertIs(fb.transcribe(Path("x.wav")), T_LOCAL)
        self.assertTrue(fb.fell_back)
        self.assertIs(fb.fallback_error, err)
        self.assertEqual((fb.name, fb.model), ("local", "local-model"))   # provenance 記本機
        self.assertIn("退回本機", fb.describe())

    def test_flag_resets_on_next_call(self):
        cloud, local = FakeEngine("openai", error=RuntimeError("x")), FakeEngine("local", T_LOCAL)
        fb = stt.FallbackStt(cloud, local)
        fb.transcribe(Path("x.wav"))
        self.assertTrue(fb.fell_back)
        cloud.error, cloud.result = None, T_CLOUD
        fb.transcribe(Path("x.wav"))
        self.assertFalse(fb.fell_back)

    def test_missing_key_skips_cloud_call(self):
        cloud = FakeEngine("openai", T_CLOUD, check_error=ToolError("auth_required", "沒金鑰"))
        fb = stt.FallbackStt(cloud, FakeEngine("local", T_LOCAL))
        fb.transcribe(Path("x.wav"))
        self.assertEqual(cloud.calls, 0)
        self.assertTrue(fb.fell_back)

    def test_cancel_is_not_a_failure(self):
        cloud, local = FakeEngine("openai", error=Cancelled()), FakeEngine("local", T_LOCAL)
        fb = stt.FallbackStt(cloud, local)
        with self.assertRaises(Cancelled):
            fb.transcribe(Path("x.wav"))
        self.assertEqual(local.calls, 0)

    def test_local_never_falls_back_to_cloud(self):
        # build_stt("local") 不包退路：本機失敗就是失敗，不會碰到任何雲端 adapter
        adapter = stt.build_stt(Settings(stt_provider="local", stt_fallback_local=True))
        self.assertNotIsInstance(adapter, stt.FallbackStt)
        with mock.patch("video_notes.adapters.stt_local.Transcriber") as tr, \
                mock.patch("importlib.util.find_spec", return_value=object()), \
                mock.patch.object(OpenAIStt, "transcribe", side_effect=AssertionError("不該呼叫雲端")):
            tr.return_value.transcribe.side_effect = RuntimeError("CUDA out of memory")
            with self.assertRaises(ToolError) as ctx:
                adapter.transcribe(Path("x.wav"))
        self.assertEqual(ctx.exception.code, "resource_exhausted")

    def test_local_wraps_transcriber_unchanged(self):
        s = Settings(whisper_model="small", whisper_device="cpu", language="auto", traditional=True)
        with mock.patch("video_notes.adapters.stt_local.Transcriber") as tr, \
                mock.patch("importlib.util.find_spec", return_value=object()):
            tr.return_value.transcribe.return_value = T_LOCAL
            out = LocalStt(s).transcribe(Path("x.wav"), on_progress=None)
        tr.assert_called_once_with("small", "cpu", "auto", True)
        self.assertIs(out, T_LOCAL)


if __name__ == "__main__":
    unittest.main()
