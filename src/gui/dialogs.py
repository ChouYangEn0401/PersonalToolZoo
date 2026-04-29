import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
from src.core.language_manager import lm

import os

def setup_autocomplete(entry, var, autocomplete_type, parent_frame, repo_path, on_submit_callback=None, multi_select=False):
    """
    通用自動完成功能：
    支援 Tab/Shift+Tab 導航，Space/Enter 確認。
    """
    listbox = None
    listbox_frame = None
    _highlighted = [-1]
    _ignore_trace = [False]

    def get_suggestions(text):
        if not repo_path: return []
        try:
            if autocomplete_type == 'branch':
                res = subprocess.run("git branch -a", cwd=repo_path, shell=True,
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
                raw = [b.strip().replace('* ', '').replace('remotes/origin/', '').replace('remotes/', '')
                       for b in res.stdout.split('\n') if b.strip()]
                items = sorted(set(b for b in raw if not text or text.lower() in b.lower()))
                return items[:15]
            elif autocomplete_type == 'tag':
                res = subprocess.run("git tag -l", cwd=repo_path, shell=True,
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
                items = sorted(t.strip() for t in res.stdout.split('\n')
                               if t.strip() and (not text or text.lower() in t.lower()))
                return items[:15]
            elif autocomplete_type == 'commit':
                res = subprocess.run("git log --oneline -n 50", cwd=repo_path, shell=True,
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
                commits = []
                for line in res.stdout.split('\n'):
                    if line.strip():
                        parts = line.split(' ', 1)
                        if len(parts) == 2 and (not text or text.lower() in line.lower()):
                            commits.append(f"{parts[0]} - {parts[1][:50]}")
                return commits[:15]
            elif autocomplete_type == 'branch_tag':
                # 綜合搜尋 (用於 checkout)
                res_b = subprocess.run("git branch -a", cwd=repo_path, shell=True,
                                       capture_output=True, text=True, encoding='utf-8', errors='replace')
                branches = [b.strip().replace('* ', '').replace('remotes/', '')
                            for b in res_b.stdout.splitlines() if b.strip()]
                res_t = subprocess.run("git tag -l", cwd=repo_path, shell=True,
                                       capture_output=True, text=True, encoding='utf-8', errors='replace')
                tags = [t.strip() for t in res_t.stdout.splitlines() if t.strip()]
                items = sorted(set(branches + tags))
                if not text: return items[:15]
                p = text.lower()
                return [i for i in items if p in i.lower()][:15]
        except: pass
        return []

    def _set_highlight(idx):
        nonlocal listbox
        if listbox is None: return
        size = listbox.size()
        if size == 0: return
        idx = max(0, min(idx, size - 1))
        _highlighted[0] = idx
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(idx)
        listbox.see(idx)

    def _confirm_selection():
        nonlocal listbox
        if listbox is None or _highlighted[0] < 0: return
        try:
            value = listbox.get(_highlighted[0])
            if autocomplete_type == 'commit':
                value = value.split(' - ')[0]
            
            _ignore_trace[0] = True
            if multi_select:
                current = var.get().strip()
                # 取得最後一個單字之前的內容
                parts = current.split()
                if parts:
                    parts[-1] = value
                    var.set(" ".join(parts) + " ")
                else:
                    var.set(value + " ")
            else:
                var.set(value)
            _ignore_trace[0] = False
            
            entry.icursor(tk.END)
            hide_suggestions()
        except tk.TclError: pass

    def show_suggestions():
        nonlocal listbox, listbox_frame
        current_val = var.get()
        # 如果是多選，只拿最後一個單字來比對
        search_text = current_val.split()[-1] if multi_select and current_val.strip() else current_val
        suggestions = get_suggestions(search_text)
        if not suggestions:
            hide_suggestions()
            return
        if listbox_frame is None:
            listbox_frame = tk.Frame(parent_frame, relief="solid", bd=1)
            listbox_frame.pack(fill="x", pady=(2, 0))
            listbox = tk.Listbox(listbox_frame, font=("Consolas", 9), bg="#fffacd",
                                 selectbackground="#3399ff", selectforeground="#ffffff",
                                 activestyle="none", exportselection=False)
            listbox.pack(fill="x")
            listbox.bind('<ButtonRelease-1>', lambda e: _confirm_selection())
        listbox.delete(0, tk.END)
        for s in suggestions: listbox.insert(tk.END, s)
        listbox.config(height=min(len(suggestions), 8))
        _set_highlight(0)

    def hide_suggestions(event=None):
        nonlocal listbox, listbox_frame
        if listbox_frame:
            listbox_frame.destroy()
            listbox_frame = None
            listbox = None
        _highlighted[0] = -1

    def on_tab(event):
        if listbox is not None and listbox.size() > 0:
            cur = _highlighted[0]
            _set_highlight(cur + 1 if cur < listbox.size() - 1 else 0)
            return "break"
        return None

    def on_shift_tab(event):
        if listbox is not None and listbox.size() > 0:
            cur = _highlighted[0]
            _set_highlight(cur - 1 if cur > 0 else listbox.size() - 1)
            return "break"
        return None

    def on_space(event):
        if listbox is not None and _highlighted[0] >= 0:
            _confirm_selection()
            return "break"
        return None

    def on_enter(event):
        if listbox is not None and _highlighted[0] >= 0:
            _confirm_selection()
            return "break"
        if on_submit_callback:
            on_submit_callback()
        return None

    def on_var_change(*_):
        if not _ignore_trace[0]:
            show_suggestions()

    var.trace('w', on_var_change)
    entry.bind('<Tab>', on_tab)
    entry.bind('<Shift-Tab>', on_shift_tab)
    entry.bind('<space>', on_space)
    entry.bind('<Return>', on_enter)
    entry.bind('<Escape>', hide_suggestions)
    # 增加少許延遲避免點擊時立刻消失
    entry.bind('<FocusOut>', lambda e: entry.after(200, hide_suggestions))

    try:
        help_label = ttk.Label(parent_frame, text=lm.t('autocomplete.hint'),
                               font=("Arial", 9), foreground="#666666", justify="left")
        help_label.pack(fill="x", pady=(4, 0))
    except: pass


class GitCommandDialog:
    """彈出式指令參數設定視窗"""

    def __init__(self, parent, command_name, params_config, repo_path=None):
        self.result = None
        self.repo_path = repo_path
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(lm.t('dialog.params.title_fmt', default=f'[{command_name}]').format(cmd=command_name))
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
        title = ttk.Label(main_frame, text=lm.t('dialog.params.header'), font=("Arial", 12, "bold"))
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
        ttk.Button(btn_frame, text=lm.t('dialog.params.submit_btn'), command=self._on_submit, width=15).pack(side="right", padx=5)
        ttk.Button(btn_frame, text=lm.t('dialog.params.cancel_btn'), command=self._on_cancel, width=15).pack(side="right")

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
            messagebox.showwarning(lm.t('dialog.params.incomplete_title'), lm.t('dialog.params.incomplete_msg'))
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
        setup_autocomplete(entry, var, autocomplete_type, parent_frame, self.repo_path, self._on_submit)

