import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os

from src.core.git_handler.commands import get_commands_configs
from src.core.git_handler.executor import GitExecutor
from src.gui.command_panel import CommandPanel
from src.gui.danger_operation_blocker import ConfirmationManager
from src.gui.dialogs import GitCommandDialog


# ==========================================
# GitAdvancedTool (主程式整合模組)
# ==========================================
class GitAdvancedTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Git Helper Pro - 進階Git版控小工具")
        self.root.geometry("1300x850")

        self._init_styles()
        self.command_configs = get_commands_configs()
        self.confirm_mgr = ConfirmationManager(root)  # 初始化確認管理器

        # 頂部工具列
        self.toolbar = ttk.Frame(self.root, padding=5)
        self.toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Button(self.toolbar, text="+ 開啟新專案分頁", command=self.open_directory).grid(row=0, column=0, padx=5)

        # 主 Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

    def _init_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TFrame", background="#f0f0f0")
        self.style.configure("TLabelframe", background="#f0f0f0")
        self.style.configure("Danger.TButton", foreground="red", font=("Arial", 9, "bold"))

    def open_directory(self):
        path = filedialog.askdirectory()
        if path and os.path.isdir(os.path.join(path, '.git')):
            self.add_project_tab(os.path.basename(path), path)
        elif path:
            messagebox.showwarning("錯誤", "無效的 Git 儲存庫")

    def add_project_tab(self, name, path):
        main_frame = ttk.Frame(self.notebook)
        self.notebook.add(main_frame, text=name)
        self.notebook.select(main_frame)

        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # === 建立右側面板 (先建立以便傳遞給 Executor) ===
        display_panel = ttk.Frame(main_frame)
        display_panel.grid(row=0, column=1, sticky="nsew", padx=5)
        display_panel.columnconfigure(0, weight=1)
        display_panel.rowconfigure(1, weight=3)
        display_panel.rowconfigure(4, weight=2)

        # Adog 區域
        ttk.Label(display_panel, text="Git Adog 圖表:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w",
                                                                                        pady=(5, 0))
        adog_text = tk.Text(display_panel, bg="#ffffff", height=15, font=("Consolas", 10), wrap="none")
        adog_text.grid(row=1, column=0, sticky="nsew")
        adog_h_scroll = ttk.Scrollbar(display_panel, orient="horizontal", command=adog_text.xview)
        adog_h_scroll.grid(row=2, column=0, sticky="ew")
        adog_text.configure(xscrollcommand=adog_h_scroll.set)

        # Terminal 區域
        ttk.Label(display_panel, text="執行輸出:", font=("Arial", 9, "bold")).grid(row=3, column=0, sticky="w",
                                                                                   pady=(5, 0))
        terminal = tk.Text(display_panel, bg="#1e1e1e", fg="#ffffff", font=("Consolas", 10))
        terminal.grid(row=4, column=0, sticky="nsew")

        # === 初始化 Executor (核心邏輯) ===
        executor = GitExecutor(terminal, adog_text, path)

        # 底部工具欄
        ctrl_bar = ttk.Frame(display_panel)
        ctrl_bar.grid(row=5, column=0, sticky="ew", pady=5)
        ttk.Button(ctrl_bar, text="🔄 刷新", width=10, command=executor.refresh_adog).pack(side="left", padx=2)
        ttk.Button(ctrl_bar, text="🕒 Reflog", width=10, command=executor.view_reflog).pack(side="left", padx=2)

        executor.refresh_adog()

        # === 建立左側 CommandPanel (注入依賴) ===
        # 傳遞 self (app) 以便 panel 可以呼叫 open_command_dialog
        CommandPanel(main_frame, executor, self.confirm_mgr, self)

    def open_command_dialog(self, cmd_key, repo_path, executor):
        """處理帶參數的 Git 指令對話框"""
        if cmd_key not in self.command_configs:
            messagebox.showerror("錯誤", f"未定義的指令: {cmd_key}")
            return

        config = self.command_configs[cmd_key]

        # 檢查危險權限
        if config.get('danger', False):
            if not self.confirm_mgr.confirm(config['name'], None):
                return

        dialog = GitCommandDialog(self.root, config['name'], config['params'], repo_path)
        result = dialog.show()

        if result:
            self._execute_configured_git(config, result, executor)

    def _execute_configured_git(self, config, params, executor):
        """解析參數並交給 Executor 執行"""
        cmd_key = next((k for k, v in self.command_configs.items() if v == config), None)

        # === 1. 自訂 Handler 邏輯 ===
        if config.get('base_cmd') == 'custom':
            # 處理：從特定 Commit 還原檔案 (你剛要求的功能)
            if cmd_key == 'restore_file_from_commit':
                self.open_commit_file_selector(executor, params.get('commit'))
                return

            # 處理：Prune 遠端分支
            handler_name = config.get('custom_handler')
            if handler_name == 'handle_prune_branches':
                remote = params.get('remote', 'origin')
                if params.get('dry_run'):
                    executor.run(f"git fetch {remote} --prune --dry-run")
                else:
                    executor.run(f"git fetch {remote} --prune")
                    executor.run(f"git remote prune {remote}")
                return
            return

        # === 2. 特殊指令組裝 (如 checkout -b) ===
        cmd_parts = ['git', config['base_cmd']]

        if config['base_cmd'] == 'checkout' and params.get('create'):
            cmd_parts.append('-b')
            if params.get('branch'):
                cmd_parts.append(params['branch'])
            executor.run(' '.join(cmd_parts))
            return

        # === 3. 一般參數自動化組裝 ===
        for param_def in config['params']:
            name = param_def['name']
            value = params.get(name)

            if param_def['type'] == 'toggle' and value:
                flag_map = {
                    'interactive': '-i', 'soft': '--soft', 'hard': '--hard',
                    'amend': '--amend', 'no_edit': '--no-edit', 'force': '-f',
                    'force_delete': '-D', 'delete': '--delete'
                }
                if name in flag_map:
                    cmd_parts.append(flag_map[name])

            elif param_def['type'] == 'text' and value:
                # 針對不同參數名稱加上對應的 Flag
                if name == 'message':
                    cmd_parts.extend(['-m', f'"{value}"'])
                elif name == 'commit' and config['base_cmd'] == 'reset':
                    cmd_parts.append(value)  # reset 不需要 -m
                elif name in ['branch', 'commit', 'tag', 'file', 'source', 'remote']:
                    cmd_parts.append(value)

        executor.run(' '.join(cmd_parts))

    def open_file_selector(self, executor):
        """開啟檔案選擇器：支援單獨 Add、雙重狀態計數"""
        repo_path = executor.repo_path

        try:
            # 1. 獲取詳細狀態
            # 使用 -s 取得短格式，這能區分 Index(暫存) 與 Worktree(工作區)
            res = subprocess.run("git status -s", cwd=repo_path, shell=True,
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')

            files = []
            staged_count = 0
            unstaged_count = 0

            for line in res.stdout.splitlines():
                if len(line) < 4: continue
                # Git status -s 前兩個字元分別代表 Index 和 Worktree
                index_stat = line[0]
                work_stat = line[1]
                filepath = line[3:].strip()

                # 計算數量邏輯
                if index_stat != ' ' and index_stat != '?': staged_count += 1
                if work_stat != ' ' or index_stat == '?': unstaged_count += 1

                files.append((index_stat, work_stat, filepath))

            if not files:
                messagebox.showinfo("提示", "目前沒有任何變更")
                return

            dialog = tk.Toplevel(self.root)
            dialog.title("檔案管理 - 精確狀態管理")
            dialog.geometry("750x650")
            dialog.transient(self.root)
            dialog.grab_set()

            # 置中
            dialog.update_idletasks()
            rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
            dw, dh = dialog.winfo_width(), dialog.winfo_height()
            dialog.geometry(f"+{rx + (rw // 2) - (dw // 2)}+{ry + (rh // 2) - (dh // 2)}")

            main_frame = ttk.Frame(dialog, padding=15)
            main_frame.pack(fill="both", expand=True)

            # 2. 狀態統計列 (新增 Stage 與 待處理 計數)
            stat_bar = ttk.Frame(main_frame)
            stat_bar.pack(fill="x", pady=(0, 5))
            ttk.Label(stat_bar, text=f"暫存區 (Staged): {staged_count}", foreground="#28a745",
                      font=("Arial", 9, "bold")).pack(side="left", padx=10)
            ttk.Label(stat_bar, text=f"待處理 (Unstaged): {unstaged_count}", foreground="#007bff",
                      font=("Arial", 9, "bold")).pack(side="left", padx=10)

            # 3. 檔案列表區
            list_frame = ttk.LabelFrame(main_frame, text=" 檔案變更列表 ", padding=10)
            list_frame.pack(fill="both", expand=True, pady=(0, 10))
            canvas = tk.Canvas(list_frame, bg="#f0f0f0", highlightthickness=0)
            scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
            scroll_frame = ttk.Frame(canvas)
            canvas.create_window((0, 0), window=scroll_frame, anchor="nw", tags="frame")
            canvas.configure(yscrollcommand=scrollbar.set)
            scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure("frame", width=e.width))
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            file_vars = {}

            # 狀態顯示優化
            def get_status_info(idx, work):
                if idx != ' ' and work != ' ' and idx != '?': return ('⚠️', '部分暫存', '#FFC107')
                if idx == '?': return ('🆕', '未追蹤', '#6c757d')
                if idx != ' ': return ('✅', '已暫存', '#28a745')
                if work == 'M': return ('✏️', '修改中', '#007bff')
                if work == 'D': return ('🗑️', '已刪除', '#dc3545')
                return ('❓', '未知', 'black')

            for idx_stat, work_stat, filepath in files:
                f_frame = ttk.Frame(scroll_frame)
                f_frame.pack(fill="x", pady=2)
                var = tk.BooleanVar(value=True)
                file_vars[filepath] = var

                ttk.Checkbutton(f_frame, variable=var).pack(side="left")
                icon, txt, color = get_status_info(idx_stat, work_stat)
                tk.Label(f_frame, text=f"{icon} {txt}", fg=color, width=10, anchor="w").pack(side="left")
                tk.Label(f_frame, text=filepath, font=("Consolas", 9)).pack(side="left", fill="x")

            # 4. Commit 訊息區
            commit_frame = ttk.LabelFrame(main_frame, text=" 操作訊息 ", padding=10)
            commit_frame.pack(fill="x", pady=(0, 10))
            commit_var = tk.StringVar()
            commit_entry = ttk.Entry(commit_frame, textvariable=commit_var, font=("Consolas", 10))
            commit_entry.pack(fill="x")

            # --- 邏輯函數 ---
            def get_selected():
                return [f'"{f}"' for f, v in file_vars.items() if v.get()]

            def on_add_only():
                selected = get_selected()
                if not selected: return
                executor.run(f"git add {' '.join(selected)}")
                dialog.destroy()  # Add 完直接關閉，因為目的是要準備去 commit 或做別的

            def on_add_commit():
                selected = get_selected()
                if not selected: return messagebox.showwarning("警告", "請選擇檔案")
                msg = commit_var.get().strip()
                if not msg:
                    commit_entry.focus_set()
                    return messagebox.showwarning("警告", "Commit 必須填寫訊息")
                executor.run(f"git add {' '.join(selected)}")
                executor.run(f'git commit -m "{msg}"')
                dialog.destroy()

            def on_stash():
                selected = get_selected()
                if not selected: return
                msg = commit_var.get().strip() or "Quick Stash"
                executor.run(f'git stash push -m "{msg}" -- {" ".join(selected)}')
                dialog.destroy()

            # 自動聚焦與 Enter 預設執行 Add+Commit
            commit_entry.focus_set()
            commit_entry.bind("<Return>", lambda e: on_add_commit())

            # 5. 按鈕列
            btn_bar = ttk.Frame(main_frame)
            btn_bar.pack(fill="x")

            # 右側主要執行
            ttk.Button(btn_bar, text="✓ Add + Commit", command=on_add_commit, width=16).pack(side="right", padx=2)
            ttk.Button(btn_bar, text="➕ 僅 Add", command=on_add_only, width=10).pack(side="right", padx=2)
            ttk.Button(btn_bar, text="📦 Stash 選中", command=on_stash, width=12).pack(side="right", padx=2)

            # 左側輔助
            ttk.Button(btn_bar, text="全選", command=lambda: [v.set(True) for v in file_vars.values()], width=8).pack( side="left", padx=2)
            ttk.Button(btn_bar, text="清空", command=lambda: [v.set(False) for v in file_vars.values()], width=8).pack( side="left", padx=2)
            ttk.Button(btn_bar, text="✗ 取消", command=dialog.destroy).pack(side="left", padx=10)

        except Exception as e:
            messagebox.showerror("錯誤", f"狀態讀取失敗: {str(e)}")

    def _show_quick_preview(self, executor, commit_hash, filepath, parent=None):
        preview_parent = parent if parent else self.root
        preview = tk.Toplevel(preview_parent)

        # 移除邊框（可選），讓它看起來更像真正的懸浮預覽，但也保留標題供辨識
        preview.title(f"預覽: {os.path.basename(filepath)}")
        preview.geometry("700x500")
        preview.attributes("-topmost", True)

        x = self.root.winfo_pointerx() + 15
        y = self.root.winfo_pointery() + 15
        preview.geometry(f"+{x}+{y}")

        def close_preview(event=None):
            if preview.winfo_exists():
                preview.destroy()

        # 標題欄：僅顯示資訊，不觸發離開關閉
        header = tk.Label(preview, text=f" 檔案: {filepath} (移出文字區域或按右鍵關閉) ",
                          bg="#444", fg="#fff", font=("Arial", 9), pady=3)
        header.pack(fill="x")

        # 文字區域
        text_area = tk.Text(preview, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 10),
                            padx=10, pady=10, wrap="none", highlightthickness=0)

        # 滾動條
        v_scroll = ttk.Scrollbar(preview, orient="vertical", command=text_area.yview)
        h_scroll = ttk.Scrollbar(preview, orient="horizontal", command=text_area.xview)
        text_area.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        text_area.pack(fill="both", expand=True)

        # --- 核心邏輯改動 ---
        # 1. 只有滑鼠離開「文字區域」時才關閉
        # 這樣你從 Header 移入 Text 的過程不會被觸發
        text_area.bind("<Leave>", close_preview)

        # 2. 右鍵點擊文字區域或標題皆可關閉
        text_area.bind("<Button-3>", close_preview)
        header.bind("<Button-3>", close_preview)

        # 3. 視窗層級的 Esc 鍵支援
        preview.bind("<Escape>", close_preview)

        try:
            # 使用 git show 讀取內容
            cmd = f'git show "{commit_hash}:{filepath}"'
            res = subprocess.run(cmd, cwd=executor.repo_path, shell=True,
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')

            text_area.insert("1.0", res.stdout if res.returncode == 0 else res.stderr)
            text_area.config(state="disabled")

            # 讓內容能滾動但保持焦點，避免立刻觸發 Leave
            text_area.focus_set()

        except Exception as e:
            text_area.insert("1.0", str(e))

    def open_commit_file_selector(self, executor, commit_hash):
        """從特定 Commit 提取檔案內容：不切換分支、不產生 Commit"""
        if not commit_hash:
            messagebox.showwarning("警告", "必須提供 Commit Hash")
            return

        try:
            # 1. 使用 diff-tree 獲取該次提交相對於其父提交的檔案清單
            # -r: 遞迴子目錄, --no-commit-id: 隱藏 commit hash, --name-only: 只顯示檔名
            cmd = f"git diff-tree -r --no-commit-id --name-only {commit_hash}"
            res = subprocess.run(
                cmd,
                cwd=executor.repo_path, shell=True,
                capture_output=True, text=True, encoding='utf-8', errors='replace'
            )

            # 過濾空白行
            files = [line.strip() for line in res.stdout.splitlines() if line.strip()]

            # 偵錯檢查：如果還是空，可能是 Hash 錯或該 Commit 真的沒東西
            if not files:
                # 備援方案：嘗試 git show (針對首個 commit 情況)
                res = subprocess.run(f"git show --name-only --pretty=format: {commit_hash}",
                                     cwd=executor.repo_path, shell=True, capture_output=True, text=True)
                files = [line.strip() for line in res.stdout.splitlines() if line.strip()]

            if not files:
                messagebox.showerror("錯誤",
                                     f"找不到 Commit [{commit_hash}] 的檔案變更。\n請確認 Hash 是否正確（例如：a1b2c3d）。")
                return

            # 2. 建立彈窗 (與 open_file_selector 風格一致)
            dialog = tk.Toplevel(self.root)
            dialog.title(f"還原檔案自: {commit_hash[:7]}")
            dialog.geometry("750x600")
            dialog.transient(self.root)
            dialog.grab_set()

            # 置中
            dialog.update_idletasks()
            rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
            dw, dh = dialog.winfo_width(), dialog.winfo_height()
            dialog.geometry(f"+{rx + (rw // 2) - (dw // 2)}+{ry + (rh // 2) - (dh // 2)}")

            main_frame = ttk.Frame(dialog, padding=15)
            main_frame.pack(fill="both", expand=True)

            ttk.Label(main_frame, text=f"📂 從 Commit [{commit_hash}] 提取檔案內容", font=("Arial", 10, "bold")).pack(anchor="w")
            ttk.Label(main_frame, text="注意：這會直接覆蓋工作區檔案，且不會自動 Commit。", foreground="red").pack(anchor="w", pady=(0, 10))

            # 3. 檔案列表區
            list_frame = ttk.LabelFrame(main_frame, text=" 該次提交的變更檔案 ", padding=10)
            list_frame.pack(fill="both", expand=True, pady=(0, 10))

            canvas = tk.Canvas(list_frame, bg="#f0f0f0", highlightthickness=0)
            scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
            scroll_frame = ttk.Frame(canvas)
            canvas.create_window((0, 0), window=scroll_frame, anchor="nw", tags="frame")

            canvas.configure(yscrollcommand=scrollbar.set)
            scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure("frame", width=e.width))
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            file_vars = {}
            for filepath in files:
                f_frame = ttk.Frame(scroll_frame)
                f_frame.pack(fill="x", pady=2)

                var = tk.BooleanVar(value=True)
                file_vars[filepath] = var

                ttk.Checkbutton(f_frame, variable=var).pack(side="left")

                # 建立檔名標籤
                lbl = tk.Label(f_frame, text=f"📄 {filepath}", font=("Consolas", 9), anchor="w", cursor="hand2")
                lbl.pack(side="left", fill="x", expand=True)

                # --- 超強功能：右鍵點擊預覽 ---
                # 傳入 dialog 作為 parent
                # 綁定右鍵 (Windows: <Button-3>, MacOS: <Button-2>)
                lbl.bind("<Button-3>", lambda e, p=filepath: self._show_quick_preview(executor, commit_hash, p, parent=dialog))

                # 順便加個懸停提示效果
                lbl.bind("<Enter>", lambda e, l=lbl: l.config(fg="blue", underline=True))
                lbl.bind("<Leave>", lambda e, l=lbl: l.config(fg="black", underline=False))

            # 4. 執行還原邏輯
            def on_restore():
                selected = [f'"{f}"' for f, v in file_vars.items() if v.get()]
                if not selected:
                    return messagebox.showwarning("警告", "請至少勾選一個檔案")

                # 確認視窗：確保使用者知道這會蓋掉目前的代碼
                if messagebox.askyesno("確認還原",
                                       f"確定要將選中的 {len(selected)} 個檔案還原到 {commit_hash[:7]} 的狀態？\n\n這只會修改檔案內容，不會切換分支，也不會產生 Commit。"):
                    # 關鍵指令：從特定 commit 抽出檔案
                    # 此指令完全不影響 HEAD 指標
                    executor.run(f"git checkout {commit_hash} -- {' '.join(selected)}")
                    dialog.destroy()
                    messagebox.showinfo("完成", f"已成功提取 {len(selected)} 個檔案內容。\n請在工作區確認變更。")

            # 5. 按鈕列
            btn_bar = ttk.Frame(main_frame)
            btn_bar.pack(fill="x")
            ttk.Button(btn_bar, text="⏮️ 提取內容至工作區", command=on_restore, width=25, style="Danger.TButton").pack(side="right", padx=2)
            ttk.Button(btn_bar, text="✗ 取消", command=dialog.destroy).pack(side="right", padx=2)
            ttk.Button(btn_bar, text="全選", command=lambda: [v.set(True) for v in file_vars.values()], width=8).pack(side="left", padx=2)
            ttk.Button(btn_bar, text="清空", command=lambda: [v.set(False) for v in file_vars.values()], width=8).pack(side="left", padx=2)

        except Exception as e:
            messagebox.showerror("錯誤", f"讀取失敗: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = GitAdvancedTool(root)
    root.mainloop()