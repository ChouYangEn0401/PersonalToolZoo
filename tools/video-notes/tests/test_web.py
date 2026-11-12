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
        self.assertIn("claude-sub", s["env"]["keyless"])
        self.assertIn("openai-compat", s["providers"])               # 相容端點也在選單裡（金鑰在 .env，不在畫面貼）
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

        self.assertEqual(job["type"], "video")
        self.assertGreater(job["streamed_chars"], 0)                  # 串流的是 JSON 原文：只算字數
        self.assertFalse(job["notes"].lstrip().startswith("{"))       # 筆記欄位放的是最後的 Markdown

        lib = self.client.get("/api/library").json()
        self.assertEqual(lib["collections"], [])
        video = lib["videos"][0]
        self.assertEqual(video["notes"], ["news+brief"])
        self.assertEqual([a["slug"] for a in video["analyses"]], ["news+brief"])   # 舊欄位之外多了分析清單
        note = self.client.get("/api/note", params={"folder": video["folder"], "slug": "news+brief"})
        self.assertTrue(note.text.startswith("# Me at the zoo"))
        transcript = self.client.get("/api/transcript", params={"folder": video["folder"]})
        self.assertIn("elephants", transcript.text)

    def test_frontend_ids_exist(self):
        """沒辦法在這裡開瀏覽器：至少確認 app.js 用到的元素 id 都在 index.html 裡（動態建立的除外）。"""
        import re

        static = TOOL / "video_notes" / "web" / "static"
        html = (static / "index.html").read_text(encoding="utf-8")
        js = (static / "app.js").read_text(encoding="utf-8")
        used = set(re.findall(r'\$\("#([\w-]+)"\)', js))
        missing = {i for i in used if f'id="{i}"' not in html} - {"btn-recheck"}
        self.assertEqual(missing, set())
        self.assertEqual(js.count(".innerHTML"), 1)      # 只有 renderMarkdown（已先跳脫）用 innerHTML，其餘資料文字都走 textContent

    def test_refine_streams(self):
        from video_notes.web import server

        with mock.patch.object(server, "build_llm", lambda *a, **k: FakeLLM()):
            r = self.client.post("/api/refine", json={"text": "筆記", "mode": "📋 精要摘要", "submode": "條列式重點"},
                                 headers=H)
        self.assertEqual(r.status_code, 200)
        self.assertIn("動物園的大象", r.text)

    # ------------------------------------------------------------------ v2：狀態、輸出、重新分析、合併
    def _video_with_analysis(self, slug="news"):
        """做一個有逐字稿與一份 analysis 的影片資料夾。"""
        from video_notes import analysis
        from test_pipeline import VALID_AI

        art = make_done_video(self.out)
        data = analysis.merge_ai(analysis.new_analysis(title="Me at the zoo", mode={"profile": "news"}), VALID_AI)
        analysis.save(art.analysis(slug), data)
        return art

    def _other_folder(self, name="Other [video-abc123]"):
        """第二支影片（只要有 analysis 就能當合併成員）。"""
        from video_notes import analysis
        from test_pipeline import VALID_AI

        folder = self.out / name
        folder.mkdir()
        (folder / "info.json").write_text('{"url": "https://example.com/x", "video": {"title": "第二支"}}', encoding="utf-8")
        analysis.save(folder / "analysis.news.json",
                      analysis.merge_ai(analysis.new_analysis(title="第二支", mode={"profile": "news"}), VALID_AI))
        return folder

    def _wait(self, job_id):
        for _ in range(200):
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] not in ("queued", "running"):
                return job
            time.sleep(0.05)
        self.fail("工作沒有結束")

    def test_state_v2_fields(self):
        s = self.client.get("/api/state").json()
        renderers = {r["name"]: r for r in s["renderers"]}
        self.assertEqual(renderers["markdown"]["group"], "notes")
        self.assertTrue(renderers["markdown"]["always"])
        self.assertEqual(renderers["tree-mermaid"]["group"], "tree")
        self.assertEqual(renderers["html-sheet"]["group"], "html")
        self.assertTrue(all(r["label"] for r in renderers.values()))
        stts = {x["name"]: x for x in s["stt_providers"]}
        self.assertEqual(stts["local"]["privacy"], "local")
        self.assertEqual(stts["openai"]["privacy"], "cloud")
        self.assertTrue(stts["openai"]["needs_key"])
        self.assertIn("version", s["ytdlp"])
        self.assertIsInstance(s["degraded"], list)
        self.assertTrue(all("outputs" in p for p in s["presets"]))

    def test_state_lists_degraded_with_remedy(self):
        from video_notes.web import server

        entry = {"state": "degraded", "code": "dependency_outdated", "count": 3, "first_seen": "a", "last_seen": "b"}
        with mock.patch.object(server.health_mod, "entries", lambda: {"yt-dlp": entry, "ffmpeg": {"state": "ok"}}):
            s = self.client.get("/api/state").json()
        self.assertEqual([d["source"] for d in s["degraded"]], ["yt-dlp"])
        self.assertTrue(s["degraded"][0]["reason"])
        self.assertTrue(s["degraded"][0]["action"])

    def test_unavailable_renderer_has_reason(self):
        from video_notes.errors import Remedy, ToolError
        from video_notes.adapters import render

        render.load_builtin()
        err = ToolError("dependency_missing", "少了某個套件", remedy=Remedy("needs_config", "裝起來"))
        with mock.patch.object(render.get("tree-md").__class__, "check", lambda self: err):
            s = self.client.get("/api/state").json()
        item = next(r for r in s["renderers"] if r["name"] == "tree-md")
        self.assertFalse(item["available"])
        self.assertEqual((item["reason"], item["action"]), ("少了某個套件", "裝起來"))

    def test_settings_validation(self):
        bad = self.client.put("/api/settings", json={"compat_base_url": "ftp://x"}, headers=H)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"]["code"], "config_invalid")
        self.assertEqual(self.client.put("/api/settings", json={"stt_provider": "nope"}, headers=H).status_code, 400)
        self.assertEqual(self.client.put("/api/settings", json={"outputs": ["nope"]}, headers=H).status_code, 400)
        ok = self.client.put("/api/settings", json={
            "stt_provider": "openai", "outputs": ["tree-md"], "compat_base_url": "http://127.0.0.1:11434/v1",
            "combine_confirm_tokens": 1234, "sleep_between_videos": [9, 3], "max_parallel_downloads": 4}, headers=H)
        self.assertEqual(ok.status_code, 200, ok.text)
        s = ok.json()["settings"]
        self.assertEqual((s["stt_provider"], s["outputs"], s["combine_confirm_tokens"]), ("openai", ["tree-md"], 1234))
        self.assertEqual(s["sleep_between_videos"], [3.0, 9.0])

    def test_render_from_analysis_and_serve_output(self):
        art = self._video_with_analysis()
        folder = str(art.folder)
        r = self.client.post("/api/render", json={"folder": folder, "slug": "news", "outputs": ["tree-md", "html-sheet", "tree-xmind"]},
                             headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["errors"], {})
        self.assertEqual(set(body["outputs"]), {"tree-md", "html-sheet", "tree-xmind"})
        self.assertEqual(self.llm.calls, [])        # 不花 token

        html = self.client.get("/api/output", params={"folder": folder, "name": body["outputs"]["html-sheet"]})
        self.assertEqual(html.status_code, 200)
        self.assertTrue(html.headers["content-type"].startswith("text/html"))
        self.assertEqual(html.headers["content-security-policy"],
                         "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:")
        self.assertEqual(html.headers["x-content-type-options"], "nosniff")
        md = self.client.get("/api/output", params={"folder": folder, "name": body["outputs"]["tree-md"]})
        self.assertTrue(md.headers["content-type"].startswith("text/plain"))
        xm = self.client.get("/api/output", params={"folder": folder, "name": body["outputs"]["tree-xmind"]})
        self.assertIn("attachment", xm.headers["content-disposition"])

        lib = self.client.get("/api/library").json()["videos"][0]
        self.assertIn(body["outputs"]["tree-md"], lib["outputs"])        # 筆記庫看得到有哪些輸出

    def test_render_errors(self):
        art = self._video_with_analysis()
        post = lambda **kw: self.client.post("/api/render", json={"folder": str(art.folder), "slug": "news",
                                                                  "outputs": ["tree-md"], **kw}, headers=H)
        self.assertEqual(self.client.post("/api/render", json={"folder": str(art.folder), "slug": "news",
                                                               "outputs": ["tree-md"]}).status_code, 403)   # 沒有標頭
        self.assertEqual(post(folder=str(self.out.parent)).status_code, 403)                                # 跑出輸出資料夾
        self.assertEqual(post(slug="..\\..\\evil").status_code, 400)                                         # slug 不能帶路徑
        bad = post(outputs=["no-such-format"])
        self.assertEqual(bad.status_code, 400)
        self.assertIn("no-such-format", bad.json()["error"]["reason"])
        missing = post(slug="other")                                                                          # 這個方案沒有分析
        self.assertEqual(missing.status_code, 400)
        self.assertTrue(missing.json()["error"]["remedy"]["action"])

    def test_output_only_serves_existing_files_in_outputs(self):
        art = self._video_with_analysis()
        folder = str(art.folder)
        self.client.post("/api/render", json={"folder": folder, "slug": "news", "outputs": ["tree-md"]}, headers=H)
        get = lambda name, **kw: self.client.get("/api/output", params={"folder": kw.get("folder", folder), "name": name})
        for name in ("info.json", "..\\info.json", "../info.json", "notes.news.md", "nope.html", ""):
            self.assertEqual(get(name).status_code, 404, name)
        self.assertEqual(get("x", folder=str(self.out.parent)).status_code, 403)

    def test_reanalyze_job_reuses_transcript_and_renders(self):
        art = self._video_with_analysis()
        r = self.client.post("/api/reanalyze", json={"folder": str(art.folder), "profile": "news", "modifiers": ["brief"],
                                                     "outputs": ["tree-md"]}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        job = self._wait(r.json()["id"])
        self.assertEqual(job["status"], "done", job["error"])
        self.assertEqual(job["type"], "reanalyze")
        self.assertEqual(set(job["outputs"]), {"markdown", "tree-md"})
        self.assertTrue(art.analysis("news+brief").exists())
        self.assertEqual(job["stages"]["outputs"], "done")
        self.assertIn("動物園的大象", job["notes"])
        self.assertEqual(job["folder"], str(art.folder))

    def test_reanalyze_errors(self):
        folder = self.out / "empty"
        folder.mkdir()
        (folder / "info.json").write_text("{}", encoding="utf-8")
        r = self.client.post("/api/reanalyze", json={"folder": str(folder)}, headers=H)
        self.assertEqual(r.status_code, 400)
        self.assertIn("逐字稿", r.json()["error"]["reason"])
        self.assertEqual(self.client.post("/api/reanalyze", json={"folder": str(self.out.parent)}, headers=H).status_code, 403)
        self.assertEqual(self.client.post("/api/reanalyze", json={"folder": str(folder), "profile": "zzz"}, headers=H).status_code, 400)

    def test_job_accepts_outputs_and_one_off_stt(self):
        hub = self.app.state.hub
        seen = []

        def fake_submit(url, options, pipeline=None):
            seen.append((options, pipeline))
            return mock.Mock(snapshot=lambda with_notes=False: {"id": "x"})

        with mock.patch.object(hub.manager, "submit", fake_submit):
            r = self.client.post("/api/jobs", json={"urls": [URL], "outputs": ["tree-md"], "stt_provider": "openai"}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        options, pipeline = seen[0]
        self.assertEqual(options.outputs, ("tree-md",))
        self.assertEqual(pipeline.settings.stt_provider, "openai")
        self.assertEqual(hub.settings.stt_provider, "local")              # 沒有改存檔
        self.assertEqual(hub.manager.pipeline.settings.stt_provider, "local")
        for bad in ({"outputs": ["zzz"]}, {"stt_provider": "zzz"}):
            self.assertEqual(self.client.post("/api/jobs", json={"urls": [URL], **bad}, headers=H).status_code, 400)

    def test_combine_estimate_and_confirm_flow(self):
        from video_notes import collection

        a = self._video_with_analysis().folder
        b = self._other_folder()
        asked = {}

        def fake_estimate(members, settings):
            asked["members"] = members
            return collection.CombineEstimate(members=len(members), input_chars=90000, input_tokens=70000, calls=3,
                                              needs_confirm=True, missing=["壞掉的"])

        def fake_combine(members, **kw):
            folder = self.out / "collections" / "20261112-000000 合併"
            folder.mkdir(parents=True)
            (folder / "analysis.news.json").write_text("{}", encoding="utf-8")
            (folder / "notes.news.md").write_text("# 合併筆記", encoding="utf-8")
            kw["emit"]("stage", {"stage": "notes", "state": "done"})
            return {"folder": str(folder), "analysis_file": str(folder / "analysis.news.json"),
                    "notes_file": str(folder / "notes.news.md"), "analysis": {}, "outputs": {"markdown": "x"}}

        body = {"folders": [str(a), str(b)], "profile": "news", "title": "動物園合輯", "outputs": ["tree-md"]}
        with mock.patch.object(collection, "estimate", fake_estimate), mock.patch.object(collection, "combine", fake_combine):
            est = self.client.post("/api/combine/estimate", json=body, headers=H)
            self.assertEqual(est.status_code, 200, est.text)
            self.assertEqual(est.json()["calls"], 3)
            self.assertEqual(est.json()["missing"], ["壞掉的"])
            self.assertIn("70,000", est.json()["text"])
            self.assertEqual([m.analysis.name for m in asked["members"]], ["analysis.news.json"] * 2)

            blocked = self.client.post("/api/combine", json=body, headers=H)       # 要確認但還沒確認
            self.assertEqual(blocked.status_code, 409)
            self.assertEqual(blocked.json()["error"]["code"], "needs_confirm")
            self.assertEqual(blocked.json()["estimate"]["input_tokens"], 70000)
            self.assertEqual(self.client.get("/api/jobs").json(), [])              # 沒有偷偷開工

            ok = self.client.post("/api/combine", json={**body, "confirmed": True}, headers=H)
            self.assertEqual(ok.status_code, 200, ok.text)
            job = self._wait(ok.json()["id"])
        self.assertEqual(job["status"], "done", job["error"])
        self.assertEqual(job["type"], "combine")
        self.assertEqual(job["notes"], "# 合併筆記")
        self.assertIn("tree-md", job["outputs"] if "tree-md" in job["outputs"] else job["output_errors"])  # 合併後補輸出（假分析讀不了就記錄錯誤）

    def test_combine_validation(self):
        a = self._video_with_analysis().folder
        r = self.client.post("/api/combine/estimate", json={"folders": [str(a)]}, headers=H)
        self.assertEqual(r.status_code, 400)
        self.assertIn("兩支", r.json()["error"]["reason"])
        outside = self.client.post("/api/combine", json={"folders": [str(a), str(self.out.parent)]}, headers=H)
        self.assertEqual(outside.status_code, 403)
        self.assertEqual(self.client.post("/api/combine", json={"folders": [str(a), str(a)]}).status_code, 403)  # 沒標頭

    def test_recombine_needs_backend_support(self):
        from video_notes import collection

        folder = self.out / "collections" / "c1"
        folder.mkdir(parents=True)
        body = {"folder": str(folder), "profile": "news"}
        if not hasattr(collection, "recombine"):
            self.assertEqual(self.client.post("/api/recombine", json=body, headers=H).status_code, 501)
        got = {}

        def fake(f, **kw):
            got["folder"] = f
            return {"folder": str(f), "notes": "ok", "outputs": {}}

        with mock.patch.object(collection, "recombine", fake, create=True):
            r = self.client.post("/api/recombine", json=body, headers=H)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(self._wait(r.json()["id"])["status"], "done")
        self.assertEqual(got["folder"], folder.resolve())

    def test_recheck_clears_health_and_runs_doctor(self):
        from video_notes.web import server

        with mock.patch.object(server.health_mod, "clear") as clear, \
                mock.patch.object(server.doctor, "run_checks", lambda settings: [{"name": "ffmpeg", "level": "ok"}]):
            r = self.client.post("/api/health/recheck", headers=H)
        self.assertEqual(r.status_code, 200)
        clear.assert_called_once()
        self.assertEqual(r.json()["checks"][0]["name"], "ffmpeg")
        self.assertEqual(self.client.post("/api/health/recheck").status_code, 403)

    def test_tool_error_becomes_error_body(self):
        art = self._video_with_analysis()
        r = self.client.post("/api/render", json={"folder": str(art.folder), "slug": "other", "outputs": ["tree-md"]}, headers=H)
        err = r.json()["error"]
        self.assertEqual(err["code"], "bad_input")
        self.assertTrue(err["reason"] and err["remedy"]["action"])

    def test_note_slug_cannot_escape(self):
        art = self._video_with_analysis()
        r = self.client.get("/api/note", params={"folder": str(art.folder), "slug": "x/../../secret"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
