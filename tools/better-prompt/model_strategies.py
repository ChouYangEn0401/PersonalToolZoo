"""
model_strategies.py  —  Strategy Pattern for OpenAI model API parameters
=========================================================================
Each model family has its own concrete strategy that knows:
  • which token-limit parameter to use (max_tokens vs max_completion_tokens)
  • whether temperature is supported
  • whether streaming is supported

To add support for a new model family, create a subclass of ModelStrategy,
override the three members, and add a matching rule inside _RULES at the bottom.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

# ─────────────────────────────────────────────────────────────────────────────
# Tuneable defaults — easy to adjust per deployment
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_MAX_TOKENS: int = 4096


# ─────────────────────────────────────────────────────────────────────────────
# Abstract base
# ─────────────────────────────────────────────────────────────────────────────

class ModelStrategy(ABC):
    """Encapsulates the parameter differences between OpenAI model families."""

    name: str = "Unknown"

    @abstractmethod
    def build_params(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
    ) -> dict:
        """
        Return a fully-constructed kwargs dict for
        ``client.chat.completions.create(**kwargs)``.
        """

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether stream=True can be passed to this model family."""


# ─────────────────────────────────────────────────────────────────────────────
# Concrete strategies
# ─────────────────────────────────────────────────────────────────────────────

class StandardGPTStrategy(ModelStrategy):
    """
    Standard GPT models: gpt-4o, gpt-4o-mini, gpt-4-turbo,
    gpt-4, gpt-3.5-turbo …
    Supports: temperature, max_tokens, streaming.
    """
    name = "StandardGPT"

    def build_params(self, model: str, messages: list[dict], temperature: float) -> dict:
        return {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "max_tokens": DEFAULT_MAX_TOKENS,
        }

    @property
    def supports_streaming(self) -> bool:
        return True


class ModernGPTStrategy(ModelStrategy):
    """
    Newer GPT chat models: gpt-4.1, gpt-4.5, gpt-5.x …
    These models dropped max_tokens in favour of max_completion_tokens
    but still support temperature and streaming.
    Supports: temperature, max_completion_tokens, streaming.
    """
    name = "ModernGPT"

    def build_params(self, model: str, messages: list[dict], temperature: float) -> dict:
        return {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "max_completion_tokens": DEFAULT_MAX_TOKENS,
        }

    @property
    def supports_streaming(self) -> bool:
        return True


class ReasoningModelStrategy(ModelStrategy):
    """
    Modern reasoning models: o1, o1-mini, o3, o3-mini, o4-mini …
    Supports: max_completion_tokens, streaming.
    Does NOT support: temperature.
    """
    name = "ReasoningModel"

    def build_params(self, model: str, messages: list[dict], temperature: float) -> dict:
        return {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_completion_tokens": DEFAULT_MAX_TOKENS,
        }

    @property
    def supports_streaming(self) -> bool:
        return True


class LegacyReasoningStrategy(ModelStrategy):
    """
    Early reasoning models (pre-streaming): o1-preview.
    Supports: max_completion_tokens only.
    Does NOT support: temperature, streaming.
    """
    name = "LegacyReasoning"

    def build_params(self, model: str, messages: list[dict], temperature: float) -> dict:
        return {
            "model": model,
            "messages": messages,
            "max_completion_tokens": DEFAULT_MAX_TOKENS,
        }

    @property
    def supports_streaming(self) -> bool:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────
#
# Each rule is (prefix_tuple, strategy_instance).  The first matching prefix
# wins; the fallback at the end covers everything else.
#
_RULES: list[tuple[tuple[str, ...], ModelStrategy]] = [
    # ── Reasoning family ───────────────────────────────────────────────────
    (("o1-preview",),                           LegacyReasoningStrategy()),
    (("o1-", "o1", "o3-", "o3", "o4-", "o4"),   ReasoningModelStrategy()),
    # ── Newer GPT family (max_completion_tokens, still supports temperature)
    (("gpt-4.1", "gpt-4.5", "gpt-5"),           ModernGPTStrategy()),
    # ── Default: standard GPT ──────────────────────────────────────────────
    (("",),                                     StandardGPTStrategy()),
]


def get_strategy(model_id: str) -> ModelStrategy:
    """Return the correct ModelStrategy for *model_id*."""
    lower = model_id.lower()
    for prefixes, strategy in _RULES:
        if any(lower.startswith(p) for p in prefixes):
            return strategy
    # Fallback — should never be reached given the ("",) catch-all above
    return StandardGPTStrategy()


# ─────────────────────────────────────────────────────────────────────────────
# Shared execution helper (runs inside a background thread)
# ─────────────────────────────────────────────────────────────────────────────

def run_completion(
    client,
    model_id: str,
    messages: list[dict],
    temperature: float,
    on_token: Callable[[str], Any],
    on_done: Callable[[], Any],
    on_error: Callable[[Exception], Any],
) -> None:
    """
    Execute an OpenAI chat completion using the strategy for *model_id*.

    Must be called from a background thread.  The three callbacks are
    invoked synchronously from that same thread — callers are responsible
    for marshalling onto the UI thread (e.g. ``self.after(0, ...)``) if needed.

    Parameters
    ----------
    client      OpenAI client instance
    model_id    Full model identifier string, e.g. "gpt-4o-mini"
    messages    OpenAI messages list
    temperature Sampling temperature (ignored by strategies that don't support it)
    on_token    Called once per text token/chunk
    on_done     Called when the completion finishes successfully
    on_error    Called with the exception when something goes wrong
    """
    strategy = get_strategy(model_id)
    params = strategy.build_params(model_id, messages, temperature)
    strategy_label = f"[策略: {strategy.name} | 模型: {model_id}]"

    try:
        if strategy.supports_streaming:
            stream = client.chat.completions.create(**params)
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    on_token(delta)
        else:
            # Non-streaming: deliver the full response as one token
            response = client.chat.completions.create(**params)
            content = response.choices[0].message.content or ""
            if content:
                on_token(content)

        on_done()
    except Exception as exc:
        # Wrap with strategy info so the UI error message is easy to debug
        enriched = RuntimeError(f"{strategy_label}\n{exc}")
        on_error(enriched)
