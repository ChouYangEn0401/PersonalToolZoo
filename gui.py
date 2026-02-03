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
        """開啟檔案選擇器，支援 Add/Stash/Commit 整合流程"""
        repo_path = executor.repo_path

        try:
            # 獲取所有未追蹤和已修改的檔案 (使用 subprocess 靜默執行，不刷屏 Terminal)
            res = subprocess.run("git status --short", cwd=repo_path, shell=True,
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')

            files = []
            for line in res.stdout.split('\n'):
                if line.strip():
                    # 格式: "?? file.txt" 或 " M file.txt"
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) == 2:
                        status, filepath = parts
                        files.append((status, filepath))

            if not files:
                messagebox.showinfo("提示", "沒有檔案需要處理")
                return

            # 創建選擇對話框
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

            # 標題區
            title_frame = ttk.Frame(main_frame)
            title_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(title_frame, text="選擇要處理的檔案:", font=("Arial", 11, "bold")).pack(side="left")
            ttk.Label(title_frame, text=f"共 {len(files)} 個檔案", font=("Arial", 9), foreground="gray").pack(
                side="left", padx=10)

            # 捲動區域
            list_frame = ttk.LabelFrame(main_frame, text=" 檔案列表 ", padding=10)
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

            # 檔案列表邏輯
            file_vars = {}
            for status, filepath in files:
                status_map = {
                    '??': ('🆕', '新增', '#4CAF50'),
                    'M': ('✏️', '修改', '#2196F3'),
                    ' M': ('✏️', '修改', '#2196F3'),
                    'A': ('✅', '已加入', '#9C27B0'),
                    'D': ('🗑️', '刪除', '#F44336'),
                    'R': ('🔄', '更名', '#FF9800'),
                    'MM': ('⚠️', '部分暫存', '#FFC107')
                }
                icon, status_text, color = status_map.get(status, ('❓', status, 'black'))

                file_frame = ttk.Frame(scroll_frame)
                file_frame.pack(fill="x", pady=2, padx=5)

                var = tk.BooleanVar(value=True)
                cb = ttk.Checkbutton(file_frame, variable=var)
                cb.pack(side="left")

                tk.Label(file_frame, text=f"{icon} [{status_text}]", font=("Arial", 9), fg=color, width=12,
                         anchor="w").pack(side="left", padx=5)
                tk.Label(file_frame, text=filepath, font=("Consolas", 9), anchor="w").pack(side="left", fill="x",
                                                                                           expand=True)

                file_vars[filepath] = var

            # Commit 訊息輸入區
            commit_frame = ttk.LabelFrame(main_frame, text=" Commit 訊息 (選填) ", padding=10)
            commit_frame.pack(fill="x", pady=(0, 10))

            commit_var = tk.StringVar()
            ttk.Entry(commit_frame, textvariable=commit_var, font=("Consolas", 10)).pack(fill="x")
            ttk.Label(commit_frame, text="提示：留空則不會 commit，只執行 add/stash", font=("Arial", 8),
                      foreground="gray").pack(anchor="w", pady=(3, 0))

            # 按鈕區域邏輯
            def get_selected():
                return [f for f, v in file_vars.items() if v.get()]

            def on_add():
                selected = get_selected()
                if not selected: return messagebox.showwarning("警告", "請至少選擇一個檔案")
                for fp in selected: executor.run(f'git add "{fp}"')
                dialog.destroy()

            def on_add_commit():
                selected = get_selected()
                if not selected: return messagebox.showwarning("警告", "請至少選擇一個檔案")
                msg = commit_var.get().strip()
                if not msg: return messagebox.showwarning("警告", "請輸入 Commit 訊息")

                for fp in selected: executor.run(f'git add "{fp}"')
                executor.run(f'git commit -m "{msg}"')
                dialog.destroy()

            def on_stash():
                selected = get_selected()
                if not selected: return messagebox.showwarning("警告", "請至少選擇一個檔案")
                for fp in selected: executor.run(f'git add "{fp}"')
                msg = commit_var.get().strip() or "Stashed changes"
                executor.run(f'git stash push -m "{msg}"')
                dialog.destroy()

            def on_stash_rest():
                selected = get_selected()  # 這些是要保留在工作區的
                # 先 Add 選中的 (保留工作區狀態)
                for fp in selected: executor.run(f'git add "{fp}"')
                msg = "Stashed unselected files"
                executor.run(f'git stash push --keep-index -m "{msg}"')
                dialog.destroy()

            # 按鈕配置
            btn_frame = ttk.Frame(main_frame)
            btn_frame.pack(fill="x")

            # 左側輔助選取
            left_btns = ttk.Frame(btn_frame)
            left_btns.pack(side="left")
            ttk.Button(left_btns, text="全選", command=lambda: [v.set(True) for v in file_vars.values()], width=8).pack(
                side="left", padx=2)
            ttk.Button(left_btns, text="全不選", command=lambda: [v.set(False) for v in file_vars.values()],
                       width=8).pack(side="left", padx=2)

            # 右側執行動作
            right_btns = ttk.Frame(btn_frame)
            right_btns.pack(side="right")
            ttk.Button(right_btns, text="✓ Add", command=on_add, width=10).pack(side="left", padx=2)
            ttk.Button(right_btns, text="✓ Add+Commit", command=on_add_commit, width=13).pack(side="left", padx=2)
            ttk.Button(right_btns, text="📦 Stash 選中", command=on_stash, width=12).pack(side="left", padx=2)
            ttk.Button(right_btns, text="📦 Stash 其他", command=on_stash_rest, width=12).pack(side="left", padx=2)
            ttk.Button(right_btns, text="✗ 取消", command=dialog.destroy, width=8).pack(side="left", padx=2)

        except Exception as e:
            messagebox.showerror("錯誤", f"無法獲取檔案列表: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = GitAdvancedTool(root)
    root.mainloop()