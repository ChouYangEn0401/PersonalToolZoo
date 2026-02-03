import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os


class GitAdvancedTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Git Pro Organizer - 精簡整理工具")
        self.root.geometry("1300x850")

        self.style = ttk.Style()
        self.style.theme_use('clam')

        # 自定義樣式：消除部分元件留白
        self.style.configure("TFrame", background="#f0f0f0")
        self.style.configure("TLabelframe", background="#f0f0f0")

        # --- 頂部工具列 ---
        self.toolbar = ttk.Frame(self.root, padding=5)
        self.toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Button(self.toolbar, text="+ 開啟新專案分頁", command=self.open_directory).grid(row=0, column=0, padx=5)

        # --- 主 Notebook ---
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

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

        main_frame.columnconfigure(1, weight=1)  # 右側撐開
        main_frame.rowconfigure(0, weight=1)

        # --- 1. 左側捲動指令區 (修正佈局消除留白) ---
        side_container = ttk.Frame(main_frame, width=280)
        side_container.grid(row=0, column=0, sticky="ns", padx=(5, 2))
        side_container.grid_propagate(False)  # 固定寬度防止縮小

        canvas = tk.Canvas(side_container, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(side_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        # 核心修正：讓內部視窗寬度等於 Canvas 寬度
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def configure_scroll(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 強制讓內容區寬度 = Canvas 寬度
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", configure_scroll)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        side_container.grid_rowconfigure(0, weight=1)
        side_container.grid_columnconfigure(0, weight=1)

        # --- 指令按鈕配置 ---
        self.build_command_ui(scrollable_frame, path, arg_entry_var := tk.StringVar())

        # --- 2. 右側顯示區 (Adog & Terminal) ---
        display_panel = ttk.Frame(main_frame)
        display_panel.grid(row=0, column=1, sticky="nsew", padx=5)
        display_panel.columnconfigure(0, weight=1)
        display_panel.rowconfigure(1, weight=3)  # Adog
        display_panel.rowconfigure(3, weight=2)  # Terminal

        # Adog 區域
        ttk.Label(display_panel, text="Git Adog 視覺化線圖:", font=("Arial", 10, "bold")).grid(row=0, column=0,
                                                                                               sticky="w", pady=5)
        adog_text = tk.Text(display_panel, bg="#ffffff", fg="#222222", font=("Consolas", 10), height=15, wrap="none",
                            relief="flat", padx=10, pady=10)
        adog_text.grid(row=1, column=0, sticky="nsew")

        adog_h = ttk.Scrollbar(display_panel, orient="horizontal", command=adog_text.xview)
        adog_h.grid(row=2, column=0, sticky="ew")
        adog_text.configure(xscrollcommand=adog_h.set)

        # Terminal 區域
        ttk.Label(display_panel, text="指令執行輸出:", font=("Arial", 10, "bold")).grid(row=3, column=0, sticky="w",
                                                                                        pady=(10, 5))
        terminal = tk.Text(display_panel, bg="#1e1e1e", fg="#ffffff", font=("Consolas", 10), relief="flat", padx=10,
                           pady=10)
        terminal.grid(row=4, column=0, sticky="nsew")

        # 控制列
        ctrl_bar = ttk.Frame(display_panel)
        ctrl_bar.grid(row=5, column=0, sticky="ew", pady=10)
        ttk.Button(ctrl_bar, text="🔄 刷新線圖", command=lambda: self.refresh_adog(path, adog_text)).grid(row=0, column=0, padx=5)
        ttk.Button(ctrl_bar, text="🕒 查看 Reflog", command=lambda: self.view_reflog(path, adog_text)).grid(row=0, column=1, padx=5)

        # 初始刷新
        self.refresh_adog(path, adog_text)

    def build_command_ui(self, parent, path, arg_var):
        # 參數輸入框
        ttk.Label(parent, text="參數 (Hash / Branch):").grid(row=0, column=0, sticky="w", padx=5)
        entry = ttk.Entry(parent, textvariable=arg_var)
        entry.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 10))

        groups = [
            ("整理與合併 (Rebase)", [
                ("Rebase Main", "rebase main"),
                ("Rebase -i", "rebase -i"),
                ("--continue", "rebase --continue"),
                ("--abort", "rebase --abort")
            ]),
            ("櫻桃採摘 (Cherry-pick)", [
                ("Cherry-pick", "cherry-pick"),
                ("--continue", "cherry-pick --continue"),
                ("--abort", "cherry-pick --abort")
            ]),
            ("存檔與還原 (Stash/Reset)", [
                ("Stash Save", "stash"),
                ("Stash Pop", "stash pop"),
                ("Soft Reset", "reset --soft"),
                ("Hard Reset", "reset --hard")
            ]),
            ("提交與推送 (Commit/Push)", [
                ("Commit (Amend)", "commit --amend --no-edit"),
                ("Force Push", "push -f"),
                ("Checkout File", "checkout")
            ]),
            ("分支管理 (Branch/Tag)", [
                ("Delete Branch", "branch -D"),
                ("New Branch", "checkout -b"),
                ("Create Tag", "tag")
            ])
        ]

        for r, (g_name, cmds) in enumerate(groups, start=2):
            lf = ttk.LabelFrame(parent, text=f" {g_name} ")
            lf.grid(row=r, column=0, sticky="ew", padx=5, pady=5)
            lf.columnconfigure(0, weight=1)
            for i, (btn_text, cmd) in enumerate(cmds):
                ttk.Button(
                    lf,
                    text=btn_text,
                    command=lambda c=cmd, p=path, v=arg_var: self.execute_git(c, v.get(), p)).grid(
                        row=i,
                        column=0,
                        sticky="ew",
                        pady=1
                )

    def execute_git(self, cmd_base, param, repo_path):
        full_cmd = f"git {cmd_base} {param}".strip()
        try:
            res = subprocess.run(full_cmd, cwd=repo_path, shell=True, capture_output=True, text=True)
            tab_id = self.notebook.select()
            current_tab = self.notebook.nametowidget(tab_id)

            # 找到對應的 Text widget 更新內容 (透過遍歷簡化開發)
            texts = []
            self._get_all_texts(current_tab, texts)
            if len(texts) >= 2:
                adog_w, term_w = texts[0], texts[1]
                term_w.insert(tk.END, f"\n$ {full_cmd}\n{res.stdout}{res.stderr}\n{'-' * 30}\n")
                term_w.see(tk.END)
                self.refresh_adog(repo_path, adog_w)
        except Exception as e:
            messagebox.showerror("錯誤", str(e))

    def _get_all_texts(self, parent, result):
        for child in parent.winfo_children():
            if isinstance(child, tk.Text):
                result.append(child)
            else:
                self._get_all_texts(child, result)

    def refresh_adog(self, path, text_widget):
        text_widget.config(state=tk.NORMAL)
        text_widget.delete('1.0', tk.END)
        # 經典 Adog 指令
        cmd = "git log --graph --oneline --all --decorate -n 50"
        res = subprocess.run(cmd, cwd=path, shell=True, capture_output=True, text=True)
        text_widget.insert(tk.END, res.stdout if res.stdout else "目前尚無 Commit 紀錄")
        text_widget.config(state=tk.DISABLED)

    def view_reflog(self, path, text_widget):
        text_widget.config(state=tk.NORMAL)
        text_widget.delete('1.0', tk.END)
        res = subprocess.run("git reflog -n 50", cwd=path, shell=True, capture_output=True, text=True)
        text_widget.insert(tk.END, "--- REFLOG HISTORY ---\n" + res.stdout)
        text_widget.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    app = GitAdvancedTool(root)
    root.mainloop()