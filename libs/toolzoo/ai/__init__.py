"""LLM 呼叫層：OpenAI / Gemini / Claude 用同一個介面。

    from toolzoo.ai import LLM, PROVIDERS, DEFAULT_MODELS, MissingKeyError
    from toolzoo.ai import text_modes          # Better Prompt 的轉換模式庫
    from toolzoo.ai.prompts import wrap         # 把素材包進 <text> 標籤

openai / anthropic 套件只在真的用到該 provider 時才 import，
所以只用其中一家的工具，requirements.txt 只需要列那一家的 SDK。
"""

from toolzoo.ai.client import DEFAULT_MODELS, LLM, PROVIDERS, MissingKeyError, provider_for_model
from toolzoo.ai.keys import find_key, keys_file, save_key

__all__ = [
    "DEFAULT_MODELS",
    "LLM",
    "MissingKeyError",
    "PROVIDERS",
    "find_key",
    "keys_file",
    "provider_for_model",
    "save_key",
]
