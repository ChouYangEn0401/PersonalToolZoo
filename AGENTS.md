# AGENTS.md — 給 AI agent／接手開發者的規則

這份是「在這個 repo 裡動手之前必須知道的事」。使用方式、指令速查看 [README.md](README.md)；
每個工具的細節看 `tools/<工具>/README.md` 最後的「交接」段落。

## 這個 repo 是什麼

個人小工具的 monorepo。每個工具住在 `tools/<kebab-name>/`，彼此獨立：
各自的依賴、各自的 venv、各自的版本號與 release tag，共用 `scripts/` 裡的一套 build／release 流程。
平台是 **Windows**（主要是 Windows PowerShell 5.1、繁中系統 = cp950）。

## 不能破壞的規則

1. **工具之間互不依賴。** 不要跨 `tools/` 資料夾 import，不要把某個工具的執行時依賴放到根目錄。
   兩個以上工具都要用、而且應該一起改的程式放 `libs/toolzoo/`（見 [libs/README.md](libs/README.md)）：
   - 工具可以 import `libs`；**`libs` 不能 import 任何工具**。
   - `libs` 沒有自己的 venv：它用到的第三方套件寫在**用到它的那個工具**的 `requirements.txt`。
   - 用到 `libs` 的工具：`tool.json` 加 `"pathex": ["../../libs"]`，進入點開頭把 `libs` 加進 `sys.path`
     （照 libs/README 的寫法），兩者缺一不可——前者給打包、後者給從原始碼執行。
   - 改了 `libs` 就要把**每個**用到它的工具都重新 build 測過（目前：better-prompt、video-notes、video-downloader）。
     `libs` 本身的測試：`python -m unittest discover -s libs\tests -v`。
2. **環境規則**（定義在 `scripts/_common.ps1`）：
   - `requirements.txt` 有第三方套件 → `tools/<tool>/.venv`；只用標準庫 → 根目錄 `.venv`。
   - 加套件 = 改 `requirements.txt`，**不要**手動 `pip install` 進 venv。
   - 版本範圍**一定要有主版本上限**：`pkg>=X.Y,<下一個主版本`。只寫 `>=` 已經害過兩個工具打包後崩潰
     （Encrypter + ttkbootstrap 2、Excel Tool + pandas 3，見 README）。
   - 打包工具鏈（pyinstaller 等）只放在根目錄 `requirements-dev.txt`。
3. **版本號規則：** 唯一來源是 `tool.json` 的 `version_from` 指到的檔案裡的 `__version__ = "X.Y.Z"`。
   - exe 檔名由 `scripts/tool.spec` 讀它；視窗標題要 `import` 同一個 `__version__`。
   - **不要在任何地方手打版本號**（標題、README 以外的程式碼、檔名）。
   - 改版本用 `scripts/bump-version.ps1` 或 `scripts/release.ps1`。
4. **一份 spec：** 不要在工具資料夾放 `.spec`、`builder.bat`。差異寫進 `tool.json`
   （欄位說明見 README「build 是怎麼運作的」）。
5. **資料檔路徑：** 打包後要讀的檔案一律走 `resource_path()`（見 `tools/_template/main.py`），不要用相對路徑。
6. **編碼：**
   - `scripts/*.ps1` 必須是 **UTF-8 with BOM**（PS 5.1 沒有 BOM 會把中文讀成亂碼、甚至語法錯誤）。
   - `.bat` 只寫 ASCII。
   - `requirements*.txt` 是 UTF-8（含中文註解）；呼叫 pip 時要 `PYTHONUTF8=1`，否則 cp950 會 `UnicodeDecodeError`。
     `_common.ps1` 的 `Initialize-ToolEnv` 已經處理。
   - Python 印簡體字到 cp950 主控台會 `UnicodeEncodeError`——那是主控台問題不是程式問題，用 `PYTHONUTF8=1` 跑。

## 動完東西怎麼驗證（宣稱完成之前必做）

使用者**不會自己再重跑一次**，所以「build 成功」不算完成，要實際跑過：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1 <tool>
```

這會自動準備環境、打包、並**把 exe 開起來 10 秒做冒煙測試**（會在使用者桌面上跳出視窗再關掉）。
結果表裡是 `OK` 才算過。另外：

- 改了程式邏輯：跑該工具「交接」段落寫的測試（Encrypter 有 pytest、Git Helper 有語言測試、
  Excel Tool 沒有自動化測試就用 CLI 把動到的操作跑一次）。
- 改了 `scripts/`：至少 `build.ps1 -List`、build 一個標準庫工具（`diff`）和一個有依賴的工具（`hash`）。
  改到 `release.ps1` 時，在**拋棄式 clone** 裡測，不要在使用者的 repo 上真的 commit／打 tag。
- 改了 `.ps1`：確認檔頭還是 BOM（`EF BB BF`），並用
  `[System.Management.Automation.Language.Parser]::ParseFile(...)` 確認沒有語法錯誤。

## 非互動地執行腳本

腳本在沒給工具名稱時會跳選單讀 stdin。agent 執行時**一律帶齊參數**：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1 hash -NoSmoke
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\release.ps1 hash patch -Yes
```

選單收到空行／EOF 會當成取消，不會卡住，但也什麼都不會做。

## Commit 慣例

- 標題英文 `type(scope): summary`，type 用 `feat` / `fix` / `build` / `docs` / `refactor` / `chore`；
  scope 是工具資料夾名稱（跨工具或 scripts 就省略）。內文用中文寫**為什麼**，以及怎麼驗證的。
- **一個主題一個 commit**。版本釘選、builder 改動、文件分開 commit。
- **工作做完就 commit，結束時 `git status` 必須是乾淨的。** 使用者明確要求過，不要留著未 commit 的修改再問要不要 commit。
- 不 commit：`dist/`、`build/`、`.venv/`、`__pycache__/`（`.gitignore` 已擋）。
- 不要 push、不要打 tag，除非使用者要求。`release(<tool>): vX.Y.Z` commit 與 tag 只由 `release.ps1` 產生。
- 修改某個工具時，同一個 commit（或緊接的 docs commit）要更新該工具 README 的「交接」段落。

## 把封存分支上的工具收進來

README「歷史」列了還沒收的分支。收的時候照原本的四步，每步一個 commit：

1. `git merge <branch>`（或 merge 到某個收尾點）→ 衝突時根目錄 `README.md` 以 master 的導覽頁為準。
2. `refactor: move <Tool> into tools/<name>/` —— 只搬資料夾，`git mv`，內容不動。
3. `build: switch <Tool> to the shared spec + tool.json` —— 刪掉分支自己的 `.spec`／`builder.bat`，
   寫 `tool.json`（含 `version_from`、`tag_prefix`）、把真正的執行時依賴寫進 `requirements.txt`（加主版本上限），
   視窗標題接上 `__version__`。
4. `docs: list <Tool> in the hub README` —— 工具表加一列，工具 README 加「交接」段落，
   並從「整併的判準」表格移除／更新該分支。

收尾判準：分支最後一個 commit 是 build／build settings。沒收尾的不要收，寫進表格說明原因。
收完一定要 `build.ps1 <tool>` 通過冒煙測試，並逐檔比對搬進來的檔案跟分支上的內容一致。

## 已知的坑

- **工具名稱比對**：`git` 會同時符合 git-diff-stats 和 git-helper-pro → 會報歧義，請用 `diff`／`githelper`。
  同理 `converter`（fast-file-converter／table-format-converter）→ 用 `fast`；`video` → 用 `notes`／`downloader`。
- **web app 型的工具**（video-notes、video-downloader）：exe 一開就會開瀏覽器，冒煙測試也一樣。
  不想跳瀏覽器時先設 `$env:TOOLZOO_NO_BROWSER = 1`。冒煙測試只看 exe 有沒有活著；要確認伺服器真的有回應，
  打 `http://127.0.0.1:<port>/api/health`（video-notes 8766、video-downloader 8765）。
- **yt-dlp 抓 YouTube 需要 JavaScript 執行環境**（deno／node／bun 其中一個），`libs/toolzoo/ytdlp.py` 會全部打開、有哪個用哪個。
- **novel-reader 不要改回 pyttsx3**：2.99 在 Windows 上第二次 `runAndWait()` 就永遠卡住；現在直接呼叫 SAPI。
- **PowerShell 的 `-match`／`-notmatch` 不分大小寫**：過濾輸出時 `'ok'` 也會濾掉結果表的 `OK` 行。
- **增量 build**：輸入沒變時 PyInstaller 不重寫 exe（時間戳是舊的），產物要用 `Get-ToolInfo` 算出的檔名找，不要用時間戳。
- **Git Helper Pro** 在開發模式切換語言會改寫有進版控的 `language_config.json`。
- **Encrypter** 的 `crypto_tool/README.md` 更新紀錄寫到 v1.4.0，但實際版本檔是 0.3.0——作者還沒決定以哪個為準，不要自行改。
