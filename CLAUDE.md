@AGENTS.md

## Claude Code 補充

- 使用者以繁體中文溝通，回覆用繁體中文。
- 寫含 Windows 路徑（反斜線）的檔案時用 Edit／Write 工具，不要用 Bash heredoc 或 `python -c` 字串拼接：
  反斜線會被吃掉（`\b` 變退格字元、行尾 `\` 吃掉換行），這個 repo 已經發生過。
- 用 PowerShell 工具跑 repo 的腳本時，透過
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ...` 呼叫，確保是使用者實際用的 Windows PowerShell 5.1。
- 冒煙測試會在使用者桌面跳出視窗，開始前先跟使用者說一聲。
- 專案技能在 `.claude/skills/`：`/merge-branch-tool`（把封存分支的工具收進來）、`/release-tool`（發布一個工具）。
