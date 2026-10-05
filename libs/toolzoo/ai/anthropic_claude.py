"""Claude（Anthropic Messages API）的呼叫層。

跟 OpenAI 相容端點分開放，因為參數規則完全不同：

- 目前的 Claude 模型（Opus 4.7 以後、Sonnet 5 / 5.5、Opus 5 / 5.5、Fable）不收 temperature，
  送了會 400，所以只對還支援的舊型號（Haiku 4.5、4.6 世代、3.x）送。
- 一律走串流：輸出長時不會撞到 HTTP timeout。
- 模型可能因安全分類器而拒答（HTTP 200、stop_reason == "refusal"）。對支援的模型
  開啟伺服器端 fallback（fallbacks: "default"），被拒時 API 會在同一次呼叫裡改用
  建議的模型重跑；整條鏈都拒絕才當成錯誤。
"""

from __future__ import annotations

from typing import Iterator

DEFAULT_MAX_TOKENS = 64000  # 串流時給足空間；這是上限不是用量
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")

_TEMPERATURE_OK = ("claude-haiku-4-5", "claude-opus-4-6", "claude-sonnet-4-6", "claude-3")


def accepts_temperature(model: str) -> bool:
    return model.startswith(_TEMPERATURE_OK)


def make_client(api_key: str, timeout: float = 600.0):
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=timeout)


def list_models(client) -> list[str]:
    return sorted({m.id for m in client.models.list()}, reverse=True)


def _final_text(message) -> str:
    """最終回覆的文字。發生過 fallback 時只取最後一個模型寫的部分。"""
    parts: list[str] = []
    for block in message.content:
        if block.type == "fallback":
            parts = []
        elif block.type == "text":
            parts.append(block.text)
    return "".join(parts)


class ClaudeRefusal(RuntimeError):
    pass


def stream_chat(
    client,
    model: str,
    system: str,
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    final: dict | None = None,
) -> Iterator[str]:
    """逐段 yield 文字。``final`` 若有給，結束時會放入 {"text": 權威的完整輸出}。

    有 fallback 時，串流過程中可能先出現被拒模型的部分文字，所以呼叫端應在結束後
    用 final["text"] 取代畫面上的內容。
    """
    params: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        params["system"] = system
    if temperature is not None and accepts_temperature(model):
        params["temperature"] = temperature

    if model in FALLBACK_MODELS:
        stream_ctx = client.beta.messages.stream(betas=[FALLBACK_BETA], fallbacks="default", **params)
    else:
        stream_ctx = client.messages.stream(**params)

    with stream_ctx as stream:
        for text in stream.text_stream:
            yield text
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        raise ClaudeRefusal(f"Claude 拒絕回答（分類：{category or '未提供'}）")
    if final is not None:
        final["text"] = _final_text(message)
        final["stop_reason"] = message.stop_reason
