# __TOOL_NAME__

> 一句話說明這個工具解決什麼問題。

## 功能

- ...

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
# 建環境（有第三方套件 → tools\__TOOL_NAME__\.venv；只用標準庫 → 根目錄共用 .venv）
.\scripts\setup-venv.ps1 __TOOL_NAME__

# 直接跑（有專屬 venv 的話把 .\.venv 換成 .\tools\__TOOL_NAME__\.venv）
.\.venv\Scripts\python.exe tools\__TOOL_NAME__\main.py

# 打包成 exe，並實際開起來檢查有沒有崩潰
.\scripts\build.ps1 __TOOL_NAME__
```

產物會出現在 `dist\__TOOL_NAME__\`。

## 開發筆記

- ...

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `main.py` |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `__TOOL_NAME__(vX.Y.Z).exe`、視窗標題 `__TOOL_NAME__ vX.Y.Z` |
| 環境 | （只用標準庫 → 根目錄共用 `.venv`／有第三方套件 → `tools\__TOOL_NAME__\.venv`） |
| 依賴 | （列出 requirements.txt 裡的套件，以及為什麼有版本上限） |
| 打包額外內容 | （tool.json 的 include / collect_all，沒有就寫「無」） |
| 測試 | （怎麼跑；沒有就寫「無」） |
| Release tag | `__TOOL_NAME___vX.Y.Z`（tool.json 的 tag_prefix） |

### 注意事項

- （接手的人一定要知道的事：已知問題、不能升級的套件、還沒收進來的分支…）
