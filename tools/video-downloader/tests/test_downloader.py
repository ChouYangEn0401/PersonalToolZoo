"""Video Downloader 的離線測試：參數組裝、下載佇列（假的 YoutubeDL）、web API。

    .\\tools\\video-downloader\\.venv\\Scripts\\python.exe -m unittest discover -s tools\\video-downloader\\tests -v
"""

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_downloader.config import Settings  # noqa: E402
from video_downloader.history import History  # noqa: E402
from video_downloader.manager import DownloadManager  # noqa: E402
from video_downloader.options import (DownloadRequest, build_options, cli_args, explain_error,  # noqa: E402
                                      output_folder, parse_headers, safe_name)
from video_downloader.presets import resolve  # noqa: E402


class OptionsTest(unittest.TestCase):
    def setUp(self):
        self.s = Settings(output_dir="D:/dl")

    def test_presets(self):
        self.assertEqual(resolve("audio-mp3").audio, "mp3")
        self.assertEqual(resolve("nope").id, "compat")            # 不認得的退回預設
        self.assertEqual(resolve("custom", "bv*+ba").format, "bv*+ba")
        with self.assertRaises(ValueError):
            resolve("custom", "")

    def test_video_options_go_through_yt_dlp(self):
        o = build_options(self.s, DownloadRequest("https://x/y", preset="1080p"))
        self.assertIn("height<=1080", o["format"])
        self.assertEqual(o["merge_output_format"], "mp4")
        self.assertTrue(o["noplaylist"])
        self.assertEqual(o["paths"]["home"], str(Path("D:/dl")))
        keys = [p["key"] for p in o["postprocessors"]]
        self.assertIn("FFmpegMetadata", keys)                      # 預設寫入影片資訊
        self.assertIn("node", o["js_runtimes"])                    # toolzoo.ytdlp 的 JS 執行環境設定

    def test_audio_subs_headers_and_playlist(self):
        s = Settings(output_dir="D:/dl", subtitles=True, embed_thumbnail=True)
        req = DownloadRequest("https://x/list", preset="audio-mp3", headers={"Referer": "https://site/"},
                              playlist_items="3", subfolder='我的:清單?')
        o = build_options(s, req)
        keys = [p["key"] for p in o["postprocessors"]]
        self.assertIn("FFmpegExtractAudio", keys)
        self.assertNotIn("FFmpegEmbedSubtitle", keys)              # 純音訊不嵌字幕
        self.assertTrue(o["writesubtitles"])
        self.assertEqual(o["http_headers"]["referer"], "https://site/")
        self.assertEqual(o["playlist_items"], "3")
        self.assertFalse(o.get("noplaylist"))
        self.assertEqual(output_folder(s, req), Path("D:/dl") / "我的 清單")

    def test_whole_playlist_and_custom_name(self):
        args = cli_args(self.s, DownloadRequest("https://x/list", playlist_items="all"))
        self.assertIn("--yes-playlist", args)
        self.assertTrue(args[args.index("-o") + 1].startswith("%(playlist_title)s/"))
        args = cli_args(self.s, DownloadRequest("https://x/a.m3u8", filename='直播/回放:1'))
        self.assertEqual(args[args.index("-o") + 1], "直播 回放 1.%(ext)s")

    def test_helpers(self):
        self.assertEqual(parse_headers("Referer: https://a/\n\nbad line\nUser-Agent: X:Y"),
                         {"Referer": "https://a/", "User-Agent": "X:Y"})
        self.assertEqual(safe_name(' a<b>c. '), "a b c")
        self.assertIn("Referer", explain_error("ERROR: unable to download video data: HTTP Error 403: Forbidden"))
        self.assertIn("登入", explain_error("ERROR: [youtube] x: Sign in to confirm your age"))
        self.assertIn("DRM", explain_error("ERROR: This video is DRM protected"))


from yt_dlp import YoutubeDL as RealYDL  # noqa: E402


class FakeYDL(RealYDL):
    """模擬 yt-dlp：依序呼叫進度回呼與後處理回呼，最後回報檔案路徑。

    繼承真的 YoutubeDL：yt-dlp 的 parse_options() 內部也會用到它的類別方法（例如 validate_outtmpl），
    只把「實際連網下載」換掉。
    """

    block = None   # threading.Event：設定後會停在下載中，讓測試可以取消

    def __init__(self, opts):  # noqa: super-init-not-called — 不要真的初始化網路相關的東西
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def download(self, urls):
        if "fail" in urls[0]:
            from yt_dlp.utils import DownloadError
            raise DownloadError("ERROR: unable to download: HTTP Error 403: Forbidden")
        info = {"title": "測試影片", "vcodec": "avc1", "acodec": "none"}
        for done in (0, 50, 100):
            for hook in self.opts["progress_hooks"]:
                hook({"status": "downloading", "downloaded_bytes": done, "total_bytes": 100, "speed": 10,
                      "eta": 1, "info_dict": info})
            while FakeYDL.block is not None and not FakeYDL.block.is_set():
                for hook in self.opts["progress_hooks"]:   # 真的 yt-dlp 也是在回呼裡被取消
                    hook({"status": "downloading", "info_dict": info})
                time.sleep(0.01)
        for hook in self.opts["postprocessor_hooks"]:
            hook({"status": "started", "postprocessor": "Merger"})
        path = Path(self.opts["paths"]["home"]) / "測試影片.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 10)
        for hook in self.opts["post_hooks"]:
            hook(str(path))


class ManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(output_dir=self.tmp.name)
        self.history = History(Path(self.tmp.name) / "history.json")
        patcher = mock.patch("yt_dlp.YoutubeDL", FakeYDL)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.manager = DownloadManager(lambda: self.settings, self.history, workers=2)
        FakeYDL.block = None

    def test_success_records_history(self):
        job = self.manager.submit(DownloadRequest("https://ok/1"))
        self.manager.wait([job])
        self.assertEqual(job.status, "done")
        self.assertEqual(job.title, "測試影片")
        self.assertTrue(job.filepath.endswith("測試影片.mp4"))
        self.assertEqual(self.history.items()[0]["size"], 10)

    def test_failure_is_explained_and_retry_works(self):
        job = self.manager.submit(DownloadRequest("https://fail/1"))
        self.manager.wait([job])
        self.assertEqual(job.status, "failed")
        self.assertIn("Referer", job.error)
        again = self.manager.retry(job.id)
        self.assertIsNotNone(again)
        self.manager.wait([again])
        self.assertIsNone(self.manager.get(job.id))               # 舊的從清單換成新的

    def test_cancel(self):
        FakeYDL.block = threading.Event()
        job = self.manager.submit(DownloadRequest("https://ok/slow"))
        for _ in range(100):
            if job.status == "downloading" and job.progress > 0:
                break
            time.sleep(0.01)
        self.assertTrue(self.manager.cancel(job.id))
        self.manager.wait([job])
        self.assertEqual(job.status, "cancelled")
        self.assertEqual(self.history.items(), [])                 # 取消的不算進紀錄


class WebTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"TOOLZOO_DATA_DIR": str(Path(self.tmp.name) / "data")})
        env.start()
        self.addCleanup(env.stop)
        patcher = mock.patch("yt_dlp.YoutubeDL", FakeYDL)
        patcher.start()
        self.addCleanup(patcher.stop)
        FakeYDL.block = None
        try:
            from fastapi.testclient import TestClient
        except RuntimeError as exc:   # TestClient 需要 httpx2（只有測試用到，不在 requirements.txt）
            self.skipTest(f"{exc}（pip install httpx2 後再跑）")

        from video_downloader.web.server import create_app

        self.client = TestClient(create_app(), base_url="http://127.0.0.1:8765")
        self.H = {"X-Video-Downloader": "1"}
        r = self.client.put("/api/settings", json={"output_dir": str(Path(self.tmp.name) / "out")}, headers=self.H)
        self.assertEqual(r.status_code, 200)

    def test_guard_and_state(self):
        self.assertEqual(self.client.post("/api/downloads", json={"items": []}).status_code, 403)
        self.assertIn("compat", [p["id"] for p in self.client.get("/api/state").json()["presets"]])
        self.assertEqual(self.client.post("/api/open", json={"path": "C:\\Windows"}, headers=self.H).status_code, 403)

    def test_download_and_history(self):
        jobs = self.client.post("/api/downloads", json={"items": [{"url": "https://ok/web", "preset": "720p"}]},
                                headers=self.H).json()
        for _ in range(200):
            snap = self.client.get("/api/downloads").json()[0]
            if snap["status"] in ("done", "failed"):
                break
            time.sleep(0.02)
        self.assertEqual(snap["status"], "done", snap["error"])
        self.assertEqual(jobs[0]["preset"], "720p")
        hist = self.client.get("/api/history").json()
        self.assertEqual(hist[0]["title"], "測試影片")
        self.assertEqual(self.client.post("/api/downloads",
                                          json={"items": [{"url": "https://ok/x", "preset": "custom"}]},
                                          headers=self.H).status_code, 400)


if __name__ == "__main__":
    unittest.main()
