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
.\scripts\build.ps1 __TOOL_NAME__ -Smoke
```

產物會出現在 `dist\__TOOL_NAME__\`。

## 開發筆記

- ...
