# diff_showcaser

簡單的 Git diff 統計 GUI 工具。

用法：

- 在專案根目錄下執行（必須是 git 倉庫）

```
python -m diff_showcaser
```

輸入 `init_commit` 與 `latest_commit`（可以是 branch 名稱或 commit hash），按 `Compute`。

顯示：
- 每種副檔名的檔案數、加上/刪除行數、淨行數、近似位元組差異（若可得）與範例檔案。
- 上方會顯示總共變更的檔案數與總加/刪行數。

備註：本工具使用 `git diff --numstat` 與 `git ls-tree -r -l` 來計算，對大型倉庫可能需些時間。
