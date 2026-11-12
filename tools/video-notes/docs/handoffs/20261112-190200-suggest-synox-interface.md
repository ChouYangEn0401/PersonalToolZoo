# Video Notes：預留給外部 AI 助理核心（SYNOX）呼叫的介面（建議，本期只留介面）

- **狀態：已修（本期範圍：1～3 與草稿 4）**（2026-11-12；merge commit `d47f868`，驗收結果見檔尾「收尾紀錄」）
- 建立：2026-11-12 ｜ 範圍：`tools/video-notes/video_notes/cli.py`、`docs/`；不新增對外部專案的相依
- 開發線：`dev/video-notes`，開工前 `git merge master`
- **寫給接手的 agent**：這張是三張 `suggest-*` 裡最輕的一張。做 v2 的時候順手把介面留好即可，
  不要因為這張去改 v2 的核心設計。旁邊的 `20261112-190000-suggest-error-contract-and-ytdlp-health.md` 與
  `20261112-190100-suggest-adapter-hardening.md` 是前提（錯誤合約、`--check`）。**全部做完回來逐項勾選驗收，三張都要收尾。**

## 擁有者原話（一字不改）

> 然后我这边想要讲的事情是因为这种外部的套件在使用的时候容易出现一些错误，所以我觉得我接下来也会要求或者是限制说，就是我的每一个套件呢，它在出现 error 的时候要很明确的写出 try and catch， 就是要写出说为什么会坏掉，因为这样一来的话，就是未来 agent 再去读的时候就会知道说，哎，这个套件说它坏了，那请问是能够更新吗？怎么更新？就是我也希望有些补救措施是可以写出来的，然后这样子的话，就是未来 agent 在做的时候才能够去判断这个套件是，例如说需要更新，那他可以自己去更新，还是真的坏了？那坏掉的原因是什么？他也要把它列出来。

> 因為你有幫我盤點所以你可能更多知道我們剛剛討論的細節，我覺得你在這份檔案旁邊可以放你對我專案的建議修改方式。

## 問題一句話

擁有者另有一個 AI 助理核心專案（SYNOX），它能用「指令」呼叫已安裝的工具，並讀工具的狀態與錯誤。
Video Notes 以後可能被它呼叫（例如「幫我把這支影片整理成筆記」），所以現在就要讓它**可以被程式安全地呼叫與判讀**，但不能變成必須依賴它。

## 脈絡

- 呼叫方式是「指令列＋機器可讀的 JSON 輸出＋穩定的退出碼」，不是 import。Video Notes 要維持獨立可用。
- 助理核心判斷「工具壞了還是只是這次輸入不對」靠的就是錯誤合約的 `code`／`retryable`／`remedy`（見 `suggest-error-contract-and-ytdlp-health`）。
- 本機網頁 GUI（現在 8766）未來也許能被核心代理顯示；那需要核心端先有對應能力，**本期不做、只在文件寫清楚怎麼啟動與健康檢查路徑**。

## 設計（建議，本期只做 1～3）

1. **機器可讀的 CLI**：給所有會被呼叫的子指令加 `--json`：成功回 `{"ok": true, "data": {...}}`，失敗回 `{"ok": false, "error": {code, reason, retryable, remedy, detail}}`
   （就是錯誤合約）。退出碼固定：0 成功、2 輸入有問題（`bad_input`）、3 依賴或環境問題（`dependency_*`、`config_invalid` 等）、4 暫時性問題可重試、1 其他。
2. **狀態指令**：`--check --json`（見錯誤合約那張）、`status --json`（目前有哪些工作、各自進度）、`list --json`（筆記庫有哪些影片與其 `analysis.json` 摘要）。全部只讀、不連網。
3. **輸出位置可設定**：`--out <資料夾>` 與環境變數，所有檔案都寫在資料夾內；程式裡不得出現任何一台電腦才有的絕對路徑。
4. **（暫緩，只寫文件）pack 宣告草稿**：在 `docs/synox-pack-draft.json` 放一份草稿（**不發佈、不被程式讀取**），內容大致如下，供日後整合時直接取用：

```json
{
  "name": "video-notes",
  "version": "0.0.0-draft",
  "stage": "alpha",
  "kind": "cli",
  "requires": { "sdk": ">=0.2,<0.3" },
  "capabilities": ["network"],
  "commands": [
    { "name": "notes_run",    "summary": "把一支影片整理成筆記", "args": ["url", "profile?"], "danger": false },
    { "name": "notes_status", "summary": "查看工作進度",       "args": [],                    "danger": false },
    { "name": "notes_list",   "summary": "列出筆記庫",         "args": [],                    "danger": false }
  ],
  "health": { "check": "--check --json" }
}
```
   欄位名稱以將來助理核心的文件為準；這裡只是預留。**不要在 repo 裡引用該專案的檔名或路徑。**

## 選項表

| 選項 | 內容 | 建議 |
|---|---|---|
| A | 只做 1～3（機器可讀 CLI、狀態指令、輸出位置可設定），4 只寫草稿 | **建議（預設）** |
| B | 連網頁 GUI 的代理與嵌入顯示一起設計 | 等核心端有對應能力再做 |
| C | 現在就做完整的 pack 整合與測試 | 不做（會讓這個工具依賴外部專案） |

## 驗收（逐項勾選）

- [x] 主要子指令支援 `--json`，成功與失敗的輸出格式有單元測試；失敗輸出就是錯誤合約。
- [x] 退出碼符合上表，並寫進 README。
- [x] `--check --json`、`status --json`、`list --json` 只讀、不連網，有測試。
- [x] 預設輸出位置可用 `--out` 或環境變數覆寫；程式碼中沒有本機絕對路徑（`grep` 檢查）。
- [x] `docs/synox-pack-draft.json` 存在，且程式不讀取它；repo 內沒有出現外部專案的路徑或私人資訊。
- [x] 既有 CLI 與網頁行為不變，既有測試全過。

## 不要做的事

- 不要 import 或安裝任何外部助理專案的程式；不要為了它改 v2 的核心設計。
- 不要把金鑰、本機路徑、個人資料寫進 repo（repo 是公開的）。
- 測試不連網、不開網路埠。
- 不要自己 push／打 tag／發版。

## 收尾紀錄（2026-11-12）

選項 A 做完。commit：b31fb04（`--json` 信封、退出碼、`--check`／`--status`／`--library`、`VIDEO_NOTES_OUT`、docs/synox-pack-draft.json）。merge commit 見 v2 計畫那張的收尾紀錄。

- 「`status --json`、`list --json`」做成旗標 `--status --json`、`--library --json`（舊的 `--list` 已經是「列出整理方式」，不能再用 list）。草稿檔與 README 都照這個寫法。
- `--json` 的輸出格式因此改成信封（`{"ok", "data"|"error"}`），README 有註明；找不到 ffmpeg 的退出碼由 2 變 3（環境問題）。
