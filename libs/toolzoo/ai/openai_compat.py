"""OpenAI 與 Gemini（走 Gemini 的 OpenAI 相容端點）的呼叫層。

不同模型家族吃的參數不一樣（源自 Better Prompt 的 model_strategies.py）：

    家族                      token 上限參數            temperature   串流
    gpt-3.5 / gpt-4 / 4o      max_tokens                可以          可以
    gpt-4.1 / 4.5 / 5.x       max_completion_tokens     可以          可以
    o1 / o3 / o4              max_completion_tokens     不行          可以
    o1-preview                max_completion_tokens     不行          不行
    gemini-*                  max_tokens                可以          可以

這張表只是「第一次猜」。模型會改版、新模型會冒出來，所以 API 回 400 說某個參數
不支援時（例如 gpt-5 不收 temperature、組織未驗證不能串流 o3），會自動調整參數
重送一次，並記住這個模型的規則，同一個程式執行期間不會再錯第二次。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterator

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

DEFAULT_MAX_TOKENS = 16384


@dataclass(frozen=True)
class ModelRules:
    token_param: str = "max_tokens"
    temperature: bool = True
    stream: bool = True


_PREFIX_RULES: list[tuple[tuple[str, ...], ModelRules]] = [
    (("o1-preview",), ModelRules("max_completion_tokens", temperature=False, stream=False)),
    (("o1", "o3", "o4"), ModelRules("max_completion_tokens", temperature=False)),
    (("gpt-4.1", "gpt-4.5", "gpt-5"), ModelRules("max_completion_tokens")),
    (("gemini",), ModelRules("max_tokens")),
]

# 執行期間學到的規則：(provider, model) -> ModelRules
_learned: dict[tuple[str, str], ModelRules] = {}


def initial_rules(model: str) -> ModelRules:
    lower = model.lower()
    for prefixes, rules in _PREFIX_RULES:
        if lower.startswith(prefixes):
            return rules
    return ModelRules()


def rules_for(provider: str, model: str) -> ModelRules:
    return _learned.get((provider, model)) or initial_rules(model)


def _error_param(exc: Exception) -> tuple[str, str]:
    """從 400 錯誤裡找出是哪個參數出問題。回傳 (param, 原始訊息)。"""
    message = str(exc)
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            param = err.get("param") or ""
            message = err.get("message") or message
            if param:
                return str(param), message
    match = re.search(r"'(temperature|max_tokens|max_completion_tokens|stream)'", message)
    return (match.group(1) if match else ""), message


def _adjust(rules: ModelRules, exc: Exception) -> ModelRules | None:
    """依錯誤內容修正參數；看不懂這個錯誤就回傳 None（直接往上丟）。"""
    param, message = _error_param(exc)
    lower = message.lower()
    if param == "temperature" and rules.temperature:
        return replace(rules, temperature=False)
    if param == "max_tokens" and rules.token_param == "max_tokens":
        return replace(rules, token_param="max_completion_tokens")
    if param == "max_completion_tokens" and rules.token_param == "max_completion_tokens":
        return replace(rules, token_param="max_tokens")
    if param == "stream" and rules.stream:
        return replace(rules, stream=False)
    if "temperature" in lower and rules.temperature and ("support" in lower or "unsupported" in lower):
        return replace(rules, temperature=False)
    return None


def make_client(provider: str, api_key: str, timeout: float = 600.0):
    from openai import OpenAI

    if provider == "gemini":
        return OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL, timeout=timeout)
    return OpenAI(api_key=api_key, timeout=timeout)


def list_models(client, provider: str) -> list[str]:
    ids = [m.id.removeprefix("models/") for m in client.models.list()]
    if provider == "gemini":
        keep = [i for i in ids if i.startswith("gemini") and "embedding" not in i and "tts" not in i]
    else:
        chat_prefixes = ("gpt-", "o1", "o3", "o4", "chatgpt-")
        not_chat = ("audio", "realtime", "tts", "transcribe", "image", "embedding",
                    "moderation", "search", "instruct", "codex", "dall-e", "whisper")
        keep = [i for i in ids if i.startswith(chat_prefixes) and not any(s in i for s in not_chat)]
    return sorted(set(keep), reverse=True)


def stream_chat(
    client,
    provider: str,
    model: str,
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Iterator[str]:
    """逐段 yield 模型輸出的文字。不支援串流的模型會一次 yield 整段。"""
    from openai import BadRequestError

    rules = rules_for(provider, model)
    for _attempt in range(4):
        params: dict = {"model": model, "messages": messages, rules.token_param: max_tokens}
        if rules.temperature and temperature is not None:
            params["temperature"] = temperature
        try:
            if rules.stream:
                response = client.chat.completions.create(stream=True, **params)
            else:
                response = client.chat.completions.create(**params)
        except BadRequestError as exc:
            fixed = _adjust(rules, exc)
            if fixed is None:
                raise
            rules = fixed
            _learned[(provider, model)] = rules
            continue

        if rules.stream:
            for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
        else:
            content = response.choices[0].message.content or ""
            if content:
                yield content
        return
    raise RuntimeError(f"{model}：調整參數後仍然被 API 拒絕")
