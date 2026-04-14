import tkinter as tk
from tkinter import ttk

# ==========================================
# CommandPanel (按鈕佈局與生成模組)
# ==========================================
class CommandPanel(ttk.Frame):
    def __init__(self, parent, executor, confirm_mgr, app_callback_handler):
        super().__init__(parent, width=320)
        self.executor = executor
        self.confirm_mgr = confirm_mgr
        self.app = app_callback_handler  # 為了呼叫複雜對話框 (open_dialog, file_selector)

        self.grid(row=0, column=0, sticky="ns", padx=(5, 2))
        self.grid_propagate(False)

        self._init_scroll_area()
        self._build_quick_entry()
        self._build_buttons()
        self._bind_mouse_wheel()

    def _init_scroll_area(self):
        self.canvas = tk.Canvas(self, bg="#f0f0f0", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def _bind_mouse_wheel(self):
        def _on_mousewheel(event):
            if event.num == 4 or event.delta > 0:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5 or event.delta < 0:
                self.canvas.yview_scroll(1, "units")

        def bind_recursive(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)
            widget.bind("<Button-5>", _on_mousewheel)
            for child in widget.winfo_children():
                bind_recursive(child)

        # 延遲綁定以確保所有元件已生成
        self.after(100, lambda: bind_recursive(self.canvas))

    def _build_quick_entry(self):
        quick_frame = ttk.LabelFrame(self.scrollable_frame, text=" ⚡ 快速執行 ")
        quick_frame.pack(fill="x", padx=5, pady=5)

        entry_var = tk.StringVar()
        entry = ttk.Entry(quick_frame, textvariable=entry_var, font=("Consolas", 10))
        entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        def run_q():
            cmd = entry_var.get().strip()
            if cmd:
                full = f"git {cmd}" if not cmd.startswith("git ") else cmd
                self.executor.run(full)
                entry_var.set("")

        ttk.Button(quick_frame, text="執行", width=8, command=run_q).pack(side="right", padx=5)
        entry.bind("<Return>", lambda e: run_q())

    def _build_buttons(self):
        # 這裡定義按鈕配置
        layout_configs = [
            ("🛠️ 快速互動 Rebase", [
                [("HEAD~2", lambda: self.executor.run_simple("rebase -i HEAD~2"), 8, False),
                ("HEAD~4", lambda: self.executor.run_simple("rebase -i HEAD~4"), 8, False),
                ("HEAD~10", lambda: self.executor.run_simple("rebase -i HEAD~10"), 8, False)],
            ]),
            ("🔄 Rebase 流程控制", [
                [("互動模式", 'rebase_interactive', 10, False),
                ("指定位置", 'rebase_branch', 10, False),
                ("🔀 OnTo", lambda: self.app.open_rebase_onto_dialog(self.executor), 10, False)],
                [("▶️ Continue", lambda: self.executor.run_simple("rebase --continue"), 12, False),
                ("🛑 Abort", lambda: self.executor.run_simple("rebase --abort"), 12, False),
                ("⏭️ Skip", lambda: self.executor.run_simple("rebase --skip"), 12, False)],
            ]),
            ("🔀 Merge 合併", [
                [("🔀 Merge 分支", lambda: self.app.open_merge_dialog(self.executor), 24, False)],
                [("▶️ Continue", lambda: self.executor.run_simple("merge --continue"), 12, False),
                ("🛑 Abort", lambda: self.executor.run_simple("merge --abort"), 12, True)],
            ]),
            ("🍒 Cherry-pick", [
                [("Cherry-pick Hash", 'cherry_pick', 24, False),
                ("⟲ 從 Hash 還原檔案", 'restore_file_from_commit', 24, False)],
                [("▶️ Continue", lambda: self.executor.run_simple("cherry-pick --continue"), 12, False),
                ("🛑 Abort", lambda: self.executor.run_simple("cherry-pick --abort"), 12, False)],
            ]),
            ("⏪ Reset 回退", [
                [("Soft HEAD~1", lambda: self.executor.run_simple("reset --soft HEAD~1"), 12, False),
                ("Soft HEAD~2", lambda: self.executor.run_simple("reset --soft HEAD~2"), 12, False)],
                [("🧨 Soft (保留變更)", 'reset_soft', 12, False),
                ("⚠️ Hard (捨棄變更)", 'reset_hard', 12, True)],
            ]),
            ("📝 提交與暫存", [
                [("🔧 Fixup (f)", lambda: self.executor.quick_commit("f", "fixup"), 6, False),
                ("📦 Squash (s)", lambda: self.executor.quick_commit("s", "squash"), 6, False),
                ("⚡ FastCommit (stash)", lambda: self.executor.quick_commit("stash", "stash"), 14, False)],
                [(("➕ Add 選擇檔案", lambda: self.app.open_file_selector(self.executor), 12, False))],
                [("💬 Commit -m", 'commit_message', 12, False),
                ("✏️ Amend", 'commit_amend', 12, False)],
            ]),
            ("✈️ 遠端推送", [
                [("⬆️ Push", lambda: self.executor.run_simple("push"), 12, False),
                ("⚡ Force Push", 'force_push', 12, True)],
                [("🛰️ Push Tags", lambda: self.executor.run_simple("push --tags"), 14, False)],
            ]),
            ("📦 Stash 緩衝區", [
                [("📥 Stash Save", lambda: self.executor.run_simple("stash"), 12, False),
                ("📤 Stash Pop", lambda: self.executor.run_simple("stash pop"), 12, False)],
                [("📜 Stash List", lambda: self.executor.run_simple("stash list"), 12, False),
                ("🧹 Stash Clear",
                 lambda: self.confirm_mgr.confirm("清空 stash", lambda: self.executor.run_simple("stash clear")), 12,
                 True),
                ("🗑️ Stash Drop",
                 lambda: self.confirm_mgr.confirm("刪除 stash", lambda: self.executor.run_simple("stash drop")), 12,
                 True)],
            ]),
            ("🌿 Branch 分支管理", [
                [("📋 List", lambda: self.executor.run_simple("branch -a"), 10, False),
                (("🔁 Checkout", lambda: self.app.open_checkout_dialog(self.executor), 12, False)),
                ("📌 Create", 'checkout_branch', 10, False)],
                [("✂️ Del Local", 'delete_branch', 12, True),
                ("🌐 Del Remote", 'delete_remote_branch', 12, True)],
                [("🧹 Prune", 'prune_branches', 12, False)],
            ]),
            ("🏷️ Tag 標籤管理", [
                [("📜 List Tags", lambda: self.executor.run_simple("tag -l"), 12, False),
                ("📌 Create Tag", 'create_tag', 12, False)],
                [("🔥 Delete Local", 'delete_tag', 12, True),
                ("☁️ Delete Remote", 'delete_remote_tag', 12, True)],
            ]),
            ("🔍 狀態與工具", [
                ("📢 Status", lambda: self.executor.run_simple("status"), 12, False),
                ("🧽 Clean -fd",
                 lambda: self.confirm_mgr.confirm("清理未追蹤檔案", lambda: self.executor.run_simple("clean -fd")), 12,
                 True),
                ("📟 Diff", lambda: self.executor.run_simple("diff"), 12, False),
                ("🎯 Checkout File", 'checkout_file', 12, False),
            ])
        ]

        # 生成按鈕
        for g_title, rows in layout_configs:
            group_box = ttk.LabelFrame(self.scrollable_frame, text=f" {g_title} ")
            group_box.pack(fill="x", padx=5, pady=5)

            for r_idx, row_content in enumerate(rows):
                # 統一轉成列表處理：單個按鈕轉成長度 1 的列表
                items = row_content if isinstance(row_content, list) else [row_content]

                # 為這一列建立一個專用的容器 Frame，達成獨立排版
                row_frame = ttk.Frame(group_box)
                row_frame.pack(fill="x", expand=True)

                for c_idx, item in enumerate(items):
                    # 解析參數
                    label = item[0]
                    action = item[1]
                    width = item[2]
                    is_danger = item[3] if len(item) > 3 else False

                    # 指令綁定邏輯
                    if isinstance(action, str):
                        cmd_key = action
                        btn_cmd = lambda k=cmd_key: self.app.open_command_dialog(k, self.executor.repo_path,
                                                                                 self.executor)
                    else:
                        btn_cmd = action

                    btn = ttk.Button(row_frame, text=label, command=btn_cmd, width=width,
                                     style="Danger.TButton" if is_danger else "TButton")
                    btn.grid(row=0, column=c_idx, padx=3, pady=3, sticky="ew")

                    # 關鍵：根據這一列的按鈕數量動態分配權重
                    row_frame.columnconfigure(c_idx, weight=1)


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Git Command Panel 測試")
    root.geometry("380x800")  # 設定適合的高度來測試捲動

    # 設定 Danger 按鈕樣式 (不然你的代碼會報錯)
    style = ttk.Style()
    style.configure("Danger.TButton", foreground="red")

    # 初始化模擬組件
    executor = None # MockExecutor()
    confirm_mgr = None # MockConfirmMgr()
    app_handler = None # MockAppHandler()

    # 建立面板
    panel = CommandPanel(root, executor, confirm_mgr, app_handler)
    panel.pack(fill="both", expand=True)

    root.mainloop()

