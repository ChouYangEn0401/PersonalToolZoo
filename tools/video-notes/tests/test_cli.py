"""CLI 參數怎麼變成這一次執行的設定（不下載、不呼叫 AI）。"""

import contextlib
import io
import sys
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes.cli import _settings_from_args, build_parser  # noqa: E402
from video_notes.config import Settings  # noqa: E402


class SettingsFromArgsTest(unittest.TestCase):
    def settings(self, *argv: str, **saved) -> Settings:
        return _settings_from_args(build_parser().parse_args(["https://youtu.be/x", *argv]), Settings(**saved))

    def test_default_is_claude_subscription(self):
        self.assertEqual(self.settings().provider, "claude-sub")

    def test_saved_choice_is_kept(self):
        s = self.settings(provider="gemini", model="gemini-2.5-pro")
        self.assertEqual((s.provider, s.model), ("gemini", "gemini-2.5-pro"))

    def test_model_alone_picks_its_provider(self):
        s = self.settings("--model", "haiku", provider="openai", model="gpt-5.1")
        self.assertEqual((s.provider, s.model), ("claude-sub", "haiku"))
        s = self.settings("--model", "gemini-2.5-flash")
        self.assertEqual((s.provider, s.model), ("gemini", "gemini-2.5-flash"))

    def test_provider_alone_uses_its_default_model(self):
        s = self.settings("--provider", "openai", model="haiku")
        self.assertEqual((s.provider, s.model), ("openai", ""))

    def test_unknown_provider_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(["--provider", "chatgpt"])


if __name__ == "__main__":
    unittest.main()
