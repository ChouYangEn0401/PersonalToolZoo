# 功能詳細說明

> 所有功能的對話框介面、參數說明與操作細節。

---

## 目錄

- [Merge 合併](#-merge-合併)
- [Checkout 搜尋器](#-checkout-搜尋器)
- [Rebase](#%EF%B8%8F-rebase)
- [Cherry-pick](#-cherry-pick)
- [Reset 回退](#-reset-回退)
- [提交與暫存](#-提交與暫存)
- [遠端推送](#%EF%B8%8F-遠端推送)
- [Stash 緩衝區](#-stash-緩衝區)
- [Branch 分支管理](#-branch-分支管理)
- [Tag 標籤管理](#%EF%B8%8F-tag-標籤管理)
- [快速指令列](#-快速指令列)
- [自動完成鍵盤操作](#%EF%B8%8F-自動完成-autocomplete-鍵盤操作)
- [介面配置圖](#-介面配置圖)

---

## 🔀 Merge 合併

點擊「🔀 Merge 分支」開啟互動對話框，版面分區如下：

| 分區 | 內容 |
|------|------|
| 📌 指令說明 | 四種模式的說明（一般 / --no-ff / --squash / --ff-only）|
| 🌿 目前分支 | 顯示當前所在分支，附 `↻ Refresh` 按鈕 |
| ⚙️ 參數設定 | 來源分支 Combobox（含 remote / commit）、`↪ 先切換到此分支`、合併模式 Radio 選項 |
| 📋 指令預覽 | 即時顯示完整指令 |
| 按鈕列 | Continue / Abort（左）、取消 / 執行（右）|

**四種合併模式：**

| 模式 | 指令 | 說明 |
|------|------|------|
| 一般 (預設) | `git merge <branch>` | Git 自行決定：能 fast-forward 就接上，否則建立 merge commit |
| `--no-ff` | `git merge --no-ff <branch>` | **強制**建立 merge commit，保留分支歷史脈絡，推薦 feature → main |
| `--squash` | `git merge --squash <branch>` | 所有 commit 壓成一筆變更放入暫存區，需**手動** commit |
| `--ff-only` | `git merge --ff-only <branch>` | 只允許 fast-forward，無法時直接失敗，適合嚴格線性歷史 |

- 「↪ 先切換到此分支」：直接從 Merge 對話框切換到來源分支，並更新目前分支顯示
- 對話框內提供 **Continue** / **Abort** 衝突控制

---

## 🔁 Checkout 搜尋器

點擊 Branch 群組的「📂 Checkouts」開啟分頁對話框。

### Tab 1：🔁 Checkout（分支 / Tag / Commit）

| 分區 | 內容 |
|------|------|
| 📌 指令說明 | `checkout` 與 `checkout -b` 用法 |
| 🌿 目前分支 | 顯示當前所在分支，附 `↻ Refresh`（成功切換後自動更新）|
| 🔍 搜尋目標 | 輸入框即時過濾清單，雙擊或點選填入，附捲軸 |
| 選項列 | 「建立新分支 (-b)」Checkbox |
| 📋 指令預覽 | 即時顯示完整指令 |
| 按鈕列 | 取消 / 執行（含成功/失敗驗證後提示）|

支援以下格式：

```bash
git checkout feature/my-work
git checkout origin/feature/remote
git checkout v1.2.0
git checkout a1b2c3d
git checkout -b new-branch
```

### Tab 2：🗂️ Checkout File

| 分區 | 內容 |
|------|------|
| 📌 指令說明 | `git checkout <commit/branch> -- <file>` |
| ⚙️ 參數設定 | 來源 Combobox（分支、commit）+ 檔案路徑 + 📂 瀏覽 Button |
| 📋 指令預覽 | 即時顯示完整指令 |

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

| 模式 | 說明 |
|------|------|
| `-f` | 標準強推（危險） |
| `--force-with-lease` | **安全強推**（建議）— 只在遠端未被他人更新時推送 |

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
| 📂 Checkouts | 分頁切換器（Checkout / Checkout File） |
| 📌 Create | 建立並切換到新分支 (`-b`) |
| 🗑️ Delete Branch | 刪除分支對話框（分頁：本地、遠端） |
| 🧹 Prune | 清理過期遠端追蹤，支援 `--dry-run` 預覽 |

### Delete Branch 對話框

支援一次對多個分支執行本地與/或遠端刪除：

- 輸入多個分支名稱（以空格分隔）
- 可勾選 `Delete local branch`（執行 `git branch -D <name>`）
- 可勾選 `Delete remote branch`（執行 `git push <remote> --delete <name>`）
- 即時顯示指令預覽，執行前確認

---

## 🏷️ Tag 標籤管理

| 功能 | 說明 |
|------|------|
| 📜 List Tags | `git tag -l` |
| 📌 Create Tag | 建立 annotated tag，可選訊息、指定 commit |
| 🗑️ Delete Tag | 刪除 Tag 對話框（分頁：本地、遠端） |

### Delete Tag 對話框

支援一次對多個 tag 執行本地與/或遠端刪除：

- 輸入多個 tag 名稱（以空格分隔）
- 可勾選 `Delete local tag`（執行 `git tag -d <name>`）
- 可勾選 `Delete remote tag`（執行 `git push <remote> --delete <name>`）
- 即時顯示指令預覽，執行前確認

---

## ⚡ 快速指令列

左側頂部輸入框，直接輸入任意 git 子指令，Enter 執行。

```bash
# 自動補 "git " 前綴，範例：
log --oneline --graph -20
cherry-pick abc123 def456
branch -D feature/old
rebase -i HEAD~6
```

---

## ⌨️ 自動完成（Autocomplete）鍵盤操作

在各輸入欄位出現建議清單時可用的鍵盤操作：

| 按鍵 | 行為 |
|------|------|
| `Tab` | 清單向下移一格（循環到首項），焦點留在 Entry |
| `Shift+Tab` | 清單向上移一格（循環到末項），焦點留在 Entry |
| `Space` | 確認目前反白項目，填入 Entry，關閉清單 |
| `Enter` | 同 Space（亦可確認） |
| 滑鼠單擊 | 直接確認（`ButtonRelease-1`） |
| `Escape` / `FocusOut` | 隱藏清單 |

當輸入框文字變動時，建議清單會更新並自動將選取重置到第一項。

---

## 🎨 介面配置圖

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
