# PersonalToolZoo

個人小工具集散地。一個 repo、一條 branch，每個工具住在 `tools/` 底下自己的資料夾裡，
共用同一套 build 流程。

## 工具一覽

| 工具 | 說明 | 版本 | 原始碼 |
|---|---|---|---|
| **Git Helper Pro** | Git 指令 GUI 助手：多專案分頁、危險指令攔截、rebase/merge/stash 引導、繁中／簡中／英三語切換 | v1.6.4 | [tools/git-helper-pro/](tools/git-helper-pro/) |
| **Encrypter** | 檔案／文字加密 GUI，自訂 `.isd` 格式，支援多種演算法與 Mixture（多階段）加密模式 | v0.3.0 | [tools/encrypter/](tools/encrypter/) |
| **Table Format Converter** | 貼上 Tab 分隔或 Markdown 表格即時預覽，一鍵輸出 MD／Tab／CSV／XLSX | v1.0.0 | [tools/table-format-converter/](tools/table-format-converter/) |
| **HashMyFile** | 拖放檔案計算 MD5／SHA-1／SHA-256，內容相同的檔案自動標色比對 | v0.1.0 | [tools/hash-my-file/](tools/hash-my-file/) |
| **Advanced Excel Tool** | 分頁式 Excel 工作台：核心整理（可疊加／undo）、多檔合併、diff 比較＋AB 審核 | v0.1.0 | [tools/excel-tool/](tools/excel-tool/) |
| **Git Diff Statistics** | 指定兩個 commit／branch，統計各副檔名的檔案數與增刪行數 | — | [tools/git-diff-stats/](tools/git-diff-stats/) |

## 快速開始

以下指令都在 repo 根目錄、用 PowerShell 執行。

```powershell
# 1. 看有哪些工具、各自用哪個環境、版本號
.\scripts\build.ps1 -List

# 2. 建立工具的隔離環境（第一次、或 requirements 改過之後）
.\scripts\setup-venv.ps1 <tool-name>
.\scripts\setup-venv.ps1 -All

# 3. 打包某一個工具；-Smoke 會把 exe 實際開起來檢查有沒有崩潰
.\scripts\build.ps1 <tool-name> -Smoke     # 產物在 dist\<tool-name>\

# 4. 全部打包
.\scripts\build.ps1 -All -Smoke
```

> 如果 PowerShell 擋腳本（執行原則），先在這個視窗跑一次
> `Set-ExecutionPolicy -Scope Process Bypass`。

## 環境隔離規則

| 工具的 `requirements.txt` | 用哪個環境 | 誰建的 |
|---|---|---|
| 有第三方套件 | `tools\<tool-name>\.venv`（專屬，互不干擾） | `setup-venv.ps1 <tool-name>` |
| 只用標準庫 | 根目錄 `.venv`（共用，只裝 build 工具鏈） | `setup-venv.ps1 <tool-name>` |

- 每個 venv 都裝 `requirements-dev.txt`（PyInstaller 等，版本全 repo 一致）＋該工具自己的 `requirements.txt`。
- `build.ps1` 每次 build 前會檢查：venv 裡裝的版本**符合** requirements 才放行；
  有第三方套件的工具如果沒有自己的 `.venv`，**不會**默默退回共用環境（那樣會產出一個缺套件、一開就崩潰的 exe）。
- 環境跟 requirements 不一致時，build 會告訴你跑 `.\scripts\setup-venv.ps1 <tool-name> -Force` 整個重建。
- `.venv` 都在 `.gitignore` 裡，隨時可以砍掉重建，不要手動往裡面 `pip install` 東西。

### 版本範圍要給主版本上限

`requirements.txt` 請寫 `套件>=最低版本,<下一個主版本`，不要只寫 `>=`。
只寫 `>=` 的話，新機器（或重建 venv）會裝到開發時根本還不存在的新主版本。這個 repo 就實際踩過兩次：

| 工具 | 只寫 `>=` 時裝到 | 結果 | 現在 |
|---|---|---|---|
| Encrypter | ttkbootstrap 2.2.2 | 2.x 改從檔案載入字型，打包後一啟動就 `FileNotFoundError` | `ttkbootstrap>=1.10.1,<2` |
| Advanced Excel Tool | pandas 3.0.6 | 「合併濃縮」遇到空格就 `TypeError`（pandas 3 改了 `astype(str)`） | `pandas>=2.0,<3` |

要升主版本：改上限 → `setup-venv.ps1 <tool> -Force` → 實際把功能跑過一輪 → `build.ps1 <tool> -Smoke`。

## 發布流程（release）

```powershell
# 1. 改版本號（tool.json 的 version_from 指到的檔案，例如 src\version.py），commit
# 2. 清掉這個工具的快取，從頭 build + 冒煙測試
.\scripts\build.ps1 <tool-name> -Clean -Smoke
# 3. 產物：dist\<tool-name>\<Name>(v<版本>).exe → 上傳 / 發給別人
# 4. 打 tag，例如  git tag HashMyFile_v0.1.1
```

平常 build 會用 PyInstaller 的增量快取（輸入沒變就不重寫 exe）；`-Clean` 會先清掉
`build\<tool-name>\` 和 `dist\<tool-name>\`，確保 release 用的 exe 是從頭 build 的。
不帶工具名稱的 `.\scripts\build.ps1 -Clean` 則清掉整個 `build\` 和 `dist\`。

## 開一個新工具

```powershell
.\scripts\new-tool.ps1 my-new-tool
```

會從 `tools/_template/` 複製一份乾淨骨架出來（tkinter 視窗 + `resource_path()` + `version.py` + `tool.json`），然後：

1. 寫 `tools/my-new-tool/main.py`，版本號在 `version.py`
2. 需要第三方套件就寫進 `tools/my-new-tool/requirements.txt`（記得給主版本上限）
3. `.\scripts\setup-venv.ps1 my-new-tool`
4. 有資料檔（圖片、語言檔、設定檔…）就填 `tool.json` 的 `include`
5. `.\scripts\build.ps1 my-new-tool -Smoke`
6. 回來這份 README 的表格加一列

## 目錄結構

```
PersonalToolZoo/
├─ README.md               ← 你正在看的導覽頁
├─ requirements-dev.txt    ← 共用 build 工具鏈（pyinstaller 等），所有 venv 都裝
├─ .venv/                  ← 共用虛擬環境（只給只用標準庫的工具）
├─ scripts/
│  ├─ tool.spec            ← 全 repo 唯一一份 PyInstaller spec
│  ├─ build.ps1            ← 統一 builder（含依賴檢查、-Smoke 冒煙測試）
│  ├─ setup-venv.ps1       ← 依 requirements 建立／重建工具的 venv
│  ├─ new-tool.ps1         ← 產生新工具骨架
│  ├─ _common.ps1          ← 上面幾支共用的 helper（環境規則定義在這）
│  └─ check_deps.py        ← 檢查 venv 裡的版本符合 requirements
├─ tools/
│  ├─ _template/           ← 新工具的空白範本
│  └─ <tool-name>/         ← 每個工具一個資料夾，自成一個乾淨單位
│     ├─ tool.json         ← 這個工具的 build 設定
│     ├─ README.md
│     ├─ requirements.txt  ← 執行時依賴（不放 pyinstaller）
│     ├─ .venv/            ← （有第三方依賴才有）這個工具專屬的隔離環境
│     └─ main.py, ...
└─ dist/<tool-name>/       ← 打包產物
```

## build 是怎麼運作的

全 repo 只有 `scripts/tool.spec` 一份 spec，各工具的差異寫在自己的 `tool.json`：

```json
{
  "name": "MyTool",
  "entry": "main.py",
  "console": false,
  "version_from": "version.py",
  "include": ["assets", "config.json"],
  "collect_all": ["some_package_with_data_files"]
}
```

產物檔名是 `<name>(v<版本>).exe`（沒有 `version_from` 就是 `<name>.exe`），一律 onefile。
`console: false` 的工具如果啟動時丟出例外，PyInstaller 會跳出「Unhandled exception in script」
視窗顯示完整 traceback，`-Smoke` 就是靠偵測這個視窗判斷 exe 壞掉。

`build.ps1` 會把工具資料夾的絕對路徑透過環境變數 `TOOLZOO_TOOL_DIR` 交給 spec，
spec 裡所有路徑都以它為基準解析，**完全不依賴當下的工作目錄**。
所以工具放在子資料夾裡也能正常打包，在哪裡執行 `build.ps1` 結果都一樣。

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
  所以 `setup-venv.ps1` 呼叫 pip 時會開 `PYTHONUTF8=1`。**手動** `pip install -r` 前也要先 `$env:PYTHONUTF8 = 1`。
- `scripts\*.ps1` 必須存成 **UTF-8 with BOM**，Windows PowerShell 5.1 才不會把中文讀成亂碼。

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

要把上面任何一段補進來，就照同一套四步流程再跑一輪。
