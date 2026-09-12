# PersonalToolZoo

個人小工具集散地。一個 repo、一條 branch，每個工具住在 `tools/` 底下自己的資料夾裡，
共用同一套 build 流程。

## 工具一覽

| 工具 | 說明 | 版本 | 原始碼 |
|---|---|---|---|
| **Git Helper Pro** | Git 指令 GUI 助手：多專案分頁、危險指令攔截、rebase/merge/stash 引導、繁中／簡中／英三語切換 | v1.6.4 | [tools/git-helper-pro/](tools/git-helper-pro/) |
| **Encrypter** | 檔案／文字加密 GUI，自訂 `.isd` 格式，支援多種演算法與 Mixture（多階段）加密模式 | v0.3.0 | [tools/encrypter/](tools/encrypter/) |
| **Table Format Converter** | 貼上 Tab 分隔或 Markdown 表格即時預覽，一鍵輸出 MD／Tab／CSV／XLSX | v1.0.0 | [tools/table-format-converter/](tools/table-format-converter/) |

## 快速開始

```powershell
# 1. 建立共用環境（只要做一次）
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 2. 看有哪些工具
.\scripts\build.ps1 -List

# 3. 打包某一個工具
.\scripts\build.ps1 <tool-name>        # 產物在 dist\<tool-name>\

# 4. 全部打包
.\scripts\build.ps1 -All
```

某個工具需要額外的第三方套件，不要裝進共用的根目錄 `.venv`——
給它自己開一個乾淨的 venv，`build.ps1` 會自動優先找 `tools\<tool-name>\.venv`：

```powershell
py -3.11 -m venv tools\<tool-name>\.venv
.\tools\<tool-name>\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r tools\<tool-name>\requirements.txt
.\scripts\build.ps1 <tool-name>
```

這樣每個工具的依賴版本互不干擾，某個工具需要 pandas 1.x、另一個需要 2.x
也不會打架。只用標準庫、沒有額外依賴的工具（例如 Git Helper Pro）才共用根目錄的
`.venv` 就好，不用每個都開一份。

## 開一個新工具

```powershell
.\scripts\new-tool.ps1 my-new-tool
```

會從 `tools/_template/` 複製一份乾淨骨架出來，然後：

1. 寫 `tools/my-new-tool/main.py`
2. 有資料檔（圖片、語言檔、設定檔…）就填 `tool.json` 的 `include`
3. `.\scripts\build.ps1 my-new-tool`
4. 回來這份 README 的表格加一列

## 目錄結構

```
PersonalToolZoo/
├─ README.md               ← 你正在看的導覽頁
├─ requirements-dev.txt    ← 共用 build 工具鏈（pyinstaller 等）
├─ .venv/                  ← 共用虛擬環境（只給無額外依賴的工具用）
├─ scripts/
│  ├─ tool.spec            ← 全 repo 唯一一份 PyInstaller spec
│  ├─ build.ps1            ← 統一 builder
│  └─ new-tool.ps1         ← 產生新工具骨架
├─ tools/
│  ├─ _template/           ← 新工具的空白範本
│  └─ <tool-name>/         ← 每個工具一個資料夾，自成一個乾淨單位
│     ├─ tool.json         ← 這個工具的 build 設定
│     ├─ README.md
│     ├─ requirements.txt  ← 執行時依賴
│     ├─ .venv/            ← （選用）這個工具專屬的隔離環境
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
  "include": ["assets", "config.json"]
}
```

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

## 歷史

早期每個工具各自開一條 branch、都待在 repo 根目錄開發，
原因是 build 腳本裡的路徑寫死成相對於工作目錄（`os.path.abspath('.')`），
工具一搬進子資料夾就找不到檔案。

`tool.json` + 共用 spec 的做法解掉了這個限制，所有工具已整併回 `master`。
各工具原本的 branch 保留作為封存，開發歷史完整保存在 commit 紀錄裡。
