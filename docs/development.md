# 開發者指南

---

## 📦 檔案結構

```
GitHelper/
├── GUI__GitHelperPro.py          # 主程式（UI 整合、對話框邏輯）
├── requirements.txt
├── README.md
├── builder.bat                   # 打包腳本
├── language_config.json          # 語言偏好設定
├── language/
│   ├── zh-tw.json                # 繁體中文（預設）
│   ├── zh-cn.json                # 簡體中文
│   ├── en.json                   # English
│   └── _template.json            # 語言範本（供社群翻譯用）
├── src/
│   ├── core/
│   │   ├── language_manager.py   # 多語言管理器
│   │   └── git_handler/
│   │       ├── commands.py       # 所有指令的參數配置
│   │       └── executor.py       # Git 指令執行器
│   └── gui/
│       ├── command_panel.py      # 左側按鈕面板（配置驅動）
│       ├── dialogs.py            # 通用參數對話框（含自動補全）
│       └── danger_operation_blocker.py  # 危險操作確認管理
└── data/                         # 工作目錄（輸出 / 暫存）
```

---

## 🔧 技術細節

### 滑鼠滾輪支援

左側指令區支援滑鼠滾輪捲動，遞迴綁定所有子元件，確保滑鼠在任何位置都能捲動。

### UTF-8 編碼處理

所有 `subprocess.run` 都加入 encoding 處理，避免中文路徑或檔名造成閃退：

```python
subprocess.run(cmd, encoding='utf-8', errors='replace')
```

### 自訂流程處理器（Stash Commit）

```python
def handle_stash_commit(self, params, repo_path):
    self.execute_git_command("git stash", repo_path)
    self.execute_git_command("git stash pop", repo_path)
    self.execute_git_command("git add .", repo_path)
    self.execute_git_command(f'git commit -m "{message}"', repo_path)
```

### 動態 UI 生成

左側按鈕面板採用配置驅動佈局（`commands.py` 定義參數格式），易於擴充新指令，無需修改 UI 程式碼。

---

## 🐛 已知問題修正記錄

| 問題 | 修正方式 |
|------|---------|
| 滑鼠滾輪無法捲動左側指令區 | 遞迴綁定所有子元件的滾輪事件 |
| 中文路徑或檔名造成閃退 | 所有 subprocess 加入 `encoding='utf-8', errors='replace'` |
| 參數對話框未驗證必填項 | 加入紅框警告和阻止執行機制 |
| Adog 視覺化缺少水平捲軸 | 加入水平 Scrollbar |
| Cherry-pick 按鈕寬度不一致 | 統一寬度配置 |
