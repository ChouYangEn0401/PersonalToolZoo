# PersonalToolZoo

個人小工具集散地。一個 repo、一條 branch，每個工具住在 `tools/` 底下自己的資料夾裡，
各自有隔離的環境，共用同一套 build／release 流程。

## 工具一覽

| 工具 | 說明 | 版本 | 指令裡的簡稱 | 原始碼 |
|---|---|---|---|---|
| **Git Helper Pro** | Git 指令 GUI 助手：多專案分頁、危險指令攔截、rebase/merge/stash 引導、繁中／簡中／英三語切換 | v1.6.4 | `githelper` | [tools/git-helper-pro/](tools/git-helper-pro/) |
| **Encrypter** | 檔案／文字加密 GUI，自訂 `.isd` 格式，支援多種演算法與 Mixture（多階段）加密模式 | v0.3.0 | `enc` | [tools/encrypter/](tools/encrypter/) |
| **Table Format Converter** | 貼上 Tab 分隔或 Markdown 表格即時預覽，一鍵輸出 MD／Tab／CSV／XLSX | v1.0.0 | `table` | [tools/table-format-converter/](tools/table-format-converter/) |
| **HashMyFile** | 拖放檔案計算 MD5／SHA-1／SHA-256，內容相同的檔案自動標色比對 | v0.1.0 | `hash` | [tools/hash-my-file/](tools/hash-my-file/) |
| **Advanced Excel Tool** | 分頁式 Excel 工作台：核心整理（可疊加／undo）、多檔合併、diff 比較＋AB 審核 | v0.1.0 | `excel` | [tools/excel-tool/](tools/excel-tool/) |
| **Git Diff Statistics** | 指定兩個 commit／branch，統計各副檔名的檔案數與增刪行數 | v1.0.0 | `diff` | [tools/git-diff-stats/](tools/git-diff-stats/) |

每個工具的 README 最後都有一段「**交接**」：入口、版本號在哪、用哪個環境、依賴與限制、怎麼測試、已知問題。

## 最快的用法

**雙擊根目錄的 `build.bat`** → 選要 build 的工具（編號，可多選）→ 回答兩個問題 → 完成。

```
選擇要「build」的工具：
  [1] encrypter                v0.3.0     tools\encrypter\.venv
  [2] excel-tool               v0.1.0     tools\excel-tool\.venv
  ...
  編號（可多選：1 3 或 1-3）、a = 全部、或打名稱；Enter 取消
```

產物會放在 `dist\<工具資料夾>\<名稱>(v<版本>).exe`，版本號自動帶上。
發新版就**雙擊 `release.bat`**（選工具 → 選 patch／minor／major → 確認）。

不用先裝任何東西或建環境：build 發現某個工具的 venv 不存在、或裝的版本跟 requirements 不符，會自己建好／修好。
唯一的前提是電腦上有 Python 3.11（`py -3.11` 叫得到）；Advanced Excel Tool 第一次建環境還需要 git 與網路。

## 指令速查

都在 repo 根目錄、用 PowerShell 執行。`.\scripts\build.ps1` 和 `.\build.bat` 參數完全一樣（`.bat` 自帶執行原則 bypass）。
**工具名稱可以打不完整**：`hash`、`HashMyFile`、`hash-my-file`、Tab 補完出來的 `.\tools\hash-my-file\` 都認得；
有歧義（例如 `git` 同時符合兩個工具）會列出候選請你打長一點。打完指令名稱後按 **Tab** 可以補完工具名稱。

| 我想… | 指令 |
|---|---|
| 用選單挑 | `.\scripts\build.ps1`（或雙擊 `build.bat`） |
| build 一個 | `.\scripts\build.ps1 hash` |
| build 好幾個 | `.\scripts\build.ps1 hash table excel` |
| 全部 build | `.\scripts\build.ps1 -All` |
| 從頭 build（清快取） | `.\scripts\build.ps1 hash -Clean` |
| 快速 build，不開 exe 檢查 | `.\scripts\build.ps1 hash -NoSmoke` |
| 看有哪些工具、版本、環境 | `.\scripts\build.ps1 -List` |
| 只改版本號 | `.\scripts\bump-version.ps1 hash patch`（`minor`／`major`／`1.2.3`） |
| 發新版（改版號＋build＋commit＋tag） | `.\scripts\release.ps1 hash patch`（或雙擊 `release.bat`） |
| 補打目前版本的 tag | `.\scripts\release.ps1 githelper keep` |
| 手動建／重建環境（想直接跑原始碼時） | `.\scripts\setup-venv.ps1 hash`、整個重建加 `-Force` |
| 開新工具 | `.\scripts\new-tool.ps1 my-new-tool` |
| 清掉所有 build 產物 | `.\scripts\build.ps1 -Clean` |
| 看某支腳本的完整說明 | `Get-Help .\scripts\build.ps1 -Detailed` |

每次 build 都會自動做三件事：**準備環境** → **打包** → **冒煙測試**（把 exe 開起來 10 秒，
跳出 PyInstaller 的「Unhandled exception in script」錯誤視窗或提早崩潰就判定失敗）。
最後印一張結果表，告訴你每個工具成功與否、產物在哪。

## 版本號規則

**每個工具的版本號只寫在一個地方**：`tool.json` 的 `version_from` 指到的檔案裡的 `__version__ = "X.Y.Z"`。

| 工具 | 版本檔 |
|---|---|
| encrypter | `crypto_tool/_version.py` |
| excel-tool | `excel_tool/__init__.py` |
| git-helper-pro | `src/version.py` |
| 其他（含新工具） | `version.py` |

改了它之後：

- **exe 檔名**自動變成 `<name>(vX.Y.Z).exe`（`scripts/tool.spec` 讀它，不用手打）
- **程式視窗標題**也顯示同一個版本（程式 `import` 同一個 `__version__`）
- **release tag** 是 `<tag_prefix>_vX.Y.Z`（`tag_prefix` 寫在 `tool.json`，沿用既有 tag 的命名）

沒有 `version_from` 或檔案裡沒有 `__version__`，build 會直接拒絕，不會產出沒有版本號的 exe。
版本號格式用 `主.次.修`：修 bug 加 patch、加功能加 minor、不相容的大改加 major。

## 發布流程

```powershell
.\scripts\release.ps1 hash patch      # 或雙擊 release.bat 用選單
```

依序做：改版號 → 清快取從頭 build → 冒煙測試 → commit 版本檔（`release(hash-my-file): v0.1.1`）→ 打 annotated tag（`HashMyFile_v0.1.1`）。
**不會自動 push**，最後會印出 push 指令讓你確認後自己推。

安全機制（不通過就什麼都不動）：

- 這個工具的資料夾裡有還沒 commit 的修改 → 拒絕（release 必須對應到已 commit 的程式碼）
- 有已經 `git add` 但還沒 commit 的檔案 → 拒絕（避免被一起 commit 進 release）
- tag 已經存在 → 拒絕
- build 或冒煙測試失敗 → 把版本檔還原，不 commit、不打 tag

產物在 `dist\<工具資料夾>\` 裡，拿去上傳／發給別人即可。

## 環境隔離規則

| 工具的 `requirements.txt` | 用哪個環境 |
|---|---|
| 有第三方套件 | `tools\<工具資料夾>\.venv`（專屬，互不干擾） |
| 只用標準庫 | 根目錄 `.venv`（共用，只裝 build 工具鏈） |

- 每個 venv 都裝 `requirements-dev.txt`（PyInstaller 等，版本全 repo 一致）＋該工具自己的 `requirements.txt`。
- build 前會檢查 venv 裡裝的版本**符合** requirements；不符合就自動同步，還不行就整個重建。
- 有第三方套件的工具**一定**用自己的 `.venv`，不會退回共用環境（那樣會產出一個缺套件、一開就崩潰的 exe）。
- `.venv` 都在 `.gitignore` 裡，隨時可以砍掉重建。要加套件請改 `requirements.txt`，不要手動往 venv 裡 `pip install`。

### 版本範圍要給主版本上限

`requirements.txt` 請寫 `套件>=最低版本,<下一個主版本`，不要只寫 `>=`。
只寫 `>=` 的話，新機器（或重建 venv）會裝到開發時根本還不存在的新主版本。這個 repo 就實際踩過兩次：

| 工具 | 只寫 `>=` 時裝到 | 結果 | 現在 |
|---|---|---|---|
| Encrypter | ttkbootstrap 2.2.2 | 2.x 改從檔案載入字型，打包後一啟動就 `FileNotFoundError` | `ttkbootstrap>=1.10.1,<2` |
| Advanced Excel Tool | pandas 3.0.6 | 「合併濃縮」遇到空格就 `TypeError`（pandas 3 改了 `astype(str)`） | `pandas>=2.0,<3` |

要升主版本：改上限 → `.\scripts\setup-venv.ps1 <tool> -Force` → 實際把功能跑過一輪 → `.\scripts\build.ps1 <tool>`。

## 開一個新工具

```powershell
.\scripts\new-tool.ps1 my-new-tool        # 名稱用小寫 kebab-case
```

從 `tools/_template/` 複製一份骨架（tkinter 視窗、`resource_path()`、`version.py`、`tool.json`、
附「交接」段落的 README），視窗標題已經接好版本號。然後：

1. 寫 `tools/my-new-tool/main.py`，版本號在 `version.py`
2. 需要第三方套件就寫進 `requirements.txt`（記得給主版本上限）
3. 有資料檔（圖片、語言檔、設定檔…）就填 `tool.json` 的 `include`
4. `.\scripts\build.ps1 my-new-tool`（環境會自動建）
5. 填好工具 README 的「交接」段落，回來這份 README 的工具表加一列

## 目錄結構

```
PersonalToolZoo/
├─ README.md               ← 你正在看的導覽頁
├─ AGENTS.md               ← 給 AI agent／接手開發者的規則（CLAUDE.md 會引用它）
├─ build.bat / release.bat ← 雙擊用的入口
├─ requirements-dev.txt    ← 共用 build 工具鏈（pyinstaller 等），所有 venv 都裝
├─ .venv/                  ← 共用虛擬環境（只給只用標準庫的工具）
├─ scripts/
│  ├─ build.ps1            ← 統一 builder：選單、名稱比對、自動環境、打包、冒煙測試
│  ├─ release.ps1          ← 發布：改版號 → build → commit → tag
│  ├─ bump-version.ps1     ← 只改版本號
│  ├─ setup-venv.ps1       ← 手動建立／重建工具的 venv
│  ├─ new-tool.ps1         ← 產生新工具骨架
│  ├─ _common.ps1          ← 上面幾支共用的 helper（環境／版本／名稱規則都定義在這）
│  ├─ check_deps.py        ← 檢查 venv 裡的版本符合 requirements
│  └─ tool.spec            ← 全 repo 唯一一份 PyInstaller spec
├─ tools/
│  ├─ _template/           ← 新工具的空白範本
│  └─ <工具資料夾>/        ← 每個工具一個資料夾，自成一個乾淨單位
│     ├─ tool.json         ← 這個工具的 build 設定（入口、版本檔、tag 前綴…）
│     ├─ README.md         ← 使用說明 ＋「交接」
│     ├─ requirements.txt  ← 執行時依賴（不放 pyinstaller）
│     ├─ .venv/            ← （有第三方依賴才有）這個工具專屬的隔離環境
│     └─ main.py, version.py, ...
├─ build/<工具資料夾>/     ← PyInstaller 增量快取（-Clean 會清）
└─ dist/<工具資料夾>/      ← 打包產物
```

## build 是怎麼運作的

全 repo 只有 `scripts/tool.spec` 一份 spec，各工具的差異寫在自己的 `tool.json`：

```json
{
  "name": "MyTool",
  "entry": "main.py",
  "console": false,
  "version_from": "version.py",
  "tag_prefix": "MyTool",
  "include": ["assets", "config.json"],
  "collect_all": ["some_package_with_data_files"]
}
```

| 欄位 | 必填 | 意思 |
|---|---|---|
| `name` | ✔ | exe 檔名主體 |
| `entry` | ✔ | 進入點（相對工具資料夾） |
| `console` | | `true` 會多一個主控台視窗；`false` 是純視窗程式（崩潰時跳錯誤視窗） |
| `version_from` | ✔ | 版本檔（見「版本號規則」） |
| `tag_prefix` | ✔ | release tag 前綴 |
| `include` | | 要一起打包的資料檔／資料夾 |
| `collect_all` / `hiddenimports` / `excludes` | | PyInstaller 自己抓不到時才需要 |

產物一律 onefile。`build.ps1` 會把工具資料夾的絕對路徑透過環境變數 `TOOLZOO_TOOL_DIR` 交給 spec，
spec 裡所有路徑都以它為基準解析，**完全不依賴當下的工作目錄**，在哪裡執行結果都一樣。
平常 build 會用 PyInstaller 的增量快取（輸入沒變就不重寫 exe）；`-Clean` 會先清掉該工具的 `build\`、`dist\`。

### 兩條規矩

1. **`.spec` 只有一份。** 各工具不要自己放 `.spec`，差異寫進 `tool.json`。
2. **程式裡不要用相對路徑讀資料檔。** 打包後 CWD 不是你想的那個目錄，
   資料會被解到 `sys._MEIPASS`。一律走這個 helper：

   ```python
   def resource_path(*parts):
       base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
       return os.path.join(base, *parts)
   ```

### 編碼注意事項（繁中 Windows）

- `requirements*.txt` 是 UTF-8 且含中文註解。pip 預設用系統編碼（cp950）讀檔會直接 `UnicodeDecodeError`，
  所以腳本呼叫 pip 時會開 `PYTHONUTF8=1`。**手動** `pip install -r` 前也要先 `$env:PYTHONUTF8 = 1`。
- `scripts\*.ps1` 必須存成 **UTF-8 with BOM**，Windows PowerShell 5.1 才不會把中文讀成亂碼。
- `.bat` 只寫 ASCII。

## 歷史

早期每個工具各自開一條 branch、都待在 repo 根目錄開發，
原因是 build 腳本裡的路徑寫死成相對於工作目錄（`os.path.abspath('.')`），
工具一搬進子資料夾就找不到檔案。

`tool.json` + 共用 spec 的做法解掉了這個限制，工具已整併回 `master`。
各工具原本的 branch 保留作為封存，開發歷史完整保存在 commit 紀錄裡
（每個工具都是 merge → 搬資料夾 → 換 build file → 更新本頁 四個 commit）。

### 整併的判準

一個工具要被收進 `master`，它在原分支上必須已經「收尾」——
最後一個 commit 是 build／build settings（通常伴隨版本號更新），代表作者確認可用。
所以有幾支是刻意只收到一半，或整支沒收：

| 分支 | 狀況 |
|---|---|
| `feat/git_command_gui_helper/dev` | 未收（收尾是 `[BU]` 不是 build，且是從 v1.6.4 之前的舊版分出去的）。主線已經有 Fetch 對話框和 Pull 按鈕；這條分支多的是 `commands.py` 裡一組**帶參數的 `fetch` / `pull` 指令設定**（remote / prune / rebase），之後想補的話從這裡撈。 |
| `feat/hash_my_file_gui/all_platform` | 只收到 tag `HashMyFile_v0.1.0`。tag 之後那個「只留重複檔」的 feat commit 還沒收尾，未收。 |
| `feat/git_diff_shower` | 只收到 BUILD 點 `0aba850`。之後的 filter 分類、no-git snapshot 分頁、snapshot 修正三個 commit 還沒收尾，未收。 |
| `feat/shell_converter/all_platform` | 未收，tag 自己標了 `shell_converter__failed`。 |
| `temp-save` | 未收，內容是 stash。 |

要把上面任何一段補進來，照同一套四步流程再跑一輪（步驟細節見 `AGENTS.md`）。
