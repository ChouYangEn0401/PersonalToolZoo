# 問題交接報告書

> 還沒處理、需要使用者決定、或之後要做的事。整體交接（每個工具的版本、用途、狀態）在 [HANDOFF.html](HANDOFF.html)。
> 處理完一項就把它移到最下面的「已解決」，寫上日期與怎麼解決的。

最後更新：2026-10-27

## 要你決定

### Q1. 刪掉已經搬完的舊專案資料夾

資料都已經搬走並比對過檔案數與大小（見 HANDOFF.html「舊專案去了哪裡」），剩下的只有舊環境（venv）、舊的打包產物與腳手架。
自動模式把「永久刪除本機資料夾」擋下來，需要你明確同意（或自己刪）：

| 資料夾（`Python Projects\` 底下） | 剩下的東西 |
|---|---|
| `VideoToSimpleNotion` | `.venv`（4.8 GB）、舊程式（已在 hub 的 import commit；漏掉的 3 個腳手架檔案內容記在 HANDOFF.html）、`.env`（金鑰已併進專案 `.env`） |
| `VideoDownloader` | `.venv`、舊的 `main.py`（已在 hub 的 import commit） |
| `。Better Prompt` | `.venv`、`build\`、`dist\`（舊 exe）、`.env`（已併入） |
| `。Fast File Converter` | `.venv`（445 MB）、`build\`（105 MB） |
| `。My Internet Novel Reader` | `venv\`、`.venv`、舊程式 |
| `My Voice Assistant` | 兩份 venv、舊程式 |
| `。File Renamer`、`。Better File Finder`、`。HashMyFile`、`64x64 Random Icon Maker` | venv 與舊腳手架 |

`Change Folder Cover (failes)` 已經刪除（程式在 hub 的 import commit，重做成 `tools/folder-cover`）。
這些資料夾的 git 歷史都只在本機；你決定過不需要保留（2026-10-23）。`ClaudeLogin` 是獨立專案，保留。

### Q2. 刪掉 `Python Projects\.git`

`Python Projects` 根目錄本身是一個 2024-12 的舊 git repo（15 個 commit、沒有遠端、追蹤的 18 個檔案都已經不在），
看起來是 Git 指令 GUI 的早期原型。沒有用處，而且在沒有自己 git 的子資料夾裡下 git 指令會動到它。只刪 `.git` 這一個資料夾。

### Q3. 清掉電腦上的殘留

內容都已經搬進專案，留著只會混淆：

- `%APPDATA%\PersonalToolZoo\`：舊的共用金鑰檔 `keys.env`（已併進專案 `.env`）與三個空資料夾。
- `%USERPROFILE%\.better_prompt_settings.json`：Better Prompt v1 的設定（金鑰已併入，模型與 temperature 已搬進 `tools\better-prompt\data\settings.json`）。
- `%TEMP%` 裡測試留下的 `novel-reader-*`、`file-renamer-test-*`（造成殘留的原因已修掉，不會再產生）。

### Q4. GitHub 上的舊分支

| 分支 | 狀態 | 建議 |
|---|---|---|
| `feat/Encrypter/all_platform`、`feat/ExcelTool`、`feat/table_form_converter`、`feat/git_command_gui_helper/new_features` | 已完整併進 master | 可以刪 |
| `feat/git_command_gui_helper/all_platform` | 已完整併進 master，但它是 **GitHub 的預設分支**（repo 首頁顯示的是它的舊 README） | 先在 GitHub → Settings → Branches 把預設分支改成 `master`，再刪 |
| `feat/git_command_gui_helper/dev` | 比 master 多 4 個 commit（帶參數的 fetch / pull 指令設定），作者沒收尾 | 想要那組功能就照 AGENTS.md 的四步流程收進來；不要就刪 |
| `feat/git_diff_shower` | 多 3 個 commit（filter 分類、no-git snapshot 分頁），沒收尾 | 同上 |
| `feat/hash_my_file_gui/all_platform` | 多 1 個 commit（「只留重複檔」、開啟、刪除按鈕），沒收尾 | 同上 |
| `feat/shell_converter/all_platform` | 多 2 個 commit，作者標了 `shell_converter__failed` | 刪，或留著當紀錄 |
| `temp-save` | 1 個 stash commit | 看一眼再決定 |

不想刪又不想讓分支清單變長，可以改成 tag 保存（例如 `archive/git_diff_shower`）再刪分支，commit 都還在。

### Q5. 換掉沒用的金鑰

專案 `.env` 裡的 OpenAI 金鑰（兩把）在 2026-10-05 實測都回 `429 insufficient_quota`，Gemini 金鑰無效。
現在預設用 Claude 訂閱，用不到它們；要用 OpenAI／Gemini 就換新的，不用就刪掉那幾行。

## 之後可以做

- **Video Downloader 的 web API 測試**需要 `httpx2`，它不在工具自己的環境裡，所以在自己的 `.venv` 跑時那 2 個測試會略過
  （用 Video Notes 的環境跑就 10/10）。要的話把測試依賴寫成獨立的 requirements。
- **Encrypter 的測試**：README 叫你手動 `pip install pytest` 進工具的環境，跟 AGENTS.md「不要手動往 venv 裝套件」衝突。
  測試本身是純 `assert` 函式，2026-10-27 是用不需要 pytest 的方式跑的（7 個全過）。要的話把它改成 unittest，或把 pytest 列成獨立的測試依賴。
- **Claude 訂閱**：「檢查 Claude Code」只確認找得到執行檔，登入過期要到第一次真的呼叫才知道；每次呼叫都用訂閱額度。
- **HANDOFF.html 在 GitHub 上看不到排版**（GitHub 只顯示 HTML 原始碼）：在本機用瀏覽器打開，或看 claude.ai 上的同名 artifact。

## 已解決

| 日期 | 項目 | 怎麼解決 |
|---|---|---|
| 2026-10-23 | 151 個檔案卡在未完成的 merge | 取消那個 merge，把分支重切成 80 個小 commit 接到 master |
| 2026-10-23 | 工具把資料寫進 `%APPDATA%`、家目錄、`~/.cache` | 一律改成工具旁邊的 `data\` 與專案的 `.env`（AGENTS.md 規則 6） |
| 2026-10-23 | Git Helper Pro 開發模式會改寫有進版控的 `language_config.json` | 改存 `data\language_config.json` |
| 2026-10-23 | File Renamer 的正規表達式改名很難用 | 重寫：規則清單、資料夾掃描、只改主檔名、兩段式套用、跨次復原（v2.0.0） |
| 2026-10-23 | Change Folder Cover 一直沒成功 | 用 Windows 的 `SHGetSetFolderCustomSettings` 重做成 `tools/folder-cover`（v1.0.0） |
| 2026-10-23 | 從原始碼執行容易用錯環境 | 每個工具一支 `run.bat`（`scripts/run.ps1`），`--check-all` 一次檢查全部 |
| 2026-10-27 | 4 個工具的依賴只寫 `>=`（Encrypter、Excel Tool、HashMyFile、Table Converter） | 照 venv 裡實際的版本補上主版本上限，重新 build 冒煙測試 OK |
| 2026-10-27 | 每個工具沒有自己的開發線 | 開 15 條 `dev/<工具資料夾>`，流程寫進 README「開發線」與 AGENTS.md |
| 2026-10-27 | GitHub 上的 `feat/tool-migration`（舊的 41 個 commit） | 確認它的內容都在 master 之後刪除 |
| 2026-10-27 | push 前要確認沒有機密 | 掃完所有分支與 tag 的歷史：沒有金鑰、`.env` 與 `data\` 沒被追蹤；之後 push 到 GitHub |
