"""Shared helpers for all tabs."""
import tkinter as tk
from tkinter import ttk, filedialog
import threading


class BaseTab(ttk.Frame):
    """Base class providing common widgets and patterns for each tab."""

    def __init__(self, parent, root):
        super().__init__(parent, padding=10)
        self.root = root
        self._running = False

    # ── widget helpers ──────────────────────────────────────────────

    def _make_file_list_section(self, filetypes, label_text="檔案列表"):
        """Create an add/remove file list with scrollbar. Returns (frame, listbox, file_paths_list)."""
        frm = ttk.LabelFrame(self, text=label_text, padding=5)

        btn_bar = ttk.Frame(frm)
        btn_bar.pack(fill="x")

        file_paths = []

        def add_files():
            paths = filedialog.askopenfilenames(filetypes=filetypes)
            for p in paths:
                if p not in file_paths:
                    file_paths.append(p)
                    lb.insert(tk.END, p)

        def remove_selected():
            sel = lb.curselection()
            for idx in reversed(sel):
                file_paths.pop(idx)
                lb.delete(idx)

        def clear_all():
            file_paths.clear()
            lb.delete(0, tk.END)

        ttk.Button(btn_bar, text="添加檔案", command=add_files).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="移除選取", command=remove_selected).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="清空全部", command=clear_all).pack(side="left", padx=2)

        list_frm = ttk.Frame(frm)
        list_frm.pack(fill="both", expand=True, pady=(5, 0))
        sb = ttk.Scrollbar(list_frm)
        sb.pack(side="right", fill="y")
        lb = tk.Listbox(list_frm, selectmode=tk.EXTENDED, yscrollcommand=sb.set, height=8)
        lb.pack(fill="both", expand=True)
        sb.config(command=lb.yview)

        return frm, lb, file_paths

    def _make_output_dir_row(self, parent):
        """Create an output directory selector row. Returns StringVar."""
        frm = ttk.Frame(parent)
        frm.pack(fill="x", pady=4)
        ttk.Label(frm, text="輸出資料夾:").pack(side="left")
        var = tk.StringVar()
        entry = ttk.Entry(frm, textvariable=var)
        entry.pack(side="left", fill="x", expand=True, padx=4)

        def browse():
            d = filedialog.askdirectory()
            if d:
                var.set(d)

        ttk.Button(frm, text="瀏覽…", command=browse).pack(side="right")
        return var

    def _make_progress_section(self, parent):
        """Create progress bar + status label. Returns (progress_var, status_var)."""
        progress_var = tk.DoubleVar()
        status_var = tk.StringVar(value="就緒")

        ttk.Progressbar(parent, variable=progress_var, maximum=100).pack(fill="x", pady=(8, 2))
        ttk.Label(parent, textvariable=status_var, foreground="gray").pack(anchor="w")
        return progress_var, status_var

    # ── threading helpers ───────────────────────────────────────────

    def _run_in_thread(self, target, on_done=None, on_error=None):
        """Run target() in a daemon thread; call on_done / on_error on the main thread."""
        if self._running:
            return

        self._running = True

        def wrapper():
            try:
                target()
                if on_done:
                    self.root.after(0, on_done)
            except Exception as e:
                if on_error:
                    self.root.after(0, lambda: on_error(e))
            finally:
                self._running = False

        t = threading.Thread(target=wrapper, daemon=True)
        t.start()

    def _update_progress(self, progress_var, value):
        self.root.after(0, lambda: progress_var.set(value))

    def _update_status(self, status_var, text):
        self.root.after(0, lambda: status_var.set(text))
