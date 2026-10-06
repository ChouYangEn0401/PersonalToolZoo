"""LLM 呼叫層：Claude 訂閱（Claude Code）/ OpenAI / Gemini / Claude API 用同一個介面。

    from toolzoo.ai import LLM, PROVIDERS, DEFAULT_PROVIDER, DEFAULT_MODELS, MissingKeyError, LLMError
    from toolzoo.ai import text_modes          # Better Prompt 的轉換模式庫
    from toolzoo.ai.prompts import wrap         # 把素材包進 <text> 標籤

claude_subscription / openai / anthropic 套件都只在真的用到該服務時才 import，
所以工具的 requirements.txt 只需要列它會用到的那幾家。
"""

from toolzoo.ai.client import (DEFAULT_MODELS, DEFAULT_PROVIDER, LLM, PROVIDERS, MissingKeyError, needs_key,
                               provider_for_model)
from toolzoo.ai.errors import LLMError
from toolzoo.ai.keys import find_key, keys_file, save_key

__all__ = [
    "DEFAULT_MODELS",
    "DEFAULT_PROVIDER",
    "LLM",
    "LLMError",
    "MissingKeyError",
    "PROVIDERS",
    "find_key",
    "keys_file",
    "needs_key",
    "provider_for_model",
    "save_key",
]
