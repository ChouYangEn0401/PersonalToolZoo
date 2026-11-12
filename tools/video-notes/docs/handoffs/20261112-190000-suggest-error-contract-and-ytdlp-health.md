# Video Notes：錯誤合約、yt-dlp 維護與批次節流（建議修改，搭配 v2 計畫一起做）

- **狀態：待處理**（只有建議，尚未動工；做完請逐項勾選驗收，把狀態改「已修」並寫 merge commit）
- 建立：2026-11-12 ｜ 範圍：`tools/video-notes/`（先只改這個工具；共用的 `libs/toolzoo/ytdlp.py` 先不動，見選項表）
- 開發線：`dev/video-notes`，開工前 `git merge master`
- **寫給接手的 agent**：這張跟旁邊的 `20261112-182622-v2-analysis-adapters-plan.md` 是同一個開發週期。
  v2 計畫的第 0 波（契約）要把這張的「錯誤合約」一起定下來，後面每個 adapter 才有共同的失敗格式。
  本檔旁邊還有兩張 `suggest-*` 檔（adapter 加固、SYNOX 介面預留）。**全部做完之後回來逐項勾選驗收，三張都要收尾。**

## 擁有者原話（一字不改）

> 然后我这边想要讲的事情是因为这种外部的套件在使用的时候容易出现一些错误，所以我觉得我接下来也会要求或者是限制说，就是我的每一个套件呢，它在出现 error 的时候要很明确的写出 try and catch， 就是要写出说为什么会坏掉，因为这样一来的话，就是未来 agent 再去读的时候就会知道说，哎，这个套件说它坏了，那请问是能够更新吗？怎么更新？就是我也希望有些补救措施是可以写出来的，然后这样子的话，就是未来 agent 在做的时候才能够去判断这个套件是，例如说需要更新，那他可以自己去更新，还是真的坏了？那坏掉的原因是什么？他也要把它列出来，甚至是未来当我的 agent 有很多工具在使用的时候，如果有一些工具已经明确坏掉了，他应该要有一个类似暂存的管理器，他去标记说这个东西已经坏了，那未来就不应该一直在去跑它，然后又坏了，然后又尝试去修。等于说，我会觉得这些东西应该要把它列起来，然后就是我会觉得是 agent core 应该要去做到的事情。

## 問題一句話

Video Notes 靠一堆會變動的外部東西（yt-dlp、ffmpeg、JavaScript 執行環境、GPU 與語音套件、雲端 API、Notion）。
壞掉的時候現在多半直接丟出上游的原始英文訊息，沒有「為什麼壞」和「下一步怎麼辦」，也沒有任何地方記住「這個已經壞了」，所以人與 agent 都會一直重試。

## 脈絡

- 維護清單其實只有四項（來源：yt-dlp 官方 wiki，見最後「參考」）：
  ① yt-dlp 版本（最常壞；YouTube 改版時上游會修，升級就好）；② ffmpeg 找得到；③ 格式選擇交給 yt-dlp 的格式語法，不要自己判斷；
  ④ **JavaScript 執行環境**（YouTube 現在需要：Deno 2.3 以上或 Node 22 以上；缺了錯誤看起來像 403）。
- 已經做的（在 `dev/video-notes` 與 `dev/video-downloader` 上）：`fe23f1e` 把 README 的「重建整個 venv」改成「只升級 yt-dlp」；
  `270c661`（video-downloader）讓 YouTube 的 403 提示「yt-dlp 太舊，升級就好」。Video Notes 的程式本身還沒有對應的錯誤處理。
- v2 會讓「一次處理多支影片」變常態：批次下載越多，越容易被 YouTube 當成機器人（官方建議影片與影片之間停 5–10 秒）。
- 擁有者的偏好：**簡單**。一個 JSON 加一個追蹤檔就能表達狀態，不要為了這件事做大 class 階層。

## 設計（建議；擁有者已認可方向，細節由你決定）

### 1. 錯誤合約（一個小模組，例如 `video_notes/errors.py`）
一個簡單的例外類別＋一張代碼表，所有外部呼叫都用它回報：

| 欄位 | 說明 |
|---|---|
| `code` | 穩定的小寫代碼（見下表）；程式與 agent 都靠它判斷，不靠文字 |
| `reason` | 一句人話：為什麼壞（≤ 120 字，不含金鑰、不含完整路徑） |
| `retryable` | 重試有沒有可能成功 |
| `remedy` | `kind`（`needs_update`／`needs_config`／`needs_owner`／`auto_fixable`／`none`）＋ `action`（要做的事，例如升級指令，**只寫出來，不自動執行**）＋ `doc`（說明連結或本專案文件路徑） |
| `detail` | 上游訊息的短摘要（≤ 300 字，已去敏感資訊）；完整內容只寫進工作 log |

代碼起手：`dependency_outdated`、`dependency_missing`（ffmpeg／JS 執行環境／套件）、`upstream_changed`、`network_unreachable`、
`auth_required`、`auth_expired`、`rate_limited`、`config_invalid`、`unsupported_source`、`resource_exhausted`（GPU 記憶體、磁碟）、
`bad_input`（只有這次輸入有問題）、`internal_bug`（其餘；要附 log 位置）。

規則：**每個外部呼叫（yt-dlp、ffmpeg 子行程、STT、AI、Notion）都要明確的 try／except，轉成上面的格式；不准吞例外、不准只印 `str(e)`。**
yt-dlp 的對照：403／「page needs to be reloaded」／找不到格式／簽章或 nsig 失敗 → `dependency_outdated`（remedy：升級 yt-dlp）；
找不到 JS 執行環境 → `dependency_missing`；「Sign in to confirm you're not a bot」→ `rate_limited`（remedy：稍後再試或由使用者自己選擇是否使用 cookie）。

### 2. 啟動前自我檢查（不連網）
`video_notes/doctor.py` 或 CLI `--check`：ffmpeg 找得到嗎、JS 執行環境有嗎且版本夠嗎、yt-dlp 版本與「已經幾天沒更新」
（版本號本身是日期，不用連網就能算）、GPU／CUDA 可用嗎、各 adapter 需要的金鑰**有沒有設**（只回有或沒有，不印內容）、Notion 權杖有沒有設。
輸出人看得懂的清單，並支援 `--json`（給日後的程式與 agent 讀）。網頁 GUI 標題列顯示 yt-dlp 版本與天數。

### 3. 「壞了就別一直試」的小記帳（一個 JSON 檔）
`data/health.json`：每個外部依賴一筆 `{code, first_seen, last_seen, count, state}`。
同一個 `code` 在同一個依賴上連續失敗 **3 次**就標 `degraded`：這個工作階段不再自動重試，GUI 顯示原因與 remedy，
等使用者按「重新檢查」或依賴版本改變才清掉。只存代碼與計數，不存內容；檔案壞了就當沒有。

### 4. 批次節流
v2 的多片處理：影片與影片之間預設停 5–10 秒（設定欄位 `download.sleep_between_videos`，用 yt-dlp 本身的 `sleep_interval`／`max_sleep_interval`，
不要自己寫 `time.sleep`）；同時下載 YouTube 的數量預設 2（現在是 3，可調）。

### 5. 其他小事
- `JS_RUNTIMES` 的清單移除 Bun（上游已標淘汰）；Node 保留。
- 交給 yt-dlp 的重試參數維持 `retries`／`fragment_retries`，不要自己再包一層重試迴圈。

## 選項表

| 選項 | 內容 | 建議 |
|---|---|---|
| A | 只在 `tools/video-notes/` 內做上面 1～5 | **建議（預設）** |
| B | A 做完後，把錯誤對照表與自我檢查抽到 `libs/toolzoo/ytdlp.py`，讓 video-downloader 共用 | 之後再做（要重 build 6 個工具，見 AGENTS.md） |
| C | 自動升級 yt-dlp（程式自己跑 pip） | **不做**：換掉的是會執行的程式碼；一律由使用者確認後手動升級（工具只負責講清楚怎麼做） |

## 驗收（逐項勾選）

- [ ] 用假的 `yt_dlp` 丟出各種上游錯誤，單元測試證明都被轉成對應 `code`＋`reason`＋`remedy`，沒有裸例外跑到畫面上。
- [ ] 所有外部呼叫點（下載、ffmpeg、STT、AI、Notion）都有明確 try／except；`grep` 不到 `except Exception: pass` 這類吞例外。
- [ ] `--check`（及 `--json`）在缺 ffmpeg／缺 JS 執行環境／yt-dlp 太舊三種情境（用假環境）下輸出正確。
- [ ] 同一代碼連續失敗 3 次後標 `degraded`、不再自動重試；重新檢查或版本改變後解除（假時鐘／假依賴測試）。
- [ ] 訊息與 `health.json` 不含金鑰、完整路徑（加一個測試用假金鑰字串確認不會出現）。
- [ ] 成功路徑行為與輸出完全不變（既有測試全過）。
- [ ] 批次下載在影片之間套用 sleep 設定（檢查傳給 yt-dlp 的選項）。
- [ ] README 的「交接」段落與 `docs/HANDOFF.html` 補上：錯誤代碼表、`--check` 用法、yt-dlp 升級指令、exe 版要重新 build。

## 不要做的事

- 不要自動 `pip install`、不要自動讀瀏覽器 cookie、不要手動維護「播放器 client 清單」（上游會變，升級 yt-dlp 才是正解）。
- 不要為了這件事做大型類別階層；一個例外類別、一張代碼表、一個 JSON 檔就夠。
- 測試不連網、不下載影片、不開網路埠。
- 不要自己 push／打 tag／發版。

## 參考（公開資料）

- yt-dlp EJS（JavaScript 執行環境）：https://github.com/yt-dlp/yt-dlp/wiki/EJS
- yt-dlp Extractors（YouTube 的速率限制、cookie 風險、建議的間隔）：https://github.com/yt-dlp/yt-dlp/wiki/Extractors
- yt-dlp PO Token Guide：https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide
- yt-dlp Releases：https://github.com/yt-dlp/yt-dlp/releases
