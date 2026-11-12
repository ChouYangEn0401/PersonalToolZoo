"""doctor：用假環境測缺 ffmpeg、缺 JS、yt-dlp 太舊；輸出不含金鑰。離線。"""

import json
import sys
import unittest
from datetime import date
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes import doctor  # noqa: E402
from video_notes.config import Settings  # noqa: E402

FAKE_KEY = "sk-test-abcdefghijklmnop1234"
VERSIONS = {"deno": "deno 2.5.1 (stable)\nv8 13.0", "node": "v22.4.0"}


def make_env(**over):
    base = dict(
        find_ffmpeg=lambda: r"C:\ffmpeg\bin\ffmpeg.exe",
        find_js=lambda: ["deno"],
        version_output=lambda cmd: VERSIONS.get(cmd[0], ""),
        ytdlp_version=lambda: "2026.10.26",
        today=lambda: date(2026, 11, 12),
        cuda=lambda: (False, "沒有偵測到 NVIDIA 顯示卡，使用 CPU"),
        keys=lambda: {"claude-sub": True, "openai": False, "gemini": False, "anthropic": False},
        health_entries=lambda: {},
        adapter_checks=lambda s: [],
        providers={"claude-sub": "Claude 訂閱", "openai": "OpenAI", "gemini": "Gemini", "anthropic": "Anthropic"},
    )
    base.update(over)
    return doctor.Env(**base)


def by_name(results, prefix):
    return next(r for r in results if r["name"].startswith(prefix))


class DoctorTest(unittest.TestCase):
    def test_healthy_environment(self):
        results = doctor.run_checks(Settings(), make_env())
        self.assertTrue(all(r["ok"] for r in results), doctor.as_text(results))
        self.assertEqual(by_name(results, "ffmpeg")["level"], "ok")
        self.assertEqual(by_name(results, "JavaScript")["level"], "ok")
        self.assertIn("距今 17 天", by_name(results, "yt-dlp")["message"])
        self.assertEqual(by_name(results, "GPU")["level"], "warn")   # 沒 GPU 只是提醒

    def test_missing_ffmpeg(self):
        results = doctor.run_checks(Settings(), make_env(find_ffmpeg=lambda: None))
        item = by_name(results, "ffmpeg")
        self.assertEqual((item["ok"], item["level"]), (False, "error"))
        self.assertEqual(item["error"]["code"], "dependency_missing")
        self.assertTrue(item["error"]["remedy"]["action"])

    def test_missing_js_runtime(self):
        results = doctor.run_checks(Settings(), make_env(find_js=lambda: []))
        item = by_name(results, "JavaScript")
        self.assertEqual(item["level"], "error")
        self.assertEqual(item["error"]["code"], "dependency_missing")

    def test_bun_alone_does_not_count(self):
        results = doctor.run_checks(Settings(), make_env(find_js=lambda: ["bun"]))
        self.assertEqual(by_name(results, "JavaScript")["error"]["code"], "dependency_missing")

    def test_old_node_is_outdated_and_unknown_version_is_warn(self):
        old = make_env(find_js=lambda: ["node"], version_output=lambda cmd: "v20.1.0")
        item = by_name(doctor.run_checks(Settings(), old), "JavaScript")
        self.assertEqual((item["level"], item["error"]["code"]), ("error", "dependency_outdated"))
        unknown = make_env(find_js=lambda: ["deno"], version_output=lambda cmd: "")
        self.assertEqual(by_name(doctor.run_checks(Settings(), unknown), "JavaScript")["level"], "warn")

    def test_old_ytdlp(self):
        warn = by_name(doctor.run_checks(Settings(), make_env(ytdlp_version=lambda: "2026.08.01")), "yt-dlp")
        self.assertEqual(warn["level"], "warn")
        err = by_name(doctor.run_checks(Settings(), make_env(ytdlp_version=lambda: "2026.01.01")), "yt-dlp")
        self.assertEqual((err["level"], err["error"]["code"]), ("error", "dependency_outdated"))
        self.assertEqual(err["error"]["remedy"]["kind"], "needs_update")
        self.assertIn("pip install -U", err["error"]["remedy"]["action"])

    def test_ytdlp_not_installed(self):
        item = by_name(doctor.run_checks(Settings(), make_env(ytdlp_version=lambda: "?")), "yt-dlp")
        self.assertEqual(item["error"]["code"], "dependency_missing")

    def test_selected_provider_without_key_is_error(self):
        results = doctor.run_checks(Settings(provider="openai"), make_env())
        item = by_name(results, "AI：OpenAI")
        self.assertEqual((item["level"], item["error"]["code"]), ("error", "auth_required"))
        self.assertEqual(by_name(results, "AI：Gemini")["level"], "ok")

    def test_degraded_entries_are_listed(self):
        entry = {"code": "dependency_outdated", "first_seen": "a", "last_seen": "b", "count": 3,
                 "state": "degraded", "version": "2026.10.26"}
        results = doctor.run_checks(Settings(), make_env(health_entries=lambda: {"yt-dlp": entry}))
        item = by_name(results, "已標記壞掉：yt-dlp")
        self.assertEqual(item["level"], "error")
        self.assertEqual(item["error"]["code"], "dependency_outdated")

    def test_output_has_no_secrets_and_json_roundtrips(self):
        env = make_env(find_ffmpeg=lambda: r"C:\Users\someone\tools\ffmpeg.exe",
                       keys=lambda: {"openai": True, "claude-sub": False})
        results = doctor.run_checks(Settings(), env)
        text, blob = doctor.as_text(results), doctor.as_json(results)
        for out in (text, blob):
            self.assertNotIn(FAKE_KEY, out)
            self.assertNotIn("someone", out)
        self.assertEqual(json.loads(blob), results)
        self.assertIn("[錯誤]", text)
        for r in results:
            self.assertEqual(set(r), {"name", "ok", "level", "message", "error"})


if __name__ == "__main__":
    unittest.main()
