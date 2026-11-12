"""yt-dlp／ffmpeg／通知的錯誤合約：假的 yt_dlp 丟各種上游訊息，都要轉成對應 code＋reason＋remedy。完全離線。"""

import contextlib
import json
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes import media, notify  # noqa: E402
from video_notes.adapters import source, source_ytdlp  # noqa: E402
from video_notes.config import Settings  # noqa: E402
from video_notes.errors import ToolError  # noqa: E402
from video_notes.transcribe import Cancelled  # noqa: E402

FAKE_KEY = "sk-test-abcdefghijklmnop1234"


class DownloadError(Exception):
    pass


class UnsupportedError(Exception):
    pass


class DownloadCancelled(Exception):
    pass


@contextlib.contextmanager
def fake_yt_dlp(extract=None, download=None, capture=None):
    """把假的 yt_dlp 放進 sys.modules，離開時還原。extract／download 是會被呼叫的函式（可丟例外）。"""
    pkg = types.ModuleType("yt_dlp")
    utils = types.ModuleType("yt_dlp.utils")
    utils.DownloadCancelled = DownloadCancelled

    class YoutubeDL:
        def __init__(self, opts):
            if capture is not None:
                capture.append(opts)
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def sanitize_info(self, info):
            return info

        def extract_info(self, url, download=False):
            return extract(url) if extract else {"id": "x", "title": "t"}

        def download(self, urls):
            if download:
                download(self.opts, urls)

    pkg.YoutubeDL = YoutubeDL
    pkg.utils = utils
    saved = {k: sys.modules.get(k) for k in ("yt_dlp", "yt_dlp.utils")}
    sys.modules["yt_dlp"], sys.modules["yt_dlp.utils"] = pkg, utils
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def raiser(exc):
    def f(*args):
        raise exc
    return f


# 上游訊息 → (code, remedy.kind)
CASES = [
    ("ERROR: unable to download video data: HTTP Error 403: Forbidden", "dependency_outdated", "needs_update"),
    ("ERROR: [youtube] abc: The page needs to be reloaded.", "dependency_outdated", "needs_update"),
    ("ERROR: [youtube] abc: Requested format is not available. Use --list-formats", "dependency_outdated", "needs_update"),
    ("ERROR: [youtube] abc: nsig extraction failed: Some formats may be missing", "dependency_outdated", "needs_update"),
    ("ERROR: [youtube] abc: Signature extraction failed: Some formats may be missing", "dependency_outdated", "needs_update"),
    ("WARNING: No supported JavaScript runtime could be found. ERROR: Requested format is not available", "dependency_missing", "needs_config"),
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", "rate_limited", "needs_owner"),
    ("ERROR: [youtube] abc: Video unavailable", "bad_input", "none"),
    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "bad_input", "none"),
    ("ERROR: [youtube] abc: The uploader has not made this video available in your country", "bad_input", "none"),
    ("ERROR: [youtube] abc: Sign in to confirm your age. This video may be inappropriate", "auth_required", "needs_config"),
    ("ERROR: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>", "network_unreachable", "none"),
    ("ERROR: unable to download video data: HTTP Error 429: Too Many Requests", "rate_limited", "none"),
    ("something nobody has ever seen before", "internal_bug", "needs_owner"),
]


class ClassifyYtdlpTest(unittest.TestCase):
    def test_upstream_messages_become_tool_errors(self):
        for message, code, kind in CASES:
            with self.subTest(message=message):
                err = media.classify_ytdlp(DownloadError(message))
                self.assertIsInstance(err, ToolError)
                self.assertEqual(err.code, code)
                self.assertEqual(err.remedy.kind, kind)
                self.assertTrue(err.reason)
                self.assertLessEqual(len(err.reason), 120)
                self.assertLessEqual(len(err.detail), 300)

    def test_outdated_remedy_has_upgrade_command_and_rebuild_note(self):
        err = media.classify_ytdlp(DownloadError("HTTP Error 403: Forbidden"))
        self.assertIn('pip install -U "yt-dlp[default]<2028"', err.remedy.action)
        self.assertIn("build", err.remedy.action)
        self.assertEqual(err.source, "yt-dlp")

    def test_unsupported_url_class(self):
        err = media.classify_ytdlp(UnsupportedError("Unsupported URL: https://example.com/x"))
        self.assertEqual(err.code, "unsupported_source")

    def test_network_exception_types(self):
        self.assertEqual(media.classify_ytdlp(TimeoutError("x")).code, "network_unreachable")
        self.assertEqual(media.classify_ytdlp(ConnectionResetError("x")).code, "network_unreachable")
        self.assertEqual(media.classify_ytdlp(urllib.error.URLError("boom")).code, "network_unreachable")

    def test_import_error_is_dependency_missing(self):
        self.assertEqual(media.classify_ytdlp(ImportError("No module named 'yt_dlp'")).code, "dependency_missing")

    def test_disk_full(self):
        err = media.classify_ytdlp(OSError(28, "No space left on device"))
        self.assertEqual(err.code, "resource_exhausted")

    def test_secrets_and_user_paths_are_redacted(self):
        msg = f"ERROR: weird failure api_key={FAKE_KEY} at C:\\Users\\someone\\secret\\x.py {FAKE_KEY}"
        err = media.classify_ytdlp(DownloadError(msg))
        text = json.dumps(err.to_dict(), ensure_ascii=False) + str(err)
        self.assertNotIn(FAKE_KEY, text)
        self.assertNotIn("someone", text)


class FetchAndDownloadTest(unittest.TestCase):
    def test_fetch_info_converts_errors(self):
        with fake_yt_dlp(extract=raiser(DownloadError("ERROR: [youtube] a: Video unavailable"))):
            with self.assertRaises(ToolError) as cm:
                media.fetch_info("https://youtu.be/a", None)
        self.assertEqual(cm.exception.code, "bad_input")

    def test_fetch_info_playlist_is_bad_input(self):
        with fake_yt_dlp(extract=lambda url: {"_type": "playlist", "entries": []}):
            with self.assertRaises(ToolError) as cm:
                media.fetch_info("https://youtube.com/playlist?list=1", None)
        self.assertEqual(cm.exception.code, "bad_input")
        self.assertIn("播放清單", cm.exception.reason)

    def test_fetch_info_success_keeps_only_known_fields(self):
        with fake_yt_dlp(extract=lambda url: {"id": "a", "title": "T", "formats": [1, 2, 3]}):
            info = media.fetch_info("https://youtu.be/a", None)
        self.assertEqual(info, {"id": "a", "title": "T"})

    def test_missing_package_is_dependency_missing(self):
        saved = {k: sys.modules.get(k) for k in ("yt_dlp", "yt_dlp.utils")}
        sys.modules["yt_dlp"] = None   # 讓 import 失敗
        sys.modules["yt_dlp.utils"] = None
        try:
            with self.assertRaises(ToolError) as cm:
                media.fetch_info("https://youtu.be/a", None)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        self.assertEqual(cm.exception.code, "dependency_missing")

    def test_download_converts_errors(self):
        with fake_yt_dlp(download=raiser(DownloadError("HTTP Error 403: Forbidden"))), tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ToolError) as cm:
                media.download("https://youtu.be/a", Path(d), keep_video=False, ffmpeg=None)
        self.assertEqual(cm.exception.code, "dependency_outdated")

    def test_cancel_still_raises_cancelled(self):
        with fake_yt_dlp(download=raiser(DownloadCancelled())), tempfile.TemporaryDirectory() as d:
            with self.assertRaises(Cancelled):
                media.download("https://youtu.be/a", Path(d), keep_video=False, ffmpeg=None)

    def test_cancel_wrapped_in_download_error_still_cancelled(self):
        wrapped = DownloadError("cancelled")
        wrapped.exc_info = (DownloadCancelled, DownloadCancelled(), None)
        with fake_yt_dlp(download=raiser(wrapped)), tempfile.TemporaryDirectory() as d:
            with self.assertRaises(Cancelled):
                media.download("https://youtu.be/a", Path(d), keep_video=False, ffmpeg=None)

    def test_download_options_unchanged_and_sleep_passed_to_ytdlp(self):
        seen = []
        with fake_yt_dlp(capture=seen), tempfile.TemporaryDirectory() as d:
            media.download("https://youtu.be/a", Path(d), keep_video=False, ffmpeg=None, sleep_between=[5.0, 10.0])
            media.download("https://youtu.be/a", Path(d), keep_video=True, ffmpeg=None)
        audio, video = seen
        self.assertEqual((audio["sleep_interval"], audio["max_sleep_interval"]), (5.0, 10.0))
        self.assertEqual(audio["format"], "bestaudio/best")
        self.assertEqual((audio["retries"], audio["fragment_retries"]), (5, 10))
        self.assertTrue(audio["outtmpl"].endswith("media.%(ext)s"))
        self.assertNotIn("sleep_interval", video)
        self.assertEqual(video["format"], "bestvideo*+bestaudio/best")
        self.assertEqual(video["merge_output_format"], "mp4")

    def test_sleep_options(self):
        self.assertEqual(media.sleep_options([]), {})
        self.assertEqual(media.sleep_options([0, 0]), {})
        self.assertEqual(media.sleep_options([7]), {"sleep_interval": 7.0, "max_sleep_interval": 7.0})


class FfmpegTest(unittest.TestCase):
    def run_extract(self, **run_kwargs):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(media.subprocess, "run", **run_kwargs):
            return media.extract_audio(Path(d) / "m.mp4", Path(d) / "a.wav", "ffmpeg.exe")

    def test_no_ffmpeg(self):
        with self.assertRaises(ToolError) as cm:
            media.extract_audio(Path("m.mp4"), Path("a.wav"), None)
        self.assertEqual(cm.exception.code, "dependency_missing")
        self.assertEqual(cm.exception.remedy.kind, "needs_config")

    def test_ffmpeg_exe_vanished(self):
        with self.assertRaises(ToolError) as cm:
            self.run_extract(side_effect=FileNotFoundError("ffmpeg"))
        self.assertEqual(cm.exception.code, "dependency_missing")

    def test_bad_media_is_bad_input(self):
        done = subprocess.CompletedProcess([], 1, "", "x.mp4: Invalid data found when processing input")
        with self.assertRaises(ToolError) as cm:
            self.run_extract(return_value=done)
        self.assertEqual(cm.exception.code, "bad_input")

    def test_disk_full(self):
        done = subprocess.CompletedProcess([], 1, "", "av_interleaved_write_frame(): No space left on device")
        with self.assertRaises(ToolError) as cm:
            self.run_extract(return_value=done)
        self.assertEqual(cm.exception.code, "resource_exhausted")

    def test_unknown_failure_is_internal_bug_and_redacted(self):
        done = subprocess.CompletedProcess([], 1, "", f"weird token={FAKE_KEY} C:\\Users\\someone\\x.mp4 boom")
        with self.assertRaises(ToolError) as cm:
            self.run_extract(return_value=done)
        err = cm.exception
        self.assertEqual(err.code, "internal_bug")
        self.assertNotIn(FAKE_KEY, err.detail)
        self.assertNotIn("someone", err.detail)

    def test_success_renames_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "a.wav"

            def fake_run(cmd, **kw):
                Path(cmd[-1]).write_bytes(b"RIFF")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with mock.patch.object(media.subprocess, "run", side_effect=fake_run):
                media.extract_audio(Path(d) / "m.mp4", wav, "ffmpeg.exe")
            self.assertTrue(wav.exists())
            self.assertFalse(wav.with_suffix(".tmp.wav").exists())


class NotifyTest(unittest.TestCase):
    def test_http_errors_are_classified(self):
        def err(code):
            return urllib.error.HTTPError("http://u:tok@h.example/x", code, "reason", {}, None)

        cases = {401: "auth_required", 403: "auth_required", 404: "config_invalid", 429: "rate_limited",
                 503: "network_unreachable", 418: "bad_input"}
        for code, expected in cases.items():
            with self.subTest(code=code):
                e = notify.classify_http_error(err(code), "http://u:tok@h.example/x")
                self.assertEqual(e.code, expected)
                self.assertNotIn("tok", e.reason)

    def test_unreachable_message_keeps_old_wording_and_hides_url_token(self):
        ok, message = notify.post_result("http://127.0.0.1:9/hook?token=SECRET123456", {"files": {}},
                                         config={"timeout": 1})
        self.assertFalse(ok)
        self.assertIn("連不上", message)
        self.assertNotIn("SECRET123456", message)

    def test_bad_scheme(self):
        with self.assertRaises(ToolError) as cm:
            notify.post_result_checked("ftp://x", {}, config={})
        self.assertEqual(cm.exception.code, "config_invalid")


class SourceAdapterTest(unittest.TestCase):
    def test_registered_and_matches_any_http(self):
        source.load_builtin()
        self.assertIn("ytdlp", source.REGISTRY)
        adapter = source.for_url("https://example.com/v", Settings())
        self.assertEqual(adapter.name, "ytdlp")
        self.assertTrue(adapter.matches("HTTP://x.y/z"))
        self.assertFalse(adapter.matches("ftp://x.y/z"))
        self.assertFalse(adapter.matches("not a url"))
        with self.assertRaises(ToolError) as cm:
            source.for_url("ftp://x", Settings())
        self.assertEqual(cm.exception.code, "unsupported_source")

    def test_capabilities(self):
        caps = source_ytdlp.YtdlpSource(Settings()).capabilities()
        self.assertEqual(caps, {"needs_network": True, "needs_key": False, "platforms": "many"})

    def test_check_reports_missing_ffmpeg_and_js(self):
        adapter = source_ytdlp.YtdlpSource(Settings())
        adapter._ffmpeg, adapter._ffmpeg_looked = None, True
        with fake_yt_dlp():
            with mock.patch("importlib.util.find_spec", return_value=object()):
                self.assertEqual(adapter.check().code, "dependency_missing")
                adapter._ffmpeg = "ffmpeg.exe"
                with mock.patch.object(source_ytdlp.ytdlp, "find_js_runtimes", return_value=[]):
                    self.assertEqual(adapter.check().code, "dependency_missing")
                with mock.patch.object(source_ytdlp.ytdlp, "find_js_runtimes", return_value=["node"]):
                    self.assertIsNone(adapter.check())

    def test_adapter_passes_sleep_setting_to_ytdlp(self):
        seen = []
        adapter = source_ytdlp.YtdlpSource(Settings(sleep_between_videos=[3.0, 6.0], cookies_from_browser="edge"))
        adapter._ffmpeg, adapter._ffmpeg_looked = None, True
        with fake_yt_dlp(capture=seen), tempfile.TemporaryDirectory() as d:
            adapter.download("https://youtu.be/a", Path(d), keep_video=False)
        self.assertEqual((seen[0]["sleep_interval"], seen[0]["max_sleep_interval"]), (3.0, 6.0))
        self.assertEqual(seen[0]["cookiesfrombrowser"], ("edge",))


if __name__ == "__main__":
    unittest.main()
