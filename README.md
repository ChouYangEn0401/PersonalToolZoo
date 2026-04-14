# Git Helper Pro

> 為進階開發者與 Project Lead 設計的 Git 圖形化管理工具  
> 讓複雜的 Git 操作變得簡單、直觀、不出錯

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 📋 專案簡介

**Git Helper Pro** 是一個專為進階 Git 使用者打造的 Tkinter 圖形化管理工具。

### 為什麼需要這個工具？

- ✅ **SourceTree / GitKraken** 適合基本操作（commit、push、pull）
- ✅ **Git Helper Pro** 專注於進階操作（rebase -i、merge、cherry-pick、force push、分支清理）
- ✅ 提供**參數驗證**和**安全機制**，避免下錯指令造成災難

### 核心特色

🎯 **快速互動 Rebase**：一鍵執行 `rebase -i HEAD~2/4/10`  
🔀 **Merge 對話框**：四種合併模式可選，即時指令預覽  
🔁 **Checkout 搜尋器**：跨 branch / remote / tag / commit 全域搜尋，一鍵切換  
⚡ **智能參數對話框**：必填驗證、紅框提示、自動補全  
🛡️ **安全推送**：支援 `--force-with-lease` 避免覆蓋他人提交  
🧹 **分支 / 標籤清理**：批量刪除、自動修剪、dry-run 預覽  
📊 **即時視覺化**：Git Graph + Reflog 每次操作後自動刷新  
🔧 **快速指令列**：內建終端，支援任意 Git 指令

---

## ✨ 功能總覽

### 左側按鈕區（可捲動）

| 群組 | 功能 |
|------|------|
| ⚡ 快速執行 | 任意 Git 指令輸入框，Enter 即執行 |
| 🛠️ 快速互動 Rebase | HEAD~2 / HEAD~4 / HEAD~10 一鍵執行 |
| 🔄 Rebase 流程控制 | 互動模式、指定位置、--onto 對話框、Continue / Abort / Skip |
| 🔀 Merge 合併 | 四模式合併對話框、Continue / Abort |
| 🍒 Cherry-pick | 批量 hash、-n 模式、Continue / Abort |
| ⏪ Reset 回退 | Soft HEAD~1/2、Soft/Hard 自訂範圍 |
| 📝 提交與暫存 | Fixup / Squash / FastCommit、Add 選檔器、Commit -m、Amend |
| ✈️ 遠端推送 | Push、Force Push（含 --force-with-lease）、Push Tags |
| 📦 Stash 緩衝區 | Save / Pop / List / Drop / Clear |
| 🌿 Branch 分支管理 | List、Checkout 搜尋器、Create、Del Local / Remote、Prune |
| 🏷️ Tag 標籤管理 | List / Create / Del Local / Del Remote |
| 🔍 狀態與工具 | Status、Diff、Clean -fd、Checkout File |

---

## 🔀 Merge 合併

### 對話框功能

點擊「🔀 Merge 分支」開啟互動對話框：

| 模式 | 指令 | 說明 |
|------|------|------|
| 一般 (預設) | `git merge <branch>` | Git 自行決定：能 fast-forward 就接上，否則建立 merge commit |
| `--no-ff` | `git merge --no-ff <branch>` | **強制**建立 merge commit，保留分支歷史脈絡，推薦 feature → main |
| `--squash` | `git merge --squash <branch>` | 把所有 commit 壓成一筆變更放入暫存區，需手動 commit |
| `--ff-only` | `git merge --ff-only <branch>` | 只允許 fast-forward，無法時直接失敗，適合嚴格線性歷史 |

- 來源分支下拉選單：本地分支、remote 分支、近期 commit hash
- 即時指令預覽
- 對話框內也提供 **Continue** / **Abort** 衝突控制按鈕

---

## 🔁 Checkout 搜尋器

點擊 Branch 群組的「🔁 Checkout」開啟搜尋式切換器：

- 即時搜尋：**本地 branch**、**origin/branch**、**tag**、**commit hash**（最近 60 筆）
- 輸入框邊打字，下方清單即時過濾，點選即填入
- 支援「**建立新分支 (-b)**」勾選
- 即時預覽最終指令

```bash
# 點選後執行的指令範例
git checkout feature/my-work
git checkout origin/feature/remote
git checkout v1.2.0
git checkout a1b2c3d
git checkout -b new-branch
```

---

## 🛠️ Rebase

### 快速互動 Rebase（一鍵）

```bash
HEAD~2    # 整理最近 2 個 commit
HEAD~4    # 整理最近 4 個 commit
HEAD~10   # 整理最近 10 個 commit
```

### Rebase 流程控制

| 按鈕 | 功能 |
|------|------|
| **互動模式** | 自訂 HEAD~N 或 hash 執行 `rebase -i` |
| **指定位置** | 將當前分支 rebase 到指定目標分支 |
| **🔀 OnTo** | `git rebase --onto`，見下方說明 |
| **Continue / Abort / Skip** | 衝突解決流程控制 |

### Rebase --onto 對話框

```
git rebase --onto <newbase> <upstream> [<branch>]
```

| 欄位 | 說明 | 範例 |
|------|------|------|
| **New Base** | commit 要搬到哪裡的上面（目標基底） | `main`、`dev`、commit hash |
| **Upstream** | 搬移起點（不含此點）：此點之後才會被搬移 | `HEAD~3`、commit hash |
| **Branch** | 要操作的分支（留空 = 當前分支 HEAD） | `feature/my-branch` |

**範例**：把 feature 最後 3 個 commit 搬到 main → `newbase=main`，`upstream=HEAD~3`

各欄位皆提供下拉選單，底部有即時指令預覽。

---

## 🍒 Cherry-pick

```bash
# 單個
abc123
# 多個（空格分隔）
abc123 def456 789ghi
```

- 可選 `-n`（不自動提交，讓你先確認）
- Continue / Abort 衝突控制

---

## ⏪ Reset 回退

| 按鈕 | 指令 | 說明 |
|------|------|------|
| Soft HEAD~1 | `reset --soft HEAD~1` | 撤銷最近一次 commit，保留變更 |
| Soft HEAD~2 | `reset --soft HEAD~2` | 撤銷最近兩次 commit，保留變更 |
| 🧨 Soft (保留變更) | `reset --soft <N>` | 自訂範圍，保留修改 |
| ⚠️ Hard (捨棄變更) | `reset --hard <N>` | 捨棄所有修改，**危險** |

---

## 📝 提交與暫存

### 快速 Commit

| 按鈕 | 訊息 | 適合場景 |
|------|------|---------|
| 🔧 Fixup (f) | `"fixup"` | 稍後用 rebase -i 壓進上一個 commit |
| 📦 Squash (s) | `"squash"` | 稍後用 rebase -i 合併並修改訊息 |
| ⚡ FastCommit (stash) | `"stash"` | 快速存檔，語義上的臨時 commit |

三個按鈕均會先確認暫存區是否有檔案，若無則提示警告。

### Add 選擇檔案

精確選擇要 Add / Commit / Stash 的檔案：

- 顯示每個檔案的暫存狀態（✅ 已暫存 / ✏️ 修改中 / 🆕 未追蹤 / ⚠️ 部分暫存）
- 選中後可：**Add only**、**Add + Commit（一次完成）**、**Stash 選中**

---

## ✈️ 遠端推送

```bash
⬆️ Push              # 正常推送
🛰️ Push Tags         # 推送所有 tag
⚡ Force Push        # 強制推送
```

**Force Push 選項**：

- `-f`：標準強推（危險）
- `--force-with-lease`：**安全強推**（建議）— 只在遠端未被他人更新時推送

---

## 📦 Stash 緩衝區

```bash
📥 Save     →  git stash
📤 Pop      →  git stash pop
📜 List     →  git stash list
🗑️ Drop     →  git stash drop
🧹 Clear    →  git stash clear  (危險，需確認)
```

---

## 🌿 Branch 分支管理

| 功能 | 說明 |
|------|------|
| 📋 List | `git branch -a`（含遠端） |
| 🔁 Checkout | 搜尋式切換器（見上方說明） |
| 📌 Create | 建立並切換到新分支 (`-b`) |
| ✂️ Del Local | 刪除本地分支（支援批量，`-D` 強制） |
| 🌐 Del Remote | 刪除遠端分支 |
| 🧹 Prune | 清理過期遠端追蹤，支援 `--dry-run` 預覽 |

---

## 🏷️ Tag 標籤管理

| 功能 | 說明 |
|------|------|
| 📜 List Tags | `git tag -l` |
| 📌 Create Tag | 建立 annotated tag，可選訊息、指定 commit |
| 🔥 Delete Local | 批量刪除本地 tag |
| ☁️ Delete Remote | 刪除遠端 tag |

---

## 🔍 狀態與工具

- **Status** — `git status`
- **Diff** — `git diff`
- **Clean -fd** — 清理未追蹤檔案（需確認）
- **Checkout File** — 從指定 commit / branch 還原特定檔案

---

## ⚡ 快速指令列

左側頂部輸入框，直接輸入任意 git 子指令，Enter 執行：

```bash
# 自動補 "git " 前綴
log --oneline --graph -20
cherry-pick abc123 def456
branch -D feature/old
rebase -i HEAD~6
```

---

## 🚀 快速開始

### 需求

```bash
python --version   # 3.8+
git --version      # 任意版本
```

### 執行

```bash
# 下載後直接執行
python GUI__GitHelperPro.py
```

### 開啟專案

1. 點擊「**+ 開啟新專案分頁**」
2. 選擇含有 `.git` 的資料夾
3. 開始使用

---

## 📖 使用情境指南

### 情境 1：整理最近幾個 commit

```
1. 點擊「HEAD~10」或「互動模式」
2. 在 Git 編輯器中調整：
   pick → squash（合併）
   pick → reword（改訊息）
   pick → edit（停下來修改）
3. 儲存關閉編輯器
4. 若有衝突 → 解決後點「▶️ Continue」
```

### 情境 2：將 feature 合回 main（保留歷史）

```
1. Checkout 到 main
2. 點擊「🔀 Merge 分支」
3. 來源選擇 feature/your-branch
4. 模式選「--no-ff」（強制產生 merge commit）
5. 執行
```

### 情境 3：Checkout 到某個舊 commit

```
1. 點擊「🔁 Checkout」
2. 在搜尋框輸入部分 hash 或訊息關鍵字
3. 從清單點選目標
4. 執行
```

### 情境 4：安全 Force Push

```
1. 點擊「⚡ Force Push」
2. 確認遠端（預設 origin）
3. 勾選「安全強推 (--force-with-lease)」
4. 執行
```

### 情境 5：清理過期分支

```
1. 點擊「🧹 Prune」
2. 先勾選「僅預覽」確認範圍
3. 取消預覽，正式執行
```

---

## 🎨 介面配置

```
┌────────────────────────────────────────────────────────────────┐
│  [+ 開啟新專案分頁]                                             │
├──────────────┬─────────────────────────────────────────────────┤
│ ⚡ 快速執行   │  Git Adog 圖表:                                  │
│ 🛠️ 快速互動  │  * abc123 (HEAD -> main) Latest commit          │
│ 🔄 Rebase    │  * def456 feature/work                          │
│ 🔀 Merge     │  * 789abc Initial commit                        │
│ 🍒 Cherry-pk │  ────────────────────────────────────────────── │
│ ⏪ Reset     │  執行輸出:                                       │
│ 📝 提交      │  $ git merge --no-ff feature/work               │
│ ✈️ 推送      │  Merge made by the 'recursive' strategy.        │
│ 📦 Stash     │  ────────────────────────────────────────────── │
│ 🌿 Branch    │  [🔄 刷新]  [🕒 Reflog]                          │
│ 🏷️ Tag       │                                                 │
│ 🔍 工具      │                                                 │
└──────────────┴─────────────────────────────────────────────────┘
```

---

## 🔒 安全機制

1. **必填驗證** — 未填寫時紅框標記，阻止執行
2. **危險操作標示** — 紅色按鈕（Hard Reset、Force Push、Clean 等），需額外確認
3. **即時回饋** — Terminal 區域顯示完整指令與輸出
4. **Reflog 保護** — 隨時查看操作歷史，方便 `reset` 復原
5. **UTF-8 編碼** — 正確處理中文路徑與檔名，不閃退

---

## 📝 指令對照表

| 工具按鈕 | 實際 Git 指令 |
|---------|--------------|
| HEAD~2 | `git rebase -i HEAD~2` |
| 互動模式 | `git rebase -i <自訂範圍>` |
| Rebase --onto | `git rebase --onto <newbase> <upstream> [branch]` |
| 🔀 Merge 分支 (一般) | `git merge <branch>` |
| 🔀 Merge 分支 (--no-ff) | `git merge --no-ff <branch>` |
| 🔀 Merge 分支 (--squash) | `git merge --squash <branch>` |
| 🔀 Merge 分支 (--ff-only) | `git merge --ff-only <branch>` |
| 🔁 Checkout | `git checkout <branch/tag/hash>` |
| Cherry-pick Hash | `git cherry-pick <hash1> <hash2>...` |
| Soft HEAD~1 | `git reset --soft HEAD~1` |
| 🧨 Soft Reset | `git reset --soft <commit>` |
| ⚠️ Hard Reset | `git reset --hard <commit>` |
| 🔧 Fixup (f) | `git commit -m "fixup"` |
| 📦 Squash (s) | `git commit -m "squash"` |
| ➕ Add 選檔 | `git add <選中檔案>` |
| ✓ Add + Commit | `git add <files> && git commit -m "<msg>"` |
| Stash Save | `git stash` |
| Stash Pop | `git stash pop` |
| 📋 List (Branch) | `git branch -a` |
| 📌 Create (Branch) | `git checkout -b <branch>` |
| ✂️ Del Local | `git branch -D <branch...>` |
| 🌐 Del Remote | `git push origin --delete <branch>` |
| 🧹 Prune | `git fetch origin --prune && git remote prune origin` |
| 📌 Create Tag | `git tag <name> -m "<message>"` |
| 🔥 Delete Local (Tag) | `git tag -d <tag...>` |
| ☁️ Delete Remote (Tag) | `git push origin --delete <tag>` |
| ⬆️ Push | `git push` |
| ⚡ Force Push | `git push -f` 或 `git push --force-with-lease` |
| 🛰️ Push Tags | `git push --tags` |

---

## 📦 檔案結構

```
GitHelper/
├── GUI__GitHelperPro.py          # 主程式（UI 整合、對話框邏輯）
├── requirements.txt
├── README.md
├── builder.bat                   # 打包腳本
├── src/
│   ├── core/
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

## 🤝 適用場景

✅ 需要頻繁 **rebase** 整理提交歷史  
✅ 管理多個功能分支與實驗性分支  
✅ 需要安全的 **merge** 策略選擇  
✅ 經常需要 **cherry-pick** 特定 commit  
✅ 快速在分支 / tag / commit 間 **checkout**  
✅ 團隊協作中需要清理過期分支  

❌ Git 初學者（建議先熟悉基本指令）  
❌ 只需要簡單 commit/push/pull  

---

## 📄 授權

MIT License

---

**Made with ❤️ for Git Power Users & Project Leads**


---

## 📋 專案簡介

**Git Pro Organizer** 是一個專為進階 Git 使用者打造的圖形化管理工具。

### 為什麼需要這個工具？

- ✅ **SourceTree/GitKraken** 適合基本操作（commit, push, pull）
- ✅ **Git Pro Organizer** 專注於進階操作（rebase -i, cherry-pick, force push, 分支清理）
- ✅ 提供**參數驗證**和**安全機制**，避免下錯指令造成災難

### 核心特色

🎯 **快速互動 Rebase**：一鍵執行 `rebase -i HEAD~2/4/10`  
⚡ **智能參數對話框**：必填項驗證、紅框警告、防呆機制  
🛡️ **安全推送選項**：支援 `--force-with-lease` 避免覆蓋他人提交  
🧹 **分支/標籤清理**：批量刪除本地/遠端分支、自動修剪過期追蹤  
📊 **即時視覺化**：Git Graph + Reflog 即時更新  
🔧 **快速指令列**：內建終端，支援任意 Git 指令

---

## ✨ 核心功能

### 1. 快速互動 Rebase 🛠️

**一鍵執行常用的 rebase 範圍**，無需手動輸入：
```bash
# 三個快速按鈕
HEAD~2    # 整理最近 2 個 commit
HEAD~4    # 整理最近 4 個 commit
HEAD~10   # 整理最近 10 個 commit
```

**進階模式**（Rebase 流程控制區）：

| 按鈕 | 功能 |
|------|------|
| **互動模式** | 自訂 `HEAD~N` 或指定 commit hash 執行 `rebase -i` |
| **指定位置** | 將當前分支 rebase 到指定目標分支 |
| **🔀 OnTo** | `git rebase --onto`，三欄位可點選下拉填寫（見下方說明）|

- 完整的 `--continue` / `--abort` / `--skip` 流程控制

#### Rebase --onto 說明

```
git rebase --onto <newbase> <upstream> [<branch>]
```

| 欄位 | 說明 | 範例 |
|------|------|------|
| **New Base** | 目標基底，commit 搬移到此之上 | `main`、`dev`、commit hash |
| **Upstream** | 舊基底起點（不含此點） | `HEAD~3`、commit hash |
| **Branch** | 要搬移的分支（留空=當前分支） | `feature/my-branch` |

各欄位皆提供**下拉選單**，可直接點選現有分支或近期 commit，也可手動輸入。底部**即時預覽**顯示完整指令。

---

### 2. Cherry-pick 批量操作 🍒

```bash
# 支援一次 cherry-pick 多個 commit（空格分隔）
abc123 def456 789ghi
```

- 可選 `-n` 參數（不自動提交）
- 完整的 conflict resolution 流程

---

### 3. Reset & 回退 ⏪

| 操作 | 指令 | 說明 |
|------|------|------|
| **🔙 Undo Commit** | `reset --soft HEAD~1` | 撤銷最近一次 commit，保留變更 |
| **🧨 Soft Reset** | `reset --soft HEAD~N` | 自訂範圍，保留修改 |
| **⚠️ Hard Reset** | `reset --hard HEAD~N` | 捨棄所有修改（危險！） |

---

### 4. 提交與暫存 📝

| 按鈕 | 指令 | 說明 |
|------|------|------|
| **🔧 Fixup (f)** | `git commit -m "fixup"` | 快速提交暫存區，訊息為 `fixup`，稍後 rebase -i 整理 |
| **📦 Squash (s)** | `git commit -m "squash"` | 快速提交，訊息為 `squash` |
| **⚡ FastCommit (stash)** | `git commit -m "stash"` | 快速提交，訊息命名為 `stash`，語義上標記為臨時存放點 |

三個按鈕執行前均會檢查**暫存區是否為空**，若無已 staged 的文件則提示警告。

- **Amend 上則**：修改上次提交（可選 `--no-edit`）
- **Add 選擇檔案**：精確選擇要 Add/Commit/Stash 的檔案

---

### 5. Stash 緩衝區 📦

```bash
📥 Stash Save     # 暫存當前修改
📤 Stash Pop      # 恢復最近的 stash
📜 Stash List     # 查看所有 stash
🗑️ Stash Drop     # 刪除指定 stash
🧹 Stash Clear    # 清空所有 stash
```

---

### 6. Branch 分支管理 🌿

#### 本地操作
- **List All**：顯示所有分支（含遠端）
- **Create Branch**：建立並切換到新分支
- **Delete Local**：刪除本地分支（支援批量）

#### 遠端操作
- **Delete Remote**：刪除遠端分支
- **Prune (修剪)**：清理過期的遠端追蹤分支
  - 支援 `--dry-run` 預覽模式

**批量刪除範例**：
```
# 輸入多個分支名稱（空格分隔）
feature/old-1 feature/old-2 bugfix/deprecated
```

---

### 7. Tag 標籤管理 🏷️

| 功能 | 說明 |
|------|------|
| **List Tags** | 列出所有 tag |
| **Create Tag** | 建立 annotated tag（可選訊息） |
| **Delete Local** | 刪除本地 tag（支援批量） |
| **Delete Remote** | 刪除遠端 tag |

**批量刪除範例**：
```
v1.0.0-alpha v1.0.0-beta v1.0.0-rc1
```

---

### 8. 遠端推送 ✈️

```bash
⬆️ Push              # 正常推送
🛰️ Push Tags         # 推送所有 tag
⚡ Force Push        # 強制推送（含安全選項）
```

**Force Push 選項**：
- `-f`：標準強推（危險）
- `--force-with-lease`：安全強推（建議使用）
  - 只在遠端未被他人更新時才推送
  - 避免覆蓋團隊成員的提交

---

### 9. 狀態與工具 🔍

- **Status**：查看當前狀態
- **Diff**：查看未提交的變更
- **Clean -fd**：清理未追蹤的檔案和目錄
- **Checkout File**：從指定 commit 還原檔案

---

### 10. 快速指令列 ⚡

**內建終端輸入框**，支援任意 Git 指令：

```bash
# 直接輸入指令（自動加上 git 前綴）
rebase -i HEAD~3
cherry-pick abc123 def456
branch -D feature/old
tag -d v1.0.0
```

按 **Enter** 即可執行，執行結果即時顯示在下方終端區。

---

## 🚀 快速開始

### 安裝需求

```bash
# Python 3.8 或更高版本
python --version

# Git（必須已安裝）
git --version
```

### 執行程式

```bash
# 1. 下載專案
git clone <repository-url>
cd git-pro-organizer

# 2. 直接執行（無需額外依賴）
python git_gui_final.py
```

### 開啟專案

1. 點擊「**+ 開啟新專案分頁**」
2. 選擇包含 `.git` 的 Git 儲存庫資料夾
3. 開始使用！

---

## 📖 使用指南

### 基本操作流程

#### 場景 1：整理最近 5 個 commit

```
1. 點擊「HEAD~10」或「互動模式」
2. Git 編輯器會開啟，修改 rebase 指令：
   - pick → squash (合併)
   - pick → reword (修改訊息)
   - pick → edit (停下來修改)
3. 儲存並關閉編輯器
4. 如有衝突：
   - 解決衝突
   - 點擊「▶️ Continue」
5. 完成後自動刷新 Git Graph
```

#### 場景 2：清理過期分支

```
1. 點擊「🧹 Prune (修剪)」
2. 確認遠端名稱（預設 origin）
3. 勾選「僅預覽」查看會刪除什麼
4. 取消預覽，執行清理
5. 查看執行結果
```

#### 場景 3：批量刪除本地分支

```
1. 點擊「✂️ Delete Local」
2. 輸入分支名稱（空格分隔）：
   feature/old-1 feature/old-2 bugfix/deprecated
3. 確認執行（預設使用 -D 強制刪除）
4. 完成
```

#### 場景 4：安全 Force Push

```
1. 點擊「⚡ Force Push」
2. 確認遠端（預設 origin）
3. 輸入分支名稱（留空=當前分支）
4. 選擇推送模式：
   ✅ 勾選「安全強推 (--force-with-lease)」（建議）
   ❌ 取消勾選 = 使用 -f（危險）
5. 確認執行
```

---

## 🎨 介面配置

```
┌────────────────────────────────────────────────────────────────┐
│  [+ 開啟新專案分頁]                                             │
├──────────────┬─────────────────────────────────────────────────┤
│              │  Git Adog 圖表:                                  │
│ ⚡ 快速執行   │  * abc123 (HEAD -> main) Latest commit          │
│ [輸入框][執行]│  * def456 Previous commit                       │
│              │  * 789abc Initial commit                        │
│ 🛠️ 快速互動  │  ────────────────────────────────────────────── │
│ [HEAD~2/4/10]│  執行輸出:                                       │
│              │  $ git rebase -i HEAD~5                         │
│ 🔄 Rebase    │  Successfully rebased...                        │
│ 🍒 Cherry-pk │  ────────────────────────────────────────────── │
│ ⏪ Reset     │  [🔄 刷新]  [🕒 Reflog]                          │
│ 📝 提交      │                                                 │
│ 📦 Stash     │                                                 │
│ 🌿 Branch    │                                                 │
│ 🏷️ Tag       │                                                 │
│ ✈️ 推送      │                                                 │
│ 🔍 工具      │                                                 │
└──────────────┴─────────────────────────────────────────────────┘
```

---

## 🛠️ 進階技巧

### 快速指令範例

#### 批量 Cherry-pick
```bash
# 快速指令列輸入
cherry-pick abc123 def456 789abc
```

#### 互動式 Rebase 指定範圍
```bash
# 方法 1: 使用快速按鈕
點擊 HEAD~10

# 方法 2: 自訂範圍
點擊「互動模式」→ 輸入 HEAD~15
```

#### 刪除多個分支
```bash
# 方法 1: 使用對話框
點擊「Delete Local」→ 輸入多個分支名稱

# 方法 2: 快速指令列
branch -D feature/old-1 feature/old-2 bugfix/test
```

#### 查看特定檔案的修改歷史
```bash
# 快速指令列
log --follow -- path/to/file.py
```

---

## 🔒 安全機制

### 1. 參數驗證
- **必填項**標記紅色星號 `*`
- 未填寫時顯示**紅框警告**
- 阻止執行不完整的指令

### 2. 危險操作警告
- **Hard Reset**：標記 ⚠️ 符號
- **Force Push**：預設建議使用 `--force-with-lease`
- **Branch/Tag 刪除**：預設使用 `-D`/`-d` 強制刪除

### 3. 即時回饋
- **Terminal 區域**：所有指令執行結果即時顯示
- **Git Graph**：每次操作後自動刷新
- **Reflog**：隨時查看操作歷史，方便復原

### 4. UTF-8 編碼處理
- 自動處理中文路徑和檔案名稱
- 避免執行指令時閃退

---

## 📝 指令對照表

| 工具按鈕 | 實際執行的 Git 指令 |
|---------|-------------------|
| HEAD~2 | `git rebase -i HEAD~2` |
| 互動模式 | `git rebase -i <自訂範圍>` |
| Cherry-pick Hash | `git cherry-pick <hash1> <hash2>...` |
| 🔙 Undo Commit | `git reset --soft HEAD~1` |
| Soft Reset | `git reset --soft <commit>` |
| Hard Reset | `git reset --hard <commit>` |
| Squash 訊息 | `git commit -m "s"` |
| Amend 上則 | `git commit --amend` |
| Add All (.) | `git add .` |
| Stash Save | `git stash` |
| Stash Pop | `git stash pop` |
| Delete Local | `git branch -D <branch1> <branch2>...` |
| Delete Remote | `git push origin --delete <branch>` |
| Prune (修剪) | `git fetch origin --prune && git remote prune origin` |
| Create Tag | `git tag <name> -m "<message>"` |
| Delete Local (Tag) | `git tag -d <tag1> <tag2>...` |
| Delete Remote (Tag) | `git push origin --delete <tag>` |
| Force Push | `git push -f origin <branch>` |
| Force Push (安全) | `git push --force-with-lease origin <branch>` |

---

## 🤝 適用場景

### ✅ 適合使用的情況
- 需要頻繁 **rebase** 整理提交歷史
- 管理多個功能分支和實驗性分支
- 經常需要 **cherry-pick** 特定 commit
- 團隊協作中需要清理過期分支
- 快速建立 **squash commit** 稍後整理
- 需要安全的 **force push** 機制

### ❌ 不適合的情況
- Git 初學者（建議先使用 SourceTree 等基礎工具）
- 只需要簡單的 commit/push/pull 操作
- 不熟悉 rebase、cherry-pick 等進階概念

---

## 🔧 技術細節

### 關鍵特性

#### 1. 滑鼠滾輪支援
- 左側指令區支援滑鼠滾輪捲動
- 遞迴綁定所有子元件，確保滑鼠在任何位置都能捲動

#### 2. UTF-8 編碼處理
```python
# 所有 subprocess.run 都加入 encoding 處理
subprocess.run(cmd, encoding='utf-8', errors='replace')
```
- 避免中文路徑或檔案名稱造成閃退
- 正確顯示中文輸出

#### 3. 自訂流程處理器
```python
# Stash → Commit 自訂流程
def handle_stash_commit(self, params, repo_path):
    self.execute_git_command("git stash", repo_path)
    self.execute_git_command("git stash pop", repo_path)
    self.execute_git_command("git add .", repo_path)
    self.execute_git_command(f'git commit -m "{message}"', repo_path)
```

#### 4. 動態 UI 生成
- 使用配置驅動的按鈕佈局
- 易於擴充新指令

---

## 📦 檔案結構

```
git-pro-organizer/
├── git_gui_final.py       # 主程式
├── README.md              # 本文件
└── .git/                  # Git 儲存庫（如果有）
```

---

## 🐛 已知問題修正

### ✅ 已修正的問題

1. **滑鼠滾輪無法捲動左側指令區**
   - 修正：遞迴綁定所有子元件的滾輪事件

2. **中文路徑或檔案名稱造成閃退**
   - 修正：所有 subprocess 加入 `encoding='utf-8', errors='replace'`

3. **參數對話框未驗證必填項**
   - 修正：加入紅框警告和阻止執行機制

4. **Adog 視覺化缺少水平捲軸**
   - 修正：加入水平 Scrollbar

5. **Cherry-pick 按鈕寬度不一致**
   - 修正：統一寬度配置

---

## 📄 授權

MIT License - 自由使用、修改、分發

---

## 🙏 致謝

此工具專為提升 Git 進階使用者和 Project Lead 的工作效率而設計。

如果你發現任何問題或有改進建議，歡迎提出 Issue 或 Pull Request！

---

**Made with ❤️ for Git Power Users & Project Leads**

---

## 📚 延伸閱讀

- [Git 官方文件](https://git-scm.com/doc)
- [Git Rebase 詳解](https://git-scm.com/book/zh-tw/v2/Git-分支-分支的衍合)
- [Git Cherry-pick 使用指南](https://git-scm.com/docs/git-cherry-pick)
- [安全的 Force Push](https://git-scm.com/docs/git-push#Documentation/git-push.txt---force-with-lease)