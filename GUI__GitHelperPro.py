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
        self.root.title("Git Helper Pro - 進階Git版控小工具 - v1.0.0")
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

    def open_rebase_onto_dialog(self, executor):
        """Rebase --onto 對話框：三個欄位可點選下拉填寫"""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title("Rebase --onto")
        dialog.geometry("580x430")
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{rx + (rw // 2) - (dw // 2)}+{ry + (rh // 2) - (dh // 2)}")

        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill="both", expand=True)

        # 說明區
        info_frame = ttk.LabelFrame(main_frame, text=" 📌 指令說明 ", padding=8)
        info_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(info_frame, text="git rebase --onto <newbase> <upstream> [<branch>]",
                  font=("Consolas", 9), foreground="#555").pack(anchor="w")
        ttk.Label(info_frame, text="把 upstream 之後（不含）到 branch 之間的 commit，搬到 newbase 的上面",
                  font=("Arial", 9), foreground="#333").pack(anchor="w", pady=(3, 0))
        ttk.Label(info_frame,
                  text="範例：只把 feature 最後 3 個 commit 搬到 main → newbase=main，upstream=HEAD~3",
                  font=("Arial", 8), foreground="#888").pack(anchor="w", pady=(2, 0))

        # 載入下拉選項
        def get_branches():
            try:
                res = subprocess.run("git branch -a", cwd=repo_path, shell=True,
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
                items = [b.strip().replace("* ", "").strip() for b in res.stdout.splitlines() if b.strip()]
                return sorted(set(items))
            except:
                return []

        def get_short_commits():
            try:
                res = subprocess.run("git log --oneline -n 30", cwd=repo_path, shell=True,
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
                return [line.strip() for line in res.stdout.splitlines() if line.strip()]
            except:
                return []

        branches = get_branches()
        commit_lines = get_short_commits()
        commit_hashes = [c.split()[0] for c in commit_lines]
        head_shortcuts = ["HEAD~1", "HEAD~2", "HEAD~3", "HEAD~5", "HEAD~10"]

        # 三組 Combobox 欄位
        fields_frame = ttk.Frame(main_frame)
        fields_frame.pack(fill="x", pady=(0, 12))
        fields_frame.columnconfigure(1, weight=1)

        newbase_var = tk.StringVar(value=branches[0] if branches else "main")
        upstream_var = tk.StringVar(value="HEAD~3")
        branch_var = tk.StringVar(value="")

        field_defs = [
            (0, "New Base *",
             "commit 要搬到哪裡的上面（目標基底，例如：main、dev、某個 hash）",
             newbase_var, branches + head_shortcuts + commit_hashes),
            (1, "Upstream *",
             "搬移起點（不含此點）：此點之後的 commit 才會被搬移（例如：HEAD~3、某個 hash）",
             upstream_var, head_shortcuts + commit_hashes + branches),
            (2, "Branch",
             "要操作的分支（留空 = 使用當前分支 HEAD）",
             branch_var, [""] + branches),
        ]

        comboboxes = []
        for row, label, hint, var, choices in field_defs:
            ttk.Label(fields_frame, text=label, font=("Arial", 9, "bold")).grid(
                row=row * 2, column=0, sticky="nw", padx=(0, 10), pady=(10, 0))
            cb = ttk.Combobox(fields_frame, textvariable=var, values=choices,
                              font=("Consolas", 10), state="normal")
            cb.grid(row=row * 2, column=1, sticky="ew", pady=(10, 0))
            ttk.Label(fields_frame, text=hint, font=("Arial", 8), foreground="#777").grid(
                row=row * 2 + 1, column=1, sticky="w", padx=(2, 0))
            comboboxes.append(cb)

        # 即時預覽
        preview_var = tk.StringVar()

        def update_preview(*_):
            nb = newbase_var.get().strip()
            up = upstream_var.get().strip()
            br = branch_var.get().strip()
            cmd = f"git rebase --onto {nb or '<newbase>'} {up or '<upstream>'}"
            if br:
                cmd += f" {br}"
            preview_var.set(cmd)

        for v in (newbase_var, upstream_var, branch_var):
            v.trace_add("write", update_preview)
        update_preview()

        preview_frame = ttk.LabelFrame(main_frame, text=" 📋 指令預覽 ", padding=8)
        preview_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(preview_frame, textvariable=preview_var,
                  font=("Consolas", 10), foreground="#0066cc").pack(anchor="w")

        # 按鈕列
        def on_execute():
            nb = newbase_var.get().strip()
            up = upstream_var.get().strip()
            br = branch_var.get().strip()
            if not nb or not up:
                messagebox.showwarning("參數不完整", "New Base 與 Upstream 為必填欄位！")
                return
            cmd = f"git rebase --onto {nb} {up}"
            if br:
                cmd += f" {br}"
            executor.run(cmd)
            dialog.destroy()

        btn_bar = ttk.Frame(main_frame)
        btn_bar.pack(fill="x")
        ttk.Button(btn_bar, text="✓ 執行 Rebase --onto", command=on_execute, width=22).pack(side="right", padx=2)
        ttk.Button(btn_bar, text="✗ 取消", command=dialog.destroy, width=10).pack(side="right", padx=2)

        comboboxes[0].focus_set()

    def open_merge_dialog(self, executor):
        """Merge 對話框：支援一般、--no-ff、--squash、--ff-only 四種模式"""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title("Merge - 合併分支")
        dialog.geometry("600x630")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        dialog.update_idletasks()
        rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{rx + (rw // 2) - (dw // 2)}+{ry + (rh // 2) - (dh // 2)}")

        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)

        # === 說明區 ===
        info_frame = ttk.LabelFrame(main_frame, text=" 📌 指令說明 ", padding=8)
        info_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(info_frame, text="git merge <來源分支>  [--no-ff | --squash | --ff-only]",
                  font=("Consolas", 9), foreground="#555").pack(anchor="w")
        ttk.Label(info_frame, text="將指定分支的提交合併進目前所在的分支",
                  font=("Arial", 9), foreground="#333").pack(anchor="w", pady=(3, 4))
        mode_descs = [
            ("一般 (預設)",  "Git 自行決定：能 fast-forward 就接上，否則建立 merge commit"),
            ("--no-ff",      "強制建立 merge commit，保留分支歷史脈絡，推薦 feature → 主線"),
            ("--squash",     "所有 commit 壓成一筆變更放入暫存區，需手動 commit"),
            ("--ff-only",    "只允許 fast-forward，無法時直接失敗，適合嚴格線性歷史"),
        ]
        for mode, desc in mode_descs:
            row = ttk.Frame(info_frame)
            row.pack(anchor="w", fill="x", pady=1)
            ttk.Label(row, text=f"  {mode}", font=("Consolas", 8), foreground="#0066cc",
                      width=14, anchor="w").pack(side="left")
            ttk.Label(row, text=desc, font=("Arial", 8), foreground="#555").pack(side="left")

        # === 共用函式 ===
        def get_current_branch():
            try:
                r = subprocess.run("git rev-parse --abbrev-ref HEAD", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                cur = r.stdout.strip()
                if not cur or cur == "HEAD":
                    r2 = subprocess.run("git rev-parse --short HEAD", cwd=repo_path, shell=True,
                                        capture_output=True, text=True, encoding='utf-8', errors='replace')
                    cur = f"(detached) {r2.stdout.strip()}" or "(unknown)"
                return cur
            except:
                return "(unknown)"

        def get_branches():
            try:
                res = subprocess.run("git branch -a", cwd=repo_path, shell=True,
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
                items = [b.strip().replace("* ", "").replace("remotes/", "").strip()
                         for b in res.stdout.splitlines() if b.strip()]
                return sorted(set(items))
            except:
                return []

        def get_short_commits():
            try:
                res = subprocess.run("git log --oneline -n 30", cwd=repo_path, shell=True,
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
                return [line.strip() for line in res.stdout.splitlines() if line.strip()]
            except:
                return []

        branches = get_branches()
        commit_hashes = [c.split()[0] for c in get_short_commits()]

        # === 本分支列 ===
        cur_lf = ttk.LabelFrame(main_frame, text=" 🌿 目前分支 ", padding=8)
        cur_lf.pack(fill="x", pady=(0, 10))
        current_var = tk.StringVar(value=get_current_branch())
        cur_row = ttk.Frame(cur_lf)
        cur_row.pack(fill="x")
        ttk.Label(cur_row, textvariable=current_var, font=("Consolas", 11), foreground="#0066cc").pack(side="left")
        ttk.Button(cur_row, text="↻ Refresh", command=lambda: current_var.set(get_current_branch()),
                   width=10).pack(side="right")
        ttk.Label(cur_lf, text="合併後的結果會套用到這個分支上",
                  font=("Arial", 8), foreground="#888").pack(anchor="w", pady=(4, 0))

        # === 欄位區 ===
        fields_lf = ttk.LabelFrame(main_frame, text=" ⚙️ 參數設定 ", padding=10)
        fields_lf.pack(fill="x", pady=(0, 10))
        fields_lf.columnconfigure(1, weight=1)

        source_var = tk.StringVar(value="")
        mode_var = tk.StringVar(value="normal")

        # 來源分支
        ttk.Label(fields_lf, text="來源分支 *", font=("Arial", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 2))
        source_cb = ttk.Combobox(fields_lf, textvariable=source_var,
                                 values=branches + commit_hashes, font=("Consolas", 10), state="normal")
        source_cb.grid(row=0, column=1, sticky="ew", pady=(0, 2))

        def checkout_source():
            src = source_var.get().strip()
            if not src:
                messagebox.showwarning("參數缺失", "請先選擇來源分支或 commit")
                return
            res = executor.run(f"git checkout {src}")
            if res is None:
                messagebox.showerror("執行失敗", "執行 checkout 時發生錯誤，請查看 Terminal 日誌。")
                return
            if getattr(res, 'returncode', 1) == 0:
                current_var.set(get_current_branch())
                messagebox.showinfo("完成", f"已切換到: {src}")
            else:
                stderr = (res.stderr or res.stdout or "").strip()
                messagebox.showerror("切換失敗", f"切換分支失敗：\n{stderr}")

        hint_row = ttk.Frame(fields_lf)
        hint_row.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(hint_row, text="要合併進來的分支（合進目前分支）",
                  font=("Arial", 8), foreground="#777").pack(side="left")
        ttk.Button(hint_row, text="↪ 先切換到此分支", command=checkout_source,
                   width=16).pack(side="right")

        # 合併模式
        ttk.Label(fields_lf, text="合併模式", font=("Arial", 9, "bold")).grid(
            row=2, column=0, sticky="nw", padx=(0, 10), pady=(4, 0))
        mode_frame = ttk.Frame(fields_lf)
        mode_frame.grid(row=2, column=1, sticky="w", pady=(4, 0))
        for val, lbl, hint in [
            ("normal",    "一般 (預設)",           "Git 自行決定合併方式"),
            ("--no-ff",   "強制 merge commit",     "保留分支歷史，推薦 feature → main"),
            ("--squash",  "壓縮 commit (squash)",  "壓成一筆需手動 commit"),
            ("--ff-only", "僅 fast-forward",       "無法 FF 則失敗，嚴格線性"),
        ]:
            r = ttk.Frame(mode_frame)
            r.pack(anchor="w", fill="x", pady=1)
            ttk.Radiobutton(r, text=lbl, variable=mode_var, value=val, width=22).pack(side="left")
            ttk.Label(r, text=hint, font=("Arial", 8), foreground="#888").pack(side="left")

        # === 預覽 ===
        preview_var = tk.StringVar()

        def update_preview(*_):
            src = source_var.get().strip() or '<branch>'
            mode = mode_var.get()
            preview_var.set(f"git merge {src}" if mode == "normal" else f"git merge {mode} {src}")

        source_var.trace_add("write", update_preview)
        mode_var.trace_add("write", update_preview)
        update_preview()

        preview_frame = ttk.LabelFrame(main_frame, text=" 📋 指令預覽 ", padding=8)
        preview_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(preview_frame, textvariable=preview_var,
                  font=("Consolas", 10), foreground="#0066cc").pack(anchor="w")

        # === 按鈕列 ===
        def on_execute():
            src = source_var.get().strip()
            if not src:
                messagebox.showwarning("參數不完整", "請選擇來源分支或輸入 commit hash！")
                return
            mode = mode_var.get()
            cmd = f"git merge {src}" if mode == "normal" else f"git merge {mode} {src}"
            executor.run(cmd)
            dialog.destroy()

        btn_bar = ttk.Frame(main_frame)
        btn_bar.pack(fill="x")
        ttk.Button(btn_bar, text="✓ 執行 Merge", command=on_execute, width=16).pack(side="right", padx=2)
        ttk.Button(btn_bar, text="✗ 取消", command=dialog.destroy, width=10).pack(side="right", padx=2)
        ttk.Button(btn_bar, text="🛑 Abort",
                   command=lambda: (executor.run_simple("merge --abort"), dialog.destroy()),
                   width=10, style="Danger.TButton").pack(side="left", padx=2)
        ttk.Button(btn_bar, text="▶️ Continue",
                   command=lambda: (executor.run_simple("merge --continue"), dialog.destroy()),
                   width=14).pack(side="left", padx=2)

        source_cb.focus_set()

    def open_checkout_dialog(self, executor):
        """Checkout 搜尋器：可搜尋 branch / origin/branch / tag / commit，支援 -b 建立新分支"""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title("Checkout - 切換分支 / Commit")
        dialog.geometry("580x490")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        dialog.update_idletasks()
        rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{rx + (rw // 2) - (dw // 2)}+{ry + (rh // 2) - (dh // 2)}")

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        # === 說明區 ===
        info_frame = ttk.LabelFrame(main, text=" 📌 指令說明 ", padding=8)
        info_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(info_frame, text="git checkout <target>      切換到分支、tag 或 commit",
                  font=("Consolas", 9), foreground="#555").pack(anchor="w")
        ttk.Label(info_frame, text="git checkout -b <name>     建立新分支並立刻切換過去",
                  font=("Consolas", 9), foreground="#555").pack(anchor="w", pady=(2, 0))
        ttk.Label(info_frame, text="支援：本地 branch、origin/branch、tag、commit hash",
                  font=("Arial", 8), foreground="#888").pack(anchor="w", pady=(4, 0))

        # === 共用函式 ===
        def get_current_branch():
            try:
                r = subprocess.run("git rev-parse --abbrev-ref HEAD", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                cur = r.stdout.strip()
                if not cur or cur == "HEAD":
                    r2 = subprocess.run("git rev-parse --short HEAD", cwd=repo_path, shell=True,
                                        capture_output=True, text=True, encoding='utf-8', errors='replace')
                    cur = f"(detached) {r2.stdout.strip()}" or "(unknown)"
                return cur
            except:
                return "(unknown)"

        def get_candidates(prefix):
            try:
                res_b = subprocess.run("git branch -a", cwd=repo_path, shell=True,
                                       capture_output=True, text=True, encoding='utf-8', errors='replace')
                branches = [b.strip().replace('* ', '').replace('remotes/', '')
                            for b in res_b.stdout.splitlines() if b.strip()]
                res_t = subprocess.run("git tag -l", cwd=repo_path, shell=True,
                                       capture_output=True, text=True, encoding='utf-8', errors='replace')
                tags = [t.strip() for t in res_t.stdout.splitlines() if t.strip()]
                res_c = subprocess.run("git log --oneline -n 60", cwd=repo_path, shell=True,
                                       capture_output=True, text=True, encoding='utf-8', errors='replace')
                commits = [line.split()[0] for line in res_c.stdout.splitlines() if line.strip()]
                candidates = list(dict.fromkeys(branches + tags + commits))
                if not prefix:
                    return candidates[:50]
                p = prefix.lower()
                return [c for c in candidates if p in c.lower()][:50]
            except:
                return []

        # === 本分支列 ===
        cur_lf = ttk.LabelFrame(main, text=" 🌿 目前分支 ", padding=8)
        cur_lf.pack(fill="x", pady=(0, 10))
        current_var = tk.StringVar(value=get_current_branch())
        cur_row = ttk.Frame(cur_lf)
        cur_row.pack(fill="x")
        ttk.Label(cur_row, textvariable=current_var, font=("Consolas", 11), foreground="#0066cc").pack(side="left")
        ttk.Button(cur_row, text="↻ Refresh", command=lambda: current_var.set(get_current_branch()),
                   width=10).pack(side="right")

        # === 搜尋與清單 ===
        search_lf = ttk.LabelFrame(main, text=" 🔍 搜尋目標 ", padding=10)
        search_lf.pack(fill="both", expand=True, pady=(0, 10))
        search_lf.columnconfigure(0, weight=1)

        entry_var = tk.StringVar()
        entry = ttk.Entry(search_lf, textvariable=entry_var, font=("Consolas", 11))
        entry.pack(fill="x", pady=(0, 4))
        ttk.Label(search_lf, text="即時過濾：輸入關鍵字篩選 branch / origin/branch / tag / hash",
                  font=("Arial", 8), foreground="#888").pack(anchor="w", pady=(0, 6))

        listbox_frame = ttk.Frame(search_lf)
        listbox_frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(listbox_frame, font=("Consolas", 10), activestyle="dotbox",
                             selectbackground="#cce5ff", selectforeground="#000")
        lb_scroll = ttk.Scrollbar(listbox_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=lb_scroll.set)
        lb_scroll.pack(side="right", fill="y")
        listbox.pack(side="left", fill="both", expand=True)

        def update_listbox(*_):
            items = get_candidates(entry_var.get().strip())
            listbox.delete(0, tk.END)
            for it in items:
                listbox.insert(tk.END, it)

        entry_var.trace_add("write", update_listbox)
        update_listbox()

        def on_lb_select(e=None):
            if listbox.curselection():
                entry_var.set(listbox.get(listbox.curselection()[0]))

        listbox.bind('<<ListboxSelect>>', on_lb_select)
        listbox.bind('<Double-Button-1>', lambda e: on_execute())

        # === 選項列 ===
        opt_frame = ttk.Frame(main)
        opt_frame.pack(fill="x", pady=(0, 6))
        cb_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="建立新分支 (-b)", variable=cb_var).pack(side="left")

        # === 預覽 ===
        preview_lf = ttk.LabelFrame(main, text=" 📋 指令預覽 ", padding=8)
        preview_lf.pack(fill="x", pady=(0, 10))
        preview_var = tk.StringVar()
        ttk.Label(preview_lf, textvariable=preview_var, font=("Consolas", 10), foreground="#0066cc").pack(anchor="w")

        def update_preview(*_):
            t = entry_var.get().strip() or '<target>'
            preview_var.set(f"git checkout -b {t}" if cb_var.get() else f"git checkout {t}")

        entry_var.trace_add("write", update_preview)
        cb_var.trace_add("write", update_preview)
        update_preview()

        # === 按鈕列 ===
        def on_execute():
            target = entry_var.get().strip()
            if not target:
                messagebox.showwarning("參數缺失", "請輸入或選擇分支、tag 或 commit hash")
                return
            cmd = f"git checkout -b {target}" if cb_var.get() else f"git checkout {target}"
            res = executor.run(cmd)
            if res is None:
                messagebox.showerror("執行失敗", "執行指令時發生錯誤，請查看 Terminal 日誌。")
                return
            if getattr(res, 'returncode', 1) == 0:
                current_var.set(get_current_branch())
                messagebox.showinfo("完成", f"已切換到: {target}")
                dialog.destroy()
            else:
                stderr = (res.stderr or res.stdout or "").strip()
                messagebox.showerror("切換失敗", f"切換失敗：\n{stderr}")

        btn_bar = ttk.Frame(main)
        btn_bar.pack(fill="x")
        ttk.Button(btn_bar, text="✓ 執行 Checkout", command=on_execute, width=16).pack(side="right", padx=2)
        ttk.Button(btn_bar, text="✗ 取消", command=dialog.destroy, width=10).pack(side="right", padx=2)

        entry.focus_set()

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