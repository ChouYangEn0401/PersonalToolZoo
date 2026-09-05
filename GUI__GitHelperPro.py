import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os

from src.core.git_handler.commands import get_commands_configs
from src.core.git_handler.executor import GitExecutor
from src.gui.command_panel import CommandPanel
from src.gui.danger_operation_blocker import ConfirmationManager
from src.gui.dialogs import GitCommandDialog
from src.gui.ac_helper import attach_autocomplete
from src.core.language_manager import lm
from src.version import __version__


# ==========================================
# GitAdvancedTool (主程式整合模組)
# ==========================================
class GitAdvancedTool:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{lm.t('app.title')} (v{__version__})")
        self.root.geometry("1300x850")

        self._init_styles()
        self.command_configs = get_commands_configs()
        self.confirm_mgr = ConfirmationManager(root)
        self._command_panels = []   # track all CommandPanel instances for rebuild

        # 頂部工具列
        self.toolbar = ttk.Frame(self.root, padding=5)
        self.toolbar.grid(row=0, column=0, sticky="ew")
        self.open_btn = ttk.Button(self.toolbar, text=lm.t('toolbar.new_project'), command=self.open_directory)
        self.open_btn.grid(row=0, column=0, padx=5)

        # 語言切換
        self.lang_label = ttk.Label(self.toolbar, text=lm.t('toolbar.language_label'))
        self.lang_label.grid(row=0, column=1, padx=(20, 4))
        self._langs = lm.available_languages()          # {code: display_name}
        _codes = list(self._langs.keys())
        _names = list(self._langs.values())
        self._lang_var = tk.StringVar(value=self._langs.get(lm.current_language, lm.current_language))
        self.lang_combobox = ttk.Combobox(self.toolbar, textvariable=self._lang_var,
                               values=_names, state="readonly", width=14)
        self.lang_combobox.grid(row=0, column=2, padx=4)

        def _on_lang_change(event=None):
            display = self._lang_var.get()
            code = next((c for c, n in self._langs.items() if n == display), None)
            if code and code != lm.current_language:
                lm.load_language(code)
                self._rebuild_ui()

        self.lang_combobox.bind("<<ComboboxSelected>>", _on_lang_change)

        # 主 Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self._setup_tab_controls()

    def _setup_tab_controls(self):
        """Bind right-click context menu and Ctrl+W for tab close/move."""
        self.notebook.bind("<Button-3>", self._on_tab_right_click)
        self.root.bind("<Control-w>", lambda e: self._close_current_tab())

    def _on_tab_right_click(self, event):
        try:
            clicked_tab = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
        except Exception:
            return
        if clicked_tab == "":
            return
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=lm.t("tab.close", default="關閉分頁"),
                         command=lambda: self._close_tab_by_index(int(clicked_tab)))
        menu.add_separator()
        menu.add_command(label=lm.t("tab.move_left", default="← 向左移"),
                         command=lambda: self._move_tab(int(clicked_tab), -1))
        menu.add_command(label=lm.t("tab.move_right", default="→ 向右移"),
                         command=lambda: self._move_tab(int(clicked_tab), 1))
        menu.post(event.x_root, event.y_root)

    def _close_current_tab(self):
        try:
            idx = self.notebook.index(self.notebook.select())
            self._close_tab_by_index(idx)
        except Exception:
            pass

    def _close_tab_by_index(self, idx: int):
        try:
            tabs = self.notebook.tabs()
            if idx < 0 or idx >= len(tabs):
                return
            tab_id = tabs[idx]
            self.notebook.forget(tab_id)
            # Remove from _command_panels if index still valid
            if idx < len(self._command_panels):
                self._command_panels.pop(idx)
        except Exception:
            pass

    def _move_tab(self, idx: int, direction: int):
        try:
            tabs = self.notebook.tabs()
            n = len(tabs)
            new_idx = idx + direction
            if new_idx < 0 or new_idx >= n:
                return
            tab_id = tabs[idx]
            frame = self.notebook.nametowidget(tab_id)
            tab_text = self.notebook.tab(tab_id, "text")
            # tkinter Notebook.insert
            self.notebook.insert(new_idx, frame, text=tab_text)
            # Reorder _command_panels list
            if 0 <= idx < len(self._command_panels) and 0 <= new_idx < len(self._command_panels):
                self._command_panels.insert(new_idx, self._command_panels.pop(idx))
        except Exception:
            pass

    def _rebuild_ui(self):
        """Refresh all translatable UI text after a language switch."""
        self.root.title(f"{lm.t('app.title')} ({__version__})")
        self.open_btn.config(text=lm.t('toolbar.new_project'))
        # update toolbar language label and combobox values
        try:
            self.lang_label.config(text=lm.t('toolbar.language_label'))
        except Exception:
            pass
        try:
            self._langs = lm.available_languages()
            _names = list(self._langs.values())
            self.lang_combobox.config(values=_names)
            self._lang_var.set(self._langs.get(lm.current_language, lm.current_language))
        except Exception:
            pass
        # Rebuild each CommandPanel in-place
        for panel in self._command_panels:
            try:
                panel.rebuild()
            except Exception:
                pass
        # Update per-project tab labels/buttons (refresh/reflog/adog/terminal)
        try:
            for tab_id in self.notebook.tabs():
                try:
                    frame = self.notebook.nametowidget(tab_id)
                except Exception:
                    continue
                refresh_btn = getattr(frame, '_refresh_btn', None)
                reflog_btn = getattr(frame, '_reflog_btn', None)
                adog_lbl = getattr(frame, '_adog_label', None)
                term_lbl = getattr(frame, '_terminal_label', None)
                if refresh_btn:
                    try:
                        refresh_btn.config(text=lm.t('display.refresh_btn'))
                    except Exception:
                        pass
                if reflog_btn:
                    try:
                        reflog_btn.config(text=lm.t('display.reflog_btn'))
                    except Exception:
                        pass
                if adog_lbl:
                    try:
                        adog_lbl.config(text=lm.t('display.adog_title'))
                    except Exception:
                        pass
                if term_lbl:
                    try:
                        term_lbl.config(text=lm.t('display.terminal_title'))
                    except Exception:
                        pass
        except Exception:
            pass

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
            messagebox.showwarning(lm.t('msg.error_title'), lm.t('msg.invalid_repo'))

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
        adog_lbl = ttk.Label(display_panel, text=lm.t('display.adog_title'), font=("Arial", 9, "bold"))
        adog_lbl.grid(row=0, column=0, sticky="w", pady=(5, 0))
        adog_text = tk.Text(display_panel, bg="#ffffff", height=15, font=("Consolas", 10), wrap="none")
        adog_text.grid(row=1, column=0, sticky="nsew")
        adog_h_scroll = ttk.Scrollbar(display_panel, orient="horizontal", command=adog_text.xview)
        adog_h_scroll.grid(row=2, column=0, sticky="ew")
        adog_text.configure(xscrollcommand=adog_h_scroll.set)

        # Terminal 區域
        term_lbl = ttk.Label(display_panel, text=lm.t('display.terminal_title'), font=("Arial", 9, "bold"))
        term_lbl.grid(row=3, column=0, sticky="w", pady=(5, 0))
        terminal = tk.Text(display_panel, bg="#1e1e1e", fg="#ffffff", font=("Consolas", 10))
        terminal.grid(row=4, column=0, sticky="nsew")

        # === 初始化 Executor (核心邏輯) ===
        executor = GitExecutor(terminal, adog_text, path)

        # 底部工具欄
        ctrl_bar = ttk.Frame(display_panel)
        ctrl_bar.grid(row=5, column=0, sticky="ew", pady=5)
        refresh_btn = ttk.Button(ctrl_bar, text=lm.t('display.refresh_btn'), width=10, command=executor.refresh_adog)
        refresh_btn.pack(side="left", padx=2)
        reflog_btn = ttk.Button(ctrl_bar, text=lm.t('display.reflog_btn'),  width=10, command=executor.view_reflog)
        reflog_btn.pack(side="left", padx=2)

        # expose widgets for runtime language refresh
        main_frame._adog_label = adog_lbl
        main_frame._terminal_label = term_lbl
        main_frame._refresh_btn = refresh_btn
        main_frame._reflog_btn = reflog_btn

        executor.refresh_adog()

        # === 建立左側 CommandPanel (注入依賴) ===
        panel = CommandPanel(main_frame, executor, self.confirm_mgr, self)
        self._command_panels.append(panel)

    def open_command_dialog(self, cmd_key, repo_path, executor):
        """處理帶參數的 Git 指令對話框"""
        self.command_configs = get_commands_configs()
        if cmd_key not in self.command_configs:
            messagebox.showerror(lm.t('msg.error_title'), lm.t('msg.undefined_cmd', default=f'[{cmd_key}]'))
            return

        config = self.command_configs[cmd_key]

        # 檢查危險權限
        if config.get('danger', False):
            # Route to typed confirm methods for specific operations
            _danger_method = {
                'reset_hard':  self.confirm_mgr.confirm_reset,
                'force_push':  self.confirm_mgr.confirm_force_push,
            }.get(cmd_key, self.confirm_mgr.confirm)
            if not _danger_method(config['name'], None):
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
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)
        w, h = 640, 600
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dialog.geometry(f"{w}x{h}+{rx+(rw-w)//2}+{ry+(rh-h)//2}")

        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)

        # === 說明區 ===
        info_frame = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.shared.info_section')} ", padding=8)
        info_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(info_frame, text=lm.t('dialog.rebase_onto.desc1'),
                  font=("Consolas", 9), foreground="#555").pack(anchor="w")
        ttk.Label(info_frame, text=lm.t('dialog.rebase_onto.desc2'),
                  font=("Arial", 9), foreground="#333").pack(anchor="w", pady=(3, 0))
        ttk.Label(info_frame,
                  text=lm.t('dialog.rebase_onto.desc3'),
                  font=("Arial", 8), foreground="#888").pack(anchor="w", pady=(2, 0))

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
        commit_hashes = [c.split()[0] for c in get_short_commits()]
        head_shortcuts = ["HEAD~1", "HEAD~2", "HEAD~3", "HEAD~5", "HEAD~10"]

        # === 目前分支 ===
        cur_lf = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.shared.branch_section')} ", padding=8)
        cur_lf.pack(fill="x", pady=(0, 10))
        current_var = tk.StringVar(value=get_current_branch())
        cur_row = ttk.Frame(cur_lf)
        cur_row.pack(fill="x")
        ttk.Label(cur_row, textvariable=current_var, font=("Consolas", 11), foreground="#0066cc").pack(side="left")
        ttk.Button(cur_row, text=lm.t('dialog.shared.refresh_btn'), command=lambda: current_var.set(get_current_branch()),
                   width=10).pack(side="right")
        ttk.Label(cur_lf, text=lm.t('dialog.rebase_onto.branch_hint'),
                  font=("Arial", 8), foreground="#888").pack(anchor="w", pady=(4, 0))

        # === 欄位區 ===
        fields_lf = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.shared.params_section')} ", padding=10)
        fields_lf.pack(fill="x", pady=(0, 10))
        fields_lf.columnconfigure(1, weight=1)

        newbase_var = tk.StringVar(value=branches[0] if branches else "main")
        upstream_var = tk.StringVar(value="HEAD~3")
        branch_var = tk.StringVar(value="")

        field_defs = [
            (lm.t('dialog.rebase_onto.newbase_label'),
             lm.t('dialog.rebase_onto.newbase_hint'),
             newbase_var, branches + head_shortcuts + commit_hashes),
            (lm.t('dialog.rebase_onto.upstream_label'),
             lm.t('dialog.rebase_onto.upstream_hint'),
             upstream_var, head_shortcuts + commit_hashes + branches),
            (lm.t('dialog.rebase_onto.branch_label'),
             lm.t('dialog.rebase_onto.branch_field_hint'),
             branch_var, [""] + branches),
        ]

        comboboxes = []
        _ac_pools = [
            branches + head_shortcuts + commit_hashes,   # newbase
            head_shortcuts + commit_hashes + branches,   # upstream
            [""] + branches,                             # branch
        ]
        for row, (label, hint, var, choices), pool in zip(range(3), field_defs, _ac_pools):
            ttk.Label(fields_lf, text=label, font=("Arial", 9, "bold")).grid(
                row=row * 2, column=0, sticky="nw", padx=(0, 10), pady=(8, 0))
            cb = ttk.Combobox(fields_lf, textvariable=var, values=choices,
                              font=("Consolas", 10), state="normal")
            cb.grid(row=row * 2, column=1, sticky="ew", pady=(8, 0))
            comboboxes.append(cb)

            # Autocomplete yellow popup
            _pool = pool
            def _ac_fn(text, p=_pool):
                if not text:
                    return p[:20]
                t = text.lower()
                return [x for x in p if t in x.lower()][:20]
            attach_autocomplete(cb, var, _ac_fn, fields_lf)

            hint_row = ttk.Frame(fields_lf)
            hint_row.grid(row=row * 2 + 1, column=1, sticky="ew", padx=(2, 0), pady=(2, 0))
            ttk.Label(hint_row, text=hint, font=("Arial", 8), foreground="#777").pack(side="left")

            # Branch 欄加「↪ 先切換到此分支」按鈕
            if row == 2:
                def checkout_branch_field():
                    target = branch_var.get().strip()
                    if not target:
                        messagebox.showwarning(lm.t('dialog.shared.missing_param_title'), lm.t('dialog.rebase_onto.switch_field_empty'))
                        return
                    res = executor.run(f"git checkout {target}")
                    if res is None:
                        messagebox.showerror(lm.t('msg.run_error_title'), lm.t('msg.checkout_error'))
                        return
                    if getattr(res, 'returncode', 1) == 0:
                        current_var.set(get_current_branch())
                        messagebox.showinfo(lm.t('msg.done'), lm.t('msg.switch_success', target=target))
                    else:
                        stderr = (res.stderr or res.stdout or "").strip()
                        messagebox.showerror(lm.t('msg.switch_fail_title'), lm.t('msg.switch_fail_msg', stderr=stderr))
                ttk.Button(hint_row, text=lm.t('dialog.rebase_onto.switch_btn'), command=checkout_branch_field,
                           width=16).pack(side="right")

        # === 預覽 ===
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

        preview_frame = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.shared.preview_section')} ", padding=8)
        preview_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(preview_frame, textvariable=preview_var,
                  font=("Consolas", 10), foreground="#0066cc").pack(anchor="w")

        # === 按鈕列 ===
        def on_execute():
            nb = newbase_var.get().strip()
            up = upstream_var.get().strip()
            br = branch_var.get().strip()
            if not nb or not up:
                messagebox.showwarning(lm.t('dialog.shared.missing_param_title'), lm.t('dialog.rebase_onto.missing_msg'))
                return
            cmd = f"git rebase --onto {nb} {up}"
            if br:
                cmd += f" {br}"
            executor.run(cmd)
            dialog.destroy()

        btn_bar = ttk.Frame(main_frame)
        btn_bar.pack(fill="x")
        ttk.Button(btn_bar, text=lm.t('dialog.rebase_onto.execute_btn'), command=on_execute, width=22).pack(side="right", padx=2)
        ttk.Button(btn_bar, text=lm.t('dialog.shared.cancel_btn'), command=dialog.destroy, width=10).pack(side="right", padx=2)

        dialog.bind("<Return>", lambda e: on_execute())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        comboboxes[0].focus_set()

    def open_merge_dialog(self, executor):
        """Merge 對話框：支援一般、--no-ff、--squash、--ff-only 四種模式"""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.merge.title'))
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)
        w, h = 640, 640
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dialog.geometry(f"{w}x{h}+{rx+(rw-w)//2}+{ry+(rh-h)//2}")

        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)

        # === 說明區 ===
        info_frame = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.shared.info_section')} ", padding=8)
        info_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(info_frame, text=lm.t('dialog.merge.header_cmd'),
                  font=("Consolas", 9), foreground="#555").pack(anchor="w")
        ttk.Label(info_frame, text=lm.t('dialog.merge.general_desc'),
                  font=("Arial", 9), foreground="#333").pack(anchor="w", pady=(3, 4))
        mode_descs = [
            (lm.t('dialog.merge.mode_default'),  lm.t('dialog.merge.mode_default_hint')),
            ("--no-ff",      lm.t('dialog.merge.mode_noff_hint')),
            ("--squash",     lm.t('dialog.merge.mode_squash_hint')),
            ("--ff-only",    lm.t('dialog.merge.mode_ffonly_hint')),
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
        cur_lf = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.shared.branch_section')} ", padding=8)
        cur_lf.pack(fill="x", pady=(0, 10))
        current_var = tk.StringVar(value=get_current_branch())
        cur_row = ttk.Frame(cur_lf)
        cur_row.pack(fill="x")
        ttk.Label(cur_row, textvariable=current_var, font=("Consolas", 11), foreground="#0066cc").pack(side="left")
        ttk.Button(cur_row, text=lm.t('dialog.shared.refresh_btn'), command=lambda: current_var.set(get_current_branch()),
                   width=10).pack(side="right")
        ttk.Label(cur_lf, text=lm.t('dialog.merge.branch_hint'),
                  font=("Arial", 8), foreground="#888").pack(anchor="w", pady=(4, 0))

        # === 欄位區 ===
        fields_lf = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.shared.params_section')} ", padding=10)
        fields_lf.pack(fill="x", pady=(0, 10))
        fields_lf.columnconfigure(1, weight=1)

        source_var = tk.StringVar(value="")
        mode_var = tk.StringVar(value="normal")

        # 來源分支
        ttk.Label(fields_lf, text=lm.t('dialog.merge.source_label'), font=("Arial", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 2))
        source_cb = ttk.Combobox(fields_lf, textvariable=source_var,
                                 values=branches + commit_hashes, font=("Consolas", 10), state="normal")
        source_cb.grid(row=0, column=1, sticky="ew", pady=(0, 2))

        # Autocomplete yellow popup for source combobox
        def _merge_ac(text):
            pool = branches + commit_hashes
            if not text:
                return pool[:20]
            t = text.lower()
            return [x for x in pool if t in x.lower()][:20]
        attach_autocomplete(source_cb, source_var, _merge_ac, source_cb)

        def checkout_source():
            src = source_var.get().strip()
            if not src:
                messagebox.showwarning(lm.t('dialog.shared.missing_param_title'), lm.t('dialog.merge.switch_missing'))
                return
            res = executor.run(f"git checkout {src}")
            if res is None:
                messagebox.showerror(lm.t('msg.run_error_title'), lm.t('msg.checkout_error'))
                return
            if getattr(res, 'returncode', 1) == 0:
                current_var.set(get_current_branch())
                messagebox.showinfo(lm.t('msg.done'), lm.t('msg.switch_success', target=src))
            else:
                stderr = (res.stderr or res.stdout or "").strip()
                messagebox.showerror(lm.t('msg.switch_fail_title'), lm.t('msg.switch_fail_msg', stderr=stderr))

        hint_row = ttk.Frame(fields_lf)
        hint_row.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(hint_row, text=lm.t('dialog.merge.source_hint2'),
                  font=("Arial", 8), foreground="#777").pack(side="left")
        ttk.Button(hint_row, text=lm.t('dialog.merge.switch_btn'), command=checkout_source,
                   width=16).pack(side="right")

        # 合併模式
        ttk.Label(fields_lf, text=lm.t('dialog.merge.mode_label'), font=("Arial", 9, "bold")).grid(
            row=2, column=0, sticky="nw", padx=(0, 10), pady=(4, 0))
        mode_frame = ttk.Frame(fields_lf)
        mode_frame.grid(row=2, column=1, sticky="w", pady=(4, 0))
        for val, lbl, hint in [
            ("normal",    lm.t('dialog.merge.mode_default_radio'),   lm.t('dialog.merge.mode_default_hint')),
            ("--no-ff",   lm.t('dialog.merge.mode_noff_radio'),      lm.t('dialog.merge.mode_noff_hint')),
            ("--squash",  lm.t('dialog.merge.mode_squash_radio'),    lm.t('dialog.merge.mode_squash_hint')),
            ("--ff-only", lm.t('dialog.merge.mode_ffonly_radio'),     lm.t('dialog.merge.mode_ffonly_hint')),
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

        preview_frame = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.shared.preview_section')} ", padding=8)
        preview_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(preview_frame, textvariable=preview_var,
                  font=("Consolas", 10), foreground="#0066cc").pack(anchor="w")

        # === 按鈕列 ===
        def on_execute():
            src = source_var.get().strip()
            if not src:
                messagebox.showwarning(lm.t('dialog.shared.missing_param_title'), lm.t('dialog.merge.incomplete_msg'))
                return
            mode = mode_var.get()
            cmd = f"git merge {src}" if mode == "normal" else f"git merge {mode} {src}"
            executor.run(cmd)
            dialog.destroy()

        btn_bar = ttk.Frame(main_frame)
        btn_bar.pack(fill="x")
        ttk.Button(btn_bar, text=lm.t('dialog.merge.execute_btn'), command=on_execute, width=16).pack(side="right", padx=2)
        ttk.Button(btn_bar, text=lm.t('dialog.shared.cancel_btn'), command=dialog.destroy, width=10).pack(side="right", padx=2)

        dialog.bind("<Return>", lambda e: on_execute())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        source_cb.focus_set()
        ttk.Button(btn_bar, text=lm.t('dialog.merge.abort_btn'),
                   command=lambda: (executor.run_simple("merge --abort"), dialog.destroy()),
                   width=10, style="Danger.TButton").pack(side="left", padx=2)
        ttk.Button(btn_bar, text=lm.t('dialog.merge.continue_btn'),
                   command=lambda: (executor.run_simple("merge --continue"), dialog.destroy()),
                   width=14).pack(side="left", padx=2)

        source_cb.focus_set()

    def open_checkout_dialog(self, executor):
        """Checkout 搜尋器：可搜尋 branch / origin/branch / tag / commit，支援 -b 建立新分支"""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.checkouts.title'))
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
        info_frame = ttk.LabelFrame(main, text=f" {lm.t('dialog.shared.info_section')} ", padding=8)
        info_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(info_frame, text=lm.t('dialog.checkouts.desc1'),
                  font=("Consolas", 9), foreground="#555").pack(anchor="w")
        ttk.Label(info_frame, text=lm.t('dialog.checkouts.desc2'),
                  font=("Consolas", 9), foreground="#555").pack(anchor="w", pady=(2, 0))
        ttk.Label(info_frame, text=lm.t('dialog.checkouts.desc3'),
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
        cur_lf = ttk.LabelFrame(main, text=f" {lm.t('dialog.shared.branch_section')} ", padding=8)
        cur_lf.pack(fill="x", pady=(0, 10))
        current_var = tk.StringVar(value=get_current_branch())
        cur_row = ttk.Frame(cur_lf)
        cur_row.pack(fill="x")
        ttk.Label(cur_row, textvariable=current_var, font=("Consolas", 11), foreground="#0066cc").pack(side="left")
        ttk.Button(cur_row, text=lm.t('dialog.shared.refresh_btn'), command=lambda: current_var.set(get_current_branch()),
                   width=10).pack(side="right")

        # === 搜尋與清單 ===
        search_lf = ttk.LabelFrame(main, text=f" {lm.t('dialog.checkouts.search_section')} ", padding=10)
        search_lf.pack(fill="both", expand=True, pady=(0, 10))
        search_lf.columnconfigure(0, weight=1)

        entry_var = tk.StringVar()
        entry = ttk.Entry(search_lf, textvariable=entry_var, font=("Consolas", 11))
        entry.pack(fill="x", pady=(0, 4))
        ttk.Label(search_lf, text=lm.t('dialog.checkouts.filter_hint'),
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
        ttk.Checkbutton(opt_frame, text=lm.t('dialog.checkouts.new_branch_cb'), variable=cb_var).pack(side="left")

        # === 預覽 ===
        preview_lf = ttk.LabelFrame(main, text=f" {lm.t('dialog.shared.preview_section')} ", padding=8)
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
                messagebox.showwarning(lm.t('dialog.shared.missing_param_title'), lm.t('dialog.checkouts.missing_msg'))
                return
            cmd = f"git checkout -b {target}" if cb_var.get() else f"git checkout {target}"
            res = executor.run(cmd)
            if res is None:
                messagebox.showerror(lm.t('msg.run_error_title'), lm.t('msg.checkout_error'))
                return
            if getattr(res, 'returncode', 1) == 0:
                current_var.set(get_current_branch())
                messagebox.showinfo(lm.t('msg.done'), lm.t('msg.switch_success', target=target))
                dialog.destroy()
            else:
                stderr = (res.stderr or res.stdout or "").strip()
                messagebox.showerror(lm.t('msg.switch_fail_title'), lm.t('dialog.checkouts.fail_msg', stderr=stderr))

        btn_bar = ttk.Frame(main)
        btn_bar.pack(fill="x")
        ttk.Button(btn_bar, text=lm.t('dialog.checkouts.execute_btn'), command=on_execute, width=16).pack(side="right", padx=2)
        ttk.Button(btn_bar, text=lm.t('dialog.shared.cancel_btn'), command=dialog.destroy, width=10).pack(side="right", padx=2)

        entry.focus_set()

    # ─────────────────────────────────────────────────────────────────────
    def open_checkouts_dialog(self, executor):
        """Checkouts Notebook：Tab1 = Checkout 分支/Tag/Commit，Tab2 = Checkout File"""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.checkouts.title'))
        dialog.geometry("600x650")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        dialog.update_idletasks()
        rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{rx + (rw // 2) - (dw // 2)}+{ry + (rh // 2) - (dh // 2)}")

        nb = ttk.Notebook(dialog)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        # ── shared helpers ───────────────────────────────────────────────
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

        def get_candidates(prefix=""):
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

        # ══════════════ TAB 1 : Checkout 分支/Tag/Commit ══════════════
        tab1 = ttk.Frame(nb, padding=12)
        nb.add(tab1, text=lm.t('dialog.checkouts.tab_switch'))
        tab1.columnconfigure(0, weight=1)

        info1 = ttk.LabelFrame(tab1, text=f" {lm.t('dialog.shared.info_section')} ", padding=8)
        info1.pack(fill="x", pady=(0, 8))
        ttk.Label(info1, text=lm.t('dialog.checkouts.desc1'),
                  font=("Consolas", 9), foreground="#555").pack(anchor="w")
        ttk.Label(info1, text=lm.t('dialog.checkouts.desc2'),
                  font=("Consolas", 9), foreground="#555").pack(anchor="w", pady=(2, 0))
        ttk.Label(info1, text=lm.t('dialog.checkouts.desc3'),
                  font=("Arial", 8), foreground="#888").pack(anchor="w", pady=(2, 0))

        cur_lf1 = ttk.LabelFrame(tab1, text=f" {lm.t('dialog.shared.branch_section')} ", padding=8)
        cur_lf1.pack(fill="x", pady=(0, 8))
        current_var = tk.StringVar(value=get_current_branch())
        cur_row1 = ttk.Frame(cur_lf1)
        cur_row1.pack(fill="x")
        ttk.Label(cur_row1, textvariable=current_var, font=("Consolas", 11), foreground="#0066cc").pack(side="left")
        ttk.Button(cur_row1, text=lm.t('dialog.shared.refresh_btn'), command=lambda: current_var.set(get_current_branch()),
                   width=10).pack(side="right")

        search_lf = ttk.LabelFrame(tab1, text=f" {lm.t('dialog.checkouts.search_section')} ", padding=10)
        search_lf.pack(fill="both", expand=True, pady=(0, 8))

        entry_var = tk.StringVar()
        entry1 = ttk.Entry(search_lf, textvariable=entry_var, font=("Consolas", 11))
        entry1.pack(fill="x", pady=(0, 4))
        ttk.Label(search_lf, text=lm.t('dialog.checkouts.filter_hint'),
                  font=("Arial", 8), foreground="#888").pack(anchor="w", pady=(0, 6))

        lb_frame = ttk.Frame(search_lf)
        lb_frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(lb_frame, font=("Consolas", 10), activestyle="dotbox",
                             selectbackground="#cce5ff", selectforeground="#000")
        lb_scroll = ttk.Scrollbar(lb_frame, orient="vertical", command=listbox.yview)
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
        listbox.bind('<Double-Button-1>', lambda e: on_checkout())

        opt_frame = ttk.Frame(tab1)
        opt_frame.pack(fill="x", pady=(0, 6))
        cb_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text=lm.t('dialog.checkouts.new_branch_cb'), variable=cb_var).pack(side="left")

        preview1_lf = ttk.LabelFrame(tab1, text=f" {lm.t('dialog.shared.preview_section')} ", padding=8)
        preview1_lf.pack(fill="x", pady=(0, 8))
        preview1_var = tk.StringVar()
        ttk.Label(preview1_lf, textvariable=preview1_var, font=("Consolas", 10), foreground="#0066cc").pack(anchor="w")

        def update_preview1(*_):
            t = entry_var.get().strip() or '<target>'
            preview1_var.set(f"git checkout -b {t}" if cb_var.get() else f"git checkout {t}")

        entry_var.trace_add("write", update_preview1)
        cb_var.trace_add("write", update_preview1)
        update_preview1()

        def on_checkout():
            target = entry_var.get().strip()
            if not target:
                messagebox.showwarning(lm.t('dialog.shared.missing_param_title'), lm.t('dialog.checkouts.missing_msg'))
                return
            cmd = f"git checkout -b {target}" if cb_var.get() else f"git checkout {target}"
            res = executor.run(cmd)
            if res is None:
                messagebox.showerror(lm.t('msg.run_error_title'), lm.t('msg.checkout_error'))
                return
            if getattr(res, 'returncode', 1) == 0:
                current_var.set(get_current_branch())
                messagebox.showinfo(lm.t('msg.done'), lm.t('dialog.checkouts.success_msg', target=target))
                dialog.destroy()
            else:
                stderr = (res.stderr or res.stdout or "").strip()
                messagebox.showerror(lm.t('dialog.checkouts.fail_title'), lm.t('dialog.checkouts.fail_msg', stderr=stderr))

        btn1 = ttk.Frame(tab1)
        btn1.pack(fill="x")
        ttk.Button(btn1, text=lm.t('dialog.checkouts.execute_btn'), command=on_checkout, width=16).pack(side="right", padx=2)
        ttk.Button(btn1, text=lm.t('dialog.shared.cancel_btn'), command=dialog.destroy, width=10).pack(side="right", padx=2)

        # ══════════════ TAB 2 : Checkout File ══════════════
        tab2 = ttk.Frame(nb, padding=12)
        nb.add(tab2, text=lm.t('dialog.checkouts.tab_file'))
        tab2.columnconfigure(0, weight=1)

        info2 = ttk.LabelFrame(tab2, text=f" {lm.t('dialog.shared.info_section')} ", padding=8)
        info2.pack(fill="x", pady=(0, 8))
        ttk.Label(info2, text=lm.t('dialog.checkouts.file_desc1'),
                  font=("Consolas", 9), foreground="#555").pack(anchor="w")
        ttk.Label(info2, text=lm.t('dialog.checkouts.file_desc2'),
                  font=("Arial", 9), foreground="#333").pack(anchor="w", pady=(3, 0))

        fields2 = ttk.LabelFrame(tab2, text=f" {lm.t('dialog.shared.params_section')} ", padding=10)
        fields2.pack(fill="x", pady=(0, 8))
        fields2.columnconfigure(1, weight=1)

        # source
        ttk.Label(fields2, text=lm.t('dialog.checkouts.source_label'), font=("Arial", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        source_vals = []
        try:
            r_b = subprocess.run("git branch -a", cwd=repo_path, shell=True,
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')
            source_vals += [b.strip().replace('* ', '') for b in r_b.stdout.splitlines() if b.strip()]
            r_c = subprocess.run("git log --oneline -n 20", cwd=repo_path, shell=True,
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')
            source_vals += [line.split()[0] for line in r_c.stdout.splitlines() if line.strip()]
        except:
            pass
        source_var = tk.StringVar(value="HEAD")
        source_cb2 = ttk.Combobox(fields2, textvariable=source_var, values=["HEAD"] + source_vals,
                     font=("Consolas", 10), state="normal")
        source_cb2.grid(row=0, column=1, sticky="ew")

        def _src_ac(text):
            pool = ["HEAD"] + source_vals
            if not text:
                return pool[:20]
            t = text.lower()
            return [x for x in pool if t in x.lower()][:20]
        attach_autocomplete(source_cb2, source_var, _src_ac, fields2)
        ttk.Label(fields2, text=lm.t('dialog.checkouts.source_hint'), font=("Arial", 8), foreground="#888").grid(
            row=1, column=1, sticky="w", pady=(2, 8))

        # file
        ttk.Label(fields2, text=lm.t('dialog.checkouts.file_label'), font=("Arial", 9, "bold")).grid(
            row=2, column=0, sticky="w", padx=(0, 8))
        file_var = tk.StringVar()
        file_row = ttk.Frame(fields2)
        file_row.grid(row=2, column=1, sticky="ew")
        file_row.columnconfigure(0, weight=1)
        ttk.Entry(file_row, textvariable=file_var, font=("Consolas", 10)).grid(row=0, column=0, sticky="ew")

        def browse_file():
            p = filedialog.askopenfilename(initialdir=repo_path)
            if p:
                try:
                    file_var.set(os.path.relpath(p, repo_path))
                except ValueError:
                    file_var.set(p)

        ttk.Button(file_row, text="📂", command=browse_file, width=3).grid(row=0, column=1, padx=(4, 0))

        preview2_lf = ttk.LabelFrame(tab2, text=f" {lm.t('dialog.shared.preview_section')} ", padding=8)
        preview2_lf.pack(fill="x", pady=(8, 8))
        preview2_var = tk.StringVar()
        ttk.Label(preview2_lf, textvariable=preview2_var, font=("Consolas", 10), foreground="#0066cc").pack(anchor="w")

        def update_preview2(*_):
            src = source_var.get().strip() or "HEAD"
            f = file_var.get().strip() or '<file>'
            preview2_var.set(f"git checkout {src} -- {f}")

        source_var.trace_add("write", update_preview2)
        file_var.trace_add("write", update_preview2)
        update_preview2()

        def on_checkout_file():
            f = file_var.get().strip()
            if not f:
                messagebox.showwarning(lm.t('dialog.shared.missing_param_title'), lm.t('dialog.checkouts.file_missing'))
                return
            src = source_var.get().strip() or "HEAD"
            res = executor.run(f"git checkout {src} -- {f}")
            if res is None:
                messagebox.showerror(lm.t('msg.run_error_title'), lm.t('msg.checkout_error'))
                return
            if getattr(res, 'returncode', 1) == 0:
                messagebox.showinfo(lm.t('msg.done'), lm.t('dialog.checkouts.file_success', src=src, file=f))
                dialog.destroy()
            else:
                stderr = (res.stderr or res.stdout or "").strip()
                messagebox.showerror(lm.t('dialog.checkouts.file_fail_title'), lm.t('dialog.checkouts.file_fail_msg', stderr=stderr))

        btn2 = ttk.Frame(tab2)
        btn2.pack(fill="x")
        ttk.Button(btn2, text=lm.t('dialog.checkouts.file_execute'), command=on_checkout_file, width=20).pack(side="right", padx=2)
        ttk.Button(btn2, text=lm.t('dialog.shared.cancel_btn'), command=dialog.destroy, width=10).pack(side="right", padx=2)

        entry1.focus_set()

    # ─────────────────────────────────────────────────────────────────────
    def open_delete_branch_dialog(self, executor):
        """Delete Branch dialog: allow deleting local and/or remote branches with checkboxes."""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.delete_branch.title'))
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)
        w, h = 520, 340
        rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dialog.geometry(f"{w}x{h}+{rx + (rw - w) // 2}+{ry + (rh - h) // 2}")

        def get_all_branches():
            try:
                r = subprocess.run("git branch -a", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                return [b.strip().replace('* ', '').replace('remotes/', '') for b in r.stdout.splitlines() if b.strip()]
            except:
                return []

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=lm.t('dialog.delete_branch.name_label'), font=("Arial", 10, "bold")).pack(anchor="w")
        name_var = tk.StringVar()
        name_cb = ttk.Combobox(frame, textvariable=name_var, values=get_all_branches(), font=("Consolas", 10), state="normal")
        name_cb.pack(fill="x", pady=(4, 6))
        _branch_pool = get_all_branches()
        attach_autocomplete(name_cb, name_var,
                            lambda text, pool=_branch_pool: (
                                pool[:20] if not text
                                else [x for x in pool if text.lower() in x.lower()][:20]
                            ))

        opts_frame = ttk.Frame(frame)
        opts_frame.pack(fill="x", pady=(0, 6))
        delete_local = tk.BooleanVar(value=True)
        delete_remote = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text=lm.t('dialog.delete_branch.del_local_cb'), variable=delete_local).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(opts_frame, text=lm.t('dialog.delete_branch.del_remote_cb'), variable=delete_remote).pack(side="left")

        rem_row = ttk.Frame(frame)
        rem_row.pack(fill="x", pady=(6, 4))
        ttk.Label(rem_row, text=lm.t('dialog.delete_branch.remote_label'), font=("Arial", 9, "bold")).pack(side="left")
        remote_var = tk.StringVar(value="origin")
        ttk.Entry(rem_row, textvariable=remote_var, font=("Consolas", 10), width=12).pack(side="left", padx=(6, 0))

        prev_lf = ttk.LabelFrame(frame, text=f" {lm.t('dialog.shared.preview_section')} ", padding=8)
        prev_lf.pack(fill="both", expand=True, pady=(6, 8))
        preview_text = tk.Text(prev_lf, font=("Consolas", 10), foreground="#cc0000",
                               bg="#fff8f8", height=4, wrap="none", state="disabled")
        preview_sb = ttk.Scrollbar(prev_lf, orient="vertical", command=preview_text.yview)
        preview_text.configure(yscrollcommand=preview_sb.set)
        preview_sb.pack(side="right", fill="y")
        preview_text.pack(fill="both", expand=True)

        def update_preview(*_):
            names = name_var.get().strip() or '<branch>'
            cmds = []
            for n in names.split():
                if delete_local.get():
                    cmds.append(f"git branch -D {n}")
                if delete_remote.get():
                    cmds.append(f"git push {remote_var.get().strip() or 'origin'} --delete {n}")
            content = '\n'.join(cmds) if cmds else '<select actions>'
            preview_text.config(state="normal")
            preview_text.delete("1.0", "end")
            preview_text.insert("1.0", content)
            preview_text.config(state="disabled")

        name_var.trace_add("write", update_preview)
        delete_local.trace_add("write", update_preview)
        delete_remote.trace_add("write", update_preview)
        remote_var.trace_add("write", update_preview)
        update_preview()

        def on_execute():
            names = name_var.get().strip()
            if not names:
                messagebox.showwarning(lm.t('dialog.shared.missing_param_title'), lm.t('dialog.delete_branch.missing_msg'))
                return
            if not (delete_local.get() or delete_remote.get()):
                messagebox.showwarning(lm.t('dialog.shared.no_action_title'), lm.t('dialog.delete_branch.no_action_msg'))
                return
            if not messagebox.askokcancel(lm.t('msg.confirm_delete_title'), lm.t('dialog.delete_branch.confirm_msg', preview=preview_text.get("1.0", "end-1c"))):
                return

            def _do_delete():
                for n in names.split():
                    if delete_local.get():
                        executor.run(f"git branch -D {n}")
                    if delete_remote.get():
                        r = remote_var.get().strip() or 'origin'
                        executor.run(f"git push {r} --delete {n}")
                messagebox.showinfo(lm.t('msg.done'), lm.t('dialog.delete_branch.done_msg'))
                dialog.destroy()

            self.confirm_mgr.confirm_delete_branch(names, _do_delete)

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text=lm.t('dialog.delete_branch.execute_btn'), command=on_execute, width=16, style="Danger.TButton").pack(side="right", padx=4)
        ttk.Button(btn_row, text=lm.t('dialog.shared.cancel_btn'), command=dialog.destroy, width=10).pack(side="right")

        dialog.bind("<Return>", lambda e: on_execute())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        name_cb.focus_set()

    # ─────────────────────────────────────────────────────────────────────
    def open_delete_tag_dialog(self, executor):
        """Delete Tag dialog: allow deleting local and/or remote tags with checkboxes."""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.delete_tag.title'))
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)

        dialog.update_idletasks()
        w, h = 520, 340
        rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dialog.geometry(f"{w}x{h}+{rx + (rw - w) // 2}+{ry + (rh - h) // 2}")

        def get_tags():
            try:
                r = subprocess.run("git tag -l", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                return sorted(t.strip() for t in r.stdout.splitlines() if t.strip())
            except:
                return []

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=lm.t('dialog.delete_tag.name_label'), font=("Arial", 10, "bold")).pack(anchor="w")
        tag_var = tk.StringVar()
        tag_cb = ttk.Combobox(frame, textvariable=tag_var, values=get_tags(), font=("Consolas", 10), state="normal")
        tag_cb.pack(fill="x", pady=(4, 6))
        _tag_pool = get_tags()
        attach_autocomplete(tag_cb, tag_var,
                            lambda text, pool=_tag_pool: (
                                pool[:20] if not text
                                else [x for x in pool if text.lower() in x.lower()][:20]
                            ))

        opts_frame = ttk.Frame(frame)
        opts_frame.pack(fill="x", pady=(0, 6))
        delete_local = tk.BooleanVar(value=True)
        delete_remote = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text=lm.t('dialog.delete_tag.del_local_cb'), variable=delete_local).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(opts_frame, text=lm.t('dialog.delete_tag.del_remote_cb'), variable=delete_remote).pack(side="left")

        rem_row = ttk.Frame(frame)
        rem_row.pack(fill="x", pady=(6, 4))
        ttk.Label(rem_row, text=lm.t('dialog.delete_tag.remote_label'), font=("Arial", 9, "bold")).pack(side="left")
        remote_var = tk.StringVar(value="origin")
        ttk.Entry(rem_row, textvariable=remote_var, font=("Consolas", 10), width=12).pack(side="left", padx=(6, 0))

        prev_lf = ttk.LabelFrame(frame, text=f" {lm.t('dialog.shared.preview_section')} ", padding=8)
        prev_lf.pack(fill="both", expand=True, pady=(6, 8))
        prev_lf.columnconfigure(0, weight=1)
        prev_lf.rowconfigure(0, weight=1)
        preview_text = tk.Text(prev_lf, font=("Consolas", 10), foreground="#cc0000",
                               bg="#fff8f8", height=4, wrap="none", state="disabled")
        preview_sb = ttk.Scrollbar(prev_lf, orient="vertical", command=preview_text.yview)
        preview_text.configure(yscrollcommand=preview_sb.set)
        preview_sb.pack(side="right", fill="y")
        preview_text.pack(fill="both", expand=True)

        def update_preview(*_):
            names = tag_var.get().strip() or '<tag>'
            cmds = []
            for t in names.split():
                if delete_local.get():
                    cmds.append(f"git tag -d {t}")
                if delete_remote.get():
                    cmds.append(f"git push {remote_var.get().strip() or 'origin'} --delete {t}")
            content = '\n'.join(cmds) if cmds else '<select actions>'
            preview_text.config(state="normal")
            preview_text.delete("1.0", "end")
            preview_text.insert("1.0", content)
            preview_text.config(state="disabled")

        tag_var.trace_add("write", update_preview)
        delete_local.trace_add("write", update_preview)
        delete_remote.trace_add("write", update_preview)
        remote_var.trace_add("write", update_preview)
        update_preview()

        def on_execute():
            names = tag_var.get().strip()
            if not names:
                messagebox.showwarning(lm.t('dialog.shared.missing_param_title'), lm.t('dialog.delete_tag.missing_msg'))
                return
            if not (delete_local.get() or delete_remote.get()):
                messagebox.showwarning(lm.t('dialog.shared.no_action_title'), lm.t('dialog.delete_tag.no_action_msg'))
                return
            if not messagebox.askokcancel(lm.t('msg.confirm_delete_title'), lm.t('dialog.delete_tag.confirm_msg', preview=preview_text.get("1.0", "end-1c"))):
                return

            for t in names.split():
                if delete_local.get():
                    executor.run(f"git tag -d {t}")
                if delete_remote.get():
                    r = remote_var.get().strip() or 'origin'
                    executor.run(f"git push {r} --delete {t}")

            messagebox.showinfo(lm.t('msg.done'), lm.t('dialog.delete_tag.done_msg'))
            dialog.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text=lm.t('dialog.delete_tag.execute_btn'), command=on_execute, width=20, style="Danger.TButton").pack(side="right", padx=4)
        ttk.Button(btn_row, text=lm.t('dialog.shared.cancel_btn'), command=dialog.destroy, width=10).pack(side="right")

        dialog.bind("<Return>", lambda e: on_execute())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        tag_cb.focus_set()

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
                messagebox.showinfo(lm.t('dialog.file_selector.no_changes_title'), lm.t('dialog.file_selector.no_changes'))
                return

            dialog = tk.Toplevel(self.root)
            dialog.title(lm.t('dialog.file_selector.title'))
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
            ttk.Label(stat_bar, text=lm.t('dialog.file_selector.staged_count', count=staged_count), foreground="#28a745",
                      font=("Arial", 9, "bold")).pack(side="left", padx=10)
            ttk.Label(stat_bar, text=lm.t('dialog.file_selector.unstaged_count', count=unstaged_count), foreground="#007bff",
                      font=("Arial", 9, "bold")).pack(side="left", padx=10)

            # 3. 檔案列表區
            list_frame = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.file_selector.file_list_section')} ", padding=10)
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
                if idx != ' ' and work != ' ' and idx != '?': return ('⚠️', lm.t('dialog.file_selector.status_partial'), '#FFC107')
                if idx == '?': return ('🆕', lm.t('dialog.file_selector.status_untracked'), '#6c757d')
                if idx != ' ': return ('✅', lm.t('dialog.file_selector.status_staged'), '#28a745')
                if work == 'M': return ('✏️', lm.t('dialog.file_selector.status_modified'), '#007bff')
                if work == 'D': return ('🗑️', lm.t('dialog.file_selector.status_deleted'), '#dc3545')
                return ('❓', lm.t('dialog.file_selector.status_unknown'), 'black')

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
            commit_frame = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.file_selector.commit_section')} ", padding=10)
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
                if not selected: return messagebox.showwarning(lm.t('msg.info_title'), lm.t('dialog.file_selector.select_files_warning'))
                msg = commit_var.get().strip()
                if not msg:
                    commit_entry.focus_set()
                    return messagebox.showwarning(lm.t('msg.info_title'), lm.t('dialog.file_selector.commit_msg_required'))
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
            ttk.Button(btn_bar, text=lm.t('dialog.file_selector.add_commit_btn'), command=on_add_commit, width=16).pack(side="right", padx=2)
            ttk.Button(btn_bar, text=lm.t('dialog.file_selector.add_only_btn'), command=on_add_only, width=10).pack(side="right", padx=2)
            ttk.Button(btn_bar, text=lm.t('dialog.file_selector.stash_btn'), command=on_stash, width=12).pack(side="right", padx=2)

            # 左側輔助
            ttk.Button(btn_bar, text=lm.t('dialog.file_selector.select_all_btn'), command=lambda: [v.set(True) for v in file_vars.values()], width=8).pack( side="left", padx=2)
            ttk.Button(btn_bar, text=lm.t('dialog.file_selector.deselect_all_btn'), command=lambda: [v.set(False) for v in file_vars.values()], width=8).pack( side="left", padx=2)
            ttk.Button(btn_bar, text=lm.t('dialog.shared.cancel_btn'), command=dialog.destroy).pack(side="left", padx=10)

        except Exception as e:
            messagebox.showerror(lm.t('msg.error_title'), lm.t('dialog.file_selector.error_read', err=str(e)))

    def _show_quick_preview(self, executor, commit_hash, filepath, parent=None):
        preview_parent = parent if parent else self.root
        preview = tk.Toplevel(preview_parent)

        # 移除邊框（可選），讓它看起來更像真正的懸浮預覽，但也保留標題供辨識
        preview.title(lm.t('dialog.preview.title', filename=os.path.basename(filepath)))
        preview.geometry("700x500")
        preview.attributes("-topmost", True)

        x = self.root.winfo_pointerx() + 15
        y = self.root.winfo_pointery() + 15
        preview.geometry(f"+{x}+{y}")

        def close_preview(event=None):
            if preview.winfo_exists():
                preview.destroy()

        # 標題欄：僅顯示資訊，不觸發離開關閉
        header = tk.Label(preview, text=f" {lm.t('dialog.preview.header', filepath=filepath)} ",
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
            messagebox.showwarning(lm.t('msg.info_title'), lm.t('dialog.restore.hash_required'))
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
                messagebox.showerror(lm.t('msg.error_title'),
                                     lm.t('dialog.restore.no_files_error', hash=commit_hash))
                return

            # 2. 建立彈窗 (與 open_file_selector 風格一致)
            dialog = tk.Toplevel(self.root)
            dialog.title(lm.t('dialog.restore.title', hash=commit_hash[:7]))
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

            ttk.Label(main_frame, text=lm.t('dialog.restore.header', hash=commit_hash), font=("Arial", 10, "bold")).pack(anchor="w")
            ttk.Label(main_frame, text=lm.t('dialog.restore.overwrite_warning'), foreground="red").pack(anchor="w", pady=(0, 10))

            # 3. 檔案列表區
            list_frame = ttk.LabelFrame(main_frame, text=f" {lm.t('dialog.restore.file_list_section')} ", padding=10)
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
                    return messagebox.showwarning(lm.t('msg.info_title'), lm.t('dialog.restore.select_warning'))

                if messagebox.askyesno(lm.t('dialog.restore.confirm_title'),
                                       lm.t('dialog.restore.confirm_msg', count=len(selected), hash=commit_hash[:7])):
                    executor.run(f"git checkout {commit_hash} -- {' '.join(selected)}")
                    dialog.destroy()
                    messagebox.showinfo(lm.t('msg.done'), lm.t('dialog.restore.done_msg', count=len(selected)))

            # 5. 按鈕列
            btn_bar = ttk.Frame(main_frame)
            btn_bar.pack(fill="x")
            ttk.Button(btn_bar, text=lm.t('dialog.restore.extract_btn'), command=on_restore, width=25, style="Danger.TButton").pack(side="right", padx=2)
            ttk.Button(btn_bar, text=lm.t('dialog.shared.cancel_btn'), command=dialog.destroy).pack(side="right", padx=2)
            ttk.Button(btn_bar, text=lm.t('dialog.file_selector.select_all_btn'), command=lambda: [v.set(True) for v in file_vars.values()], width=8).pack(side="left", padx=2)
            ttk.Button(btn_bar, text=lm.t('dialog.file_selector.deselect_all_btn'), command=lambda: [v.set(False) for v in file_vars.values()], width=8).pack(side="left", padx=2)

        except Exception as e:
            messagebox.showerror(lm.t('msg.error_title'), lm.t('dialog.restore.read_error', err=str(e)))

    # ─────────────────────────────────────────────────────────────────────
    # Fetch dialog (with optional --prune)
    # ─────────────────────────────────────────────────────────────────────
    def open_fetch_dialog(self, executor):
        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.fetch.title', default='🌐 Fetch'))
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        w, h = 360, 160
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dialog.geometry(f"{w}x{h}+{rx+(rw-w)//2}+{ry+(rh-h)//2}")

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)

        rem_row = ttk.Frame(frame)
        rem_row.pack(fill="x", pady=(0, 8))
        ttk.Label(rem_row, text=lm.t('dialog.fetch.remote_label', default='遠端:'),
                  font=("Arial", 9, "bold")).pack(side="left")
        remote_var = tk.StringVar(value="--all")
        ttk.Entry(rem_row, textvariable=remote_var, width=16, font=("Consolas", 10)).pack(side="left", padx=(6, 0))
        ttk.Label(rem_row, text=lm.t('dialog.fetch.remote_hint', default='(--all 代表全部)'),
                  font=("Arial", 8), foreground="#888").pack(side="left", padx=(8, 0))

        prune_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame,
                        text=lm.t('dialog.fetch.prune_cb', default='--prune（刪除遠端已不存在的追蹤分支）'),
                        variable=prune_var).pack(anchor="w", pady=(0, 12))

        def on_execute():
            remote = remote_var.get().strip() or "--all"
            cmd = f"fetch {remote}"
            if prune_var.get():
                cmd += " --prune"
            executor.run_simple(cmd)
            dialog.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text=lm.t('dialog.fetch.execute_btn', default='🌐 執行 Fetch'),
                   command=on_execute, width=16).pack(side="right", padx=4)
        ttk.Button(btn_row, text=lm.t('dialog.shared.cancel_btn', default='✗ 取消'),
                   command=dialog.destroy, width=10).pack(side="right")

        dialog.bind("<Return>", lambda e: on_execute())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    # ─────────────────────────────────────────────────────────────────────
    # Task 5: Rename Branch
    # ─────────────────────────────────────────────────────────────────────
    def open_rename_branch_dialog(self, executor):
        repo_path = executor.repo_path

        def get_branches():
            try:
                r = subprocess.run("git branch -a", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                return [b.strip().replace('* ', '') for b in r.stdout.splitlines() if b.strip()]
            except:
                return []

        def get_remote_branches():
            try:
                r = subprocess.run("git branch -r", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                return [b.strip().replace('origin/', '') for b in r.stdout.splitlines() if b.strip()]
            except:
                return []

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.rename_branch.title', default='重命名分支'))
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        w, h = 520, 320
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dialog.geometry(f"{w}x{h}+{rx+(rw-w)//2}+{ry+(rh-h)//2}")

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        all_branches = get_branches()
        remote_branches = get_remote_branches()

        # Old name
        ttk.Label(frame, text=lm.t('dialog.rename_branch.old_label', default='原分支名稱 *'),
                  font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4), padx=(0, 8))
        old_var = tk.StringVar()
        old_cb = ttk.Combobox(frame, textvariable=old_var, values=all_branches, font=("Consolas", 10), state="normal")
        old_cb.grid(row=0, column=1, sticky="ew", pady=(0, 4))

        def _old_ac(text):
            if not text:
                return all_branches[:20]
            t = text.lower()
            return [x for x in all_branches if t in x.lower()][:20]
        attach_autocomplete(old_cb, old_var, _old_ac, frame)

        # New name
        ttk.Label(frame, text=lm.t('dialog.rename_branch.new_label', default='新分支名稱 *'),
                  font=("Arial", 9, "bold")).grid(row=1, column=0, sticky="w", pady=(0, 4), padx=(0, 8))
        new_var = tk.StringVar()
        ttk.Entry(frame, textvariable=new_var, font=("Consolas", 10)).grid(row=1, column=1, sticky="ew", pady=(0, 4))

        # Remote options
        remote_frame = ttk.Frame(frame)
        remote_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        update_remote_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(remote_frame,
                        text=lm.t('dialog.rename_branch.update_remote_cb', default='同步更新遠端（Push 新 + Delete 舊）'),
                        variable=update_remote_var).pack(side="left")
        ttk.Label(remote_frame, text=lm.t('dialog.rename_branch.remote_label', default='遠端名稱:'),
                  font=("Arial", 9)).pack(side="left", padx=(12, 4))
        remote_var = tk.StringVar(value="origin")
        ttk.Entry(remote_frame, textvariable=remote_var, width=10, font=("Consolas", 10)).pack(side="left")

        # Remote warning label
        warn_lbl = ttk.Label(frame, text="", foreground="#cc6600", font=("Arial", 8))
        warn_lbl.grid(row=3, column=0, columnspan=2, sticky="w")

        def _check_remote_warn(*_):
            old = old_var.get().strip()
            if old and old in remote_branches:
                warn_lbl.config(text=lm.t('dialog.rename_branch.warn_remote',
                                           default='⚠️ 此分支在遠端也存在，建議勾選「同步更新遠端」。'))
            else:
                warn_lbl.config(text="")
        old_var.trace_add("write", _check_remote_warn)

        # Preview
        prev_lf = ttk.LabelFrame(frame, text=f" {lm.t('dialog.shared.preview_section')} ", padding=8)
        prev_lf.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        preview_var = tk.StringVar()
        ttk.Label(prev_lf, textvariable=preview_var, font=("Consolas", 9), foreground="#0066cc").pack(anchor="w")

        def _update_prev(*_):
            old = old_var.get().strip() or "<old>"
            new = new_var.get().strip() or "<new>"
            rem = remote_var.get().strip() or "origin"
            lines = [lm.t('dialog.rename_branch.preview_local',
                           default=f'本地重命名: git branch -m {old} {new}',
                           old=old, new=new)]
            if update_remote_var.get():
                lines.append(lm.t('dialog.rename_branch.preview_remote',
                                   default=f'遠端更新: push {new} → delete {old} @ {rem}',
                                   old=old, new=new, remote=rem))
            preview_var.set("\n".join(lines))

        old_var.trace_add("write", _update_prev)
        new_var.trace_add("write", _update_prev)
        update_remote_var.trace_add("write", _update_prev)
        remote_var.trace_add("write", _update_prev)
        _update_prev()

        def on_execute():
            old = old_var.get().strip()
            new = new_var.get().strip()
            rem = remote_var.get().strip() or "origin"
            if not old:
                messagebox.showwarning("", lm.t('dialog.rename_branch.old_required', default='請輸入原始分支名稱'))
                return
            if not new:
                messagebox.showwarning("", lm.t('dialog.rename_branch.new_required', default='請輸入新分支名稱'))
                return
            executor.run(f"git branch -m {old} {new}")
            if update_remote_var.get():
                executor.run(f"git push {rem} {new}")
                executor.run(f"git push {rem} --delete {old}")
            messagebox.showinfo(lm.t('msg.done'), lm.t('dialog.rename_branch.done_msg', default='分支重命名完成'))
            dialog.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=5, column=0, columnspan=2, sticky="ew")
        ttk.Button(btn_row, text=lm.t('dialog.rename_branch.execute_btn', default='✓ 執行重命名'),
                   command=on_execute, width=16).pack(side="right", padx=4)
        ttk.Button(btn_row, text=lm.t('dialog.shared.cancel_btn', default='✗ 取消'),
                   command=dialog.destroy, width=10).pack(side="right")
        old_cb.focus_set()

    # ─────────────────────────────────────────────────────────────────────
    # Task 5: Rename / Move Tag
    # ─────────────────────────────────────────────────────────────────────
    def open_rename_tag_dialog(self, executor):
        repo_path = executor.repo_path

        def get_tags():
            try:
                r = subprocess.run("git tag -l", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                return sorted(t.strip() for t in r.stdout.splitlines() if t.strip())
            except:
                return []

        def get_remote_tags():
            try:
                r = subprocess.run("git ls-remote --tags origin", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                tags = []
                for line in r.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and '^{}' not in parts[1]:
                        tags.append(parts[1].replace('refs/tags/', '').strip())
                return tags
            except:
                return []

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.rename_tag.title', default='移動 / 重命名 Tag'))
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        w, h = 520, 300
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dialog.geometry(f"{w}x{h}+{rx+(rw-w)//2}+{ry+(rh-h)//2}")

        all_tags = get_tags()
        remote_tags = get_remote_tags()

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text=lm.t('dialog.rename_tag.old_label', default='原 Tag 名稱 *'),
                  font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4), padx=(0, 8))
        old_var = tk.StringVar()
        old_cb = ttk.Combobox(frame, textvariable=old_var, values=all_tags, font=("Consolas", 10), state="normal")
        old_cb.grid(row=0, column=1, sticky="ew", pady=(0, 4))

        def _tag_ac(text):
            if not text:
                return all_tags[:20]
            t = text.lower()
            return [x for x in all_tags if t in x.lower()][:20]
        attach_autocomplete(old_cb, old_var, _tag_ac, frame)

        ttk.Label(frame, text=lm.t('dialog.rename_tag.new_label', default='新 Tag 名稱 *'),
                  font=("Arial", 9, "bold")).grid(row=1, column=0, sticky="w", pady=(0, 4), padx=(0, 8))
        new_var = tk.StringVar()
        ttk.Entry(frame, textvariable=new_var, font=("Consolas", 10)).grid(row=1, column=1, sticky="ew", pady=(0, 4))

        remote_frame = ttk.Frame(frame)
        remote_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        update_remote_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(remote_frame,
                        text=lm.t('dialog.rename_tag.update_remote_cb', default='同步更新遠端（Push 新 + Delete 舊）'),
                        variable=update_remote_var).pack(side="left")
        ttk.Label(remote_frame, text=lm.t('dialog.rename_tag.remote_label', default='遠端名稱:'),
                  font=("Arial", 9)).pack(side="left", padx=(12, 4))
        remote_var = tk.StringVar(value="origin")
        ttk.Entry(remote_frame, textvariable=remote_var, width=10, font=("Consolas", 10)).pack(side="left")

        warn_lbl = ttk.Label(frame, text="", foreground="#cc6600", font=("Arial", 8))
        warn_lbl.grid(row=3, column=0, columnspan=2, sticky="w")

        def _check_remote(*_):
            old = old_var.get().strip()
            if old and old in remote_tags:
                warn_lbl.config(text=lm.t('dialog.rename_tag.warn_remote',
                                           default='⚠️ 此 Tag 在遠端也存在，建議勾選「同步更新遠端」。'))
            else:
                warn_lbl.config(text="")
        old_var.trace_add("write", _check_remote)

        def on_execute():
            old = old_var.get().strip()
            new = new_var.get().strip()
            rem = remote_var.get().strip() or "origin"
            if not old:
                messagebox.showwarning("", lm.t('dialog.rename_tag.old_required', default='請輸入原始 Tag 名稱'))
                return
            if not new:
                messagebox.showwarning("", lm.t('dialog.rename_tag.new_required', default='請輸入新 Tag 名稱'))
                return
            # Get commit hash that old tag points to, create new tag, delete old
            try:
                r = subprocess.run(f"git rev-parse {old}^{{}}",
                                   cwd=repo_path, shell=True, capture_output=True,
                                   text=True, encoding='utf-8', errors='replace')
                commit_hash = r.stdout.strip()
                if not commit_hash:
                    commit_hash = old  # fallback: use tag name directly
            except Exception:
                commit_hash = old
            executor.run(f"git tag {new} {commit_hash}")
            executor.run(f"git tag -d {old}")
            if update_remote_var.get():
                executor.run(f"git push {rem} {new}")
                executor.run(f"git push {rem} --delete {old}")
            messagebox.showinfo(lm.t('msg.done'), lm.t('dialog.rename_tag.done_msg', default='Tag 移動完成'))
            dialog.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(btn_row, text=lm.t('dialog.rename_tag.execute_btn', default='✓ 執行移動 Tag'),
                   command=on_execute, width=18).pack(side="right", padx=4)
        ttk.Button(btn_row, text=lm.t('dialog.shared.cancel_btn', default='✗ 取消'),
                   command=dialog.destroy, width=10).pack(side="right")
        old_cb.focus_set()

    # ─────────────────────────────────────────────────────────────────────
    # Reverse Commit (git revert)
    # ─────────────────────────────────────────────────────────────────────
    def open_reverse_commit_dialog(self, executor):
        """建立一個逆向 commit（git revert），完全抵消指定 commit 的變更。"""
        repo_path = executor.repo_path

        def get_commits():
            try:
                res = subprocess.run("git log --oneline -n 40", cwd=repo_path, shell=True,
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
                return [line.strip() for line in res.stdout.splitlines() if line.strip()]
            except Exception:
                return []

        commits = get_commits()

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.revert.title', default='⏮️ Reverse Commit (git revert)'))
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)
        w, h = 580, 440
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dialog.geometry(f"{w}x{h}+{rx+(rw-w)//2}+{ry+(rh-h)//2}")

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)

        # === Info ===
        info_lf = ttk.LabelFrame(frame, text=f" {lm.t('dialog.shared.info_section')} ", padding=8)
        info_lf.pack(fill="x", pady=(0, 10))
        ttk.Label(info_lf, text="git revert <commit>",
                  font=("Consolas", 9), foreground="#555").pack(anchor="w")
        ttk.Label(info_lf,
                  text=lm.t('dialog.revert.desc',
                             default='建立一個新的 commit，其內容是指定 commit 的完全反向操作。\n原歷史不會被改動，適合已推送的分支。'),
                  font=("Arial", 9), foreground="#333",
                  justify="left", wraplength=520).pack(anchor="w", pady=(4, 0))

        # === Commit selector ===
        ttk.Label(frame, text=lm.t('dialog.revert.commit_label', default='要反轉的 Commit *'),
                  font=("Arial", 9, "bold")).pack(anchor="w", pady=(0, 4))
        commit_var = tk.StringVar()
        cb = ttk.Combobox(frame, textvariable=commit_var, values=commits,
                          font=("Consolas", 10), state="normal")
        cb.pack(fill="x", pady=(0, 4))

        def _commit_ac(text):
            if not text:
                return commits[:20]
            t = text.lower()
            return [x for x in commits if t in x.lower()][:20]
        attach_autocomplete(cb, commit_var, _commit_ac)

        # === Options ===
        no_commit_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text=lm.t('dialog.revert.no_commit_cb',
                       default='--no-commit（僅暫存反向變更，不自動建立 commit）'),
            variable=no_commit_var).pack(anchor="w", pady=(6, 8))

        # === Preview ===
        prev_lf = ttk.LabelFrame(frame, text=f" {lm.t('dialog.shared.preview_section')} ", padding=8)
        prev_lf.pack(fill="x", pady=(0, 10))
        preview_var = tk.StringVar()
        ttk.Label(prev_lf, textvariable=preview_var,
                  font=("Consolas", 10), foreground="#0066cc").pack(anchor="w")

        def _update_preview(*_):
            raw = commit_var.get().strip()
            h = raw.split()[0] if raw else '<commit>'
            cmd = f"git revert {h}"
            if no_commit_var.get():
                cmd += " --no-commit"
            preview_var.set(cmd)

        commit_var.trace_add("write", _update_preview)
        no_commit_var.trace_add("write", _update_preview)
        _update_preview()

        # === Buttons ===
        def on_execute():
            raw = commit_var.get().strip()
            h = raw.split()[0] if raw else ""
            if not h:
                messagebox.showwarning(
                    "", lm.t('dialog.revert.missing_commit', default='請選擇或輸入要反轉的 Commit Hash'))
                return
            cmd = f"git revert {h}"
            if no_commit_var.get():
                cmd += " --no-commit"
            executor.run(cmd)
            dialog.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text=lm.t('dialog.revert.execute_btn', default='⏮️ 執行 Revert'),
                   command=on_execute, width=18).pack(side="right", padx=4)
        ttk.Button(btn_row, text=lm.t('dialog.shared.cancel_btn'),
                   command=dialog.destroy, width=10).pack(side="right")

        dialog.bind("<Return>", lambda e: on_execute())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        cb.focus_set()

    # ─────────────────────────────────────────────────────────────────────
    # Task 6-1: Push Panel
    # ─────────────────────────────────────────────────────────────────────
    def open_push_panel(self, executor):
        repo_path = executor.repo_path

        def get_branches():
            try:
                r = subprocess.run("git branch", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                return [b.strip().replace('* ', '').strip() for b in r.stdout.splitlines() if b.strip()]
            except:
                return []

        def get_tags():
            try:
                r = subprocess.run("git tag -l", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                return sorted(t.strip() for t in r.stdout.splitlines() if t.strip())
            except:
                return []

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.push_panel.title', default='🚀 Push Panel'))
        dialog.transient(self.root)
        dialog.grab_set()
        w, h = 600, 560
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dialog.geometry(f"{w}x{h}+{rx+(rw-w)//2}+{ry+(rh-h)//2}")
        dialog.resizable(True, True)

        outer = ttk.Frame(dialog, padding=12)
        outer.pack(fill="both", expand=True)

        # Remote row
        rem_row = ttk.Frame(outer)
        rem_row.pack(fill="x", pady=(0, 8))
        ttk.Label(rem_row, text=lm.t('dialog.push_panel.remote_label', default='遠端名稱:'),
                  font=("Arial", 9, "bold")).pack(side="left")
        remote_var = tk.StringVar(value="origin")
        ttk.Entry(rem_row, textvariable=remote_var, width=12, font=("Consolas", 10)).pack(side="left", padx=(6, 0))
        ttk.Label(rem_row, text=lm.t('dialog.push_panel.force_lease_hint', default='Force = --force-with-lease'),
                  font=("Arial", 8), foreground="#888").pack(side="right")

        # Refresh + select all buttons
        ctrl_row = ttk.Frame(outer)
        ctrl_row.pack(fill="x", pady=(0, 6))

        branch_data = []   # list of (name, selected_var, force_var)
        tag_data = []

        def _build_items():
            nonlocal branch_data, tag_data
            for w in branches_inner.winfo_children():
                w.destroy()
            for w in tags_inner.winfo_children():
                w.destroy()
            branch_data.clear()
            tag_data.clear()

            for name in get_branches():
                sel = tk.BooleanVar(value=True)
                force = tk.BooleanVar(value=False)
                branch_data.append((name, sel, force))
                row = ttk.Frame(branches_inner)
                row.pack(fill="x", pady=1)
                ttk.Checkbutton(row, variable=sel).pack(side="left")
                ttk.Label(row, text=name, font=("Consolas", 10), anchor="w").pack(side="left", fill="x", expand=True)
                ttk.Checkbutton(row, text="Force", variable=force).pack(side="right")

            for name in get_tags():
                sel = tk.BooleanVar(value=False)
                force = tk.BooleanVar(value=False)
                tag_data.append((name, sel, force))
                row = ttk.Frame(tags_inner)
                row.pack(fill="x", pady=1)
                ttk.Checkbutton(row, variable=sel).pack(side="left")
                ttk.Label(row, text=name, font=("Consolas", 10), anchor="w").pack(side="left", fill="x", expand=True)
                ttk.Checkbutton(row, text="Force", variable=force).pack(side="right")

        # Branches section
        branches_lf = ttk.LabelFrame(outer, text=f" {lm.t('dialog.push_panel.branches_section', default='📌 Local Branches')} ", padding=6)
        branches_lf.pack(fill="both", expand=True, pady=(0, 6))
        branches_canvas = tk.Canvas(branches_lf, bg="#f0f0f0", highlightthickness=0, height=160)
        branches_sb = ttk.Scrollbar(branches_lf, orient="vertical", command=branches_canvas.yview)
        branches_inner = ttk.Frame(branches_canvas)
        branches_canvas.create_window((0, 0), window=branches_inner, anchor="nw", tags="bi")
        branches_canvas.configure(yscrollcommand=branches_sb.set)
        branches_inner.bind("<Configure>", lambda e: branches_canvas.configure(scrollregion=branches_canvas.bbox("all")))
        branches_canvas.bind("<Configure>", lambda e: branches_canvas.itemconfigure("bi", width=e.width))
        branches_sb.pack(side="right", fill="y")
        branches_canvas.pack(side="left", fill="both", expand=True)

        # Tags section
        tags_lf = ttk.LabelFrame(outer, text=f" {lm.t('dialog.push_panel.tags_section', default='🏷️ Tags')} ", padding=6)
        tags_lf.pack(fill="both", expand=True, pady=(0, 6))
        tags_canvas = tk.Canvas(tags_lf, bg="#f0f0f0", highlightthickness=0, height=120)
        tags_sb = ttk.Scrollbar(tags_lf, orient="vertical", command=tags_canvas.yview)
        tags_inner = ttk.Frame(tags_canvas)
        tags_canvas.create_window((0, 0), window=tags_inner, anchor="nw", tags="ti")
        tags_canvas.configure(yscrollcommand=tags_sb.set)
        tags_inner.bind("<Configure>", lambda e: tags_canvas.configure(scrollregion=tags_canvas.bbox("all")))
        tags_canvas.bind("<Configure>", lambda e: tags_canvas.itemconfigure("ti", width=e.width))
        tags_sb.pack(side="right", fill="y")
        tags_canvas.pack(side="left", fill="both", expand=True)

        _build_items()

        # Refresh button
        ttk.Button(ctrl_row, text=lm.t('dialog.push_panel.refresh_btn', default='🔄 刷新'),
                   command=_build_items, width=10).pack(side="left", padx=2)
        ttk.Button(ctrl_row, text=lm.t('dialog.push_panel.select_all_btn', default='全選'),
                   command=lambda: [v.set(True) for _, v, _ in branch_data + tag_data], width=8).pack(side="left", padx=2)
        ttk.Button(ctrl_row, text=lm.t('dialog.push_panel.deselect_btn', default='清除'),
                   command=lambda: [v.set(False) for _, v, _ in branch_data + tag_data], width=8).pack(side="left", padx=2)

        def on_execute():
            rem = remote_var.get().strip() or "origin"
            pushed_any = False
            for name, sel, force in branch_data:
                if sel.get():
                    pushed_any = True
                    if force.get():
                        executor.run(f"git push {rem} {name} --force-with-lease")
                    else:
                        executor.run(f"git push {rem} {name}")
            for name, sel, force in tag_data:
                if sel.get():
                    pushed_any = True
                    if force.get():
                        executor.run(f"git push {rem} {name} --force")
                    else:
                        executor.run(f"git push {rem} {name}")
            if not pushed_any:
                messagebox.showwarning("", lm.t('dialog.push_panel.no_selection', default='請至少選擇一個分支或 Tag'))
                return
            messagebox.showinfo(lm.t('msg.done'), lm.t('dialog.push_panel.done_msg', default='Push 已執行（請查看 Terminal）'))
            dialog.destroy()

        btn_row = ttk.Frame(outer)
        btn_row.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_row, text=lm.t('dialog.push_panel.execute_btn', default='🚀 執行 Push'),
                   command=on_execute, width=16).pack(side="right", padx=4)
        ttk.Button(btn_row, text=lm.t('dialog.shared.cancel_btn', default='✗ 取消'),
                   command=dialog.destroy, width=10).pack(side="right")

    # ─────────────────────────────────────────────────────────────────────
    # Delete Panel — unified single-page design
    # ─────────────────────────────────────────────────────────────────────
    def open_delete_panel(self, executor):
        repo_path = executor.repo_path

        # ── Dialog setup ─────────────────────────────────────────────────
        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.delete_panel.title', default='🗑️ Delete Panel'))
        dialog.transient(self.root)
        dialog.grab_set()
        w, h = 640, 600
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dialog.geometry(f"{w}x{h}+{rx+(rw-w)//2}+{ry+(rh-h)//2}")
        dialog.resizable(True, True)

        outer = ttk.Frame(dialog, padding=10)
        outer.pack(fill="both", expand=True)

        # ── Remote name ──────────────────────────────────────────────────
        rem_row = ttk.Frame(outer)
        rem_row.pack(fill="x", pady=(0, 6))
        ttk.Label(rem_row, text=lm.t('dialog.delete_panel.remote_label', default='遠端名稱:'),
                  font=("Arial", 9, "bold")).pack(side="left")
        remote_var = tk.StringVar(value="origin")
        ttk.Entry(rem_row, textvariable=remote_var, width=12, font=("Consolas", 10)).pack(side="left", padx=(6, 0))

        # ── Pool data ────────────────────────────────────────────────────
        # _pool["entries"]: list of (disp, canonical, itype, scope)
        #   disp examples:  "[B]  main"  "[rB] origin/main"  "[T]  v1.0"  "[rT] v1.0"
        # _pool["lookup"]:  disp → (canonical, itype, scope)
        # _pool["avail"]:   (canonical, itype) → set of scopes present in pool
        _pool = {"entries": None, "lookup": {}, "avail": {}}

        def _build_pool():
            entries = []
            rem = remote_var.get().strip() or "origin"
            try:
                r = subprocess.run("git branch", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                for b in r.stdout.splitlines():
                    name = b.strip().replace('* ', '').strip()
                    if name:
                        entries.append((f"[B]  {name}", name, "branch", "local"))
            except Exception:
                pass
            try:
                r = subprocess.run("git branch -r", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                prefix = rem + "/"
                for b in r.stdout.splitlines():
                    full = b.strip()
                    if not full or '->' in full:
                        continue
                    canon = full[len(prefix):] if full.startswith(prefix) else full.split("/", 1)[-1]
                    entries.append((f"[rB] {full}", canon, "branch", "remote"))
            except Exception:
                pass
            try:
                r = subprocess.run("git tag -l", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                for t in sorted(r.stdout.splitlines()):
                    name = t.strip()
                    if name:
                        entries.append((f"[T]  {name}", name, "tag", "local"))
            except Exception:
                pass
            try:
                r = subprocess.run(f"git ls-remote --tags {rem}", cwd=repo_path, shell=True,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
                for line in r.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and '^{}' not in parts[1]:
                        name = parts[1].replace('refs/tags/', '').strip()
                        if name:
                            entries.append((f"[rT] {name}", name, "tag", "remote"))
            except Exception:
                pass

            lookup, avail = {}, {}
            for disp, canonical, itype, scope in entries:
                lookup[disp] = (canonical, itype, scope)
                avail.setdefault((canonical, itype), set()).add(scope)
            _pool["entries"] = entries
            _pool["lookup"] = lookup
            _pool["avail"] = avail

        def _ensure_pool():
            if _pool["entries"] is None:
                _build_pool()

        def _valid_scope_opts(canonical, itype):
            """Ordered scope values actually present in pool for this item."""
            available = _pool["avail"].get((canonical, itype), set())
            opts = []
            if "local" in available:
                opts.append("local")
            if "remote" in available:
                opts.append("remote")
            if len(available) >= 2:
                opts.append("both")
            return opts or ["local"]

        # ── Queue ────────────────────────────────────────────────────────
        # {(canonical, itype): {"scope_var", "row", "label"}}
        queue_items = {}

        SCOPE_COLORS = {"local": "#333333", "remote": "#cc0000", "both": "#cc6600"}

        def _scope_color(scope):
            return SCOPE_COLORS.get(scope, "#333333")

        def _update_label_color(label, scope_var):
            label.config(foreground=_scope_color(scope_var.get()))

        def _flash_green_then(label, scope_var):
            label.config(foreground="#009900")
            label.after(1500, lambda: _update_label_color(label, scope_var))

        def _get_filtered(text):
            """Return up to 20 display strings, excluding already-fully-covered queue entries."""
            _ensure_pool()
            results = []
            tl = text.lower() if text else ""
            for disp, canonical, itype, scope in _pool["entries"]:
                key = (canonical, itype)
                if key in queue_items:
                    cur = queue_items[key]["scope_var"].get()
                    # Skip this display entry if its scope is already covered
                    if cur == "both" or cur == scope:
                        continue
                if not tl or tl in disp.lower():
                    results.append(disp)
                if len(results) >= 20:
                    break
            return results

        def _add_to_queue(input_str):
            """Accept an exact display string or a loose canonical/substring match."""
            _ensure_pool()
            txt = (input_str or "").strip()
            lookup = _pool["lookup"]

            # Resolve to exact display key
            if not txt:
                suggestions = _get_filtered("")
                if not suggestions:
                    return
                disp = suggestions[0]
            elif txt in lookup:
                disp = txt
            else:
                tl = txt.lower()
                disp = next(
                    (k for k, v in lookup.items() if v[0] == txt),    # exact canonical
                    next((k for k in lookup if tl in k.lower()), None) # substring
                )
            if disp is None:
                search_var.set("")
                return

            search_var.set("")
            canonical, itype, initial_scope = lookup[disp]
            key = (canonical, itype)
            avail = _pool["avail"].get(key, set())

            if key in queue_items:
                # Attempt to merge scope
                existing = queue_items[key]
                cur = existing["scope_var"].get()
                if cur != "both" and cur != initial_scope and "local" in avail and "remote" in avail:
                    existing["scope_var"].set("both")
                    _flash_green_then(existing["label"], existing["scope_var"])
                return

            # Determine valid scope options and initial value
            valid_opts = _valid_scope_opts(canonical, itype)
            init_scope = initial_scope if initial_scope in valid_opts else valid_opts[0]
            scope_var = tk.StringVar(value=init_scope)

            # Label prefix reflects current scope
            def _prefix_for(sc, it):
                if it == "branch":
                    return {"local": "[B]", "remote": "[rB]", "both": "[B+rB]"}.get(sc, "[B]")
                return {"local": "[T]", "remote": "[rT]", "both": "[T+rT]"}.get(sc, "[T]")

            row = ttk.Frame(queue_inner)
            row.pack(fill="x", pady=1)

            name_lbl = tk.Label(row,
                                text=f"{_prefix_for(init_scope, itype)} {canonical}",
                                font=("Consolas", 10), anchor="w",
                                bg="#f0f0f0",
                                foreground=_scope_color(init_scope))
            name_lbl.pack(side="left", fill="x", expand=True)

            def _remove(r=row, k=key):
                r.destroy()
                queue_items.pop(k, None)
                queue_canvas.update_idletasks()
                queue_canvas.configure(scrollregion=queue_canvas.bbox("all"))

            ttk.Button(row, text="✕", command=_remove, width=3).pack(side="right", padx=(2, 0))
            scope_cb = ttk.Combobox(row, textvariable=scope_var, values=valid_opts,
                                    width=8, state="readonly", font=("Consolas", 9))
            scope_cb.pack(side="right", padx=(2, 2))

            def _on_scope_change(*_, lbl=name_lbl, sv=scope_var, cn=canonical, it=itype):
                sc = sv.get()
                lbl.config(text=f"{_prefix_for(sc, it)} {cn}",
                           foreground=_scope_color(sc))

            scope_var.trace_add("write", _on_scope_change)
            queue_items[key] = {"scope_var": scope_var, "row": row, "label": name_lbl}
            queue_canvas.update_idletasks()
            queue_canvas.configure(scrollregion=queue_canvas.bbox("all"))

        # ── Search bar ───────────────────────────────────────────────────
        search_lf = ttk.LabelFrame(
            outer,
            text=f" {lm.t('dialog.delete_panel.search_hint', default='搜尋 (Tab選擇/Enter加入)')} ",
            padding=8)
        search_lf.pack(fill="x", pady=(0, 2))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_lf, textvariable=search_var, font=("Consolas", 10))
        search_entry.pack(fill="x")

        # Legend
        legend_row = ttk.Frame(outer)
        legend_row.pack(fill="x", pady=(2, 4))
        ttk.Label(legend_row,
                  text="[B]=本地分支  [rB]=遠端分支  [T]=本地標籤  [rT]=遠端標籤  ·  "
                       "scope顏色: 黑=local  紅=remote  橘=both",
                  font=("Arial", 8), foreground="#888").pack(side="left")

        # ── Queue canvas ─────────────────────────────────────────────────
        queue_lf = ttk.LabelFrame(
            outer,
            text=f" {lm.t('dialog.delete_panel.pending_label', default='待刪清單')} ",
            padding=6)
        queue_lf.pack(fill="both", expand=True, pady=(0, 4))

        queue_canvas = tk.Canvas(queue_lf, bg="#f0f0f0", highlightthickness=0)
        queue_sb = ttk.Scrollbar(queue_lf, orient="vertical", command=queue_canvas.yview)
        queue_inner = ttk.Frame(queue_canvas)
        queue_canvas.create_window((0, 0), window=queue_inner, anchor="nw", tags="qi")
        queue_canvas.configure(yscrollcommand=queue_sb.set)
        queue_inner.bind("<Configure>",
                         lambda e: queue_canvas.configure(scrollregion=queue_canvas.bbox("all")))
        queue_canvas.bind("<Configure>",
                          lambda e: queue_canvas.itemconfigure("qi", width=e.width))
        queue_sb.pack(side="right", fill="y")
        queue_canvas.pack(side="left", fill="both", expand=True)

        # Attach autocomplete now that all closures + widgets are defined
        attach_autocomplete(search_entry, search_var, _get_filtered, on_confirm=_add_to_queue)

        def _on_enter_add(event):
            val = search_var.get().strip()
            if not val:
                s = _get_filtered("")
                if s:
                    _add_to_queue(s[0])
            else:
                _add_to_queue(val)

        search_entry.bind("<Return>", _on_enter_add, add=True)

        # ── Control bar ──────────────────────────────────────────────────
        btn_ctrl = ttk.Frame(outer)
        btn_ctrl.pack(fill="x", pady=(2, 4))

        def _clear_queue():
            for w in queue_inner.winfo_children():
                w.destroy()
            queue_items.clear()

        def on_delete():
            if not queue_items:
                messagebox.showwarning("", lm.t('dialog.delete_panel.no_selection',
                                                default='請至少加入一個項目'))
                return
            rem = remote_var.get().strip() or "origin"
            preview_lines = []
            for (canonical, itype), data in queue_items.items():
                scope = data["scope_var"].get()
                if itype == "branch":
                    if scope in ("local", "both"):
                        preview_lines.append(f"git branch -D {canonical}")
                    if scope in ("remote", "both"):
                        preview_lines.append(f"git push {rem} --delete {canonical}")
                else:
                    if scope in ("local", "both"):
                        preview_lines.append(f"git tag -d {canonical}")
                    if scope in ("remote", "both"):
                        preview_lines.append(f"git push {rem} --delete {canonical}")
            if not preview_lines:
                return
            preview_str = "\n".join(preview_lines)
            if not messagebox.askokcancel(
                    lm.t('msg.confirm_delete_title'),
                    lm.t('dialog.delete_panel.confirm_msg',
                          default=f'確定要執行？\n\n{preview_str}', items=preview_str)):
                return
            for (canonical, itype), data in queue_items.items():
                scope = data["scope_var"].get()
                if itype == "branch":
                    if scope in ("local", "both"):
                        executor.run(f"git branch -D {canonical}")
                    if scope in ("remote", "both"):
                        executor.run(f"git push {rem} --delete {canonical}")
                else:
                    if scope in ("local", "both"):
                        executor.run(f"git tag -d {canonical}")
                    if scope in ("remote", "both"):
                        executor.run(f"git push {rem} --delete {canonical}")
            messagebox.showinfo(lm.t('msg.done'),
                                lm.t('dialog.delete_panel.done_msg',
                                     default='刪除操作已執行（請查看 Terminal）'))
            dialog.destroy()

        ttk.Button(btn_ctrl, text=lm.t('dialog.shared.refresh_btn', default='↻ Refresh'),
                   command=_build_pool, width=8).pack(side="left", padx=2)
        ttk.Button(btn_ctrl, text=lm.t('dialog.delete_panel.clear_btn', default='清空清單'),
                   command=_clear_queue, width=8).pack(side="left", padx=2)
        ttk.Button(btn_ctrl,
                   text=lm.t('dialog.delete_panel.execute_btn', default='🗑️ 執行刪除'),
                   command=on_delete, width=16, style="Danger.TButton").pack(side="right", padx=2)

        ttk.Button(outer, text=lm.t('dialog.shared.cancel_btn', default='✗ 取消'),
                   command=dialog.destroy, width=10).pack(side="right", pady=(0, 0))

        dialog.bind("<Escape>", lambda e: dialog.destroy())
        search_entry.focus_set()

if __name__ == "__main__":
    root = tk.Tk()
    app = GitAdvancedTool(root)
    root.mainloop()
