"""openai-compat 分析 AI 與 capabilities_for。完全離線：假 client，不打任何端點。"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes.adapters import llm  # noqa: E402
from video_notes.config import Settings  # noqa: E402
from video_notes.errors import ToolError  # noqa: E402

HAS_OPENAI = importlib.util.find_spec("openai") is not None
SECRET = "tok-compat-SECRET-1234567890"


class ApiError(Exception):
    def __init__(self, msg, status_code=None):
        super().__init__(msg)
        self.status_code = status_code


def chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def fake_factory(handler, seen=None):
    def factory(base_url, key, timeout):
        if seen is not None:
            seen.append((base_url, key))
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=handler)))
    return factory


@unittest.skipUnless(HAS_OPENAI, "沒裝 openai（stream_chat 需要它的例外類別）")
class StreamTests(unittest.TestCase):
    def make(self, handler, key=SECRET, seen=None):
        return llm.CompatLLM("http://localhost:11434/v1", "qwen2.5:7b", key, client_factory=fake_factory(handler, seen))

    def test_stream_yields_pieces_and_final(self):
        calls = []

        def handler(**kw):
            calls.append(kw)
            return iter([chunk("你"), chunk("好"), SimpleNamespace(choices=[])])
        model = self.make(handler)
        final = {}
        out = list(model.stream("sys", "usr", temperature=0.2, final=final))
        self.assertEqual(out, ["你", "好"])
        self.assertEqual(final["text"], "你好")
        self.assertEqual(model.provider, "openai-compat")
        self.assertEqual(model.model, "qwen2.5:7b")
        self.assertEqual(calls[0]["messages"][0], {"role": "system", "content": "sys"})
        self.assertEqual(calls[0]["temperature"], 0.2)
        self.assertTrue(calls[0]["stream"])

    def test_empty_key_uses_placeholder(self):
        seen = []
        list(self.make(lambda **kw: iter([chunk("a")]), key="", seen=seen).stream("s", "u"))
        self.assertEqual(seen, [("http://localhost:11434/v1", "not-needed")])

    def test_errors_become_tool_error_without_key(self):
        cases = [(401, "auth_expired"), (404, "config_invalid"), (429, "rate_limited"), (500, "network_unreachable")]
        for status, code in cases:
            with self.subTest(status=status):
                def boom(**kw):
                    raise ApiError(f"failed Authorization: Bearer {SECRET} key={SECRET}", status)
                with self.assertRaises(ToolError) as ctx:
                    list(self.make(boom).stream("s", "u"))
                err = ctx.exception
                self.assertEqual(err.code, code)
                self.assertNotIn(SECRET, str(err) + repr(err.to_dict()))
                self.assertIn(err.remedy.kind, ("needs_config", "none"))

    def test_connection_error_mentions_endpoint(self):
        def boom(**kw):
            raise type("APIConnectionError", (Exception,), {})("Connection error.")
        with self.assertRaises(ToolError) as ctx:
            list(self.make(boom).stream("s", "u"))
        self.assertEqual(ctx.exception.code, "network_unreachable")
        self.assertIn("localhost:11434", ctx.exception.remedy.action)

    def test_unknown_error_not_swallowed(self):
        def boom(**kw):
            raise ValueError("weird")
        with self.assertRaises(ToolError) as ctx:
            list(self.make(boom).stream("s", "u"))
        self.assertEqual(ctx.exception.code, "internal_bug")


class BuildTests(unittest.TestCase):
    def test_build_compat(self):
        with mock.patch.dict(os.environ, {"OPENAI_COMPAT_API_KEY": SECRET}):
            model = llm.build_llm(Settings(provider="openai-compat", model="llama3", compat_base_url="http://h:1/v1"))
        self.assertIsInstance(model, llm.CompatLLM)
        self.assertEqual((model.provider, model.model, model.base_url), ("openai-compat", "llama3", "http://h:1/v1"))
        self.assertEqual(model._key, SECRET)
        self.assertNotIn(SECRET, repr(model))

    def test_missing_url_or_model_is_config_invalid(self):
        for kwargs in ({"compat_base_url": "", "model": "m"}, {"compat_base_url": "http://h/v1", "model": ""}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ToolError) as ctx:
                    llm.build_llm(Settings(provider="openai-compat", **kwargs))
                self.assertEqual(ctx.exception.code, "config_invalid")
                self.assertEqual(ctx.exception.remedy.kind, "needs_config")

    def test_key_may_be_empty(self):
        with mock.patch.dict(os.environ, {"OPENAI_COMPAT_API_KEY": ""}), \
                mock.patch("toolzoo.appdirs.env_files", return_value=[]):
            self.assertEqual(llm.compat_key(), "")

    def test_key_from_env_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("OPENAI_COMPAT_API_KEY=from-file\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"OPENAI_COMPAT_API_KEY": ""}), \
                    mock.patch("toolzoo.appdirs.env_files", return_value=[env]):
                self.assertEqual(llm.compat_key(), "from-file")

    def test_other_providers_use_shared_llm(self):
        with mock.patch("toolzoo.ai.LLM") as shared:
            llm.build_llm(Settings(provider="openai", model="gpt-5.1"))
            shared.assert_called_once_with("openai", "gpt-5.1")
            shared.reset_mock()
            llm.build_llm(Settings(provider="claude-sub", model=""))
            shared.assert_called_once_with("claude-sub", None)

    def test_capabilities_for(self):
        keys = {"supports_json_mode", "max_context_tokens", "privacy", "cost_hint"}
        for provider in ("claude-sub", "openai", "gemini", "anthropic", "openai-compat", "unknown"):
            caps = llm.capabilities_for(provider, "m")
            self.assertEqual(set(caps), keys)
            self.assertGreater(caps["max_context_tokens"], 0)
        self.assertEqual(llm.capabilities_for("openai-compat", "m")["privacy"], "local-or-custom")
        self.assertLess(llm.capabilities_for("openai-compat", "m")["max_context_tokens"],
                        llm.capabilities_for("openai", "gpt-5.1")["max_context_tokens"])
        self.assertEqual(llm.capabilities_for("openai", "gpt-5.1")["privacy"], "cloud")


if __name__ == "__main__":
    unittest.main()
