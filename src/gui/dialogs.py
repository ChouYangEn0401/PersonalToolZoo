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
        """設置自動完成功能"""
        listbox = None
        listbox_frame = None

        def get_suggestions(text):
            """根據類型獲取建議列表"""
            if not text or not self.repo_path:
                return []

            try:
                if autocomplete_type == 'branch':
                    # 獲取所有分支
                    res = subprocess.run("git branch -a", cwd=self.repo_path, shell=True,
                                         capture_output=True, text=True, encoding='utf-8', errors='replace')
                    branches = [b.strip().replace('* ', '').replace('remotes/origin/', '')
                                for b in res.stdout.split('\n') if b.strip()]
                    # 去重並過濾
                    branches = list(set(b for b in branches if text.lower() in b.lower()))
                    return sorted(branches)[:10]

                elif autocomplete_type == 'tag':
                    # 獲取所有標籤
                    res = subprocess.run("git tag -l", cwd=self.repo_path, shell=True,
                                         capture_output=True, text=True, encoding='utf-8', errors='replace')
                    tags = [t.strip() for t in res.stdout.split('\n') if t.strip() and text.lower() in t.lower()]
                    return sorted(tags)[:10]

                elif autocomplete_type == 'commit':
                    # 獲取最近的 commit
                    res = subprocess.run("git log --oneline -n 50", cwd=self.repo_path, shell=True,
                                         capture_output=True, text=True, encoding='utf-8', errors='replace')
                    commits = []
                    for line in res.stdout.split('\n'):
                        if line.strip():
                            parts = line.split(' ', 1)
                            if len(parts) == 2 and text.lower() in line.lower():
                                commits.append(f"{parts[0]} - {parts[1][:50]}")
                    return commits[:10]
            except:
                pass
            return []

        def show_suggestions(event=None):
            """顯示建議列表"""
            nonlocal listbox, listbox_frame

            text = var.get()
            if len(text) < 1:
                hide_suggestions()
                return

            suggestions = get_suggestions(text)
            if not suggestions:
                hide_suggestions()
                return

            # 創建或更新 Listbox
            if not listbox_frame:
                listbox_frame = tk.Frame(parent_frame)
                listbox_frame.pack(fill="x", pady=(2, 0))

                listbox = tk.Listbox(listbox_frame, height=min(len(suggestions), 6),
                                     font=("Consolas", 9), bg="#fffacd")
                listbox.pack(fill="x")

                def on_select(event):
                    if listbox.curselection():
                        value = listbox.get(listbox.curselection()[0])
                        # 提取實際值（去除 commit 的描述部分）
                        if autocomplete_type == 'commit':
                            value = value.split(' - ')[0]
                        var.set(value)
                        hide_suggestions()

                listbox.bind('<<ListboxSelect>>', on_select)
                listbox.bind('<Double-Button-1>', on_select)

            # 更新建議
            listbox.delete(0, tk.END)
            for s in suggestions:
                listbox.insert(tk.END, s)
            listbox.config(height=min(len(suggestions), 6))

        def hide_suggestions(event=None):
            """隱藏建議列表"""
            nonlocal listbox, listbox_frame
            if listbox_frame:
                listbox_frame.destroy()
                listbox_frame = None
                listbox = None

        # 綁定事件
        var.trace('w', lambda *args: show_suggestions())
        entry.bind('<FocusOut>', lambda e: self.dialog.after(200, hide_suggestions))
        entry.bind('<Escape>', hide_suggestions)

