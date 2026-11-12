"""分析用的 AI adapter。

主要的服務（Claude 訂閱、OpenAI、Gemini、Claude API）走共用的 libs/toolzoo/ai 的 LLM，這裡不重寫。
這個檔只補兩件事：
- build_llm(settings)：依設定建立 LLM；provider == "openai-compat" 時用自訂的 base_url（Ollama、LM Studio、其他服務商）
- capabilities_for(provider, model)：{supports_json_mode, max_context_tokens, privacy, cost_hint}，給分析切段與 UI 用

任何 LLM 物件只要有：provider、model 屬性，以及
    stream(system, user, *, temperature=None, final=None) -> Iterator[str]
就能用（測試用 FakeLLM 也是這樣）。失敗丟 toolzoo.ai.LLMError 或 ToolError；analyze.py 負責轉成 ToolError。

openai-compat 的設定：settings.compat_base_url（例如 http://localhost:11434/v1）、settings.model、
金鑰在 .env 的 OPENAI_COMPAT_API_KEY（可以空：Ollama 不需要；SDK 要求非空字串，會代填 "not-needed"）。
這裡的失敗一律直接丟 ToolError（金鑰會從訊息抹掉）。
"""

from __future__ import annotations

import os
from typing import Callable, Iterator

from video_notes.errors import Remedy, ToolError

COMPAT = "openai-compat"
COMPAT_KEY_NAME = "OPENAI_COMPAT_API_KEY"
SOURCE = "llm:openai-compat"
COMPAT_MAX_TOKENS = 8192   # 輸出上限；本機小模型常常不收太大的值


def compat_key() -> str:
    """環境變數 → 專案 .env 的 OPENAI_COMPAT_API_KEY；沒有就回空字串（不是錯誤）。"""
    value = os.environ.get(COMPAT_KEY_NAME, "").strip()
    if value:
        return value
    from toolzoo.appdirs import env_files, read_env_file

    for path in env_files():
        value = read_env_file(path).get(COMPAT_KEY_NAME, "").strip()
        if value and not value.endswith("..."):
            return value
    return ""


class CompatLLM:
    """OpenAI 相容端點。介面跟 toolzoo.ai.LLM 一樣：provider、model、stream()。"""

    provider = COMPAT

    def __init__(self, base_url: str, model: str, api_key: str = "", *, timeout: float = 600.0,
                 client_factory: Callable[[str, str, float], object] | None = None):
        base_url = (base_url or "").strip()
        model = (model or "").strip()
        if not base_url:
            raise ToolError("config_invalid", "沒有設定相容端點的網址（compat_base_url）", source=SOURCE,
                            remedy=Remedy("needs_config", "在設定填入端點，例如 Ollama 是 http://localhost:11434/v1"))
        if not model:
            raise ToolError("config_invalid", "沒有指定相容端點要用的模型名稱", source=SOURCE,
                            remedy=Remedy("needs_config", "在設定的「模型」欄填入該服務的模型名稱（例如 Ollama 的 qwen2.5:7b）"))
        self.base_url = base_url
        self.model = model
        self._key = api_key
        self._client = None
        self._client_factory = client_factory
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"CompatLLM({self.base_url!r}, {self.model!r})"

    def _get_client(self):
        if self._client is None:
            key = self._key or "not-needed"
            if self._client_factory is not None:
                self._client = self._client_factory(self.base_url, key, self._timeout)
            else:
                try:
                    from openai import OpenAI
                except ImportError as exc:
                    raise _convert(exc, self._key) from exc
                self._client = OpenAI(api_key=key, base_url=self.base_url, timeout=self._timeout)
        return self._client

    def stream(self, system: str, user: str, *, temperature: float | None = None,
               final: dict | None = None) -> Iterator[str]:
        from toolzoo.ai import openai_compat

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        parts: list[str] = []
        try:
            client = self._get_client()
            for piece in openai_compat.stream_chat(client, COMPAT, self.model, messages, temperature=temperature,
                                                   max_tokens=COMPAT_MAX_TOKENS):
                parts.append(piece)
                yield piece
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 — 全部轉成 ToolError，不吞
            raise _convert(exc, self._key, self.base_url, self.model) from exc
        if final is not None:
            final["text"] = "".join(parts)


def _convert(exc: BaseException, key: str, base_url: str = "", model: str = "") -> ToolError:
    from video_notes.adapters.stt_chunk import to_tool_error

    status = getattr(exc, "status_code", None)
    err = to_tool_error(exc, source=SOURCE, service="相容端點", key=key,
                        key_hint=f"在專案的 .env 設定 {COMPAT_KEY_NAME}")
    if status == 404:
        err.reason = f"相容端點找不到模型「{model}」或網址路徑不對"[:120]
        err.remedy = Remedy("needs_config", "確認 compat_base_url 結尾有 /v1，且模型名稱存在（Ollama 要先 ollama pull）")
    elif err.code == "network_unreachable" and status is None:
        err.reason = "連不上相容端點"
        err.remedy = Remedy("needs_config", f"確認服務已啟動、網址 {base_url or 'compat_base_url'} 正確")
    return err


def build_llm(settings):
    """依設定建立 LLM；openai-compat 用自訂端點，其餘直接用 toolzoo.ai.LLM。"""
    if settings.provider == COMPAT:
        return CompatLLM(settings.compat_base_url, settings.model, compat_key())
    from toolzoo.ai import LLM

    return LLM(settings.provider, settings.model or None)


# 保守估計：寧可讓分析多切幾段，也不要超出上下文。
_CAPS: dict[str, dict] = {
    "claude-sub": {"supports_json_mode": False, "max_context_tokens": 150000, "privacy": "cloud",
                   "cost_hint": "用 Claude 訂閱額度，不另外計費"},
    "openai": {"supports_json_mode": True, "max_context_tokens": 100000, "privacy": "cloud",
               "cost_hint": "按量計費"},
    "gemini": {"supports_json_mode": True, "max_context_tokens": 200000, "privacy": "cloud",
               "cost_hint": "按量計費（有免費額度）"},
    "anthropic": {"supports_json_mode": False, "max_context_tokens": 150000, "privacy": "cloud",
                  "cost_hint": "按量計費"},
    COMPAT: {"supports_json_mode": False, "max_context_tokens": 8000, "privacy": "local-or-custom",
             "cost_hint": "依服務商；本機模型免費"},
}


def capabilities_for(provider: str, model: str) -> dict:
    """{supports_json_mode, max_context_tokens, privacy, cost_hint}。不認得的 provider 回最保守的值。"""
    caps = dict(_CAPS.get(provider) or {"supports_json_mode": False, "max_context_tokens": 8000,
                                        "privacy": "cloud", "cost_hint": ""})
    if provider == "openai" and (model or "").lower().startswith("gpt-3.5"):
        caps["max_context_tokens"] = 12000
    return caps
