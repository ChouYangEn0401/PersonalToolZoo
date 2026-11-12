"""health.json 記帳：假時鐘、3 次 degraded、成功重設、版本改變解除、壞檔、並行寫入。"""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes.errors import ToolError  # noqa: E402
from video_notes.health import HealthBook  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        self.t += 60
        return self.t


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "data" / "health.json"
        self.book = HealthBook(self.path, clock=Clock())

    def tearDown(self):
        self.tmp.cleanup()

    def test_three_failures_degrade(self):
        for i in range(2):
            self.book.record_failure("yt-dlp", "dependency_outdated", "2026.10.26")
            self.assertIsNone(self.book.is_degraded("yt-dlp"))
        entry = self.book.record_failure("yt-dlp", "dependency_outdated", "2026.10.26")
        self.assertEqual((entry["count"], entry["state"]), (3, "degraded"))
        err = self.book.is_degraded("yt-dlp")
        self.assertIsInstance(err, ToolError)
        self.assertEqual(err.code, "dependency_outdated")
        self.assertFalse(err.retryable)
        self.assertEqual(err.remedy.kind, "needs_update")
        self.assertIn("pip install -U", err.remedy.action)

    def test_accepts_tool_error_and_stores_only_codes(self):
        secret = "sk-test-abcdefghijklmnop1234"
        for _ in range(3):
            self.book.record_failure("llm:openai", ToolError("auth_required", f"key {secret} bad", detail=secret))
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn(secret, raw)
        self.assertNotIn("reason", raw)
        data = json.loads(raw)["llm:openai"]
        self.assertEqual(set(data), {"code", "first_seen", "last_seen", "count", "state", "version"})
        self.assertNotIn("Users", raw)

    def test_different_code_restarts_count(self):
        self.book.record_failure("s", "network_unreachable")
        self.book.record_failure("s", "network_unreachable")
        entry = self.book.record_failure("s", "rate_limited")
        self.assertEqual((entry["code"], entry["count"], entry["state"]), ("rate_limited", 1, "failing"))

    def test_success_resets(self):
        for _ in range(3):
            self.book.record_failure("s", "network_unreachable")
        self.book.record_success("s")
        self.assertIsNone(self.book.is_degraded("s"))
        self.assertNotIn("s", self.book.entries())
        self.assertEqual(self.book.record_failure("s", "network_unreachable")["count"], 1)

    def test_input_problems_are_not_counted(self):
        for code in ("bad_input", "unsupported_source", "cancelled"):
            self.assertIsNone(self.book.record_failure("s", code))
        self.assertEqual(self.book.entries(), {})

    def test_version_change_clears(self):
        for _ in range(3):
            self.book.record_failure("yt-dlp", "dependency_outdated", "2026.10.26")
        self.assertIsNotNone(self.book.is_degraded("yt-dlp", "2026.10.26"))
        self.assertIsNone(self.book.is_degraded("yt-dlp", "2026.11.12"))
        self.assertNotIn("yt-dlp", self.book.entries())

    def test_failure_with_new_version_restarts(self):
        for _ in range(2):
            self.book.record_failure("yt-dlp", "dependency_outdated", "2026.10.26")
        entry = self.book.record_failure("yt-dlp", "dependency_outdated", "2026.11.12")
        self.assertEqual(entry["count"], 1)

    def test_clear(self):
        for src in ("a", "b"):
            for _ in range(3):
                self.book.record_failure(src, "internal_bug")
        self.book.clear("a")
        self.assertIsNone(self.book.is_degraded("a"))
        self.assertIsNotNone(self.book.is_degraded("b"))
        self.book.clear()
        self.assertIsNone(self.book.is_degraded("b"))

    def test_corrupt_file_is_treated_as_empty(self):
        self.path.parent.mkdir(parents=True)
        for junk in ("{not json", "[1,2,3]", '{"a": 5}', ""):
            self.path.write_text(junk, encoding="utf-8")
            self.assertIsNone(self.book.is_degraded("a"))
            self.assertEqual(self.book.record_failure("a", "internal_bug")["count"], 1)
            self.book.clear()

    def test_concurrent_writes_do_not_lose_counts(self):
        def work():
            for _ in range(25):
                self.book.record_failure("s", "network_unreachable")

        threads = [threading.Thread(target=work) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(self.book.entries()["s"]["count"], 200)
        json.loads(self.path.read_text(encoding="utf-8"))   # 檔案沒被寫壞


if __name__ == "__main__":
    unittest.main()
