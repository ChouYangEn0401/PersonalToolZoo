import tkinter as tk
from tkinter import ttk
from src.core.language_manager import lm

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

    def rebuild(self):
        """Destroy and re-create all button widgets (called after language switch)."""
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self._build_quick_entry()
        self._build_buttons()

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
        quick_frame = ttk.LabelFrame(self.scrollable_frame, text=f" {lm.t('quick.group_title')} ")
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

        ttk.Button(quick_frame, text=lm.t('quick.execute_btn'), width=8, command=run_q).pack(side="right", padx=5)
        entry.bind("<Return>", lambda e: run_q())

    def _build_buttons(self):
        layout_configs = [
            (lm.t('group.rebase_control'), [
                [(lm.t('btn.rebase_interactive'), 'rebase_interactive', 12, False),
                (lm.t('btn.rebase_head4'),  lambda: self.executor.run_simple("rebase -i HEAD~4"),  8, False),
                (lm.t('btn.rebase_head8'),  lambda: self.executor.run_simple("rebase -i HEAD~8"),  8, False),
                (lm.t('btn.rebase_head14'), lambda: self.executor.run_simple("rebase -i HEAD~14"), 10, False)],
                [(lm.t('btn.rebase_branch'), 'rebase_branch', 10, False),
                (lm.t('btn.rebase_onto'), lambda: self.app.open_rebase_onto_dialog(self.executor), 10, False)],
                [(lm.t('btn.continue'), lambda: self.executor.run_simple("rebase --continue"), 12, False),
                (lm.t('btn.abort'),    lambda: self.executor.run_simple("rebase --abort"),    12, False),
                (lm.t('btn.skip'),     lambda: self.executor.run_simple("rebase --skip"),     12, False)],
            ]),
            (lm.t('group.merge'), [
                [(lm.t('btn.merge_branch'), lambda: self.app.open_merge_dialog(self.executor), 24, False),
                (lm.t('btn.continue'), lambda: self.executor.run_simple("merge --continue"), 20, False),
                (lm.t('btn.abort'),    lambda: self.executor.run_simple("merge --abort"),    20, False)],
            ]),
            (lm.t('group.cherry_pick'), [
                [(lm.t('btn.cherry_pick_hash'), 'cherry_pick', 24, False),
                (lm.t('btn.continue'), lambda: self.executor.run_simple("cherry-pick --continue"), 20, False),
                (lm.t('btn.abort'),    lambda: self.executor.run_simple("cherry-pick --abort"),    20, False)],
                [(lm.t('btn.restore_from_commit'), 'restore_file_from_commit', 24, False)],
            ]),
            (lm.t('group.reset'), [
                [("Soft HEAD~1", lambda: self.executor.run_simple("reset --soft HEAD~1"), 12, False),
                ("Soft HEAD~2",  lambda: self.executor.run_simple("reset --soft HEAD~2"), 12, False)],
                [(lm.t('btn.soft_reset'), 'reset_soft', 12, False),
                (lm.t('btn.hard_reset'), 'reset_hard', 12, True)],
            ]),
            (lm.t('group.commit'), [
                [(lm.t('btn.fixup'),       lambda: self.executor.quick_commit("f", "fixup"),    6, False),
                (lm.t('btn.squash'),       lambda: self.executor.quick_commit("s", "squash"),   6, False),
                (lm.t('btn.fast_commit'),  lambda: self.executor.quick_commit("stash", "stash"), 14, False)],
                [(lm.t('btn.add_files'),   lambda: self.app.open_file_selector(self.executor),  12, False)],
                [(lm.t('btn.commit_msg'),  'commit_message', 12, False),
                (lm.t('btn.amend'),        'commit_amend',   12, False)],
            ]),
            (lm.t('group.push'), [
                [(lm.t('btn.push'),       lambda: self.executor.run_simple("push"),       12, False),
                (lm.t('btn.force_push'),  'force_push',                                    12, True),
                (lm.t('btn.push_tags'),   lambda: self.executor.run_simple("push --tags"), 14, False)],
            ]),
            (lm.t('group.stash'), [
                [(lm.t('btn.stash_list'), lambda: self.executor.run_simple("stash list"), 12, False),
                (lm.t('btn.stash_pop'),   lambda: self.executor.run_simple("stash pop"),  12, False)],
                [(lm.t('btn.stash_save'),  lambda: self.executor.run_simple("stash"),     12, False),
                (lm.t('btn.stash_clear'),
                 lambda: self.confirm_mgr.confirm(lm.t('confirm.stash_clear'), lambda: self.executor.run_simple("stash clear")), 12, True),
                (lm.t('btn.stash_drop'),
                 lambda: self.confirm_mgr.confirm(lm.t('confirm.stash_drop'), lambda: self.executor.run_simple("stash drop")),   12, True)],
            ]),
            (lm.t('group.branch'), [
                [(lm.t('btn.branch_list'),   lambda: self.executor.run_simple("branch -a"),                    10, False),
                (lm.t('btn.branch_create'),  'checkout_branch',                                                10, False),
                (lm.t('btn.prune'),          'prune_branches',                                                 10, False),
                (lm.t('btn.delete_branch'),  lambda: self.app.open_delete_branch_dialog(self.executor),        20, True)],
            ]),
            (lm.t('group.tag'), [
                [(lm.t('btn.tag_list'),   lambda: self.executor.run_simple("tag -l"), 16, False),
                (lm.t('btn.tag_create'),  'create_tag',                               16, False),
                (lm.t('btn.delete_tag'),  lambda: self.app.open_delete_tag_dialog(self.executor), 20, True)],
            ]),
            (lm.t('group.tools'), [
                [(lm.t('btn.status'),    lambda: self.executor.run_simple("status"), 12, False),
                (lm.t('btn.checkouts'),  lambda: self.app.open_checkouts_dialog(self.executor), 12, False),
                (lm.t('btn.diff'),       lambda: self.executor.run_simple("diff"),   12, False)],
                [(lm.t('btn.clean_fd'),
                 lambda: self.confirm_mgr.confirm(lm.t('confirm.clean_fd'), lambda: self.executor.run_simple("clean -fd")), 12, True)],
            ]),
        ]

        for g_title, rows in layout_configs:
            group_box = ttk.LabelFrame(self.scrollable_frame, text=f" {g_title} ")
            group_box.pack(fill="x", padx=5, pady=5)

            for r_idx, row_content in enumerate(rows):
                items = row_content if isinstance(row_content, list) else [row_content]
                row_frame = ttk.Frame(group_box)
                row_frame.pack(fill="x", expand=True)

                for c_idx, item in enumerate(items):
                    label    = item[0]
                    action   = item[1]
                    width    = item[2]
                    is_danger = item[3] if len(item) > 3 else False

                    if isinstance(action, str):
                        cmd_key = action
                        btn_cmd = lambda k=cmd_key: self.app.open_command_dialog(k, self.executor.repo_path, self.executor)
                    else:
                        btn_cmd = action

                    btn = ttk.Button(row_frame, text=label, command=btn_cmd, width=width,
                                     style="Danger.TButton" if is_danger else "TButton")
                    btn.grid(row=0, column=c_idx, padx=3, pady=3, sticky="ew")
                    row_frame.columnconfigure(c_idx, weight=1)


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Git Command Panel 測試")
    root.geometry("380x800")
    style = ttk.Style()
    style.configure("Danger.TButton", foreground="red")
    root.mainloop()

