import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os


class GitCommandDialog:
    """彈出式指令參數設定視窗"""

    def __init__(self, parent, command_name, params_config):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"設定參數 - {command_name}")
        self.dialog.geometry("500x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # 參數配置：[{name, label, required, type(text/toggle), default}]
        self.params_config = params_config
        self.param_widgets = {}

        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (self.dialog.winfo_width() // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")

    def _build_ui(self):
        main_frame = ttk.Frame(self.dialog, padding=15)
        main_frame.pack(fill="both", expand=True)

        # 標題
        title = ttk.Label(main_frame, text="請填寫指令參數", font=("Arial", 12, "bold"))
        title.pack(pady=(0, 15))

        # 捲動區域
        canvas = tk.Canvas(main_frame, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", on_configure)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 動態生成參數欄位
        for i, param in enumerate(self.params_config):
            frame = ttk.Frame(scroll_frame)
            frame.pack(fill="x", pady=8, padx=5)

            if param['type'] == 'text':
                # 文字輸入框
                label_text = param['label']
                if param['required']:
                    label_text += " *"

                label = ttk.Label(frame, text=label_text, foreground="red" if param['required'] else "black")
                label.pack(anchor="w")

                entry_frame = ttk.Frame(frame)
                entry_frame.pack(fill="x", pady=(3, 0))

                var = tk.StringVar(value=param.get('default', ''))
                entry = ttk.Entry(entry_frame, textvariable=var, font=("Consolas", 10))
                entry.pack(fill="x")

                self.param_widgets[param['name']] = {
                    'type': 'text',
                    'var': var,
                    'required': param['required'],
                    'widget': entry,
                    'frame': entry_frame
                }

            elif param['type'] == 'toggle':
                # 開關選項
                var = tk.BooleanVar(value=param.get('default', False))
                cb = ttk.Checkbutton(frame, text=param['label'], variable=var)
                cb.pack(anchor="w")

                self.param_widgets[param['name']] = {
                    'type': 'toggle',
                    'var': var,
                    'required': False
                }

        # 底部按鈕
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(15, 0))

        ttk.Button(btn_frame, text="✓ 執行", command=self._on_submit, width=15).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="✗ 取消", command=self._on_cancel, width=15).pack(side="right")

    def _validate_and_highlight(self):
        """驗證並標記必填欄位"""
        all_valid = True

        for name, widget_info in self.param_widgets.items():
            if widget_info['type'] == 'text' and widget_info['required']:
                value = widget_info['var'].get().strip()
                if not value:
                    # 紅框標記
                    widget_info['widget'].configure(style='Error.TEntry')
                    all_valid = False
                else:
                    widget_info['widget'].configure(style='TEntry')

        return all_valid

    def _on_submit(self):
        # 創建錯誤樣式
        style = ttk.Style()
        style.configure('Error.TEntry', fieldbackground='#ffe6e6', bordercolor='red', borderwidth=2)

        if not self._validate_and_highlight():
            messagebox.showwarning("參數不完整", "請填寫所有標記 * 的必填欄位！")
            return

        # 收集結果
        self.result = {}
        for name, widget_info in self.param_widgets.items():
            if widget_info['type'] == 'text':
                self.result[name] = widget_info['var'].get().strip()
            elif widget_info['type'] == 'toggle':
                self.result[name] = widget_info['var'].get()

        self.dialog.destroy()

    def _on_cancel(self):
        self.result = None
        self.dialog.destroy()

    def show(self):
        self.dialog.wait_window()
        return self.result


class GitAdvancedTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Git Pro Organizer - 智能參數管理")
        self.root.geometry("1300x850")

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TFrame", background="#f0f0f0")
        self.style.configure("TLabelframe", background="#f0f0f0")

        # 指令參數定義
        self._init_command_configs()

        # 頂部工具列
        self.toolbar = ttk.Frame(self.root, padding=5)
        self.toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Button(self.toolbar, text="+ 開啟新專案分頁", command=self.open_directory).grid(row=0, column=0, padx=5)

        # 主 Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

    def _init_command_configs(self):
        """定義所有 Git 指令的參數配置"""
        self.command_configs = {
            # === Branch 相關 ===
            'checkout_branch': {
                'name': '建立並切換分支',
                'base_cmd': 'checkout',
                'params': [
                    {'name': 'branch', 'label': '新分支名稱', 'required': True, 'type': 'text'},
                    {'name': 'create', 'label': '建立新分支 (-b)', 'required': True, 'type': 'toggle', 'default': True}
                ]
            },

            # === Rebase 系列 ===
            'rebase_branch': {
                'name': 'Rebase 到分支',
                'base_cmd': 'rebase',
                'params': [
                    {'name': 'branch', 'label': '目標分支', 'required': True, 'type': 'text', 'default': 'main'}
                ]
            },
            'rebase_interactive': {
                'name': 'Rebase Interactive',
                'base_cmd': 'rebase',
                'params': [
                    {'name': 'commit', 'label': '起始 Commit (HEAD~N 或 Hash)', 'required': True, 'type': 'text',
                     'default': 'HEAD~5'},
                    {'name': 'interactive', 'label': '互動模式 (-i)', 'required': True, 'type': 'toggle',
                     'default': True}
                ]
            },

            # === Cherry-pick 系列 ===
            'cherry_pick': {
                'name': 'Cherry-pick',
                'base_cmd': 'cherry-pick',
                'params': [
                    {'name': 'commit', 'label': 'Commit Hash (可多個，空格分隔)', 'required': True, 'type': 'text'},
                    {'name': 'no_commit', 'label': '不自動提交 (-n)', 'required': False, 'type': 'toggle'}
                ]
            },

            # === Reset 系列 ===
            'reset_soft': {
                'name': 'Soft Reset',
                'base_cmd': 'reset',
                'params': [
                    {'name': 'commit', 'label': '目標 Commit (HEAD~N 或 Hash)', 'required': True, 'type': 'text',
                     'default': 'HEAD~1'},
                    {'name': 'soft', 'label': 'Soft 模式 (保留修改)', 'required': True, 'type': 'toggle',
                     'default': True}
                ]
            },
            'reset_hard': {
                'name': 'Hard Reset',
                'base_cmd': 'reset',
                'params': [
                    {'name': 'commit', 'label': '目標 Commit (HEAD~N 或 Hash)', 'required': True, 'type': 'text',
                     'default': 'HEAD~1'},
                    {'name': 'hard', 'label': 'Hard 模式 (捨棄所有修改 ⚠️)', 'required': True, 'type': 'toggle',
                     'default': True}
                ]
            },

            # === Stash 系列 ===
            'stash_commit': {
                'name': 'Stash → Commit Squash',
                'base_cmd': 'custom',  # 特殊處理
                'custom_handler': 'handle_stash_commit',
                'params': [
                    {'name': 'message', 'label': 'Commit 訊息 (預設: WIP)', 'required': False, 'type': 'text',
                     'default': 'WIP'}
                ]
            },

            # === Commit 系列 ===
            'commit_amend': {
                'name': 'Commit Amend',
                'base_cmd': 'commit',
                'params': [
                    {'name': 'message', 'label': 'Commit 訊息 (留空則不改)', 'required': False, 'type': 'text'},
                    {'name': 'amend', 'label': '修改上次提交 (--amend)', 'required': True, 'type': 'toggle',
                     'default': True},
                    {'name': 'no_edit', 'label': '不修改訊息 (--no-edit)', 'required': False, 'type': 'toggle'}
                ]
            },
            'commit_squash': {
                'name': 'Squash Commit',
                'base_cmd': 'commit',
                'params': [
                    {'name': 'message', 'label': 'Squash 訊息', 'required': True, 'type': 'text', 'default': 's'}
                ]
            },

            # === Push 系列 ===
            'force_push': {
                'name': 'Force Push',
                'base_cmd': 'push',
                'params': [
                    {'name': 'remote', 'label': '遠端名稱', 'required': False, 'type': 'text', 'default': 'origin'},
                    {'name': 'branch', 'label': '分支名稱 (留空=當前)', 'required': False, 'type': 'text'},
                    {'name': 'force', 'label': '強制推送 (-f)', 'required': True, 'type': 'toggle', 'default': True},
                    {'name': 'force_with_lease', 'label': '安全強推 (--force-with-lease)', 'required': False,
                     'type': 'toggle'}
                ]
            },

            # === Branch 系列 ===
            'delete_branch': {
                'name': 'Delete Branch',
                'base_cmd': 'branch',
                'params': [
                    {'name': 'branch', 'label': '分支名稱 (可多個，空格分隔)', 'required': True, 'type': 'text'},
                    {'name': 'force_delete', 'label': '強制刪除 (-D)', 'required': True, 'type': 'toggle',
                     'default': True}
                ]
            },
            'delete_remote_branch': {
                'name': 'Delete Remote Branch',
                'base_cmd': 'push',
                'params': [
                    {'name': 'remote', 'label': '遠端名稱', 'required': False, 'type': 'text', 'default': 'origin'},
                    {'name': 'branch', 'label': '分支名稱', 'required': True, 'type': 'text'},
                    {'name': 'delete', 'label': '刪除遠端分支 (--delete)', 'required': True, 'type': 'toggle',
                     'default': True}
                ]
            },
            'prune_branches': {
                'name': 'Prune Branches',
                'base_cmd': 'custom',
                'custom_handler': 'handle_prune_branches',
                'params': [
                    {'name': 'remote', 'label': '遠端名稱', 'required': False, 'type': 'text', 'default': 'origin'},
                    {'name': 'dry_run', 'label': '僅預覽 (--dry-run)', 'required': False, 'type': 'toggle'}
                ]
            },

            # === Tag 系列 ===
            'create_tag': {
                'name': 'Create Tag',
                'base_cmd': 'tag',
                'params': [
                    {'name': 'tag', 'label': 'Tag 名稱', 'required': True, 'type': 'text'},
                    {'name': 'message', 'label': 'Tag 訊息 (-m)', 'required': False, 'type': 'text'},
                    {'name': 'commit', 'label': '指定 Commit (留空=HEAD)', 'required': False, 'type': 'text'}
                ]
            },
            'delete_tag': {
                'name': 'Delete Tag',
                'base_cmd': 'tag',
                'params': [
                    {'name': 'tag', 'label': 'Tag 名稱 (可多個，空格分隔)', 'required': True, 'type': 'text'},
                    {'name': 'delete', 'label': '刪除標籤 (-d)', 'required': True, 'type': 'toggle', 'default': True}
                ]
            },
            'delete_remote_tag': {
                'name': '刪除遠端標籤',
                'base_cmd': 'push',
                'params': [
                    {'name': 'remote', 'label': '遠端名稱', 'required': False, 'type': 'text', 'default': 'origin'},
                    {'name': 'tag', 'label': 'Tag 名稱', 'required': True, 'type': 'text'},
                    {'name': 'delete', 'label': '刪除 (--delete)', 'required': True, 'type': 'toggle', 'default': True}
                ]
            },

            # === 其他 ===
            'checkout_file': {
                'name': 'Checkout File',
                'base_cmd': 'checkout',
                'params': [
                    {'name': 'source', 'label': '來源 (Commit/Branch，留空=HEAD)', 'required': False, 'type': 'text'},
                    {'name': 'file', 'label': '檔案路徑', 'required': True, 'type': 'text'}
                ]
            }
        }

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

        # === 左側：指令區 (含完善的 Scrollbar 與滾輪支援) ===
        side_container = ttk.Frame(main_frame, width=320)
        side_container.grid(row=0, column=0, sticky="ns", padx=(5, 2))
        side_container.grid_propagate(False)

        canvas = tk.Canvas(side_container, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(side_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        # 滾動窗口配置
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # --- 自動調整 Canvas 寬度與捲動區域 ---
        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_window, width=e.width)

        scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # --- 綁定滑鼠滾輪事件 (關鍵修正) ---
        def _on_mousewheel(event):
            # Windows 用 delta, Linux 用 num (4/5)
            if event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")

        # 遞迴綁定所有子元件，確保滑鼠指在哪都能捲動
        def bind_mouse_wheel(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)
            widget.bind("<Button-5>", _on_mousewheel)
            for child in widget.winfo_children():
                bind_mouse_wheel(child)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 建立 UI 後執行綁定
        self.build_command_ui(scrollable_frame, path)
        bind_mouse_wheel(canvas)

        # === 右側：顯示面板 ===
        display_panel = ttk.Frame(main_frame)
        display_panel.grid(row=0, column=1, sticky="nsew", padx=5)
        display_panel.columnconfigure(0, weight=1)
        display_panel.rowconfigure(1, weight=3)  # Adog 區域
        display_panel.rowconfigure(4, weight=2)  # Terminal 區域

        # Adog 視覺化
        ttk.Label(display_panel, text="Git Adog 圖表:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w",
                                                                                        pady=(5, 0))
        adog_text = tk.Text(display_panel, bg="#ffffff", height=15, font=("Consolas", 10), wrap="none")
        adog_text.grid(row=1, column=0, sticky="nsew")

        adog_h_scroll = ttk.Scrollbar(display_panel, orient="horizontal", command=adog_text.xview)
        adog_h_scroll.grid(row=2, column=0, sticky="ew")
        adog_text.configure(xscrollcommand=adog_h_scroll.set)

        # Terminal 輸出
        ttk.Label(display_panel, text="執行輸出:", font=("Arial", 9, "bold")).grid(row=3, column=0, sticky="w",
                                                                                   pady=(5, 0))
        terminal = tk.Text(display_panel, bg="#1e1e1e", fg="#ffffff", font=("Consolas", 10))
        terminal.grid(row=4, column=0, sticky="nsew")

        # 底部工具欄
        ctrl_bar = ttk.Frame(display_panel)
        ctrl_bar.grid(row=5, column=0, sticky="ew", pady=5)
        ttk.Button(ctrl_bar, text="🔄 刷新", width=10, command=lambda: self.refresh_adog(path, adog_text)).pack(
            side="left", padx=2)
        ttk.Button(ctrl_bar, text="🕒 Reflog", width=10, command=lambda: self.view_reflog(path, adog_text)).pack(
            side="left", padx=2)

        self.refresh_adog(path, adog_text)

    def build_command_ui(self, parent, path):
        row_counter = 0

        # --- 快速指令輸入區 ---
        quick_frame = ttk.LabelFrame(parent, text=" ⚡ 快速執行 ")
        quick_frame.grid(row=row_counter, column=0, sticky="ew", padx=5, pady=5)
        row_counter += 1

        entry_var = tk.StringVar()
        entry = ttk.Entry(quick_frame, textvariable=entry_var, font=("Consolas", 10))
        entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        def run_q():
            cmd = entry_var.get().strip()
            if cmd:
                self.execute_git_command(f"git {cmd}" if not cmd.startswith("git ") else cmd, path)
                entry_var.set("")

        ttk.Button(quick_frame, text="執行", width=8, command=run_q).pack(side="right", padx=5)
        entry.bind("<Return>", lambda e: run_q())

        # --- 按鈕群組配置 ---
        # 格式: (標題, [ (按鈕文字, 指令/Key, 寬度) ], 每行幾個)
        layout_configs = [
            ("🛠️ 快速互動 Rebase", [
                ("HEAD~2", lambda: self.execute_simple_git("rebase -i HEAD~2", path), 8),
                ("HEAD~4", lambda: self.execute_simple_git("rebase -i HEAD~4", path), 8),
                ("HEAD~10", lambda: self.execute_simple_git("rebase -i HEAD~10", path), 8),
            ], 3),

            ("🔄 Rebase 流程控制", [
                ("指定位置", 'rebase_branch', 12),
                ("互動模式", 'rebase_interactive', 12),
                ("▶️ Continue", lambda: self.execute_simple_git("rebase --continue", path), 12),
                ("🛑 Abort", lambda: self.execute_simple_git("rebase --abort", path), 12),
                ("⏭️ Skip", lambda: self.execute_simple_git("rebase --skip", path), 12),
            ], 2),

            ("⏪ Reset & 回退", [
                ("🔙 Undo Commit", lambda: self.execute_simple_git("reset --soft HEAD~1", path), 12),
                ("🧨 Soft (保留變更)", 'reset_soft', 12),
                ("⚠️ Hard (捨棄變更)", 'reset_hard', 12),
            ], 2),

            ("📝 提交與暫存", [
                ("Squash 訊息", 'commit_squash', 12),
                ("Amend 上則", 'commit_amend', 12),
                ("➕ Add All (.)", lambda: self.execute_simple_git("add .", path), 12),
            ], 3),

            ("🍒 Cherry-pick", [
                ("Cherry-pick Hash", 'cherry_pick', 24),
                ("▶️ Continue", lambda: self.execute_simple_git("cherry-pick --continue", path), 12),
                ("🛑 Abort", lambda: self.execute_simple_git("cherry-pick --abort", path), 12),
            ], 2),

            ("📦 Stash 緩衝區", [
                ("📥 Stash Save", lambda: self.execute_simple_git("stash", path), 12),
                ("📤 Stash Pop", lambda: self.execute_simple_git("stash pop", path), 12),
                ("📜 Stash List", lambda: self.execute_simple_git("stash list", path), 12),
                ("🧹 Stash Clear", lambda: self.execute_simple_git("stash clear", path), 12),
                ("🗑️ Stash Drop", lambda: self.execute_simple_git("stash drop", path), 12),
            ], 2),

            ("🌿 Branch 分支管理", [
                ("📋 List All", lambda: self.execute_simple_git("branch -a", path), 12),
                ("📌 Create Branch", 'checkout_branch', 12),
                ("✂️ Delete Local", 'delete_branch', 12),
                ("🌐 Delete Remote", 'delete_remote_branch', 12),
                ("🧹 Prune (修剪)", 'prune_branches', 12),
            ], 2),

            ("🏷️ Tag 標籤管理", [
                ("📜 List Tags", lambda: self.execute_simple_git("tag -l", path), 12),
                ("📌 Create Tag", 'create_tag', 12),
                ("🔥 Delete Local", 'delete_tag', 12),
                ("☁️ Delete Remote", 'delete_remote_tag', 12),
            ], 2),

            ("✈️ 遠端推送", [
                ("⬆️ Push", lambda: self.execute_simple_git("push", path), 12),
                ("🛰️ Push Tags", lambda: self.execute_simple_git("push --tags", path), 12),
                ("⚡ Force Push", 'force_push', 12),
            ], 3),

            ("🔍 狀態與工具", [
                ("📢 Status", lambda: self.execute_simple_git("status", path), 12),
                ("📟 Diff", lambda: self.execute_simple_git("diff", path), 12),
                ("🧽 Clean -fd", lambda: self.execute_simple_git("clean -fd", path), 12),
                ("🎯 Checkout File", 'checkout_file', 12),
            ], 2)
        ]

        # 根據配置動態生成介面
        for g_title, btns, col_count in layout_configs:
            group_box = ttk.LabelFrame(parent, text=f" {g_title} ")
            group_box.grid(row=row_counter, column=0, sticky="ew", padx=5, pady=5)
            row_counter += 1

            for i, (label, action, width) in enumerate(btns):
                r, c = divmod(i, col_count)

                # 區別指令類型
                if callable(action):
                    btn_cmd = action
                else:
                    btn_cmd = lambda k=action, p=path: self.open_command_dialog(k, p)

                btn = ttk.Button(group_box, text=label, command=btn_cmd, width=width)
                btn.grid(row=r, column=c, padx=3, pady=3, sticky="ew")

            # 讓每一欄等寬
            for col in range(col_count):
                group_box.columnconfigure(col, weight=1)

    def open_command_dialog(self, cmd_key, repo_path):
        """開啟指令參數設定對話框"""
        if cmd_key not in self.command_configs:
            messagebox.showerror("錯誤", f"未定義的指令: {cmd_key}")
            return

        config = self.command_configs[cmd_key]
        dialog = GitCommandDialog(self.root, config['name'], config['params'])
        result = dialog.show()

        if result:
            self.execute_configured_git(config, result, repo_path)

    def execute_configured_git(self, config, params, repo_path):
        """根據參數配置執行 Git 指令"""
        if config.get('base_cmd') == 'custom' and 'custom_handler' in config:
            handler_name = config['custom_handler']
            handler = getattr(self, handler_name, None)
            if handler:
                handler(params, repo_path)
                return

        # --- 修正組裝邏輯 ---
        cmd_parts = ['git', config['base_cmd']]

        # 提取特殊的 flag (例如 -b, -i, --soft 等)
        flags = []
        args = []

        for param_def in config['params']:
            name = param_def['name']
            value = params.get(name)

            if param_def['type'] == 'toggle' and value:
                flag_map = {
                    'interactive': '-i', 'soft': '--soft', 'hard': '--hard',
                    'amend': '--amend', 'no_edit': '--no-edit', 'no_commit': '-n',
                    'force': '-f', 'force_with_lease': '--force-with-lease',
                    'force_delete': '-D', 'delete': '--delete',
                    'create': '-b',  # 建立分支的 flag
                    'dry_run': '--dry-run'
                }
                if name in flag_map:
                    flags.append(flag_map[name])

            elif param_def['type'] == 'text' and value:
                if name == 'message':
                    args.extend(['-m', f'"{value}"'])
                else:
                    args.append(value)

        # 關鍵順序： git + command + flags + args
        full_cmd = ' '.join(cmd_parts + flags + args)
        self.execute_git_command(full_cmd, repo_path)

    # === Custom Handlers ===

    def handle_stash_commit(self, params, repo_path):
        """Stash → Commit 's' 的自訂流程"""
        message = params.get('message', 'WIP')

        # 1. Stash
        self.execute_git_command("git stash", repo_path)

        # 2. Stash pop
        self.execute_git_command("git stash pop", repo_path)

        # 3. Add all
        self.execute_git_command("git add .", repo_path)

        # 4. Commit
        self.execute_git_command(f'git commit -m "{message}"', repo_path)

    def handle_prune_branches(self, params, repo_path):
        """清理遠端分支的自訂流程"""
        remote = params.get('remote', 'origin')
        dry_run = params.get('dry_run', False)

        # Fetch with prune
        if dry_run:
            self.execute_git_command(f"git fetch {remote} --prune --dry-run", repo_path)
        else:
            self.execute_git_command(f"git fetch {remote} --prune", repo_path)
            self.execute_git_command(f"git remote prune {remote}", repo_path)

    def execute_simple_git(self, cmd, repo_path):
        """執行簡單的 Git 指令 (無參數)"""
        full_cmd = f"git {cmd}"
        self.execute_git_command(full_cmd, repo_path)

    def execute_git_command(self, full_cmd, repo_path):
        """執行 Git 指令並更新 UI"""
        try:
            # 必須加入 encoding 和 errors，否則執行指令遇到中文路徑或錯誤時會閃退
            res = subprocess.run(full_cmd, cwd=repo_path, shell=True, capture_output=True,
                                 text=True, encoding='utf-8', errors='replace')

            tab_id = self.notebook.select()
            current_tab = self.notebook.nametowidget(tab_id)

            texts = []
            self._get_all_texts(current_tab, texts)
            if len(texts) >= 2:
                adog_w, term_w = texts[0], texts[1]
                # 輸出到 Terminal
                term_w.insert(tk.END, f"\n$ {full_cmd}\n{res.stdout}{res.stderr}\n{'-' * 50}\n")
                term_w.see(tk.END)
                self.refresh_adog(repo_path, adog_w)
        except Exception as e:
            messagebox.showerror("錯誤", f"指令執行失敗: {str(e)}")

    def _get_all_texts(self, parent, result):
        for child in parent.winfo_children():
            if isinstance(child, tk.Text):
                result.append(child)
            else:
                self._get_all_texts(child, result)

    def refresh_adog(self, path, text_widget):
        text_widget.config(state=tk.NORMAL)
        text_widget.delete('1.0', tk.END)
        cmd = "git log --graph --oneline --all --decorate -n 150"
        # 關鍵修正：指定 encoding 和 errors 處理
        res = subprocess.run(cmd, cwd=path, shell=True, capture_output=True,
                             text=True, encoding='utf-8', errors='replace')
        text_widget.insert(tk.END, res.stdout if res.stdout else "目前尚無 Commit 紀錄")
        text_widget.config(state=tk.DISABLED)

    def view_reflog(self, path, text_widget):
        text_widget.config(state=tk.NORMAL)
        text_widget.delete('1.0', tk.END)
        # 關鍵修正：指定 encoding 和 errors 處理
        res = subprocess.run("git reflog -n 150", cwd=path, shell=True, capture_output=True,
                             text=True, encoding='utf-8', errors='replace')
        text_widget.insert(tk.END, "--- REFLOG HISTORY ---\n" + res.stdout)
        text_widget.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    app = GitAdvancedTool(root)
    root.mainloop()