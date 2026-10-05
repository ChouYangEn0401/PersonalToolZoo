# Better File Finder

> 比檔案總管好用的檔案搜尋：多個關鍵字、排除、模糊比對、副檔名篩選，也能搜尋文字檔的內容。

## 功能

| 你輸入 | 意思 |
|---|---|
| `報告 2024` | 兩個詞都要出現在檔名裡（不分大小寫、不分順序） |
| `"季度 報告"` | 整段文字要原樣出現 |
| `-草稿` | 檔名有「草稿」的不要 |
| 副檔名欄 `txt, md` 或 `*.py` | 只看這些副檔名；關鍵字可以空白（只用副檔名找） |

- **模糊比對**：詞不用完全出現，相似就算（打錯字也找得到）。
- **搜尋檔案內容**：文字檔（20 MB 以下，自動判斷 UTF-8 / Big5 / UTF-16）的內容也搜尋，並顯示第一個符合的那一行。
- **也找資料夾**：資料夾名稱也比對。
- 背景搜尋不會卡住視窗，結果邊找邊出現；搜尋中按「停止」可以中斷。
- 結果可以按欄位排序；雙擊開啟檔案，「在檔案總管中顯示」會選取該檔案。
- 自動略過 `.git`、`node_modules`、`__pycache__`、`.venv` 等資料夾。

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
.\scripts\setup-venv.ps1 better-file-finder        # 只用標準庫 → 共用根目錄的 .venv
.\.venv\Scripts\python.exe tools\better-file-finder\main.py
.\scripts\build.ps1 better-file-finder
```

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `main.py` |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `BetterFileFinder(vX.Y.Z).exe`、視窗標題 `Better File Finder vX.Y.Z` |
| 環境 | 只用標準庫 → 根目錄共用 `.venv` |
| 依賴 | 無 |
| 打包額外內容 | 無 |
| 測試 | `py -3.11 -m unittest discover -s tools\better-file-finder\tests -v`（7 個） |
| Release tag | `BetterFileFinder_vX.Y.Z` |

### 注意事項

- 舊版（`Python Projects\。Better File Finder`）的問題都在這版修掉了，測試裡有對應的回歸測試：
  `-排除` 的判斷寫反、`+` 條件在排除前就加入結果、模糊比對門檻 `> 0` 幾乎什麼都會中、
  「匹配文件內容」勾了沒作用、大資料夾會卡住視窗、結尾的 `input()` 讓沒有主控台的 exe 關閉時崩潰。
- 搜尋在背景執行緒跑，結果透過 queue 交給主執行緒更新畫面（Tk 只能在主執行緒操作）。
