# 🎬 Video Notes

> 貼上影片網址 → 下載 → 語音辨識成逐字稿 → AI 依影片類型**分析一次**，存成結構化的 `analysis.json` →
> 從它產生 Notion 筆記、樹狀圖（XMind／Mermaid／OPML…）、網頁範本，或把好幾支影片**合併成一份**。
> 有 GUI（本機網頁）也有 CLI（可給程式呼叫的 `--json`），處理完還能用 HTTP 把結果丟給別的程式。

```
來源（yt-dlp…） → 語音辨識（本機 Whisper／OpenAI／Gemini） → 分析（AI → analysis.json） → 輸出（筆記／樹狀圖／網頁…）
                                                                         └→ 多片合併（好幾份 analysis → 一份）
```
四層都是可換的 adapter（`video_notes/adapters/`）：本機一定能跑，要更好的時候換服務商只改設定。

前身是 `VideoToSimpleNotion`，依作者自己寫的重建規格 [`docs/update_plan.txt`](docs/update_plan.txt) 整個重寫（對照表在最後）。

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
.\tools\video-notes\run.bat                               # GUI：自動開瀏覽器 http://127.0.0.1:8766
.\tools\video-notes\run.bat <網址> [選項]                     # CLI（後面的參數原封不動交給程式）
# 第一次會自動建 tools\video-notes\.venv（含 GPU 用的 cuBLAS / cuDNN，約 2 GB）
.\scripts\build.ps1 video-notes                               # 打包成 exe（雙擊開 GUI，帶參數就是 CLI）
```

需要：**ffmpeg**（PATH 上，或裝在 `C:\ffmpeg\bin`）、**Node（≥ 22）或 Deno（≥ 2.3）**（yt-dlp 抓 YouTube 要用），
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

# v2
VideoNotes <網址1> <網址2> <網址3> --preset news-roundup --combine --title "今天的新聞"   # 處理完合併成一份
VideoNotes --combine --folders "<資料夾A>,<資料夾B>" --preset course --yes           # 合併已經處理過的影片
VideoNotes <網址> --outputs tree-md,html-tabs                        # 額外產生樹狀圖與分頁網頁
VideoNotes --render "<影片資料夾>" --outputs tree-xmind               # 只從既有分析產生輸出（不花 token）
VideoNotes --reanalyze "<影片資料夾>" -p knowledge                    # 沿用逐字稿重新分析（不重新下載）
VideoNotes <網址> --stt openai                                       # 這次用雲端語音辨識（音訊會上傳）
VideoNotes --check                                                  # 自我檢查（ffmpeg、JS、yt-dlp、金鑰…）
VideoNotes --library --json                                         # 筆記庫（給程式讀）
```

| 選項 | 說明 |
|---|---|
| `-o downloads` / `-o data` / `-o <資料夾>` | 輸出位置（預設「下載\Video Notes」，其次工具旁邊的 `data\videos\`，或自選） |
| `-p` / `-w` / `--preset` / `--focus` | 整理方式、加料、常用組合、特別想知道的主題 |
| `--reuse` / `--redo download,transcribe,notes`（或 `all`） | 處理過的影片：一律沿用 / 指定重做。都沒給而且是互動視窗時會逐項詢問 |
| `--provider` / `--model` | 這次用哪個 AI（不改存檔設定）。服務：`claude-sub`（預設）/ `openai` / `gemini` / `anthropic`；只給 `--model`（例如 `haiku`）會從名稱判斷服務 |
| `--whisper-model` / `--device` / `--language` | 語音辨識模型、GPU/CPU、語言（`auto` 會先判斷） |
| `--video` | 連影片一起保留（預設只下載音訊，快很多） |
| `--post [網址]` | socket 模式（見下方） |
| `-j N` | 同時處理幾支 |
| `--outputs a,b` 或 `all` | 這次額外產生哪些輸出（Markdown 筆記一律產生）。不給就用常用組合建議的，再沒有就用設定值。名稱見「輸出形式」 |
| `--stt local\|openai\|gemini`、`--stt-model` | 這次用哪個語音辨識服務與模型（不改存檔設定）。選雲端會提醒「音訊會上傳到 …」 |
| `--render <資料夾> --outputs …`（`--slug`） | 只從既有分析產生輸出，不呼叫 AI。`--slug` 指定哪份分析，不給用最新的 |
| `--reanalyze <資料夾>` | 沿用逐字稿重新分析，可配 `-p`、`-w`、`--preset`、`--focus`、`--outputs` |
| `--combine`（`--folders a,b,c`、`--title`） | 把這次處理的網址（或指定的既有影片資料夾）合併成一份；至少兩支 |
| `-y` / `--yes` | 合併規模超過確認門檻時視為同意。非互動或 `--json` 時必須加，否則回「輸入有問題」 |
| `--check` / `--recheck` | 自我檢查；`--recheck` 先清掉「壞掉」記帳再檢查。有錯誤等級時退出碼 3 |
| `--status` / `--library` | 目前工作與依賴健康狀態／筆記庫（只讀、不連網） |
| `--json` | 機器可讀輸出（見下方「給程式呼叫」）；進度改印到 stderr |
| 環境變數 `VIDEO_NOTES_OUT` | 預設輸出位置，用法同 `-o`。優先序：`-o` > 環境變數 > 設定 |

### 給程式呼叫（`--json` 與退出碼）

stdout 只有一份 JSON：成功 `{"ok": true, "data": …}`；失敗 `{"ok": false, "error": {code, reason, retryable, remedy, detail, source}, "data": …}`
（`error` 就是錯誤合約，見 [docs/analysis-schema.md](docs/analysis-schema.md#錯誤合約所有-adapter-共用)）。
單支影片時 `data` 是該支的結果；批次時是每支一筆（成功的 `error: null`）。**v2 起 `--json` 改成這個信封格式**（舊版直接印結果）。

| 退出碼 | 意思 | 對應 code |
|---|---|---|
| 0 | 成功 | |
| 2 | 輸入有問題 | `bad_input`、`unsupported_source` |
| 3 | 依賴或環境問題 | `dependency_outdated`、`dependency_missing`、`upstream_changed`、`auth_required`、`auth_expired`、`config_invalid`（`--check` 有錯誤項也是 3；找不到 ffmpeg 是 3） |
| 4 | 暫時性，可重試 | `network_unreachable`、`rate_limited`、`resource_exhausted` |
| 1 | 其他 | `internal_bug`、`cancelled`、未預期的例外 |
| 130 | 使用者中斷（Ctrl+C） | |

批次有多個失敗時取最嚴重的：3 > 1 > 2 > 4。外部助理整合用的宣告草稿在 [docs/synox-pack-draft.json](docs/synox-pack-draft.json)（程式不讀它）。

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
**常用組合（preset，也就是「模式」）**：選了模式，整理方式、加料與**建議的輸出形式**一次決定好：

| 模式 | 內容 | 建議輸出 |
|---|---|---|
| `news-roundup` 新聞快訊總結 | 新聞＋極簡；適合好幾支一起合併 | 一小張網頁 |
| `course` 上課筆記／課程合集 | 知識＋名詞解釋＋時間軸 | 樹狀圖（Markdown）＋分頁網頁 |
| `movie-recap` 電影解說 | 娛樂快看＋金句 | 長文網頁 |
| `daily-news` | 新聞＋極簡 | 一小張網頁 |
| `stock-show` | 財經＋行動清單＋時間軸 | 長文網頁 |
| `study` | 知識＋名詞解釋＋時間軸 | 樹狀圖（Markdown） |

加料裡的時間軸、名詞解釋、行動清單、金句會寫進分析的專屬欄位（TOML 的 `field`），不會在段落裡重複一次。

**自訂**：把 TOML 放到工具旁邊的 `data\prompts\profiles|modifiers|presets|combine\`
（原始碼執行是 `tools\video-notes\data\prompts\`，exe 是 exe 旁邊的 `data\prompts\`），
同名的會覆蓋內建的（更新程式也不會被蓋掉），GUI 重新整理就生效。格式照 `prompts/` 裡的範例，例如：

```toml
# tools\video-notes\data\prompts\presets\my-ai.toml
name = "AI 產業追蹤"
profile = "finance"
modifiers = ["timeline"]
focus = "AI 伺服器、輝達、台積電先進封裝"
outputs = ["tree-md", "html-longform"]   # 選填：這個模式建議的輸出
```

`combine\<profile>.toml` 是「多片合併時怎麼整理」（`general` 是預設；新聞依事件去重歸類、知識依學習順序…），
欄位 `name`、`goal`、`rules`、`structure`，格式照 `prompts/combine/` 的範例。

### 為什麼比舊版好

舊版只有一句「請幫我重點整理」加整份逐字稿。現在：

- **給模型影片資訊**（標題、頻道、說明欄、章節）＋明確要求依上下文校正語音辨識的錯字與專有名詞。
- **依類型決定保留 / 略過什麼**，而不是所有影片同一套。
- **指令與素材分開**：指令在 system，逐字稿包在 `<transcript>` 標籤裡，逐字稿裡的句子不會被當成指令。
- **長影片分段整理再合併**（超過設定的字數門檻時），中段不會被漏掉。
- **固定的筆記標頭**（標題、網址、頻道、長度、日期、方案）由程式產生，不讓模型抄錯。
- 中文逐字稿先轉繁體（OpenCC，台灣用語），Whisper 也帶「繁體中文、有標點」的提示。
- **v2：分析一次、輸出很多種**。AI 只產生結構化的 `analysis.json`（格式見 [docs/analysis-schema.md](docs/analysis-schema.md)），
  不直接寫 Markdown／HTML；回來的 JSON 先驗證，不合格請 AI 修正一次，再不行就降級成舊寫法的 Markdown 並在筆記標頭提醒，
  整條流程不會卡住。之後換輸出形式只讀 analysis，**不再花 token**。

## 輸出形式（renderer）

都從 `analysis.json` 產生、不呼叫 AI；GUI 的「產生其他輸出」與 CLI 的 `--outputs`／`--render` 用下面的名稱。

| 名稱 | 是什麼 | 適合 |
|---|---|---|
| `markdown` | Notion 筆記（`notes.<slug>.md`，一律產生） | 貼進 Notion |
| `tree-md` | 樹狀圖：Markdown 巢狀清單 | 貼 Notion 就是一棵可折疊的樹 |
| `tree-mermaid` | Mermaid mindmap（`.mmd`） | 支援 Mermaid 的編輯器、GitHub |
| `tree-opml` | OPML | XMind、各種大綱軟體匯入 |
| `tree-freemind` | FreeMind `.mm` | XMind／FreeMind 匯入 |
| `tree-xmind` | XMind 原生 `.xmind` | 直接用 XMind 開（尚未用真的 XMind 驗證，打不開就改用 OPML） |
| `tree-html` | 可折疊的心智圖網頁 | 先看架構、複習 |
| `html-sheet` | 一小張網頁 | 短影音、新聞快訊 |
| `html-longform` | 長文網頁（目錄＋各區塊） | 一般長度、要從頭讀或列印 |
| `html-tabs` | 多分頁網頁（課綱式） | 長課程、主題多、多片合併 |

網頁範本在 [`templates/`](templates/README.md)（單檔、不載入任何外部資源）；同名檔案放到工具旁邊的 `data\templates\` 會覆蓋內建的。
樹狀圖各格式的查證與取捨見 [docs/tree-formats.md](docs/tree-formats.md)。

## 多片合併

把好幾支影片（各自已經有分析）合併成一份：新聞快訊總結、上課筆記、電影解說…。
吃的是各片的 `analysis.json` 而不是逐字稿，所以便宜；**每支影片自己的筆記照舊保留**。
怎麼合併由 AI 依你選的模式決定（`prompts/combine/`）；內容太多時自動分批合併再合併。
合併前會先估 token，超過設定的門檻（預設 60000）會先問你。

結果放在輸出資料夾的 `collections\<YYYYMMDD-HHMMSS> <標題>\`：`analysis.<slug>.json`、`notes.<slug>.md`、`outputs\`，
以及 `collection.json`（成員清單、每次合併的紀錄）。之後可以換模式再合併一次（同一批成員，不同 slug 是不同檔案）。

## 輸出檔案

每支影片一個資料夾，名稱結尾是只看網址就算得出來的 `[<kind>-<id>]`：

```
下載\Video Notes\
  台積電漲太多？鴻海卻漲不動 [video-knWPw9_a5qY]\
    media.m4a              下載的影音（保留影片時是 media.mp4）
    audio.wav              16 kHz 單聲道，給 Whisper
    transcript.txt / .srt / .json   逐字稿、字幕、含時間碼的資料
    notes.finance+timeline.md       筆記；不同方案各一份，互不覆蓋
    analysis.finance+timeline.json  v2：同一個方案的結構化分析（其他輸出都從它來）
    outputs\finance+timeline.tree-xmind.xmind   v2：其他輸出
    info.json              影片資訊、自動判斷結果、用了哪個語音辨識服務、每次處理的紀錄
  collections\
    20261112-203000 今天的新聞\     v2：多片合併（analysis／notes／outputs／collection.json）
```

- 舊資料夾（只有 `notes.*.md`、沒有 `analysis.*.json`）照常可以開；只要 Markdown 時直接沿用、不花 token，
  要其他輸出時才重新分析（沿用逐字稿）。

- 換網址寫法（`youtu.be/…`、`watch?v=…&t=42s`）還是同一支，會找到同一個資料夾。
- **沿用規則**：檔案在就沿用；要求重做或上游重做過（例如重新下載）才重做。產生的檔案一律保留，
  只有你明確要求「重新下載」時才換掉舊的影音檔。

## 同時處理多支

下載最多 2 支同時（`max_parallel_downloads`），影片與影片之間停 5～10 秒（`sleep_between_videos`，交給 yt-dlp；
YouTube 抓太兇會被當成機器人）；語音辨識一次 1 支（同一張 GPU 跑兩支只會互搶）；AI 一次 1 個請求（避免被限流）。
GUI 與 CLI 批次都一樣。「同時處理幾支」在設定裡改。

## 語音辨識服務

| 服務 | 隱私 | 說明 |
|---|---|---|
| `local`（預設） | 不離開這台電腦 | 本機 Whisper（faster-whisper）；GPU 有就用 |
| `openai` | 音訊上傳到 OpenAI | 預設 `gpt-4o-transcribe`（`whisper-1` 才有真正的分段時間碼）；單檔 25 MB，長音訊自動切段 |
| `gemini` | 音訊上傳到 Google | 走 Gemini 的 OpenAI 相容端點；時間碼是依句子估的 |

- 設定的「雲端失敗退回本機」（`stt_fallback_local`，預設開）：雲端失敗會改用本機 Whisper，分析檔會標記；**本機絕不會自動改用雲端**。
- 金鑰和 AI 服務共用（`.env` 的 `OPENAI_API_KEY`／`GEMINI_API_KEY`）。
- OpenAI 公告 `whisper-1`、`gpt-4o-transcribe` 等將於 2027-02-26 停用、改推 `gpt-transcribe`：屆時在設定的語音辨識模型填新名稱即可（見 docs/OPEN_ISSUES）。

## 錯誤與自我檢查

外部套件（yt-dlp、ffmpeg、雲端 API）壞掉時，錯誤一律講清楚「為什麼壞、下一步怎麼辦」（錯誤合約：`code`／`reason`／`remedy`，
見 [docs/analysis-schema.md](docs/analysis-schema.md#錯誤合約所有-adapter-共用)）。例如 YouTube 回 403 → 「yt-dlp 太舊」＋升級指令。

- **壞了就別一直試**：同一個依賴同一種錯誤連續 3 次，記成「壞掉」（`data\health.json`，只記代碼與次數），之後直接回報原因、不再自動重試；
  按「重新檢查」（CLI `--recheck`）或依賴版本改變（例如升級了 yt-dlp）就解除。
- **自我檢查**：`--check`（GUI 的重新檢查）不連網，看 ffmpeg、JS 執行環境（Deno ≥ 2.3 或 Node ≥ 22）、yt-dlp 已經幾天沒更新、
  GPU、各服務的金鑰**有沒有設**（不顯示內容）、各 adapter 的自我檢查。
- 程式**不會**自動升級任何套件，只告訴你指令。

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

和 Better Prompt 共用：環境變數 `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` → 專案的 `.env`
（原始碼執行讀 repo 根目錄的 `.env`；打包的 exe 先讀 exe 旁邊的 `.env`，在 repo 的 `dist\` 裡時也讀 repo 的那份）。
範本與每一項的說明在 repo 根目錄的 [`.env.example`](../../.env.example)；舊專案 `.env` 的 `chatgpt=…`、`gemini=…` 寫法也認得。
GUI 設定頁也可以直接貼金鑰，會寫進同一份 `.env`。

### OpenAI 相容端點（Ollama、LM Studio、其他服務商）

AI 服務選 `openai-compat`，在設定填端點網址（例如 Ollama 是 `http://localhost:11434/v1`）與模型名稱；
金鑰放 `.env` 的 `OPENAI_COMPAT_API_KEY`（Ollama／LM Studio 不需要，可以不填）。
本機小模型的上下文通常很短，逐字稿會自動切成小段分析（設定的 `chunk_chars` 可以手動指定段大小）。

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
| 10 | 多執行緒，只有 LLM 排隊 | `jobs.py` 執行緒池＋`pipeline.Locks`（下載 2（可設定）、轉錄 1、LLM 1） |
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
| 資料與金鑰 | 工具旁邊的 `data\`：`settings.json`、`prompts\`（自訂提示詞）、`templates\`（自訂網頁範本）、`models\`（Whisper）、`health.json`（壞掉記帳）、`videos\`（選「data」輸出時）；影片筆記預設輸出到「下載\Video Notes」；金鑰與參數在專案的 `.env` |
| 打包額外內容 | `include`: `prompts`、`socket`、`templates`、`video_notes/web/static`；`collect_all`: `yt_dlp_ejs`、`faster_whisper`（VAD 模型）、`opencc`（字典）；uvicorn 的 hiddenimports |
| 測試 | `.\tools\video-notes\.venv\Scripts\python.exe -m unittest discover -s tools\video-notes\tests -v`（離線；假的 LLM／STT／來源，不打 API、不開網路埠） |
| v2 架構（2026-11） | 核心資產 `analysis.<slug>.json`（`analysis.py`、[docs/analysis-schema.md](docs/analysis-schema.md)，改 schema 兩邊一起改並加 `SCHEMA_VERSION`）。四層 adapter 在 `video_notes/adapters/`：`source.py`（`source_ytdlp`）、`stt.py`（`stt_local`／`stt_openai`／`stt_gemini`＋`stt_chunk` 切段；`build_stt` 負責退路）、`llm.py`（`openai-compat`、`capabilities_for`）、`render.py`（`render_markdown`／`render_tree`／`render_html`）。每個 adapter 有 `capabilities()` 與不連網的 `check()`，失敗一律丟 `errors.ToolError`。分析在 `analyze.py`（驗證→修復一次→降級）、合併在 `collection.py`、筆記庫在 `library.py`、自我檢查 `doctor.py`、壞掉記帳 `health.py` |
| 加新輸出格式 | 在 `adapters/` 新增模組並 `REGISTRY.register(...)`，在 `render.load_builtin()` 加一行**明確的** import（用 importlib 動態載入的話打包的 exe 會缺模組）；只讀 analysis、不呼叫 AI；所有文字當不可信資料跳脫 |
| 加新語音辨識服務 | 新增 `adapters/stt_<name>.py` 實作 `SttAdapter` 並註冊，在 `stt.load_builtin()` 加明確的 import；雲端要自己切段（`stt_chunk`）並把錯誤轉成錯誤合約 |
| Release tag | `VideoNotes_vX.Y.Z` |

### 注意事項

- 外部程式：ffmpeg、Node（≥ 22）或 Deno（≥ 2.3）（YouTube；Bun 已被 yt-dlp 標為淘汰）。`--check`（`doctor.py`）與 `debug/check_env.py` 會檢查。
- AI 回來的 JSON 不合格時只修復一次，再不行降級成舊的 Markdown 寫法並標 `schema_repair_failed`；
  `analyze.convert_llm_error` 目前靠 `libs/toolzoo/ai/errors.py` 的中文訊息字串分類 AI 錯誤，改那邊的訊息要一起看。
- 雲端語音辨識的時間碼：只有 OpenAI `whisper-1` 是真的分段時間碼，其他是依句子字數估的（誤差在一段 5～10 分鐘以內）。
- `tree-xmind`、Mermaid 的跳脫寫法、Gemini 的 mp3 音訊輸入都還沒用真的軟體／服務驗證過（見 docs/tree-formats.md 與 docs/OPEN_ISSUES）。
- YouTube 改版導致抓不到時（403、「page needs to be reloaded」、格式不見了），只升級 yt-dlp 就好：
  `tools\video-notes\.venv\Scripts\python.exe -m pip install -U "yt-dlp[default]<2028"`（會連同 yt-dlp-ejs 一起更新）。
  **不要**為了這件事跑 `setup-venv.ps1 video-notes -Force`：那會砍掉整個 venv 重裝，包含約 2 GB 的 CUDA 套件。
  exe 版的 yt-dlp 是打包時固定的，升級後要重新 `build.ps1 video-notes`。
- Whisper 模型放在工具旁邊的 `data\models\`（Hugging Face 快取格式；medium 約 1.5 GB），沒有就第一次用時下載；
  打包的 exe 在 repo 的 `dist\` 裡時直接借用 `tools\video-notes\data\models\`，也可以用 `.env` 的 `VIDEO_NOTES_MODEL_DIR` 指定。
  程式把 `HF_HOME` 指到這裡，不會寫到使用者的 `~\.cache\huggingface`。
- 改 `libs/toolzoo/ai` 會同時影響 Better Prompt，兩個工具都要重新測。
- Claude 訂閱每次呼叫最多等 900 秒（`libs/toolzoo/ai/claude_code.py` 的 `DEFAULT_TIMEOUT`；套件預設 180 秒，長逐字稿不夠）。
  `claude-subscription` 不要降到 v0.2.1 以下：舊版在打包後的 exe 裡每呼叫一次就閃一個黑窗。
- 「AI 能不能用」（`service.environment()` 的 `keys`）對 Claude 訂閱只代表找得到 Claude Code，驗不出登入是否過期。
- GUI 的 API 只聽 127.0.0.1，寫入請求要帶 `X-Video-Notes: 1`（擋其他網站跨站呼叫），檔案存取限輸出資料夾內。
