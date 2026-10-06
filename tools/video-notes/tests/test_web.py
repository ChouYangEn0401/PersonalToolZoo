"""GUI 的後端 API（FastAPI TestClient，不開瀏覽器；用假的 LLM，完全離線）。"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from fastapi.testclient import TestClient  # noqa: E402

from test_pipeline import URL, FakeLLM, make_done_video  # noqa: E402

H = {"X-Video-Notes": "1"}


class WebTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"TOOLZOO_DATA_DIR": str(base / "data")})
        env.start()
        self.addCleanup(env.stop)
        self.out = base / "out"
        self.out.mkdir()

        from video_notes.pipeline import Pipeline
        from video_notes.web.server import create_app

        self.app = create_app()
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8766")
        r = self.client.put("/api/settings", json={"output": "custom", "output_custom": str(self.out)}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        hub = self.app.state.hub
        self.llm = FakeLLM()
        hub.manager.pipeline = Pipeline(hub.settings, hub.manager.pipeline.library, hub.locks,
                                        llm_factory=lambda _s: self.llm)

    def test_guard(self):
        self.assertEqual(self.client.post("/api/check", json={"urls": []}).status_code, 403)   # 沒有 header
        evil = TestClient(self.app, base_url="http://evil.example")
        self.assertEqual(evil.get("/api/health").status_code, 403)                            # DNS rebinding
        self.assertEqual(self.client.get("/api/note", params={"folder": "C:\\Windows", "slug": "x"}).status_code, 403)

    def test_state(self):
        s = self.client.get("/api/state").json()
        self.assertEqual(s["settings"]["output_custom"], str(self.out))
        self.assertIn("finance", [p["id"] for p in s["profiles"]])
        self.assertIn("✨ 文字精練", s["text_modes"])
        self.assertEqual(self.client.get("/api/health").json()["app"], "video-notes")

    def test_claude_subscription_needs_no_key(self):
        from toolzoo.ai import claude_code

        with mock.patch.object(claude_code, "available", lambda: (True, r"C:\fake\claude.exe")):
            s = self.client.get("/api/state").json()
        self.assertEqual(s["settings"]["provider"], "claude-sub")    # 沒存過設定 → 預設 Claude 訂閱
        self.assertEqual(s["env"]["keyless"], ["claude-sub"])
        self.assertTrue(s["env"]["keys"]["claude-sub"])               # 找得到 Claude Code 就算可用
        self.assertEqual(s["env"]["claude_code"], r"C:\fake\claude.exe")
        r = self.client.post("/api/keys", json={"provider": "claude-sub", "key": "x"}, headers=H)
        self.assertEqual(r.status_code, 400)

    def test_full_flow(self):
        make_done_video(self.out)
        check = self.client.post("/api/check", json={"urls": [URL]}, headers=H).json()[0]
        self.assertTrue(check["status"]["transcript"])
        self.assertEqual(check["kind"], "video")

        jobs = self.client.post("/api/jobs", json={"urls": [URL], "profile": "news", "modifiers": ["brief"]},
                                headers=H).json()
        job_id = jobs[0]["id"]
        for _ in range(100):
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] not in ("queued", "running"):
                break
            time.sleep(0.05)
        self.assertEqual(job["status"], "done", job["error"])
        self.assertIn("動物園的大象", job["notes"])
        self.assertEqual(job["stages"]["transcribe"], "reused")

        lib = self.client.get("/api/library").json()
        self.assertEqual(lib[0]["notes"], ["news+brief"])
        note = self.client.get("/api/note", params={"folder": lib[0]["folder"], "slug": "news+brief"})
        self.assertTrue(note.text.startswith("# Me at the zoo"))
        transcript = self.client.get("/api/transcript", params={"folder": lib[0]["folder"]})
        self.assertIn("elephants", transcript.text)

    def test_refine_streams(self):
        from video_notes.web import server

        with mock.patch.object(server, "LLM", lambda *a, **k: FakeLLM()):
            r = self.client.post("/api/refine", json={"text": "筆記", "mode": "📋 精要摘要", "submode": "條列式重點"},
                                 headers=H)
        self.assertEqual(r.status_code, 200)
        self.assertIn("動物園的大象", r.text)


if __name__ == "__main__":
    unittest.main()
