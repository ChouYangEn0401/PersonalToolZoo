import tkinter as tk
from tkinter import ttk, messagebox
import subprocess


class GitCommandDialog:
    """彈出式指令參數設定視窗"""

    def __init__(self, parent, command_name, params_config, repo_path=None):
        self.result = None
        self.repo_path = repo_path
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
        """確保彈窗出現在父視窗的正中央"""
        self.dialog.update_idletasks()

        # 取得父視窗 (主程式) 的尺寸與位置
        parent = self.dialog.master
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()

        # 取得彈窗目前的尺寸
        dialog_width = self.dialog.winfo_width()
        dialog_height = self.dialog.winfo_height()

        # 計算相對於父視窗的中心座標
        # 公式：父座標 + (父寬 - 子寬) // 2
        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)

        # 設定位置
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
        canvas.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        first_entry = None  # 用於紀錄第一個 Entry

        # 動態生成參數欄位
        for i, param in enumerate(self.params_config):
            frame = ttk.Frame(scroll_frame)
            frame.pack(fill="x", pady=8, padx=5)

            if param['type'] == 'text':
                label_text = param['label'] + (" *" if param['required'] else "")
                ttk.Label(frame, text=label_text, foreground="red" if param['required'] else "black").pack(anchor="w")

                entry_frame = ttk.Frame(frame)
                entry_frame.pack(fill="x", pady=(3, 0))

                var = tk.StringVar(value=param.get('default', ''))
                entry = ttk.Entry(entry_frame, textvariable=var, font=("Consolas", 10))
                entry.pack(fill="x")

                # --- 綁定 Enter 執行 ---
                entry.bind("<Return>", lambda e: self._on_submit())

                # 紀錄第一個輸入框
                if first_entry is None:
                    first_entry = entry

                if param.get('autocomplete') and self.repo_path:
                    self._setup_autocomplete(entry, var, param.get('autocomplete'), entry_frame)

                self.param_widgets[param['name']] = {
                    'type': 'text', 'var': var, 'required': param['required'],
                    'widget': entry, 'frame': entry_frame
                }

            elif param['type'] == 'toggle':
                var = tk.BooleanVar(value=param.get('default', False))
                ttk.Checkbutton(frame, text=param['label'], variable=var).pack(anchor="w")
                self.param_widgets[param['name']] = {'type': 'toggle', 'var': var, 'required': False}

        # 底部按鈕
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(15, 0))
        ttk.Button(btn_frame, text="✓ 執行", command=self._on_submit, width=15).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="✗ 取消", command=self._on_cancel, width=15).pack(side="right")

        # --- 自動聚焦 ---
        if first_entry:
            first_entry.focus_set()

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

    def _setup_autocomplete(self, entry, var, autocomplete_type, parent_frame):
        """自動完成：Tab/Shift+Tab 導航清單，Space 確認選取，焦點留在 Entry"""
        listbox = None
        listbox_frame = None
        _highlighted = [-1]          # 追蹤目前反白的 index
        _ignore_trace = [False]       # 選取後寫回 var 時暫停 trace

        # ── 取得建議清單 ─────────────────────────────────────────
        def get_suggestions(text):
            if not self.repo_path:
                return []
            try:
                if autocomplete_type == 'branch':
                    res = subprocess.run("git branch -a", cwd=self.repo_path, shell=True,
                                         capture_output=True, text=True, encoding='utf-8', errors='replace')
                    raw = [b.strip().replace('* ', '').replace('remotes/origin/', '')
                           for b in res.stdout.split('\n') if b.strip()]
                    items = sorted(set(b for b in raw if not text or text.lower() in b.lower()))
                    return items[:12]

                elif autocomplete_type == 'tag':
                    res = subprocess.run("git tag -l", cwd=self.repo_path, shell=True,
                                         capture_output=True, text=True, encoding='utf-8', errors='replace')
                    items = sorted(t.strip() for t in res.stdout.split('\n')
                                   if t.strip() and (not text or text.lower() in t.lower()))
                    return items[:12]

                elif autocomplete_type == 'commit':
                    res = subprocess.run("git log --oneline -n 50", cwd=self.repo_path, shell=True,
                                         capture_output=True, text=True, encoding='utf-8', errors='replace')
                    commits = []
                    for line in res.stdout.split('\n'):
                        if line.strip():
                            parts = line.split(' ', 1)
                            if len(parts) == 2 and (not text or text.lower() in line.lower()):
                                commits.append(f"{parts[0]} - {parts[1][:50]}")
                    return commits[:12]
            except:
                pass
            return []

        # ── 把 listbox 第 idx 項反白（不改 Entry 內容）────────────
        def _set_highlight(idx):
            nonlocal listbox
            if listbox is None:
                return
            size = listbox.size()
            if size == 0:
                return
            idx = max(0, min(idx, size - 1))
            _highlighted[0] = idx
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(idx)
            listbox.see(idx)

        # ── 確認選取當前反白項目 ───────────────────────────────────
        def _confirm_selection():
            nonlocal listbox
            if listbox is None or _highlighted[0] < 0:
                return
            try:
                value = listbox.get(_highlighted[0])
                if autocomplete_type == 'commit':
                    value = value.split(' - ')[0]
                _ignore_trace[0] = True
                var.set(value)
                _ignore_trace[0] = False
                # 把游標移到 Entry 末尾
                entry.icursor(tk.END)
                hide_suggestions()
            except tk.TclError:
                pass

        # ── 顯示 / 更新 建議列表 ──────────────────────────────────
        def show_suggestions():
            nonlocal listbox, listbox_frame
            suggestions = get_suggestions(var.get())

            if not suggestions:
                hide_suggestions()
                return

            if listbox_frame is None:
                listbox_frame = tk.Frame(parent_frame, relief="solid", bd=1)
                listbox_frame.pack(fill="x", pady=(2, 0))
                nonlocal listbox
                listbox = tk.Listbox(
                    listbox_frame,
                    font=("Consolas", 9),
                    bg="#fffacd",
                    selectbackground="#3399ff",
                    selectforeground="#ffffff",
                    activestyle="none",
                    exportselection=False,
                )
                listbox.pack(fill="x")

                # 滑鼠點一下直接確認
                listbox.bind('<ButtonRelease-1>', lambda e: _confirm_selection())

            listbox.delete(0, tk.END)
            for s in suggestions:
                listbox.insert(tk.END, s)
            listbox.config(height=min(len(suggestions), 6))

            # 文字改變 → 清單刷新 → 反白第一項
            _set_highlight(0)

        # ── 隱藏建議列表 ──────────────────────────────────────────
        def hide_suggestions(event=None):
            nonlocal listbox, listbox_frame
            if listbox_frame:
                listbox_frame.destroy()
                listbox_frame = None
                listbox = None
            _highlighted[0] = -1

        # ── Tab：往下，Shift+Tab：往上（焦點留在 Entry）────────────
        def on_tab(event):
            if listbox is not None and listbox.size() > 0:
                cur = _highlighted[0]
                _set_highlight(cur + 1 if cur < listbox.size() - 1 else 0)
                return "break"          # 阻止 Tab 跳焦點
            return None

        def on_shift_tab(event):
            if listbox is not None and listbox.size() > 0:
                cur = _highlighted[0]
                _set_highlight(cur - 1 if cur > 0 else listbox.size() - 1)
                return "break"
            return None

        # ── Space：選取目前反白項目 ───────────────────────────────
        def on_space(event):
            if listbox is not None and _highlighted[0] >= 0:
                _confirm_selection()
                return "break"
            return None

        # ── Enter：也可以確認（不阻止表單提交） ───────────────────
        def on_enter(event):
            if listbox is not None and _highlighted[0] >= 0:
                _confirm_selection()
                return "break"
            # 若沒有建議清單或未反白任何項目，維持原先 Enter 的行為（提交對話框）
            try:
                self._on_submit()
            except Exception:
                pass
            return None

        # ── 綁定事件 ──────────────────────────────────────────────
        def on_var_change(*_):
            if not _ignore_trace[0]:
                show_suggestions()

        var.trace('w', on_var_change)
        entry.bind('<Tab>',            on_tab)
        entry.bind('<Shift-Tab>',      on_shift_tab)
        entry.bind('<space>',          on_space)
        entry.bind('<Return>',         on_enter)
        entry.bind('<Escape>',         hide_suggestions)
        entry.bind('<FocusOut>',       lambda e: self.dialog.after(200, hide_suggestions))

        # 在輸入框下方顯示簡短鍵盤說明（小字、灰色）
        try:
            help_text = (
                "Tab: 清單向下移一格（循環到首項）\n"
                "Shift+Tab: 清單向上移一格（循環到末項）\n"
                "Space: 確認目前反白項目，填入 Entry，關閉清單\n"
                "Enter: 同 Space（亦可確認）\n"
                "滑鼠單擊: 直接確認（ButtonRelease-1）\n"
                "Escape / FocusOut: 隱藏清單"
            )
            help_label = ttk.Label(parent_frame, text=help_text, font=("Arial", 9), foreground="#666666", justify="left")
            help_label.pack(fill="x", pady=(4, 0))
        except Exception:
            # UI 輸出不影響功能
            pass

