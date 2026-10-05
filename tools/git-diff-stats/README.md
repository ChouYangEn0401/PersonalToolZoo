# diff_showcaser

簡單的 Git diff 統計 GUI 工具。

用法：

只用標準庫，用 PersonalToolZoo 根目錄共用的 `.venv` 即可。在 repo 根目錄執行：

```powershell
.\.venv\Scripts\python.exe tools\git-diff-stats\GUI_GitDiffStatistics.py

# 打包成 exe → dist\git-diff-stats\
.\scripts\build.ps1 git-diff-stats
```

啟動後在視窗裡選要分析的 git repo。

輸入 `init_commit` 與 `latest_commit`（可以是 branch 名稱或 commit hash），按 `Compute`。

顯示：
- 每種副檔名的檔案數、加上/刪除行數、淨行數、近似位元組差異（若可得）與範例檔案。
- 上方會顯示總共變更的檔案數與總加/刪行數。

備註：本工具使用 `git diff --numstat` 與 `git ls-tree -r -l` 來計算，對大型倉庫可能需些時間。

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `GUI_GitDiffStatistics.py`（統計邏輯在 `git_utils.py`） |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `GUI_GitDiffStatistics(vX.Y.Z).exe`、視窗標題 `... — vX.Y.Z` |
| 環境 | 只用標準庫 → 根目錄共用 `.venv` |
| 依賴 | 執行時需要電腦上有 `git`（在 PATH 上） |
| 打包額外內容 | 無；console 版（`console: true`） |
| 測試 | 無自動化測試 |
| Release tag | `GitDiffStatistics_vX.Y.Z` |

常用指令（repo 根目錄）：

```powershell
.\scripts\build.ps1 diff                # build + 冒煙測試
.\scripts\release.ps1 diff patch        # 發新版
```

### 注意事項

- `__init__.py`、`__main__.py` 是早期以 `diff_showcaser` 套件形式執行時留下的；
  資料夾名稱有連字號，`python -m` 這條路已經不能用，請直接跑 `GUI_GitDiffStatistics.py`。
- **分支上還有未收的功能**：`feat/git_diff_shower` 在收進來的點（`0aba850`）之後還有 3 個 commit
  （副檔名篩選分類、no-git snapshot 分頁、snapshot 修正），還沒收尾所以沒併。詳見根目錄 README「歷史」。
