import tkinter as tk
from tkinter import messagebox
import subprocess

# ==========================================
# GitExecutor (指令執行模組)
# ==========================================
class GitExecutor:
    def __init__(self, terminal_widget, adog_widget, repo_path):
        self.terminal = terminal_widget
        self.adog_text = adog_widget
        self.repo_path = repo_path

    def run(self, full_cmd):
        """執行 Git 指令並輸出結果"""
        try:
            res = subprocess.run(full_cmd, cwd=self.repo_path, shell=True, capture_output=True,
                                 text=True, encoding='utf-8', errors='replace')

            # 輸出到 Terminal
            self.terminal.insert(tk.END, f"\n$ {full_cmd}\n{res.stdout}{res.stderr}\n{'-' * 50}\n")
            self.terminal.see(tk.END)

            # 自動刷新圖表
            self.refresh_adog()
            return res
        except Exception as e:
            messagebox.showerror("錯誤", f"指令執行失敗: {str(e)}")
            return None

    def run_simple(self, cmd_base):
        """執行簡單指令 (無參數)"""
        self.run(f"git {cmd_base}")

    def refresh_adog(self):
        """刷新 Adog 圖表"""
        self.adog_text.config(state=tk.NORMAL)
        self.adog_text.delete('1.0', tk.END)

        cmd = "git log --graph --oneline --all --decorate -n 150"
        res = subprocess.run(cmd, cwd=self.repo_path, shell=True, capture_output=True,
                             text=True, encoding='utf-8', errors='replace')

        self.adog_text.insert(tk.END, res.stdout if res.stdout else "目前尚無 Commit 紀錄")
        self.adog_text.config(state=tk.DISABLED)

    def view_reflog(self):
        """顯示 Reflog"""
        self.adog_text.config(state=tk.NORMAL)
        self.adog_text.delete('1.0', tk.END)

        res = subprocess.run("git reflog -n 150", cwd=self.repo_path, shell=True, capture_output=True,
                             text=True, encoding='utf-8', errors='replace')

        self.adog_text.insert(tk.END, "--- REFLOG HISTORY ---\n" + res.stdout)
        self.adog_text.config(state=tk.DISABLED)

    def quick_commit(self, mode, message):
        """處理 fixup / squash，並檢查暫存區是否為空"""
        try:
            # 檢查 Stage 區是否有變更內容
            # --quiet 會根據是否有差異回傳 exit code (0: 無差異, 1: 有差異)
            check_res = subprocess.run(
                "git diff --cached --quiet",
                cwd=self.repo_path,
                shell=True
            )

            # exit_code 為 0 代表暫存區 (Stage) 是空的
            if check_res.returncode == 0:
                messagebox.showwarning("操作中止",
                                       "暫存區 (Stage) 目前沒有任何檔案！\n請先使用 'Add 選擇檔案' 將變更加入暫存。")
                return

            # 如果有東西，執行 Commit
            # 這裡移除 git add .，僅針對已經在 stage 的檔案處理
            self.run(f'git commit -m "{message}"')

        except Exception as e:
            self.terminal.insert(tk.END, f"\n[ERROR] 檢查暫存區失敗: {str(e)}\n")

