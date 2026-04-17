# 指令對照表

> 所有 UI 按鈕對應的實際 Git 指令。

| 工具按鈕 | 實際 Git 指令 |
|---------|--------------|
| HEAD~2 | `git rebase -i HEAD~2` |
| HEAD~4 | `git rebase -i HEAD~4` |
| HEAD~10 | `git rebase -i HEAD~10` |
| 互動模式 | `git rebase -i <自訂範圍>` |
| 指定位置 | `git rebase <branch>` |
| Rebase --onto | `git rebase --onto <newbase> <upstream> [branch]` |
| Rebase Continue | `git rebase --continue` |
| Rebase Abort | `git rebase --abort` |
| Rebase Skip | `git rebase --skip` |
| 🔀 Merge 分支 (一般) | `git merge <branch>` |
| 🔀 Merge 分支 (--no-ff) | `git merge --no-ff <branch>` |
| 🔀 Merge 分支 (--squash) | `git merge --squash <branch>` |
| 🔀 Merge 分支 (--ff-only) | `git merge --ff-only <branch>` |
| Merge Continue | `git merge --continue` |
| Merge Abort | `git merge --abort` |
| 📂 Checkouts (Tab1=Checkout) | `git checkout <branch/tag/hash>` |
| 📂 Checkouts (Tab2=Checkout File) | `git checkout <commit> -- <file>` |
| Cherry-pick Hash | `git cherry-pick <hash1> <hash2>...` |
| Cherry-pick (-n) | `git cherry-pick -n <hash>` |
| Cherry-pick Continue | `git cherry-pick --continue` |
| Cherry-pick Abort | `git cherry-pick --abort` |
| Soft HEAD~1 | `git reset --soft HEAD~1` |
| Soft HEAD~2 | `git reset --soft HEAD~2` |
| 🧨 Soft Reset | `git reset --soft <commit>` |
| ⚠️ Hard Reset | `git reset --hard <commit>` |
| 🔧 Fixup (f) | `git commit -m "fixup"` |
| 📦 Squash (s) | `git commit -m "squash"` |
| ⚡ FastCommit | `git commit -m "stash"` |
| Amend | `git commit --amend` |
| ➕ Add 選檔 | `git add <選中檔案>` |
| ✓ Add + Commit | `git add <files> && git commit -m "<msg>"` |
| Stash Save | `git stash` |
| Stash Pop | `git stash pop` |
| Stash List | `git stash list` |
| Stash Drop | `git stash drop` |
| Stash Clear | `git stash clear` |
| 📋 List (Branch) | `git branch -a` |
| 📌 Create (Branch) | `git checkout -b <branch>` |
| 🗑️ Delete Branch (本地) | `git branch -d/-D <branch...>` |
| 🗑️ Delete Branch (遠端) | `git push origin --delete <branch>` |
| 🧹 Prune | `git fetch origin --prune && git remote prune origin` |
| 📜 List Tags | `git tag -l` |
| 📌 Create Tag | `git tag <name> -m "<message>"` |
| 🔥 Delete Local (Tag) | `git tag -d <tag...>` |
| ☁️ Delete Remote (Tag) | `git push origin --delete <tag>` |
| ⬆️ Push | `git push` |
| ⚡ Force Push (-f) | `git push -f` |
| ⚡ Force Push (安全) | `git push --force-with-lease` |
| 🛰️ Push Tags | `git push --tags` |
| Status | `git status` |
| Diff | `git diff` |
| Clean -fd | `git clean -fd` |
