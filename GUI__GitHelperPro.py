import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os

from src.core.git_handler.commands import get_commands_configs
from src.core.git_handler.executor import GitExecutor
from src.gui.command_panel import CommandPanel
from src.gui.danger_operation_blocker import ConfirmationManager
from src.gui.dialogs import GitCommandDialog, setup_autocomplete
from src.core.language_manager import lm
from src.version import __version__


# ==========================================
# ReorderableClosableNotebook (可互動標籤頁)
# ==========================================
class ReorderableClosableNotebook(ttk.Notebook):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<Button-2>", self._on_middle_click)
        self.bind("<Button-3>", self._show_context_menu)
        self._dragging_tab = None

    def _on_press(self, event):
        try:
            element = self.identify(event.x, event.y)
            if "label" in element:
                self._dragging_tab = self.index(f"@{event.x},{event.y}")
        except Exception:
            self._dragging_tab = None

    def _on_drag(self, event):
        if self._dragging_tab is None:
            return
        try:
            new_index = self.index(f"@{event.x},{event.y}")
            if new_index != self._dragging_tab:
                tabs = self.tabs()
                self.insert(new_index, tabs[self._dragging_tab])
                self._dragging_tab = new_index
        except Exception:
            pass

    def _on_middle_click(self, event):
        try:
            index = self.index(f"@{event.x},{event.y}")
            if index is not None:
                self.forget(index)
        except Exception:
            pass

    def _show_context_menu(self, event):
        try:
            index = self.index(f"@{event.x},{event.y}")
            if index is not None:
                menu = tk.Menu(self, tearoff=0)
                menu.add_command(label=lm.t('tab.close', default="Close Tab"), 
                                 command=lambda: self.forget(index))
                menu.post(event.x_root, event.y_root)
        except Exception:
            pass

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
        self.notebook = ReorderableClosableNotebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

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
            if not self.confirm_mgr.confirm(config['name'], None, category=cmd_key):
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
        dialog.geometry("600x550")
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
            (0, lm.t('dialog.rebase_onto.newbase_label'),
             lm.t('dialog.rebase_onto.newbase_hint'),
             newbase_var, branches + head_shortcuts + commit_hashes),
            (1, lm.t('dialog.rebase_onto.upstream_label'),
             lm.t('dialog.rebase_onto.upstream_hint'),
             upstream_var, head_shortcuts + commit_hashes + branches),
            (2, lm.t('dialog.rebase_onto.branch_label'),
             lm.t('dialog.rebase_onto.branch_field_hint'),
             branch_var, [""] + branches),
        ]

        for row, label, hint, var, atype in [
            (0, lm.t('dialog.rebase_onto.newbase_label'), lm.t('dialog.rebase_onto.newbase_hint'), newbase_var, 'branch_tag'),
            (1, lm.t('dialog.rebase_onto.upstream_label'), lm.t('dialog.rebase_onto.upstream_hint'), upstream_var, 'commit'),
            (2, lm.t('dialog.rebase_onto.branch_label'), lm.t('dialog.rebase_onto.branch_field_hint'), branch_var, 'branch'),
        ]:
            ttk.Label(fields_lf, text=label, font=("Arial", 9, "bold")).grid(
                row=row * 2, column=0, sticky="nw", padx=(0, 10), pady=(8, 0))
            
            f_container = ttk.Frame(fields_lf)
            f_container.grid(row=row * 2, column=1, sticky="ew", pady=(8, 0))
            
            ent = ttk.Entry(f_container, textvariable=var, font=("Consolas", 10))
            ent.pack(fill="x")
            
            setup_autocomplete(ent, var, atype, f_container, repo_path, on_execute)

            hint_row = ttk.Frame(fields_lf)
            hint_row.grid(row=row * 2 + 1, column=1, sticky="ew", padx=(2, 0), pady=(2, 0))
            ttk.Label(hint_row, text=hint, font=("Arial", 8), foreground="#777").pack(side="left")
            
            if row == 0: first_ent = ent

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

        first_ent.focus_set()

    def open_merge_dialog(self, executor):
        """Merge 對話框：支援一般、--no-ff、--squash、--ff-only 四種模式"""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.merge.title'))
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
        
        source_frame = ttk.Frame(fields_lf)
        source_frame.grid(row=0, column=1, sticky="ew", pady=(0, 2))
        source_entry = ttk.Entry(source_frame, textvariable=source_var, font=("Consolas", 10))
        source_entry.pack(fill="x")
        
        setup_autocomplete(source_entry, source_var, 'branch_tag', source_frame, repo_path, on_execute)

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
        ttk.Button(btn_bar, text=lm.t('dialog.merge.abort_btn'),
                   command=lambda: (executor.run_simple("merge --abort"), dialog.destroy()),
                   width=10, style="Danger.TButton").pack(side="left", padx=2)
        ttk.Button(btn_bar, text=lm.t('dialog.merge.continue_btn'),
                   command=lambda: (executor.run_simple("merge --continue"), dialog.destroy()),
                   width=14).pack(side="left", padx=2)

        source_entry.focus_set()

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

        def on_execute_checkout():
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

        setup_autocomplete(entry, entry_var, 'branch_tag', search_lf, repo_path, on_execute_checkout)

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
        ttk.Button(btn_bar, text=lm.t('dialog.checkouts.execute_btn'), command=on_execute_checkout, width=16).pack(side="right", padx=2)
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

        setup_autocomplete(entry1, entry_var, 'branch_tag', search_lf, repo_path, on_checkout)

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
        ttk.Combobox(fields2, textvariable=source_var, values=["HEAD"] + source_vals,
                     font=("Consolas", 10), state="normal").grid(row=0, column=1, sticky="ew")
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
    def open_rename_branch_dialog(self, executor):
        """Rename/Move Branch: rename local and optionally handle remote."""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('btn.branch_rename'))
        dialog.geometry("550x450")
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        pw, ph, px, py = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{px + (pw // 2) - (dw // 2)}+{py + (ph // 2) - (dh // 2)}")

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill="both", expand=True)

        # 選擇現有分支
        ttk.Label(main, text="Select Branch to Rename:", font=("Arial", 9, "bold")).pack(anchor="w")
        old_var = tk.StringVar()
        old_frame = ttk.Frame(main)
        old_frame.pack(fill="x", pady=(2, 10))
        old_ent = ttk.Entry(old_frame, textvariable=old_var, font=("Consolas", 10))
        old_ent.pack(fill="x")
        setup_autocomplete(old_ent, old_var, 'branch', old_frame, repo_path)

        # 輸入新名稱
        ttk.Label(main, text="New Branch Name:", font=("Arial", 9, "bold")).pack(anchor="w")
        new_var = tk.StringVar()
        new_ent = ttk.Entry(main, textvariable=new_var, font=("Consolas", 10))
        new_ent.pack(fill="x", pady=(2, 10))

        # 選項
        sync_remote = tk.BooleanVar(value=True)
        ttk.Checkbutton(main, text="Also Rename on Remote (Delete old, Push new)", variable=sync_remote).pack(anchor="w", pady=5)
        
        remote_var = tk.StringVar(value="origin")
        rem_frame = ttk.Frame(main)
        rem_frame.pack(fill="x", pady=5)
        ttk.Label(rem_frame, text="Remote:").pack(side="left")
        ttk.Entry(rem_frame, textvariable=remote_var, width=10).pack(side="left", padx=5)

        def on_rename():
            old_n = old_var.get().strip()
            new_n = new_var.get().strip()
            rem = remote_var.get().strip() or "origin"
            if not old_n or not new_n:
                messagebox.showwarning("Missing Info", "Please provide both old and new names.")
                return
            
            # Local Rename
            executor.run(f"git branch -m {old_n} {new_n}")
            
            if sync_remote.get():
                # Check if old branch exists on remote
                res = subprocess.run(f"git ls-remote --heads {rem} {old_n}", cwd=repo_path, shell=True, capture_output=True, text=True)
                if old_n in res.stdout:
                    if messagebox.askyesno("Remote Sync", f"Branch '{old_n}' exists on '{rem}'.\nDo you want to delete it and push '{new_n}'?"):
                        executor.run(f"git push {rem} :{old_n}")
                        executor.run(f"git push {rem} {new_n}")
                        # Set upstream
                        executor.run(f"git branch --set-upstream-to={rem}/{new_n} {new_n}")
            
            messagebox.showinfo("Done", f"Branch renamed from {old_n} to {new_n}")
            dialog.destroy()

        btn_bar = ttk.Frame(main)
        btn_bar.pack(fill="x", pady=(15, 0))
        ttk.Button(btn_bar, text="✓ Execute Rename", command=on_rename, width=20).pack(side="right")
        ttk.Button(btn_bar, text="Cancel", command=dialog.destroy).pack(side="right", padx=5)

    def open_rename_tag_dialog(self, executor):
        """Rename/Move Tag: rename local and optionally handle remote."""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('btn.tag_rename'))
        dialog.geometry("550x450")
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        pw, ph, px, py = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{px + (pw // 2) - (dw // 2)}+{py + (ph // 2) - (dh // 2)}")

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill="both", expand=True)

        # 選擇現有 Tag
        ttk.Label(main, text="Select Tag to Rename/Move:", font=("Arial", 9, "bold")).pack(anchor="w")
        old_var = tk.StringVar()
        old_frame = ttk.Frame(main)
        old_frame.pack(fill="x", pady=(2, 10))
        old_ent = ttk.Entry(old_frame, textvariable=old_var, font=("Consolas", 10))
        old_ent.pack(fill="x")
        setup_autocomplete(old_ent, old_var, 'tag', old_frame, repo_path)

        # 輸入新名稱
        ttk.Label(main, text="New Tag Name:", font=("Arial", 9, "bold")).pack(anchor="w")
        new_var = tk.StringVar()
        new_ent = ttk.Entry(main, textvariable=new_var, font=("Consolas", 10))
        new_ent.pack(fill="x", pady=(2, 10))

        # 選項
        sync_remote = tk.BooleanVar(value=True)
        ttk.Checkbutton(main, text="Also Rename on Remote (Delete old, Push new)", variable=sync_remote).pack(anchor="w", pady=5)
        
        remote_var = tk.StringVar(value="origin")
        rem_frame = ttk.Frame(main)
        rem_frame.pack(fill="x", pady=5)
        ttk.Label(rem_frame, text="Remote:").pack(side="left")
        ttk.Entry(rem_frame, textvariable=remote_var, width=10).pack(side="left", padx=5)

        def on_rename():
            old_n = old_var.get().strip()
            new_n = new_var.get().strip()
            rem = remote_var.get().strip() or "origin"
            if not old_n or not new_n:
                messagebox.showwarning("Missing Info", "Please provide both old and new names.")
                return
            
            # Local Rename: Create new at old's location, then delete old
            executor.run(f"git tag {new_n} {old_n}")
            executor.run(f"git tag -d {old_n}")
            
            if sync_remote.get():
                # Check if old tag exists on remote
                res = subprocess.run(f"git ls-remote --tags {rem} {old_n}", cwd=repo_path, shell=True, capture_output=True, text=True)
                if old_n in res.stdout:
                    if messagebox.askyesno("Remote Sync", f"Tag '{old_n}' exists on '{rem}'.\nDo you want to delete it and push '{new_n}'?"):
                        executor.run(f"git push {rem} :refs/tags/{old_n}")
                        executor.run(f"git push {rem} {new_n}")
            
            messagebox.showinfo("Done", f"Tag renamed from {old_n} to {new_n}")
            dialog.destroy()

        btn_bar = ttk.Frame(main)
        btn_bar.pack(fill="x", pady=(15, 0))
        ttk.Button(btn_bar, text="✓ Execute Rename", command=on_rename, width=20).pack(side="right")
        ttk.Button(btn_bar, text="Cancel", command=dialog.destroy).pack(side="right", padx=5)

    def open_delete_branch_dialog(self, executor):
        """Delete Branch dialog: allow deleting local and/or remote branches with checkboxes."""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.delete_branch.title'))
        dialog.geometry("520x260")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        dialog.update_idletasks()
        rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{rx + (rw // 2) - (dw // 2)}+{ry + (rh // 2) - (dh // 2)}")

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
        name_frame = ttk.Frame(frame)
        name_frame.pack(fill="x", pady=(4, 6))
        name_ent = ttk.Entry(name_frame, textvariable=name_var, font=("Consolas", 10))
        name_ent.pack(fill="x")

        setup_autocomplete(name_ent, name_var, 'branch', name_frame, repo_path, on_execute, multi_select=True)

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
        prev_lf.pack(fill="x", pady=(6, 8))
        preview_var = tk.StringVar()
        ttk.Label(prev_lf, textvariable=preview_var, font=("Consolas", 10), foreground="#cc0000").pack(anchor="w")

        def update_preview(*_):
            names = name_var.get().strip() or '<branch>'
            cmds = []
            for n in names.split():
                if delete_local.get():
                    cmds.append(f"git branch -D {n}")
                if delete_remote.get():
                    cmds.append(f"git push {remote_var.get().strip() or 'origin'} --delete {n}")
            preview_var.set('\n'.join(cmds) if cmds else '<select actions>')

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
            if not messagebox.askokcancel(lm.t('msg.confirm_delete_title'), lm.t('dialog.delete_branch.confirm_msg', preview=preview_var.get())):
                return

            for n in names.split():
                if delete_local.get():
                    executor.run(f"git branch -D {n}")
                if delete_remote.get():
                    r = remote_var.get().strip() or 'origin'
                    executor.run(f"git push {r} --delete {n}")

            messagebox.showinfo(lm.t('msg.done'), lm.t('dialog.delete_branch.done_msg'))
            dialog.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text=lm.t('dialog.delete_branch.execute_btn'), command=on_execute, width=16, style="Danger.TButton").pack(side="right", padx=4)
        ttk.Button(btn_row, text=lm.t('dialog.shared.cancel_btn'), command=dialog.destroy, width=10).pack(side="right")

        name_ent.focus_set()

    # ─────────────────────────────────────────────────────────────────────
    def open_delete_tag_dialog(self, executor):
        """Delete Tag dialog: allow deleting local and/or remote tags with checkboxes."""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.delete_tag.title'))
        dialog.geometry("520x260")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        dialog.update_idletasks()
        rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{rx + (rw // 2) - (dw // 2)}+{ry + (rh // 2) - (dh // 2)}")

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
        tag_frame = ttk.Frame(frame)
        tag_frame.pack(fill="x", pady=(4, 6))
        tag_ent = ttk.Entry(tag_frame, textvariable=tag_var, font=("Consolas", 10))
        tag_ent.pack(fill="x")

        setup_autocomplete(tag_ent, tag_var, 'tag', tag_frame, repo_path, on_execute, multi_select=True)

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
        prev_lf.pack(fill="x", pady=(6, 8))
        preview_var = tk.StringVar()
        ttk.Label(prev_lf, textvariable=preview_var, font=("Consolas", 10), foreground="#cc0000").pack(anchor="w")

        def update_preview(*_):
            names = tag_var.get().strip() or '<tag>'
            cmds = []
            for t in names.split():
                if delete_local.get():
                    cmds.append(f"git tag -d {t}")
                if delete_remote.get():
                    cmds.append(f"git push {remote_var.get().strip() or 'origin'} --delete {t}")
            preview_var.set('\n'.join(cmds) if cmds else '<select actions>')

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
            if not messagebox.askokcancel(lm.t('msg.confirm_delete_title'), lm.t('dialog.delete_tag.confirm_msg', preview=preview_var.get())):
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

        tag_ent.focus_set()

    def open_pushes_dialog(self, executor):
        """Advanced Multi-Push Panel: Select multiple branches/tags, toggle force for each."""
        repo_path = executor.repo_path

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('btn.pushes_panel'))
        dialog.geometry("700x650")
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        rw, rh, rx, ry = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{rx + (rw // 2) - (dw // 2)}+{ry + (rh // 2) - (dh // 2)}")

        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="🚀 Advanced Pushes Panel", font=("Arial", 12, "bold")).pack(pady=(0, 10))

        # 遠端選擇
        rem_frame = ttk.Frame(main_frame)
        rem_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(rem_frame, text="Remote:", font=("Arial", 9, "bold")).pack(side="left", padx=(0, 5))
        remote_var = tk.StringVar(value="origin")
        ttk.Entry(rem_frame, textvariable=remote_var, font=("Consolas", 10), width=15).pack(side="left")

        # 列表區 (Scrollable)
        list_frame = ttk.LabelFrame(main_frame, text=" Select Branches & Tags to Push ", padding=10)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))

        canvas = tk.Canvas(list_frame, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scroll_content = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=scroll_content, anchor="nw", tags="frame")
        canvas.configure(yscrollcommand=scrollbar.set)
        scroll_content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure("frame", width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        items_data = [] # list of (type, name, select_var, force_var)

        def add_item_row(itype, name):
            row = ttk.Frame(scroll_content)
            row.pack(fill="x", pady=2)
            
            sel_var = tk.BooleanVar(value=False)
            force_var = tk.BooleanVar(value=False)
            
            ttk.Checkbutton(row, variable=sel_var).pack(side="left")
            
            icon = "🌿" if itype == "branch" else "🏷️"
            tk.Label(row, text=f"{icon} {name}", font=("Consolas", 10), width=40, anchor="w").pack(side="left", padx=5)
            
            force_cb = ttk.Checkbutton(row, text="Force", variable=force_var)
            force_cb.pack(side="right")
            
            items_data.append({'type': itype, 'name': name, 'sel': sel_var, 'force': force_var})

        # 獲取資料
        try:
            # Branches
            res_b = subprocess.run("git branch", cwd=repo_path, shell=True, capture_output=True, text=True, encoding='utf-8')
            for line in res_b.stdout.splitlines():
                name = line.replace('*', '').strip()
                if name: add_item_row("branch", name)
            
            # Tags
            res_t = subprocess.run("git tag", cwd=repo_path, shell=True, capture_output=True, text=True, encoding='utf-8')
            for line in res_t.stdout.splitlines():
                name = line.strip()
                if name: add_item_row("tag", name)
        except:
            pass

        def on_push_all():
            remote = remote_var.get().strip() or "origin"
            selected = [item for item in items_data if item['sel'].get()]
            if not selected:
                messagebox.showwarning("No Selection", "Please select at least one branch or tag.")
                return
            
            # 先確認
            preview = []
            for item in selected:
                prefix = "+" if item['force'].get() else ""
                preview.append(f"{item['name']} ({'Branch' if item['type']=='branch' else 'Tag'}{' + Force' if item['force'].get() else ''})")
            
            if not messagebox.askokcancel("Confirm Multi-Push", "Ready to push the following items to " + remote + ":\n\n" + "\n".join(preview)):
                return
            
            for item in selected:
                cmd = ["git", "push", remote]
                if item['force'].get():
                    cmd.append("-f")
                
                if item['type'] == "tag":
                    cmd.append(f"refs/tags/{item['name']}:refs/tags/{item['name']}")
                else:
                    cmd.append(item['name'])
                
                executor.run(" ".join(cmd))
            
            messagebox.showinfo("Done", "Multi-Push operations completed. Check Terminal for results.")
            dialog.destroy()

        btn_bar = ttk.Frame(main_frame)
        btn_bar.pack(fill="x")
        ttk.Button(btn_bar, text="🚀 Execute All Pushes", command=on_push_all, width=25).pack(side="right", padx=5)
        ttk.Button(btn_bar, text="Cancel", command=dialog.destroy).pack(side="right")
        
        # 全選/全不選
        def set_all(val):
            for item in items_data: item['sel'].set(val)
        ttk.Button(btn_bar, text="Select All", command=lambda: set_all(True), width=10).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="Clear All", command=lambda: set_all(False), width=10).pack(side="left", padx=2)

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

if __name__ == "__main__":
    root = tk.Tk()
    app = GitAdvancedTool(root)
    root.mainloop()