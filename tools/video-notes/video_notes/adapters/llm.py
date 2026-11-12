"""分析用的 AI adapter。

主要的服務（Claude 訂閱、OpenAI、Gemini、Claude API）走共用的 libs/toolzoo/ai 的 LLM，這裡不重寫。
這個檔只補兩件事：
- build_llm(settings)：依設定建立 LLM；provider == "openai-compat" 時用自訂的 base_url（Ollama、LM Studio、其他服務商）
- capabilities_for(provider, model)：{supports_json_mode, max_context_tokens, privacy, cost_hint}，給分析切段與 UI 用

任何 LLM 物件只要有：provider、model 屬性，以及
    stream(system, user, *, temperature=None, final=None) -> Iterator[str]
就能用（測試用 FakeLLM 也是這樣）。失敗丟 toolzoo.ai.LLMError 或 ToolError；analyze.py 負責轉成 ToolError。
"""

from __future__ import annotations

COMPAT = "openai-compat"


def build_llm(settings):
    """第 1 波 STT／AI adapter agent 實作（openai-compat）；其他 provider 直接用 toolzoo.ai.LLM。"""
    from toolzoo.ai import LLM

    if settings.provider == COMPAT:
        raise NotImplementedError("第 1 波實作 openai-compat")
    return LLM(settings.provider, settings.model or None)


def capabilities_for(provider: str, model: str) -> dict:
    """保守的預設；第 1 波 agent 補上各家的值。"""
    local = provider == COMPAT
    return {"supports_json_mode": False, "max_context_tokens": 8000 if local else 100000,
            "privacy": "local-or-custom" if local else "cloud", "cost_hint": ""}
