# Git Helper Pro

> 為進階開發者與 Project Lead 設計的 Git 圖形化管理工具  
> 讓複雜的 Git 操作變得簡單、直觀、不出錯

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

![GUI Preview](docs/GUI_Image.png)

---

## 為什麼需要這個工具？

SourceTree / GitKraken 適合基本操作（commit、push、pull）。  
**Git Helper Pro** 專注於進階操作，並提供參數驗證與安全機制，避免下錯指令造成災難。

---

## 🚀 快速開始

**需求**：Python 3.8+，Git（任意版本）

```bash
python GUI__GitHelperPro.py
```

1. 點擊「**+ 開啟新專案分頁**」
2. 選擇含有 `.git` 的資料夾
3. 開始使用

---

## ✨ 功能總覽

| 群組 | 功能 |
|------|------|
| ⚡ 快速執行 | 任意 Git 指令輸入框，Enter 即執行 |
| 🧩 Rebase 流程控制 | 互動模式、HEAD~N 快捷、指定位置、--onto 對話框（含黃色自動補全）、Continue / Abort / Skip |
| 🔗 Merge 合併 | 四模式合併對話框（含黃色自動補全）、Continue / Abort |
| 🍒 Cherry-pick | 批量 hash、-n 模式、Continue / Abort |
| ⏪ Reset 回退 | Soft HEAD~1/2、Soft/Hard 自訂範圍，Hard Reset 有獨立危險確認彈窗 |
| 📝 提交與暫存 | Fixup / Squash / FastCommit、Add 選檔器、Commit -m、Amend |
| 🌐 Fetch / Pull | 一鍵 Fetch --all --prune、一鍵 Pull |
| ✈️ 遠端推送 | Push、Force Push（獨立危險確認彈窗）、Push Tags、🚀 Push Panel（批次 Push + 個別 Force） |
| 📦 Stash 緩衝區 | Save / Pop / List / Drop / Clear |
| 🌿 Branch 分支管理 | List、Checkout 搜尋器、Create、✏️ Rename（含遠端同步）、🗑️ Delete（獨立危險確認彈窗）、Prune、🗑️ Delete Panel |
| 🏷️ Tag 標籤管理 | List / Create / ✏️ Move Tag（重建到同 Commit）/ Delete |
| 🗑️ Delete Panel | 四分類（本地分支、遠端分支、本地 Tag、遠端 Tag）批次刪除，含搜尋自動補全 |
| 🔍 狀態與工具 | Status、Diff、Clean -fd、Checkouts（分支切換 + Checkout File 兩頁） |

---

## 🟡 黃色自動補全（Yellow Autocomplete）

在 **Merge 來源分支**、**Rebase --onto 三欄位**、**Delete Panel 搜尋** 等欄位中，  
輸入關鍵字時會自動彈出黃色候選清單：

| 按鍵 | 動作 |
|------|------|
| `Tab` | 清單向下選（循環） |
| `Shift+Tab` | 清單向上選（循環） |
| `Space` / `Enter` | 確認選中項目填入欄位 |
| 滑鼠單擊 | 直接確認 |
| `Escape` / 失焦 | 關閉清單 |

---

## 🔒 危險操作確認系統

每種危險操作都有**獨立的確認彈窗**，互不影響跳過計時器：

| 操作類型 | 說明 |
|----------|------|
| ⚠️ Rebase | 提示重寫歷史風險 |
| ⚠️ Hard Reset | 提示永久丟失變更 |
| ⚠️ Delete Branch | 提示分支難以找回 |
| ⚠️ Force Push | 提示覆蓋遠端歷史 |

確認後可選擇跳過時間：**1 分鐘 / 5 分鐘 / 15 分鐘 / 30 分鐘**（下拉選單）

---

## 📑 分頁管理

- **右鍵點擊分頁** → 彈出選單：關閉分頁 / ← 向左移 / → 向右移  
- **Ctrl+W** → 關閉目前分頁

---

## 🚀 Push Panel

批次推送多個分支與 Tag：

- 列出所有本地分支與 Tag，各自帶勾選框
- 每項目都有獨立 **Force** 勾選（使用 `--force-with-lease`）
- 指定遠端名稱（預設 `origin`）
- 支援全選 / 清除 / 刷新

---

## 🗑️ Delete Panel

四個分頁批次刪除：

- **🌿 Local Branch** — 搜尋 + 加入待刪清單 → 一鍵刪除
- **☁️ Remote Branch** — 同上，執行 `git push <remote> --delete`
- **🏷️ Local Tag** — 搜尋 + 加入待刪清單 → `git tag -d`
- **☁️🏷️ Remote Tag** — 同上，執行 `git push <remote> --delete`

所有搜尋欄均配備黃色自動補全 popup。

---

## 🌐 多語言

| 語言 | 代碼 |
|------|------|
| 繁體中文 | `zh-tw` |
| 简体中文 | `zh-cn` |
| English | `en` |

語言資料統一儲存在 **`language/translations.csv`**（單一檔案，Excel 易於維護）。  
CSV 欄位：`key, zh-tw, zh-cn, en`，每行一個翻譯 key。

---

## 📖 常見使用情境

**整理最近幾個 commit**
```
1. 點擊「HEAD~10」或「互動模式」
2. 在 Git 編輯器中調整：pick → squash / reword / edit
3. 儲存關閉
4. 若有衝突 → 解決後點「▶️ Continue」
```

**將 feature 合回 main（保留歷史）**
```
1. Checkout 到 main
2. 點擊「🔗 Merge 分支」→ 輸入來源分支（黃色補全幫你搜尋）→ 模式選「--no-ff」→ 執行
```

**Checkout 到某個舊 commit**
```
1. 點擊「📂 Checkouts」
2. 在搜尋框輸入部分 hash 或關鍵字 → 從清單點選 → 執行
```

**安全 Force Push**
```
1. 點擊「💥 Force Push」
2. 勾選「安全強推 (--force-with-lease)」→ 執行（需通過 Force Push 危險確認）
```

**批次清理多個分支 / Tag**
```
1. 點擊「🗑️ Delete Panel」
2. 選擇對應分頁（Local Branch / Remote Branch / Local Tag / Remote Tag）
3. 搜尋 → 加入待刪清單（支援黃色自動補全）
4. 執行刪除
```

**重命名分支**
```
1. 點擊「✏️ Rename」（Branch 群組）
2. 填入原名與新名
3. 可選：勾選「同步更新遠端」一次完成 push 新 + delete 舊
```

**移動 / 重命名 Tag**
```
1. 點擊「✏️ Move Tag」（Tag 群組）
2. 填入原 Tag 名與新名（保留相同 commit）
3. 可選：勾選「同步更新遠端」
```

---

## 🔒 安全機制

1. **必填驗證** — 未填寫時阻止執行
2. **危險操作獨立彈窗** — Rebase / Hard Reset / Delete Branch / Force Push 各自獨立，可分別設定跳過時間
3. **即時回饋** — Terminal 區域顯示完整指令與輸出
4. **Reflog 保護** — 隨時查看操作歷史，方便 `reset` 復原
5. **UTF-8 編碼** — 正確處理中文路徑與檔名，不閃退

---

## 適用對象

✅ 需要頻繁 rebase 整理提交歷史  
✅ 管理多個功能分支與實驗性分支  
✅ 需要安全的 merge 策略選擇  
✅ 批次推送或刪除多個分支 / Tag  
✅ 快速在分支 / tag / commit 間切換  
✅ 團隊協作中需要清理過期分支  

❌ Git 初學者（建議先熟悉基本指令）  
❌ 只需要簡單 commit/push/pull  

---

## 📚 文件目錄

| 文件 | 說明 |
|------|------|
| [功能詳細說明](docs/features.md) | 每個功能的對話框介面、參數說明與操作細節 |
| [指令對照表](docs/commands-reference.md) | 所有 UI 按鈕對應的 Git 指令 |
| [多語言支援](docs/multilang.md) | 語言切換、自訂語言、CSV 格式說明 |
| [開發者指南](docs/development.md) | 檔案結構、技術細節、已知問題記錄 |

---

## 📄 License

MIT License — Made with ❤️ for Git Power Users & Project Leads
