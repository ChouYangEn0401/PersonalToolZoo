"""toolzoo.ai 的單元測試（不打 API）。

    python -m unittest discover -s libs/tests -t libs
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolzoo.ai import errors, keys, openai_compat, text_modes  # noqa: E402
from toolzoo.ai.client import provider_for_model  # noqa: E402
from toolzoo.ai.prompts import strip_outer_fence, wrap  # noqa: E402


class FakeBadRequest(Exception):
    def __init__(self, message, param=None):
        super().__init__(message)
        self.body = {"error": {"message": message, "param": param}} if param else None


class KeysTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"TOOLZOO_DATA_DIR": self.tmp.name}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        for names in keys.KEY_NAMES.values():
            for name in names:
                os.environ.pop(name, None)

    def test_legacy_aliases_from_old_dotenv(self):
        legacy = Path(self.tmp.name) / "old.env"
        legacy.write_text("chatgpt=sk-legacy\ngemini = AIza-legacy\n", encoding="utf-8")
        self.assertEqual(keys.find_key("openai", [legacy])[0], "sk-legacy")
        self.assertEqual(keys.find_key("gemini", [legacy])[0], "AIza-legacy")

    def test_template_placeholder_is_ignored(self):
        template = Path(self.tmp.name) / ".env.example"
        template.write_text("OPENAI_API_KEY=sk-proj-......", encoding="utf-8")
        self.assertEqual(keys.find_key("openai", [template]), ("", ""))

    def test_env_var_wins_over_file(self):
        keys.save_key("openai", "sk-file")
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env"}):
            self.assertEqual(keys.find_key("openai")[0], "sk-env")

    def test_save_replaces_only_that_provider(self):
        keys.save_key("openai", "sk-1")
        keys.save_key("gemini", "AIza-1")
        keys.save_key("openai", "sk-2")
        text = keys.keys_file().read_text(encoding="utf-8")
        self.assertIn("OPENAI_API_KEY=sk-2", text)
        self.assertIn("GEMINI_API_KEY=AIza-1", text)
        self.assertNotIn("sk-1", text)


class OpenAIRulesTest(unittest.TestCase):
    def test_initial_guesses(self):
        self.assertEqual(openai_compat.initial_rules("gpt-4o-mini").token_param, "max_tokens")
        self.assertEqual(openai_compat.initial_rules("gpt-5.1").token_param, "max_completion_tokens")
        self.assertFalse(openai_compat.initial_rules("o3-mini").temperature)
        self.assertFalse(openai_compat.initial_rules("o1-preview").stream)

    def test_adjusts_on_unsupported_temperature(self):
        rules = openai_compat.initial_rules("gpt-5")
        exc = FakeBadRequest("Unsupported value: 'temperature' does not support 0.7 with this model.", "temperature")
        self.assertFalse(openai_compat._adjust(rules, exc).temperature)

    def test_adjusts_token_param_both_ways(self):
        legacy = openai_compat.initial_rules("gpt-4o")
        exc = FakeBadRequest("Unsupported parameter: 'max_tokens' is not supported with this model.")
        self.assertEqual(openai_compat._adjust(legacy, exc).token_param, "max_completion_tokens")

    def test_unknown_error_is_not_swallowed(self):
        rules = openai_compat.initial_rules("gpt-4o")
        self.assertIsNone(openai_compat._adjust(rules, FakeBadRequest("Invalid API key")))

    def test_stream_falls_back_and_remembers(self):
        calls = []

        class Completions:
            def create(self, **params):
                calls.append(params)
                if params.get("stream"):
                    raise FakeBadRequest("Your organization must be verified to stream this model.", "stream")
                msg = mock.Mock(content="完整回覆")
                return mock.Mock(choices=[mock.Mock(message=msg)])

        client = mock.Mock()
        client.chat.completions = Completions()
        with mock.patch("openai.BadRequestError", FakeBadRequest):
            out = "".join(openai_compat.stream_chat(client, "openai", "o3-test", [{"role": "user", "content": "hi"}]))
            self.assertEqual(out, "完整回覆")
            self.assertFalse(openai_compat.rules_for("openai", "o3-test").stream)
            calls.clear()
            "".join(openai_compat.stream_chat(client, "openai", "o3-test", []))
            self.assertEqual(len(calls), 1)  # 第二次直接用學到的規則，不再先撞一次 400


class PromptTest(unittest.TestCase):
    def test_wrap_and_fence(self):
        self.assertEqual(wrap(" hi ", "part", index="2"), '<part index="2">\nhi\n</part>')
        self.assertEqual(strip_outer_fence("```markdown\n# 標題\n內容\n```"), "# 標題\n內容")
        self.assertEqual(strip_outer_fence("一般文字 ```code```"), "一般文字 ```code```")

    def test_every_mode_builds(self):
        for mode, data in text_modes.MODES.items():
            for sub in data.submodes:
                system, user = text_modes.build_messages(mode, sub, "測試")
                self.assertIn("共通規則", system)
                self.assertTrue(user.startswith("<text>"))

    def test_provider_guess(self):
        self.assertEqual(provider_for_model("gemini-2.5-flash"), "gemini")
        self.assertEqual(provider_for_model("claude-opus-5-5"), "anthropic")   # 完整模型名 = API 金鑰版
        self.assertEqual(provider_for_model("gpt-5.1"), "openai")
        self.assertEqual(provider_for_model("sonnet"), "claude-sub")         # Claude Code 的別名 = 訂閱


def fake_claude_subscription(answer="整理好的文字", error=None):
    """假的 claude_subscription 模組：記錄呼叫參數，不會真的叫 claude、不花錢。"""
    import types

    mod = types.ModuleType("claude_subscription")

    class ClaudeError(RuntimeError):
        pass

    class ClaudeAuthError(ClaudeError):
        pass

    class ClaudeNotFoundError(FileNotFoundError):
        pass

    mod.ClaudeError, mod.ClaudeAuthError, mod.ClaudeNotFoundError = ClaudeError, ClaudeAuthError, ClaudeNotFoundError
    mod.calls = []

    def ask(prompt, **kwargs):
        mod.calls.append((prompt, kwargs))
        if error:
            raise getattr(mod, error)("boom")
        return types.SimpleNamespace(text=answer, cost_usd=0.001)

    def find_claude_binary():
        if error == "ClaudeNotFoundError":
            raise ClaudeNotFoundError("找不到 claude 執行檔")
        return r"C:\fake\claude.exe"

    mod.ask, mod.find_claude_binary = ask, find_claude_binary
    return mod


class ClaudeSubscriptionTest(unittest.TestCase):
    def use(self, mod):
        patcher = mock.patch.dict(sys.modules, {"claude_subscription": mod})
        patcher.start()
        self.addCleanup(patcher.stop)
        return mod

    def test_no_key_needed_and_one_piece(self):
        from toolzoo.ai import LLM

        mod = self.use(fake_claude_subscription("答案"))
        with mock.patch.dict(os.environ, {}, clear=True):          # 沒有任何金鑰也能建立
            llm = LLM("claude-sub")
        self.assertEqual(llm.model, "sonnet")
        final = {}
        self.assertEqual(list(llm.stream("系統", "內容", temperature=0.3, final=final)), ["答案"])
        self.assertEqual(final["text"], "答案")
        prompt, kwargs = mod.calls[0]
        self.assertEqual(prompt, "內容")
        self.assertEqual((kwargs["system"], kwargs["model"]), ("系統", "sonnet"))
        self.assertNotIn("temperature", kwargs)                     # 不支援的參數不會傳下去
        self.assertGreaterEqual(kwargs["timeout"], 600)             # 長逐字稿要夠久

    def test_list_models_checks_the_binary(self):
        from toolzoo.ai import LLM, LLMError

        self.use(fake_claude_subscription())
        self.assertEqual(LLM("claude-sub").list_models(), ["sonnet", "haiku", "opus"])
        self.use(fake_claude_subscription(error="ClaudeNotFoundError"))
        with self.assertRaises(LLMError) as ctx:
            LLM("claude-sub").list_models()
        self.assertIn("install.ps1", str(ctx.exception))

    def test_errors_are_explained(self):
        from toolzoo.ai import LLM, LLMError

        for error, words in (("ClaudeAuthError", "登入"), ("ClaudeError", "額度")):
            self.use(fake_claude_subscription(error=error))
            with self.assertRaises(LLMError) as ctx:
                LLM("claude-sub", "haiku").complete("s", "u")
            self.assertIn(words, str(ctx.exception), error)
        with mock.patch.dict(sys.modules, {"claude_subscription": None}):   # 沒裝套件
            with self.assertRaises(LLMError) as ctx:
                LLM("claude-sub").complete("s", "u")
        self.assertIn("claude-subscription", str(ctx.exception))


class ErrorTextTest(unittest.TestCase):
    """用 2026-10-05 實際收到的錯誤內容測，確保使用者看到的是下一步該做什麼。"""

    @staticmethod
    def api_error(status, body, message="Error"):
        exc = Exception(message)
        exc.status_code, exc.body = status, body
        return exc

    def test_quota_exhausted(self):
        exc = self.api_error(429, {"message": "You have no credits remaining.", "type": "insufficient_quota",
                                   "code": "credit_balance_exhausted"})
        text = errors.explain(exc, "openai", "gpt-5.1")
        self.assertIn("額度用完", text)
        self.assertIn("billing", text)

    def test_gemini_invalid_key(self):
        exc = self.api_error(400, [{"error": {"code": 400, "message": "Please pass a valid API key",
                                              "status": "INVALID_ARGUMENT"}}],
                             "Error code: 400 - Please pass a valid API key")
        self.assertIn("金鑰無效", errors.explain(exc, "gemini", "gemini-2.5-flash"))

    def test_unknown_model_and_fallback(self):
        self.assertIn("找不到模型", errors.explain(self.api_error(404, {}), "openai", "gpt-9"))
        self.assertIn("呼叫失敗", errors.explain(ValueError("boom"), "openai", "gpt-5.1"))

    def test_stream_wraps_errors(self):
        from toolzoo.ai.client import LLM

        llm = LLM.__new__(LLM)
        llm.provider, llm.model = "openai", "gpt-5.1"

        def broken(*_args):
            raise self.api_error(429, {"code": "insufficient_quota"})
            yield  # pragma: no cover

        llm._stream = broken
        with self.assertRaises(errors.LLMError) as ctx:
            list(llm.stream("s", "u"))
        self.assertIn("額度用完", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
