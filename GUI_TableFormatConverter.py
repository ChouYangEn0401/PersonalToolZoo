"""
Table Tool — 輸入文字或 MD 表格，預覽並多格式輸出
支援輸入：
  - Tab 分隔（你叫「Excel可貼 tab 表格」）
  - Markdown 表格（| col | col | 格式）
輸出：
  1. MD 格式 → 剪貼簿
  2. Tab 分隔 → 剪貼簿（可貼進 Excel）
  3. 存成 .csv
  4. 存成 .xlsx
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import io
import re


# ── 解析輸入 ──────────────────────────────────────────────

def parse_input(text: str) -> list[list[str]]:
    """自動偵測 tab 分隔 或 MD 表格，回傳 list[list[str]]"""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return []

    # 判斷是否為 MD 表格（有 | 且有分隔線 ---）
    has_pipe = any("|" in l for l in lines)
    has_separator = any(re.match(r"^\s*\|?[\s\-|:]+\|?\s*$", l) for l in lines)

    if has_pipe and has_separator:
        return parse_md(lines)
    else:
        return parse_tab(lines)


def parse_md(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        # 跳過分隔線（只有 - : | 空白組成）
        if re.match(r"^\s*\|?[\s\-|:]+\|?\s*$", line):
            continue
        # 去掉首尾 |，拆欄
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows


def parse_tab(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        rows.append(line.split("\t"))
    return rows


# ── 輸出格式化 ────────────────────────────────────────────

def to_md(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    col_widths = [max(len(r[i]) if i < len(r) else 0 for r in rows)
                  for i in range(max(len(r) for r in rows))]
    lines = []
    for idx, row in enumerate(rows):
        padded = [row[i].ljust(col_widths[i]) if i < len(row) else " " * col_widths[i]
                  for i in range(len(col_widths))]
        lines.append("| " + " | ".join(padded) + " |")
        if idx == 0:
            lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")
    return "\n".join(lines)


def to_tab(rows: list[list[str]]) -> str:
    return "\n".join("\t".join(row) for row in rows)


def to_csv_str(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return buf.getvalue()


# ── 主視窗 ────────────────────────────────────────────────

class TableTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Table Tool")
        self.geometry("820x720")
        self.configure(bg="#f0f0f0")
        self.resizable(True, True)

        self.rows: list[list[str]] = []
        # UI state
        self.encoding_var = tk.StringVar(value="utf-8-sig")

        # ttk styling
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure("Treeview", font=("Consolas", 11), rowheight=24)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", padding=6)

        self._build_ui()

    def _build_ui(self):
        # ── 頂部：輸入區 ──
        input_frame = ttk.LabelFrame(self, text="輸入（Tab 分隔 或 MD 表格）", padding=6)
        input_frame.pack(fill="x", padx=10, pady=(10, 4))

        self.input_box = tk.Text(input_frame, height=7, font=("Consolas", 11),
                                 wrap="none", undo=True)
        self.input_box.pack(fill="x")

        btn_row = tk.Frame(input_frame, bg="#f0f0f0")
        btn_row.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_row, text="▶ 解析 / 預覽", command=self.parse_and_preview).pack(side="left")
        ttk.Button(btn_row, text="清除", command=self.clear_all).pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="")
        tk.Label(btn_row, textvariable=self.status_var, fg="#555", bg="#f0f0f0").pack(side="left")

        # ── 中間：表格預覽 ──
        preview_frame = ttk.LabelFrame(self, text="表格預覽", padding=6)
        preview_frame.pack(fill="both", expand=True, padx=10, pady=4)

        self.tree = ttk.Treeview(preview_frame, show="headings")
        vsb = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        # alternate row colors
        self.tree.tag_configure('odd', background='#ffffff')
        self.tree.tag_configure('even', background='#f7f7f7')

        # ── 底部：輸出按鈕 ──
        out_frame = ttk.LabelFrame(self, text="輸出", padding=6)
        out_frame.pack(fill="x", padx=10, pady=(4, 10))

        btns = [
            ("📋 MD → 剪貼簿",     self.copy_md),
            ("📋 Tab → 剪貼簿\n(可貼 Excel)", self.copy_tab),
            ("💾 存成 .csv",        self.save_csv),
            ("💾 存成 .xlsx",       self.save_xlsx),
        ]
        for label, cmd in btns:
            ttk.Button(out_frame, text=label, command=cmd, width=18).pack(
                side="left", padx=5, pady=2)

        # CSV encoding chooser
        enc_label = ttk.Label(out_frame, text="編碼:")
        enc_label.pack(side="left", padx=(12, 4))
        enc_box = ttk.Combobox(out_frame, textvariable=self.encoding_var,
                               values=("utf-8-sig", "utf-8", "cp950"), width=10, state="readonly")
        enc_box.pack(side="left")

    # ── 動作 ──────────────────────────────────────────────

    def parse_and_preview(self):
        text = self.input_box.get("1.0", "end")
        rows = parse_input(text)
        if not rows:
            self.status_var.set("⚠ 沒有偵測到資料")
            return
        self.rows = rows
        self._refresh_tree()
        self.status_var.set(f"✓ {len(rows)} 列 × {max(len(r) for r in rows)} 欄")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        if not self.rows:
            return
        cols = self.rows[0]
        self.tree["columns"] = [str(i) for i in range(len(cols))]
        for i, c in enumerate(cols):
            self.tree.heading(str(i), text=c)
            self.tree.column(str(i), width=max(80, len(c) * 10), anchor="w")
        for idx, row in enumerate(self.rows[1:]):
            padded = row + [""] * (len(cols) - len(row))
            tag = 'even' if idx % 2 else 'odd'
            self.tree.insert("", "end", values=padded, tags=(tag,))

    def clear_all(self):
        self.input_box.delete("1.0", "end")
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = []
        self.rows = []
        self.status_var.set("")

    def _require_rows(self) -> bool:
        if not self.rows:
            messagebox.showwarning("尚未解析", "請先按「解析 / 預覽」")
            return False
        return True

    def copy_md(self):
        if not self._require_rows():
            return
        self.clipboard_clear()
        self.clipboard_append(to_md(self.rows))
        self.status_var.set("✓ MD 已複製到剪貼簿")

    def copy_tab(self):
        if not self._require_rows():
            return
        self.clipboard_clear()
        self.clipboard_append(to_tab(self.rows))
        self.status_var.set("✓ Tab 格式已複製（可貼到 Excel）")

    def save_csv(self):
        if not self._require_rows():
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 檔案", "*.csv"), ("所有檔案", "*.*")],
            title="存成 CSV")
        if not path:
            return
        enc = self.encoding_var.get() or "utf-8-sig"
        try:
            with open(path, "w", newline="", encoding=enc) as f:
                csv.writer(f).writerows(self.rows)
        except Exception as e:
            messagebox.showerror("儲存失敗", f"無法儲存 CSV：{e}")
            return
        self.status_var.set(f"✓ 已儲存 {path} ({enc})")

    def save_xlsx(self):
        if not self._require_rows():
            return
        try:
            import openpyxl
        except ImportError:
            messagebox.showerror("缺少套件",
                "請先安裝 openpyxl：\npip install openpyxl")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel 檔案", "*.xlsx"), ("所有檔案", "*.*")],
            title="存成 Excel")
        if not path:
            return
        wb = openpyxl.Workbook()
        ws = wb.active
        for row in self.rows:
            ws.append(row)
        # 自動欄寬
        for col in ws.columns:
            max_len = max((len(str(c.value or "")) for c in col), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)
        wb.save(path)
        self.status_var.set(f"✓ 已儲存 {path}")


if __name__ == "__main__":
    app = TableTool()
    app.mainloop()
