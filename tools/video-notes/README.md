# 🎬 Video Notes

> 貼上影片網址 → 下載 → 語音辨識成逐字稿 → AI 依影片類型整理成可以直接貼進 Notion 的筆記。
> 有 GUI（本機網頁）也有 CLI，處理完還能用 HTTP 把結果丟給別的程式。

前身是 `VideoToSimpleNotion`，依作者自己寫的重建規格 [`docs/update_plan.txt`](docs/update_plan.txt) 整個重寫（對照表在最後）。

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
.\scripts\setup-venv.ps1 video-notes          # 建專屬環境（含 GPU 用的 cuBLAS / cuDNN，約 2 GB）
$py = ".\tools\video-notes\.venv\Scripts\python.exe"

& $py tools\video-notes\VideoNotes.py                         # GUI：自動開瀏覽器 http://127.0.0.1:8766
& $py tools\video-notes\VideoNotes.py <網址> [選項]            # CLI
.\scripts\build.ps1 video-notes                               # 打包成 exe（雙擊開 GUI，帶參數就是 CLI）
```

需要：**ffmpeg**（PATH 上，或裝在 `C:\ffmpeg\bin`）、**Node / Bun / Deno 其中一個**（yt-dlp 抓 YouTube 要用），
以及 AI：預設用 **Claude 訂閱**（電腦上裝好並登入 Claude Code，不需要金鑰），也可以改用 OpenAI / Gemini / Claude API 的金鑰
（見下方「AI 服務」；只要逐字稿可以不用）。

### GUI

- 左邊貼網址（一行一個，可以一次很多支）、選整理方式與加料、填「特別想知道」，按「開始處理」。
- 處理過的影片會先跳出視窗告訴你「已有：影音 ✓ 逐字稿 ✓ 筆記 news」，勾選要重做哪些，其他沿用。
- 每支影片顯示 資訊 → 下載 → 音訊 → 轉錄 → 筆記 五個階段（綠色＝完成、紫色＝沿用既有檔案）；
  AI 寫筆記時右邊即時顯示（Claude 訂閱沒有串流，寫完才一次出現）。
- 右邊看筆記：「複製 Markdown」直接貼進 Notion；也可以切到 Markdown 原文或逐字稿。
- **✨ 二次加工**：用 Better Prompt 的轉換模式（執行摘要、條列式重點、正式化…）再處理一次筆記。
- 「筆記庫」分頁列出輸出資料夾裡所有處理過的影片。
- ⚙ 設定：輸出位置、AI 服務與模型、API 金鑰、語音辨識模型與語言、同時處理幾支、socket 通知網址。

### CLI

```powershell
VideoNotes https://youtu.be/xxxx                                   # 自動判斷類型
VideoNotes https://youtu.be/xxxx -p finance -w actions,timeline --focus "AI 伺服器"
VideoNotes --file urls.txt --preset daily-news --reuse --post      # 批次＋送給別的程式
VideoNotes https://youtu.be/xxxx --no-notes                         # 只要逐字稿
VideoNotes --list                                                   # 有哪些整理方式 / 加料 / 組合
VideoNotes --dry-run -p news -w brief                               # 印出會送給 AI 的 prompt（不呼叫）
```

| 選項 | 說明 |
|---|---|
| `-o downloads` / `-o data` / `-o <資料夾>` | 輸出位置（預設「下載\Video Notes」，其次工具的 `data\`，或自選） |
| `-p` / `-w` / `--preset` / `--focus` | 整理方式、加料、常用組合、特別想知道的主題 |
| `--reuse` / `--redo download,transcribe,notes`（或 `all`） | 處理過的影片：一律沿用 / 指定重做。都沒給而且是互動視窗時會逐項詢問 |
| `--provider` / `--model` | 這次用哪個 AI（不改存檔設定）。服務：`claude-sub`（預設）/ `openai` / `gemini` / `anthropic`；只給 `--model`（例如 `haiku`）會從名稱判斷服務 |
| `--whisper-model` / `--device` / `--language` | 語音辨識模型、GPU/CPU、語言（`auto` 會先判斷） |
| `--video` | 連影片一起保留（預設只下載音訊，快很多） |
| `--post [網址]` | socket 模式（見下方） |
| `--json` | 結束時把結果以 JSON 印出（給腳本串接） |
| `-j N` | 同時處理幾支 |

## 整理方案：可插拔、可混用

筆記好不好，關鍵在「這類影片什麼重要、什麼該略過」。方案由三種積木組成，全是 `prompts/` 底下的 TOML，不用改程式：

| 整理方式（profile） | 重點 |
|---|---|
| 🤖 `auto` | 先用一個小呼叫判斷影片類型，再套對應方案（結果記在 info.json，下次不再判斷） |
| 📚 `knowledge` 知識學習 | 簡潔但保留脈絡與「為什麼」，整理成可以複習的筆記 |
| 📰 `news` 新聞快訊 | 30 秒看完：發生什麼事、條列事實、各方說法、後續 |
| 🎙 `podcast` Podcast／訪談 | 依話題重新歸類；搭配「特別想知道」只展開你關心的，其他一行帶過 |
| ⚡ `quick` 娛樂快看 | 電影解說、遊戲快訊、開箱：最短時間知道在講什麼 |
| 📈 `finance` 財經產業 | 只留有依據的觀點與數據，過濾串場、互捧、玩笑、喊單；附風險與免責 |
| 📝 `general` 通用 | 其他都不適合時 |

**加料（modifier，可多選）**：⏱ 時間軸、✅ 行動清單、💬 金句、📖 名詞解釋、✂ 極簡、🔍 詳細、🌐 英文輸出。
**常用組合（preset）**：`daily-news`（新聞＋極簡）、`stock-show`（財經＋行動清單＋時間軸）、`study`（知識＋名詞解釋＋時間軸）。

**自訂**：把 TOML 放到 `%APPDATA%\PersonalToolZoo\video-notes\prompts\profiles|modifiers|presets\`，
同名的會覆蓋內建的（更新程式也不會被蓋掉），GUI 重新整理就生效。格式照 `prompts/` 裡的範例，例如：

```toml
# %APPDATA%\PersonalToolZoo\video-notes\prompts\presets\my-ai.toml
name = "AI 產業追蹤"
profile = "finance"
modifiers = ["timeline"]
focus = "AI 伺服器、輝達、台積電先進封裝"
```

### 為什麼比舊版好

舊版只有一句「請幫我重點整理」加整份逐字稿。現在：

- **給模型影片資訊**（標題、頻道、說明欄、章節）＋明確要求依上下文校正語音辨識的錯字與專有名詞。
- **依類型決定保留 / 略過什麼**，而不是所有影片同一套。
- **指令與素材分開**：指令在 system，逐字稿包在 `<transcript>` 標籤裡，逐字稿裡的句子不會被當成指令。
- **長影片分段整理再合併**（超過設定的字數門檻時），中段不會被漏掉。
- **固定的筆記標頭**（標題、網址、頻道、長度、日期、方案）由程式產生，不讓模型抄錯。
- 中文逐字稿先轉繁體（OpenCC，台灣用語），Whisper 也帶「繁體中文、有標點」的提示。

## 輸出檔案

每支影片一個資料夾，名稱結尾是只看網址就算得出來的 `[<kind>-<id>]`：

```
下載\Video Notes\
  台積電漲太多？鴻海卻漲不動 [video-knWPw9_a5qY]\
    media.m4a              下載的影音（保留影片時是 media.mp4）
    audio.wav              16 kHz 單聲道，給 Whisper
    transcript.txt / .srt / .json   逐字稿、字幕、含時間碼的資料
    notes.finance+timeline.md       筆記；不同方案各一份，互不覆蓋
    info.json              影片資訊、自動判斷結果、每次處理的紀錄
```

- 換網址寫法（`youtu.be/…`、`watch?v=…&t=42s`）還是同一支，會找到同一個資料夾。
- **沿用規則**：檔案在就沿用；要求重做或上游重做過（例如重新下載）才重做。產生的檔案一律保留，
  只有你明確要求「重新下載」時才換掉舊的影音檔。

## 同時處理多支

下載最多 3 支同時；語音辨識一次 1 支（同一張 GPU 跑兩支只會互搶）；AI 一次 1 個請求（避免被限流）。
GUI 與 CLI 批次都一樣。「同時處理幾支」在設定裡改。

## socket 模式（把結果送給別的程式）

處理完每支影片，把結果用 HTTP POST（JSON）送出——例如另一個程式收到後自動寫進 Notion、丟到 Telegram。
設定在 `socket/config.json`（打包後放在 exe 旁邊的 `socket\config.json`）：`enabled: true` 時 CLI 每次都送，
否則加 `--post`（或 `--post <網址>` 臨時指定）。GUI 在設定裡填「處理完通知網址」。

```json
{
  "event": "video-notes.completed", "sent_at": "2026-10-05T19:30:00",
  "url": "https://youtu.be/…", "platform": "youtube", "id": "…", "kind": "video", "title": "…",
  "folder": "C:\\…", "language": "zh", "profile": "finance", "profile_reason": "…",
  "notes": "# 標題\n\n> 🔗 …\n\n---\n\n## 一句話結論…",
  "files": {"notes": "…", "transcript": "…", "srt": "…", "audio": "…", "media": "…", "info": "…"}
}
```

`include_transcript: true` 會再附上整份逐字稿。送不出去不會讓處理失敗（筆記已經在硬碟上了）。
測試接收端：`python debug\notify_receiver.py`（在 127.0.0.1:8787 印出收到的內容）。

## AI 服務

預設用 **Claude 訂閱**：透過電腦上官方的 Claude Code 登入的 Claude 帳號呼叫，不需要 API 金鑰。第一次使用前：

1. 安裝 Claude Code：PowerShell 執行 `irm https://claude.ai/install.ps1 | iex`，或在 VS Code 安裝擴充「Anthropic.claude-code」
2. 開終端機執行一次 `claude`，用瀏覽器登入你的 Claude 帳號

模型 `sonnet`（預設）/ `haiku` / `opus`。**每支影片的筆記都會用掉訂閱額度**：整理方式選 `auto` 時會先多一次判斷類型的小呼叫，
逐字稿太長時會分段整理再合併，次數更多。GUI 頂端的「AI」標籤會顯示找不找得到 Claude Code（只找執行檔，不花錢）；
沒登入或登入過期要到真的寫筆記時才會知道，錯誤訊息會說要執行 `claude` 重新登入。
已經存過設定的人照原本選的服務；在 ⚙ 設定或 CLI 的 `--provider` 切換。

### API 金鑰（OpenAI / Gemini / Claude API）

和 Better Prompt 共用：環境變數 `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` →
`%APPDATA%\PersonalToolZoo\keys.env` → 工具資料夾（或 exe 旁）的 `.env`。
舊專案的 `.env`（`chatgpt=…`、`gemini=…`）整個複製到 `tools\video-notes\.env` 就能用。GUI 設定頁也可以直接貼金鑰。

錯誤會翻成看得懂的訊息。**舊版「LLM 無法總結」的真正原因**：2026-10-05 測試時，舊 `.env` 與
Better Prompt 的 OpenAI 金鑰都回 `429 insufficient_quota`（帳戶額度用完），`.env` 裡的 Gemini 金鑰則已失效——
程式本身沒有壞，儲值或換一把新的金鑰就好。

## GPU

`requirements.txt` 裝了 NVIDIA 的 cuBLAS / cuDNN wheel，從原始碼執行時自動用 GPU（RTX 4060 實測 medium 模型 OK）；
DLL 不齊時自動改用 CPU（int8，比較慢）。設定頁標題列會顯示目前用的是 GPU 還是 CPU。

打包的 exe 不含這些 DLL（約 2 GB），會依序找：環境變數 `VIDEO_NOTES_CUDA_DIR` → repo 裡這個工具的 `.venv`
（exe 在 `<repo>\dist\video-notes\` 時）→ 系統 PATH；都沒有就用 CPU。

## 除錯

`debug/` 是給開發時用的，跟正式程式分開：

| 檔案 | 用途 |
|---|---|
| `check_env.py` | 印出 ffmpeg、GPU、JS 執行環境、AI 能不能用（Claude Code、金鑰）、設定檔位置——出問題先跑這支 |
| `run_stage.py` | 單獨跑一個階段：`info` / `download` / `audio` / `transcribe` / `prompt`（只印 prompt）/ `notes` |
| `notify_receiver.py` | socket 模式的測試接收端 |

## 對照 update_plan.txt

| # | 規格 | 做法 |
|---|---|---|
| 1 | 整理成乾淨的 library 架構 | `video_notes/` 套件，每個模組一個職責（見 `video_notes/__init__.py`）；CLI 與 GUI 共用同一套底層 |
| 2 | 測試程式另外放 | `tests/`（單元測試，離線、不打 API）與 `debug/`（手動除錯工具） |
| 3 | 不再用 terminal input，提供 CLI 與漂亮的 GUI | `cli.py`（argparse）、`web/`（本機網頁 GUI）；同一支程式不帶參數開 GUI |
| 4 | 判斷 short / video；可選資料夾：下載 > data > 自選 | `naming.classify`（YouTube Shorts、TikTok、Reels…）；設定與 `-o` 三種輸出位置，預設「下載」 |
| 5 | CLI 的 socket 模式，設定放 socket 資料夾 | `--post` ＋ `socket/config.json`，`notify.py` 用 HTTP POST 送 JSON |
| 6 | 依影片類型的預設 prompt、可插拔可混用、預先做好的組合 | `prompts/` 的 profile / modifier / preset（TOML），CLI `--preset`、GUI 下拉選單 |
| 7 | 可注入、可串接其他工具 | `Pipeline(llm_factory=…)`、`--json`、socket 模式 |
| 8 | 通用的預設值 | `config.Settings` 的預設（下載資料夾、medium、auto 判斷類型與語言…） |
| 9 | 檔名可預測，重複時詢問是否重做 | 每支影片的資料夾由網址決定；GUI 跳出勾選視窗、CLI 逐項詢問或 `--reuse` / `--redo` |
| 10 | 多執行緒，只有 LLM 排隊 | `jobs.py` 執行緒池＋`pipeline.Locks`（下載 3、轉錄 1、LLM 1） |
| 11 | 產生的檔案不要亂刪 | 一律保留；只有要求「重新下載」時換掉舊的影音檔 |

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `VideoNotes.py`（無參數 → `video_notes/web/server.py` 的 GUI；有參數 → `video_notes/cli.py`） |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `VideoNotes(vX.Y.Z).exe`、GUI 標題與 CLI |
| 環境 | 有第三方套件 → `tools\video-notes\.venv` |
| 依賴 | `yt-dlp[default]<2028`（網站常改版，上限刻意給到年底後一年）、`faster-whisper<2`、`nvidia-cublas-cu12<13`、`nvidia-cudnn-cu12<10`、`opencc-python-reimplemented<0.2`、`claude-subscription`（Claude 訂閱，釘在 GitHub tag `v0.2.1`，安裝要有 git）、`openai<3`、`anthropic<2`、`fastapi<1`、`uvicorn<1` |
| 預設 AI | Claude 訂閱（`claude-sub`，模型 `sonnet`）——要先安裝並登入 Claude Code，**會用掉訂閱額度**；存過設定的人照原本的選擇 |
| 共用程式 | `libs/toolzoo`：`ai`（LLM、金鑰、Better Prompt 模式庫）、`ytdlp`（JS 執行環境、ffmpeg 位置）、`webapp`（啟動器）、`appdirs` |
| 打包額外內容 | `include`: `prompts`、`socket`、`video_notes/web/static`；`collect_all`: `yt_dlp_ejs`、`faster_whisper`（VAD 模型）、`opencc`（字典）；uvicorn 的 hiddenimports |
| 測試 | `.\tools\video-notes\.venv\Scripts\python.exe -m unittest discover -s tools\video-notes\tests -v`（離線） |
| Release tag | `VideoNotes_vX.Y.Z` |

### 注意事項

- 外部程式：ffmpeg、Node / Bun / Deno 其中一個（YouTube）。`debug/check_env.py` 會檢查。
- YouTube 改版導致抓不到時，先在 `requirements.txt` 範圍內升級 yt-dlp：`setup-venv.ps1 video-notes -Force`。
- Whisper 模型第一次用會從 Hugging Face 下載到 `~\.cache\huggingface`（medium 約 1.5 GB）。
- 改 `libs/toolzoo/ai` 會同時影響 Better Prompt，兩個工具都要重新測。
- Claude 訂閱每次呼叫最多等 900 秒（`libs/toolzoo/ai/claude_code.py` 的 `DEFAULT_TIMEOUT`；套件預設 180 秒，長逐字稿不夠）。
  `claude-subscription` 不要降到 v0.2.1 以下：舊版在打包後的 exe 裡每呼叫一次就閃一個黑窗。
- 「AI 能不能用」（`service.environment()` 的 `keys`）對 Claude 訂閱只代表找得到 Claude Code，驗不出登入是否過期。
- GUI 的 API 只聽 127.0.0.1，寫入請求要帶 `X-Video-Notes: 1`（擋其他網站跨站呼叫），檔案存取限輸出資料夾內。
