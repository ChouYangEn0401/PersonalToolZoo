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
        self.root.title("Git Pro Organizer - 智能參數管理")
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
        # 自訂 Handler 邏輯
        if config.get('base_cmd') == 'custom' and 'custom_handler' in config:
            # 這裡簡化處理，若有需要可將 custom handlers 也移入 Executor
            handler_name = config['custom_handler']
            if handler_name == 'handle_prune_branches':
                remote = params.get('remote', 'origin')
                if params.get('dry_run'):
                    executor.run(f"git fetch {remote} --prune --dry-run")
                else:
                    executor.run(f"git fetch {remote} --prune")
                    executor.run(f"git remote prune {remote}")
            return

        cmd_parts = ['git', config['base_cmd']]

        # 特殊處理：checkout -b
        if config['base_cmd'] == 'checkout' and params.get('create'):
            cmd_parts.append('-b')
            if params.get('branch'):
                cmd_parts.append(params['branch'])
            executor.run(' '.join(cmd_parts))
            return

        # 一般參數組裝
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
                if name == 'message':
                    cmd_parts.extend(['-m', f'"{value}"'])
                elif name in ['branch', 'commit', 'tag', 'file', 'source', 'remote']:
                    cmd_parts.append(value)

        executor.run(' '.join(cmd_parts))

    def open_file_selector(self, executor):
        """開啟檔案選擇器：自動聚焦 Commit 欄位，Enter 直接執行 Add+Commit"""
        repo_path = executor.repo_path

        try:
            # 1. 獲取檔案狀態
            res = subprocess.run("git status --short", cwd=repo_path, shell=True,
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')
            files = []
            for line in res.stdout.splitlines():
                if line.strip():
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) == 2:
                        files.append(parts)  # (status, filepath)

            if not files:
                messagebox.showinfo("提示", "目前沒有任何變更的檔案")
                return

            # 2. 建立彈窗
            dialog = tk.Toplevel(self.root)
            dialog.title("檔案管理 - Add / Stash / Commit")
            dialog.geometry("700x600")
            dialog.transient(self.root)
            dialog.grab_set()

            # 置中
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
            y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")

            main_frame = ttk.Frame(dialog, padding=15)
            main_frame.pack(fill="both", expand=True)

            # 3. 檔案列表區
            list_frame = ttk.LabelFrame(main_frame, text=f" 待處理檔案 ({len(files)}) ", padding=10)
            list_frame.pack(fill="both", expand=True, pady=(0, 10))

            canvas = tk.Canvas(list_frame, bg="#f0f0f0", highlightthickness=0)
            scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
            scroll_frame = ttk.Frame(canvas)
            canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

            canvas.configure(yscrollcommand=scrollbar.set)
            scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))

            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            # --- 重點：定義 file_vars 字典存放狀態 ---
            file_vars = {}
            status_map = {
                '??': ('🆕', '新增', '#4CAF50'), 'M': ('✏️', '修改', '#2196F3'),
                'A': ('✅', '已加入', '#9C27B0'), 'D': ('🗑️', '刪除', '#F44336')
            }

            for status, filepath in files:
                f_frame = ttk.Frame(scroll_frame)
                f_frame.pack(fill="x", pady=2)

                var = tk.BooleanVar(value=True)
                file_vars[filepath] = var  # 將路徑與變數綁定

                ttk.Checkbutton(f_frame, variable=var).pack(side="left")
                icon, txt, color = status_map.get(status.strip(), ('❓', status, 'black'))
                tk.Label(f_frame, text=f"{icon} {txt}", fg=color, width=10, anchor="w").pack(side="left")
                tk.Label(f_frame, text=filepath, font=("Consolas", 9)).pack(side="left", fill="x")

            # 4. Commit 訊息區
            commit_frame = ttk.LabelFrame(main_frame, text=" Commit 訊息 (填寫後按 Enter 直接執行) ", padding=10)
            commit_frame.pack(fill="x", pady=(0, 10))

            commit_var = tk.StringVar()
            commit_entry = ttk.Entry(commit_frame, textvariable=commit_var, font=("Consolas", 10))
            commit_entry.pack(fill="x")

            # 5. 操作邏輯
            def get_selected():
                return [f for f, v in file_vars.items() if v.get()]

            def on_add_commit():
                selected = get_selected()
                if not selected:
                    return messagebox.showwarning("警告", "請至少勾選一個檔案")
                msg = commit_var.get().strip()
                if not msg:
                    commit_entry.focus_set()  # 沒寫訊息就閃紅燈(這裡僅提示)
                    return messagebox.showwarning("警告", "請輸入 Commit 訊息")

                for fp in selected: executor.run(f'git add "{fp}"')
                executor.run(f'git commit -m "{msg}"')
                dialog.destroy()

            def on_stash():
                selected = get_selected()
                if not selected: return
                for fp in selected: executor.run(f'git add "{fp}"')
                msg = commit_var.get().strip() or "Quick Stash"
                executor.run(f'git stash push -m "{msg}"')
                dialog.destroy()

            # --- 自動聚焦與 Enter 綁定 ---
            commit_entry.focus_set()
            commit_entry.bind("<Return>", lambda e: on_add_commit())

            # 6. 按鈕列
            btn_bar = ttk.Frame(main_frame)
            btn_bar.pack(fill="x")

            ttk.Button(btn_bar, text="✓ Add + Commit", command=on_add_commit, width=18).pack(side="right", padx=2)
            ttk.Button(btn_bar, text="📦 Stash 選中", command=on_stash, width=12).pack(side="right", padx=2)
            ttk.Button(btn_bar, text="✗ 取消", command=dialog.destroy).pack(side="right", padx=2)

            # 全選/全不選按鈕
            ttk.Button(btn_bar, text="全選", command=lambda: [v.set(True) for v in file_vars.values()], width=8).pack(
                side="left", padx=2)
            ttk.Button(btn_bar, text="清空", command=lambda: [v.set(False) for v in file_vars.values()], width=8).pack(
                side="left", padx=2)

        except Exception as e:
            messagebox.showerror("錯誤", f"開啟檔案選擇器失敗: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = GitAdvancedTool(root)
    root.mainloop()