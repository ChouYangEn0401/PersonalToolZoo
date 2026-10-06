# ✦ Better Prompt — AI Text Transformer

> 貼上一段文字、選一個轉換模式，交給 AI（Claude 訂閱 / OpenAI / Gemini / Claude API）改寫成更好的版本——
> 整理、摘要、改寫風格，或把一段口語需求變成結構完整的 prompt。

```
┌─ 服務 / API Key / 模型 ──────────────────────────────────────────────────┐
│  ┌─ 轉換模式 ─────┐   ┌─ 📥 輸入文字 ────────────────────────────────┐  │
│  │ ✨ 文字精練    │   │    將要轉換的文字貼在這裡...                 │  │
│  │  • 基本整理 ◉  │   └──────────────────────────────────────────────┘  │
│  │  • 商務風格    │          [ ▶ 立即轉換 ]  [ 📋 複製 ]  [ ⬇ 移至輸入 ] │
│  │ 📋 精要摘要    │   ┌─ 📤 輸出結果 ────────────────────────────────┐  │
│  │ 🚀 Prompt 優化 │   │    AI 的回覆即時串流顯示在這裡...            │  │
│  │ 💡 發散思考 …  │   └──────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
.\scripts\setup-venv.ps1 better-prompt                                   # 建專屬環境 tools\better-prompt\.venv
.\tools\better-prompt\.venv\Scripts\python.exe tools\better-prompt\GUI__BetterPrompt.py
.\scripts\build.ps1 better-prompt -Smoke                                 # 打包成 exe
```

1. 頂端選 **服務**（預設是 **Claude 訂閱**，見下方）；選 OpenAI / Gemini / Claude API 時貼上 API Key，按「連接 API」
2. 左側選模式 → 貼上文字 → `Ctrl + Enter` 或「▶ 立即轉換」
3. 「⬇ 移至輸入」可以把結果搬回輸入框，連續加工多次
4. 「📚 批次筆記本」分頁可以一次排好多段文字、各自選模式，一鍵全部執行

沒連上 API 時按轉換，會顯示「將要送出的完整 prompt」，方便檢查或手動貼到別的地方用。

### Claude 訂閱（預設，不需要金鑰）

用電腦上官方的 **Claude Code** 登入的 Claude 帳號（訂閱方案）呼叫 Claude，不用 API 金鑰。第一次使用前：

1. 安裝 Claude Code：PowerShell 執行 `irm https://claude.ai/install.ps1 | iex`，或在 VS Code 安裝擴充「Anthropic.claude-code」
2. 開終端機執行一次 `claude`，用瀏覽器登入你的 Claude 帳號

開啟程式時會自動檢查 Claude Code 找不找得到（不花錢），顯示「● Claude Code 可用」。模型可選 `sonnet`（預設）/ `haiku` / `opus`。
注意：**每次轉換都會用掉訂閱額度**（haiku 短短一次約 0.002～0.009 美元）；這個服務沒有串流（整段一次出現）、不吃 temperature。
已經存過設定的人照原本選的服務；想換回 OpenAI 等，在頂端選單切換即可。

### API 金鑰（OpenAI / Gemini / Claude API）

連接成功後，手動輸入的金鑰會存進 **`%APPDATA%\PersonalToolZoo\keys.env`**——
這是所有工具共用的金鑰檔（Video Notes 也讀這個），設一次就好。也可以：

- 設環境變數 `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY`
- 在 exe（或 `GUI__BetterPrompt.py`）旁邊放一個 `.env`，格式見 `.env.example`

金鑰是以**純文字**存在你自己的使用者資料夾（舊版 README 說「加密儲存」並不正確）。
v1 存在 `~/.better_prompt_settings.json` 的金鑰仍然讀得到，第一次連接成功時會自動搬進共用金鑰檔。

### Temperature（創意度）

側欄底部的滑桿：0.0–0.5 穩定保守、0.6–1.1 平衡（預設 0.7）、1.2–2.0 發散。
部分模型不接受 temperature（OpenAI 的 o 系列、目前的 Claude 模型、Claude 訂閱），這時會自動忽略這個設定。

## 六大功能模式

| 分類 | 子模式 |
|---|---|
| ✨ 文字精練 | 基本整理、商務風格、學術風格、口語化 |
| 📋 精要摘要 | 重點摘要、一句話摘要、條列式重點、執行摘要 |
| 🚀 Prompt 優化 | ChatGPT Prompt（把口語需求變成完整 prompt）、程式碼說明、AI 繪圖 Prompt（輸出英文）、技術規格說明 |
| 💡 發散思考 | 腦力激盪、文章發想、繪圖 Prompt 發散、創意點子 |
| 🔍 研究討論 | 多角度分析、資料補充、反駁辯證、深度討論 |
| 📝 文件改寫 | 全面改寫、正式化、簡化、擴展豐富 |

每個模式的 prompt 都拆成兩部分送出：**指令放 system、你的文字用 `<text>` 標籤包起來放 user**。
模型因此分得清楚哪些是任務、哪些是素材——素材裡就算有「請忽略以上指示」之類的句子也只會被當成文字處理，
而且統一要求「只輸出結果、不加開場白、不捏造素材沒有的事實、中文用繁體」。

模式庫在 [`libs/toolzoo/ai/text_modes.py`](../../libs/toolzoo/ai/text_modes.py)，Video Notes 的「二次加工」也用同一份，改一次兩邊都生效。

### 推薦模型

模式橫幅上的「推薦模型」可以按 ✎ 編輯，用比較符號連接：
`>>` 明顯優於、`>` 優於、`>=` 不亞於、`=` 相當，例如 `gpt-5.1 >> gpt-5.2 = gpt-5.4`。點徽章就會切換到那個模型。
預設值在 `model_recommendations.json`；你的編輯存在 `%APPDATA%\PersonalToolZoo\better-prompt\`（打包後也不會遺失）。

## 模型相容性

各家模型吃的參數不一樣（`max_tokens` 或 `max_completion_tokens`、收不收 temperature、能不能串流）。
呼叫層有一張「第一次猜」的規則表，猜錯時 API 會回 400 指出是哪個參數，程式會自動修正重送並記住，
所以新模型通常不用改程式就能用。細節見 [`libs/README.md`](../../libs/README.md)。

## 專案結構

```
tools/better-prompt/
├── GUI__BetterPrompt.py        # 主程式（CustomTkinter 介面）
├── version.py                  # 版本號（exe 檔名會帶上）
├── model_recommendations.json  # 推薦模型的預設值
├── .env.example                # 金鑰範本
├── requirements.txt            # customtkinter、claude-subscription、openai（含 Gemini）、anthropic
└── tool.json                   # build 設定（pathex 指向 repo 的 libs/）

libs/toolzoo/ai/                # 共用：LLM 呼叫層、金鑰、模式庫（Video Notes 也用）
```

設定（服務、各服務選的模型、temperature）存在 `%APPDATA%\PersonalToolZoo\better-prompt\settings.json`。

## 隱私

- 文字只在你按「轉換」時送給你選的服務商，本程式不記錄、不保存輸入與輸出。
- 金鑰只存在本機（見上方「API 金鑰」）。

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `GUI__BetterPrompt.py` |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `GUI__BetterPrompt(vX.Y.Z).exe`、視窗標題 `Better Prompt ✦ AI Text Transformer vX.Y.Z` |
| 環境 | 有第三方套件 → `tools\better-prompt\.venv` |
| 依賴 | `customtkinter<6`、`claude-subscription`（Claude 訂閱，釘在 GitHub tag `v0.2.1`，安裝要有 git）、`openai<3`（OpenAI 與 Gemini）、`anthropic<2`（Claude API；1.11 起 `fallbacks` 是正式參數） |
| 預設服務 | Claude 訂閱（`claude-sub`，模型 `sonnet`）——要先安裝並登入 Claude Code，**會用掉訂閱額度**；存過設定的人照原本的選擇 |
| 共用程式 | `libs/toolzoo/ai`（LLM 呼叫層、金鑰、模式庫）——tool.json 的 `pathex` 指向 `../../libs`，進入點開頭也把它加進 `sys.path` |
| 打包額外內容 | `include`: `model_recommendations.json`；`collect_all`: `customtkinter`（主題 JSON 與字型） |
| 測試 | 程式本身無；共用層 `python -m unittest discover -s libs\tests` |
| Release tag | `BetterPrompt_vX.Y.Z`（tool.json 的 tag_prefix） |

### 注意事項

- 模式的名稱是 `model_recommendations.json` 的 key，改 `libs/toolzoo/ai/text_modes.py` 的分類或子模式名稱時要一起改。
- 改 `libs/toolzoo/ai` 也會影響 Video Notes，兩個工具都要重新 build 測過。
- v1 的設定檔 `~/.better_prompt_settings.json` 只會被讀、不會被刪；金鑰搬進 keys.env 之後，那個檔可以手動刪掉。
  v1 只會帶過來 OpenAI 的模型與 temperature，不會帶服務——v1 只有 OpenAI，所以升上來的人預設也是 Claude 訂閱。
- Claude 訂閱的「檢查 Claude Code」只找執行檔（`claude_subscription.find_claude_binary`），不會真的呼叫、不花額度；
  沒登入或登入過期要到第一次轉換才會知道，錯誤訊息會叫使用者執行 `claude` 重新登入（訊息在 `libs/toolzoo/ai/errors.py`）。
- `claude-subscription` 不要降到 v0.2.1 以下：舊版在打包後的視窗程式裡每呼叫一次就閃一個黑窗。
- Claude 訂閱一次回整段，沒有串流；轉換時輸出框要等整段回來才會出現文字。
