"""工具端唯一需要用的介面：``LLM``。

    from toolzoo.ai import LLM

    llm = LLM("claude-sub", "sonnet")         # Claude 訂閱（Claude Code）：不需要金鑰
    llm = LLM("openai", "gpt-5.1")            # 金鑰自動從環境變數 / keys.env 找
    for piece in llm.stream(system, user):    # 串流（GUI 用）
        ...
    text = llm.complete(system, user)         # 一次拿完整結果（CLI / 批次用）

provider 不給時會從模型名稱猜：sonnet / haiku / opus → claude-sub、gemini-* → gemini、
claude-* → anthropic（API 金鑰版），其餘 openai。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from toolzoo.ai import anthropic_claude, claude_code, openai_compat
from toolzoo.ai.errors import LLMError, explain
from toolzoo.ai.keys import KEY_NAMES, find_key, keys_file

# 順序就是選單的順序；Claude 訂閱是預設服務（用自己的訂閱、不需要 API 金鑰）
PROVIDERS: dict[str, str] = {
    claude_code.KEY: "Claude 訂閱（Claude Code）",
    "openai": "OpenAI（ChatGPT）",
    "gemini": "Google Gemini",
    "anthropic": "Anthropic Claude（API 金鑰）",
}

DEFAULT_PROVIDER = claude_code.KEY

DEFAULT_MODELS: dict[str, str] = {
    claude_code.KEY: claude_code.DEFAULT_MODEL,
    "openai": "gpt-5.1",
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-opus-5-5",
}

NO_KEY_PROVIDERS = {claude_code.KEY}


class MissingKeyError(RuntimeError):
    def __init__(self, provider: str):
        name = KEY_NAMES[provider][0]
        super().__init__(
            f"找不到 {PROVIDERS[provider]} 的 API 金鑰。\n"
            f"請在 {keys_file()} 加一行 {name}=你的金鑰，或設定環境變數 {name}。"
        )
        self.provider = provider


def needs_key(provider: str) -> bool:
    return provider not in NO_KEY_PROVIDERS


def provider_for_model(model: str | None) -> str | None:
    if not model:
        return None
    lower = model.lower()
    if lower in claude_code.MODELS:
        return claude_code.KEY
    if lower.startswith("gemini"):
        return "gemini"
    if lower.startswith("claude"):
        return "anthropic"
    return "openai"


class LLM:
    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        *,
        api_key: str | None = None,
        key_files: Iterable[Path] = (),
        timeout: float = 600.0,
    ):
        provider = provider or provider_for_model(model) or DEFAULT_PROVIDER
        if provider not in PROVIDERS:
            raise ValueError(f"不認得的 provider：{provider}（可用：{', '.join(PROVIDERS)}）")
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]
        self._client = None
        if not needs_key(provider):
            return
        key = (api_key or "").strip() or find_key(provider, key_files)[0]
        if not key:
            raise MissingKeyError(provider)
        if provider == "anthropic":
            self._client = anthropic_claude.make_client(key, timeout)
        else:
            self._client = openai_compat.make_client(provider, key, timeout)

    def __repr__(self) -> str:
        return f"LLM({self.provider!r}, {self.model!r})"

    def list_models(self) -> list[str]:
        """帳號可用的模型。Claude 訂閱沒有清單 API：順便確認 Claude Code 找得到（不花錢）。"""
        try:
            if self.provider == claude_code.KEY:
                claude_code.find_binary()
                return list(claude_code.MODELS)
            if self.provider == "anthropic":
                return anthropic_claude.list_models(self._client)
            return openai_compat.list_models(self._client, self.provider)
        except Exception as exc:  # noqa: BLE001 — 統一翻成看得懂的訊息
            raise LLMError(explain(exc, self.provider, self.model)) from exc

    def stream(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        final: dict | None = None,
    ) -> Iterator[str]:
        """逐段 yield 輸出。``final`` 有給的話，結束時 final["text"] 是完整、權威的結果。

        出錯時丟 LLMError，訊息已經是給人看的中文（額度用完、金鑰無效、被限流…），原始例外在 __cause__。
        """
        try:
            yield from self._stream(system, user, temperature, max_tokens, final)
        except (LLMError, anthropic_claude.ClaudeRefusal):
            raise
        except Exception as exc:  # noqa: BLE001
            raise LLMError(explain(exc, self.provider, self.model)) from exc

    def _stream(self, system, user, temperature, max_tokens, final) -> Iterator[str]:
        if self.provider == claude_code.KEY:
            # 沒有串流：一次回整段；temperature / max_tokens 不支援，忽略
            text = claude_code.complete(self.model, system, user)
            if final is not None:
                final["text"] = text
            yield text
            return

        if self.provider == "anthropic":
            yield from anthropic_claude.stream_chat(
                self._client, self.model, system,
                [{"role": "user", "content": user}],
                temperature=temperature,
                max_tokens=max_tokens or anthropic_claude.DEFAULT_MAX_TOKENS,
                final=final,
            )
            return

        messages = [{"role": "user", "content": user}]
        if system:
            messages.insert(0, {"role": "system", "content": system})
        parts: list[str] = []
        for piece in openai_compat.stream_chat(
            self._client, self.provider, self.model, messages,
            temperature=temperature,
            max_tokens=max_tokens or openai_compat.DEFAULT_MAX_TOKENS,
        ):
            parts.append(piece)
            yield piece
        if final is not None:
            final["text"] = "".join(parts)

    def complete(self, system: str, user: str, **kwargs) -> str:
        final: dict = {}
        streamed = "".join(self.stream(system, user, final=final, **kwargs))
        return final.get("text", streamed)
