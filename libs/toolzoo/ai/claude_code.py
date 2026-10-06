"""Claude 訂閱：透過電腦上官方的 Claude Code（`claude -p`），用使用者自己的 Claude 訂閱呼叫 Claude。

不需要 API 金鑰。背後是使用者自己寫的 claude-subscription 套件（ClaudeLogin，v0.2.1 以上：
v0.2.0 在沒有主控台的視窗程式裡，每呼叫一次會閃一個 claude 黑窗）。

跟其他服務不一樣的地方：
- 沒有串流，一次回整段文字（LLM.stream() 對這個服務只 yield 一次）。
- 不支援 temperature / max_tokens，直接忽略。
- 提示走 stdin，沒有命令列長度限制，長逐字稿也可以；system prompt 走命令列參數（幾千字沒問題）。
- 工具全關（純文字進出），最便宜；不要開 tools / permission_mode。
- **會消耗使用者的訂閱額度**（haiku 一次短呼叫約 0.002～0.009 美元）。
"""

from __future__ import annotations

KEY = "claude-sub"
MODELS = ["sonnet", "haiku", "opus"]      # Claude Code 的模型別名；沒有列出模型的 API，固定清單
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT = 900                     # 套件預設 180 秒，長影片的逐字稿不夠


def find_binary() -> str:
    """找 claude 執行檔（不花錢）；找不到丟 ClaudeNotFoundError（訊息裡有安裝方式）。"""
    from claude_subscription import find_claude_binary

    return find_claude_binary()


def available() -> tuple[bool, str]:
    """(能不能用, 說明)。給 GUI 顯示狀態用，任何錯誤都轉成說明文字，不丟例外。"""
    try:
        return True, find_binary()
    except ImportError:
        return False, "沒有安裝 claude-subscription 套件"
    except Exception as exc:  # noqa: BLE001 — ClaudeNotFoundError 等
        return False, str(exc).splitlines()[0]


def complete(model: str, system: str, user: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    from claude_subscription import ask

    kwargs = {"system": system} if system else {}   # 不給 system 時用套件的精簡預設（system=None 會比較貴）
    return ask(user, model=model or DEFAULT_MODEL, timeout=timeout, **kwargs).text
