"""Table conversion tab — Excel ↔ CSV / Parquet."""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from gui.tabs.base_tab import BaseTab
from core.table_converter import excel_to_format, tables_to_excel, group_files_by_stem

_EXCEL_FILETYPES = [
    ("Excel 檔案", "*.xlsx *.xls *.xlsm"),
    ("所有檔案", "*.*"),
]

_TABLE_FILETYPES = [
    ("CSV / Parquet", "*.csv *.parquet"),
    ("CSV 檔案", "*.csv"),
    ("Parquet 檔案", "*.parquet"),
    ("所有檔案", "*.*"),
]


class TableTab(BaseTab):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        self._excel_paths: list[str] = []
        self._table_paths: list[str] = []
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Mode selector ──
        mode_frm = ttk.LabelFrame(self, text="轉換方向", padding=(10, 6))
        mode_frm.pack(fill="x", pady=(0, 6))

        self.mode_var = tk.StringVar(value="excel_to_table")
        ttk.Radiobutton(
            mode_frm,
            text="📊  Excel  →  CSV / Parquet  （每個工作表拆分為獨立檔案）",
            variable=self.mode_var,
            value="excel_to_table",
            command=self._on_mode_change,
        ).pack(anchor="w", pady=1)
        ttk.Radiobutton(
            mode_frm,
            text="📁  CSV / Parquet  →  Excel  （依命名規則合併為工作表）",
            variable=self.mode_var,
            value="table_to_excel",
            command=self._on_mode_change,
        ).pack(anchor="w", pady=1)

        # ── Swappable content area ──
        self._panel_container = ttk.Frame(self)
        self._panel_container.pack(fill="both", expand=True, pady=(0, 4))

        self._build_excel_panel()
        self._build_table_panel()

        # ── Output dir ──
        self.out_dir_var = self._make_output_dir_row(self)

        # ── Convert button ──
        self.convert_btn = ttk.Button(
            self,
            text="▶   開始轉換",
            command=self._start,
            style="Accent.TButton",
        )
        self.convert_btn.pack(fill="x", ipady=6, pady=(4, 2))

        # ── Progress ──
        self.progress_var, self.status_var = self._make_progress_section(self)

        # Show correct panel
        self._on_mode_change()

    def _build_excel_panel(self):
        """Panel for Excel → CSV/Parquet mode."""
        self._excel_panel = ttk.Frame(self._panel_container)

        # File list
        file_frm = ttk.LabelFrame(self._excel_panel, text="Excel 檔案", padding=5)
        file_frm.pack(fill="both", expand=True)

        btn_bar = ttk.Frame(file_frm)
        btn_bar.pack(fill="x", pady=(0, 4))
        ttk.Button(btn_bar, text="＋ 添加檔案", command=self._add_excel).pack(side="left", padx=2)
        ttk.Button(
            btn_bar, text="✕ 移除選取",
            command=lambda: self._remove_selected(self._excel_lb, self._excel_paths),
        ).pack(side="left", padx=2)
        ttk.Button(
            btn_bar, text="清空全部",
            command=lambda: self._clear_list(self._excel_lb, self._excel_paths),
        ).pack(side="left", padx=2)

        lb_frm = ttk.Frame(file_frm)
        lb_frm.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(lb_frm)
        sb.pack(side="right", fill="y")
        self._excel_lb = tk.Listbox(
            lb_frm, selectmode=tk.EXTENDED, yscrollcommand=sb.set, height=7,
            activestyle="dotbox",
        )
        self._excel_lb.pack(fill="both", expand=True)
        sb.config(command=self._excel_lb.yview)

        # Format options
        opt_frm = ttk.LabelFrame(self._excel_panel, text="輸出格式", padding=(10, 5))
        opt_frm.pack(fill="x", pady=(6, 0))

        self.fmt_var = tk.StringVar(value="csv")
        ttk.Radiobutton(
            opt_frm, text="📄  CSV  (.csv)  — 通用文字格式，相容性最佳",
            variable=self.fmt_var, value="csv",
        ).pack(anchor="w", pady=1)
        ttk.Radiobutton(
            opt_frm, text="⚡  Parquet  (.parquet)  — 高效壓縮格式，適合大型資料",
            variable=self.fmt_var, value="parquet",
        ).pack(anchor="w", pady=1)

    def _build_table_panel(self):
        """Panel for CSV/Parquet → Excel mode."""
        self._table_panel = ttk.Frame(self._panel_container)

        # ── Left: file list ──
        left = ttk.Frame(self._table_panel)
        left.pack(side="left", fill="both", expand=True)

        file_frm = ttk.LabelFrame(left, text="CSV / Parquet 檔案", padding=5)
        file_frm.pack(fill="both", expand=True)

        btn_bar = ttk.Frame(file_frm)
        btn_bar.pack(fill="x", pady=(0, 4))
        ttk.Button(btn_bar, text="＋ 添加檔案", command=self._add_tables).pack(side="left", padx=2)
        ttk.Button(
            btn_bar, text="✕ 移除選取",
            command=lambda: self._remove_selected(self._table_lb, self._table_paths, refresh_preview=True),
        ).pack(side="left", padx=2)
        ttk.Button(
            btn_bar, text="清空全部",
            command=lambda: self._clear_list(self._table_lb, self._table_paths, refresh_preview=True),
        ).pack(side="left", padx=2)

        lb_frm = ttk.Frame(file_frm)
        lb_frm.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(lb_frm)
        sb.pack(side="right", fill="y")
        self._table_lb = tk.Listbox(
            lb_frm, selectmode=tk.EXTENDED, yscrollcommand=sb.set, height=7,
            activestyle="dotbox",
        )
        self._table_lb.pack(fill="both", expand=True)
        sb.config(command=self._table_lb.yview)

        # Naming hint
        hint = ttk.Label(
            left,
            text="💡 符合  {名稱}.[{工作表}].csv  命名的檔案將自動合併為同一個 Excel",
            foreground="gray",
            wraplength=340,
            justify="left",
        )
        hint.pack(anchor="w", pady=(4, 0))

        # ── Right: preview treeview ──
        right = ttk.LabelFrame(self._table_panel, text="合併預覽", padding=5)
        right.pack(side="right", fill="both", expand=True, padx=(8, 0))

        tree_frm = ttk.Frame(right)
        tree_frm.pack(fill="both", expand=True)
        tree_sb = ttk.Scrollbar(tree_frm)
        tree_sb.pack(side="right", fill="y")

        self._preview_tree = ttk.Treeview(
            tree_frm, show="tree", height=9, yscrollcommand=tree_sb.set,
        )
        self._preview_tree.pack(fill="both", expand=True)
        tree_sb.config(command=self._preview_tree.yview)

        # Tree tags for styling
        self._preview_tree.tag_configure("excel_root", font=("Segoe UI", 9, "bold"))
        self._preview_tree.tag_configure("sheet_item", font=("Segoe UI", 9))

    # ── Mode switching ───────────────────────────────────────────────────────

    def _on_mode_change(self):
        if self.mode_var.get() == "excel_to_table":
            self._table_panel.pack_forget()
            self._excel_panel.pack(fill="both", expand=True)
        else:
            self._excel_panel.pack_forget()
            self._table_panel.pack(fill="both", expand=True)

    # ── File list helpers ────────────────────────────────────────────────────

    def _add_excel(self):
        paths = filedialog.askopenfilenames(filetypes=_EXCEL_FILETYPES)
        for p in paths:
            if p not in self._excel_paths:
                self._excel_paths.append(p)
                self._excel_lb.insert(tk.END, f"  {os.path.basename(p)}")
        # Auto-fill output directory from first file
        if paths and not self.out_dir_var.get():
            self.out_dir_var.set(os.path.dirname(paths[0]))

    def _add_tables(self):
        paths = filedialog.askopenfilenames(filetypes=_TABLE_FILETYPES)
        for p in paths:
            if p not in self._table_paths:
                self._table_paths.append(p)
                self._table_lb.insert(tk.END, f"  {os.path.basename(p)}")
        if paths and not self.out_dir_var.get():
            self.out_dir_var.set(os.path.dirname(paths[0]))
        self._refresh_preview()

    def _remove_selected(self, lb: tk.Listbox, paths: list, *, refresh_preview=False):
        for idx in reversed(lb.curselection()):
            paths.pop(idx)
            lb.delete(idx)
        if refresh_preview:
            self._refresh_preview()

    def _clear_list(self, lb: tk.Listbox, paths: list, *, refresh_preview=False):
        paths.clear()
        lb.delete(0, tk.END)
        if refresh_preview:
            self._refresh_preview()

    # ── Preview treeview ─────────────────────────────────────────────────────

    def _refresh_preview(self):
        self._preview_tree.delete(*self._preview_tree.get_children())
        if not self._table_paths:
            return

        groups = group_files_by_stem(self._table_paths)
        for stem, files in groups.items():
            parent = self._preview_tree.insert(
                "", "end",
                text=f"📗  {stem}.xlsx  （{len(files)} 個工作表）",
                open=True,
                tags=("excel_root",),
            )
            for sheet, path in files:
                fname = os.path.basename(path)
                self._preview_tree.insert(
                    parent, "end",
                    text=f"    [{sheet}]  ←  {fname}",
                    tags=("sheet_item",),
                )

    # ── Conversion ───────────────────────────────────────────────────────────

    def _start(self):
        mode = self.mode_var.get()
        out_dir = self.out_dir_var.get().strip()
        if not out_dir:
            messagebox.showwarning("提示", "請選擇輸出資料夾。")
            return
        os.makedirs(out_dir, exist_ok=True)

        if mode == "excel_to_table":
            if not self._excel_paths:
                messagebox.showwarning("提示", "請先添加 Excel 檔案。")
                return
            self._run_excel_to_table(out_dir)
        else:
            if not self._table_paths:
                messagebox.showwarning("提示", "請先添加 CSV / Parquet 檔案。")
                return
            self._run_table_to_excel(out_dir)

    def _run_excel_to_table(self, out_dir: str):
        fmt = self.fmt_var.get()
        paths = list(self._excel_paths)
        total_files = len(paths)

        self.convert_btn.config(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("轉換中…")

        def do():
            errors: list[str] = []
            for fi, p in enumerate(paths):
                def sheet_cb(frac: float, msg: str, _fi: int = fi) -> None:
                    overall = (_fi + frac) / total_files * 100
                    self._update_progress(self.progress_var, overall)
                    self._update_status(self.status_var, msg)

                try:
                    excel_to_format(p, out_dir, fmt, progress_cb=sheet_cb)
                except Exception as exc:
                    errors.append(f"{os.path.basename(p)}: {exc}")

            if errors:
                msg = "以下檔案轉換失敗：\n" + "\n".join(errors)
                self.root.after(0, lambda: messagebox.showwarning("部分失敗", msg))

        self._run_in_thread(do, on_done=self._on_done)

    def _run_table_to_excel(self, out_dir: str):
        paths = list(self._table_paths)

        self.convert_btn.config(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("合併中…")

        def do():
            def cb(frac: float, msg: str) -> None:
                self._update_progress(self.progress_var, frac * 100)
                self._update_status(self.status_var, msg)

            try:
                tables_to_excel(paths, out_dir, progress_cb=cb)
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("轉換失敗", str(exc)))

        self._run_in_thread(do, on_done=self._on_done)

    def _on_done(self):
        self.progress_var.set(100)
        self.status_var.set("✅ 完成！")
        self.convert_btn.config(state="normal")
