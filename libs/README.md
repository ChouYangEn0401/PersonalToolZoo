# libs/ — 工具之間共用的程式碼

`tools/` 底下每個工具還是自成一個單位（自己的 `tool.json`、`requirements.txt`、venv）。
只有「兩個以上的工具都需要、而且應該一起改」的東西才放進這裡。

| 套件 | 內容 | 誰在用 |
|---|---|---|
| `toolzoo.appdirs` | 資料放工具旁邊的 `data\`、金鑰與參數放專案的 `.env`、「下載」資料夾位置 | 需要存設定的工具 |
| `toolzoo.ai` | LLM 呼叫層：OpenAI / Gemini / Claude 同一個介面、API 金鑰管理、提示詞工具、Better Prompt 的轉換模式庫 | better-prompt、video-notes |
| `toolzoo.webapp` | 本機 web app 啟動器（找空的 port、開瀏覽器、跑 uvicorn） | video-downloader、video-notes |

## 讓工具用到 libs

1. `tool.json` 加上 `pathex`，打包時 PyInstaller 才找得到：

   ```json
   { "pathex": ["../../libs"] }
   ```

2. 進入點最上面加這段，從原始碼執行時 import 才找得到（打包後由第 1 步處理）：

   ```python
   _LIBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "libs")
   if not getattr(sys, "frozen", False) and os.path.isdir(_LIBS):
       sys.path.insert(0, os.path.abspath(_LIBS))
   ```

3. 用到的第三方套件寫進**工具自己的** `requirements.txt`（libs 本身沒有 venv）：

   | 用到 | 需要 |
   |---|---|
   | `toolzoo.ai` 的 Claude 訂閱 | `claude-subscription @ git+https://github.com/ChouYangEn0401/ClaudeLogin.git@v0.2.1`（**至少 v0.2.1**：v0.2.0 在視窗程式裡每次呼叫都會閃一個黑窗） |
   | `toolzoo.ai` 的 OpenAI / Gemini | `openai>=2.0,<3` |
   | `toolzoo.ai` 的 Claude API | `anthropic>=1.11,<2` |
   | `toolzoo.webapp` | `fastapi`、`uvicorn` |

## toolzoo.ai

```python
from toolzoo.ai import LLM

llm = LLM("claude-sub", "sonnet")           # Claude 訂閱：不需要金鑰（預設服務）
llm = LLM("openai", "gpt-5.1")              # provider 不給會從模型名稱猜
for piece in llm.stream(system, user):      # 串流
    ...
text = llm.complete(system, user)           # 一次拿完整結果
```

| 服務（provider） | 認證 | 模型 | 備註 |
|---|---|---|---|
| `claude-sub` Claude 訂閱（預設） | 電腦上官方的 **Claude Code** 登入的帳號（不需要金鑰） | `sonnet`（預設）/ `haiku` / `opus` | 透過使用者自己寫的 claude-subscription（ClaudeLogin）呼叫 `claude -p`。沒有串流（一次回整段）、不支援 temperature。**會用掉訂閱額度**（haiku 一次短呼叫約 0.002～0.009 美元）。要先安裝 Claude Code 並執行一次 `claude` 登入 |
| `openai` | `OPENAI_API_KEY` | `gpt-5.1` 等 | |
| `gemini` | `GEMINI_API_KEY` | `gemini-2.5-flash` 等 | 走 Gemini 的 OpenAI 相容端點 |
| `anthropic` Claude API | `ANTHROPIC_API_KEY` | `claude-opus-5-5` 等 | 按量計費，跟訂閱分開 |

### API 金鑰放哪裡

讀取順序，先找到先用：

1. 環境變數 `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY`
2. **專案的 `.env`** —— 從原始碼執行讀 repo 根目錄的 `.env`；打包的 exe 先讀 exe 旁邊的 `.env`，
   exe 在 repo 的 `dist\` 裡時也讀 repo 的那份。所有工具共用，設一次就好（Better Prompt 的設定畫面就是寫到這裡）
3. 工具自己指定的額外檔案（`find_key(provider, extra_files)`）

舊專案 `.env` 的寫法（`chatgpt=...`、`gemini=...`）也認得，整個檔案複製過來就能用。
`.env` 是純文字，已被 `.gitignore` 擋掉；每一項的說明在 repo 根目錄的 `.env.example`。

## toolzoo.appdirs：資料與參數放哪裡

工具**不寫使用者資料夾**（`%APPDATA%`、家目錄、`~/.cache`）：

```python
from toolzoo.appdirs import load_env, tool_data_dir

load_env()                                   # 專案 .env 的參數載入環境變數（已設定的不覆蓋，佔位值 ... 不載入）
settings = tool_data_dir("my-tool") / "settings.json"
# 原始碼執行 → tools/my-tool/data/settings.json；打包的 exe → exe 旁邊的 data/settings.json
```

| 函式 | 用途 |
|---|---|
| `tool_data_dir(tool)` | 工具的資料夾（設定、紀錄、快取、模型），會自動建立 |
| `env_files()` / `env_file()` | 要讀的 `.env`（前面的優先）／要寫入的 `.env` |
| `load_env()` | 把 `.env` 的參數載入環境變數，回傳載入了哪些 |
| `repo_root()` | repo 根目錄（打包的 exe 不在 repo 裡時是 `None`） |
| `downloads_dir()` | 使用者的「下載」資料夾（影片類輸出用） |

測試時設 `TOOLZOO_DATA_DIR` 可以把資料與 `.env` 整個搬到暫存資料夾。

### 為什麼不需要為每個新模型改程式

各家模型吃的參數不同（`max_tokens` 還是 `max_completion_tokens`、收不收 `temperature`、能不能串流），
`openai_compat.py` 有一張「第一次猜」的表；猜錯時 API 會回 400 指出是哪個參數，程式會自動調整重送，
並記住這個模型的規則。Claude 的規則（目前的模型不收 `temperature`、拒答時伺服器端 fallback）在 `anthropic_claude.py`。

## 測試

不會打 API、也不會呼叫 Claude Code（用假的 claude_subscription 模組），隨便哪個裝了 `openai` 的 Python 都能跑：

```powershell
python -m unittest discover -s libs\tests -v
```
