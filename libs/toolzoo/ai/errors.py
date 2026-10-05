"""把各家 SDK 的錯誤翻成使用者看得懂、知道下一步該做什麼的訊息。

原始錯誤長這樣：
    Error code: 429 - {'error': {'message': 'You have no credits remaining...', 'code': 'credit_balance_exhausted'}}
使用者看到會以為「程式壞了」（VideoToSimpleNotion 當初「LLM 無法總結」其實就是額度用完）。
只看 status_code / body / 訊息文字，不 import 各家的例外類別，所以沒裝某家 SDK 也能用。
"""

from __future__ import annotations

BILLING = {
    "openai": "https://platform.openai.com/settings/organization/billing/",
    "gemini": "https://aistudio.google.com/apikey",
    "anthropic": "https://console.anthropic.com/settings/billing",
}
KEY_PAGES = {
    "openai": "https://platform.openai.com/api-keys",
    "gemini": "https://aistudio.google.com/apikey",
    "anthropic": "https://console.anthropic.com/settings/keys",
}


class LLMError(RuntimeError):
    """訊息已經是給人看的中文；原始例外在 __cause__。"""


def _code(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            return str(err.get("code") or err.get("type") or err.get("status") or "")
    return ""


def explain(exc: Exception, provider: str, model: str) -> str:
    name = {"openai": "OpenAI", "gemini": "Gemini", "anthropic": "Claude"}.get(provider, provider)
    status = getattr(exc, "status_code", None)
    code = _code(exc)
    text = str(exc)
    lower = text.lower()

    if code in ("insufficient_quota", "credit_balance_exhausted") or "credit balance" in lower or "no credits" in lower:
        return (f"{name} 帳戶的額度用完了（{code or status}）。請到 {BILLING.get(provider, '')} 儲值，"
                f"或在設定裡改用其他 AI 服務。")
    if status == 401 or "invalid api key" in lower or "incorrect api key" in lower \
            or "valid api key" in lower or "api key not valid" in lower:
        return (f"{name} 的 API 金鑰無效或已被撤銷。請到 {KEY_PAGES.get(provider, '')} 重新產生一把，"
                f"存進 keys.env（或在工具的設定畫面貼上）。")
    if status == 403:
        return f"{name} 拒絕這個請求（權限不足）：這把金鑰可能沒有使用 {model} 的權限。"
    if status == 404:
        return f"{name} 找不到模型「{model}」：可能打錯名稱，或這個帳號沒有權限，換一個模型試試。"
    if status == 429:
        return f"{name} 回應「請求太頻繁」被限流了，等一下再試（程式已經自動重試過）。"
    if status is not None and status >= 500:
        return f"{name} 伺服器暫時出錯（HTTP {status}），稍後再試。"
    if type(exc).__name__ in ("APIConnectionError", "APITimeoutError", "ConnectError", "ConnectTimeout"):
        return f"連不上 {name}（網路問題或逾時）：{text}"
    return f"{name}（{model}）呼叫失敗：{text}"
