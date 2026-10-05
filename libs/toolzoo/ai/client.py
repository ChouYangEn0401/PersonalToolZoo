"""工具端唯一需要用的介面：``LLM``。

    from toolzoo.ai import LLM

    llm = LLM("openai", "gpt-5.1")            # 金鑰自動從環境變數 / keys.env 找
    for piece in llm.stream(system, user):    # 串流（GUI 用）
        ...
    text = llm.complete(system, user)         # 一次拿完整結果（CLI / 批次用）

provider 不給時會從模型名稱猜（gemini-* → gemini、claude-* → anthropic，其餘 openai）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from toolzoo.ai import anthropic_claude, openai_compat
from toolzoo.ai.errors import LLMError, explain
from toolzoo.ai.keys import KEY_NAMES, find_key, keys_file

PROVIDERS: dict[str, str] = {
    "openai": "OpenAI（ChatGPT）",
    "gemini": "Google Gemini",
    "anthropic": "Anthropic Claude",
}

DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-5.1",
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-opus-5-5",
}


class MissingKeyError(RuntimeError):
    def __init__(self, provider: str):
        name = KEY_NAMES[provider][0]
        super().__init__(
            f"找不到 {PROVIDERS[provider]} 的 API 金鑰。\n"
            f"請在 {keys_file()} 加一行 {name}=你的金鑰，或設定環境變數 {name}。"
        )
        self.provider = provider


def provider_for_model(model: str | None) -> str | None:
    if not model:
        return None
    lower = model.lower()
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
        provider = provider or provider_for_model(model) or "openai"
        if provider not in PROVIDERS:
            raise ValueError(f"不認得的 provider：{provider}（可用：{', '.join(PROVIDERS)}）")
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]
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
        try:
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
