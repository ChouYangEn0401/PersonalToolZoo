"""File Renamer —— 拖進檔案，用正規表達式或雜湊批次改名。

改名前一律先預覽：新檔名重複、目標已存在、規則寫錯的列會標紅而且不會套用。
套用後可以「復原上次改名」。
"""

import hashlib
import os
import re
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from version import __version__

MODE_REGEX = "正規表達式"
MODE_NAME_HASH = "檔名雜湊（SHA-256）"
MODE_CONTENT_HASH = "檔案內容雜湊（SHA-256）"


def resource_path(*parts):
    """打包後也正確的資料檔路徑（PyInstaller 會把資料解到 sys._MEIPASS）。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def content_hash(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def plan_renames(paths, mode, pattern="", replacement="", ignore_case=False):
    """回傳 [(原路徑, 新檔名, 問題)]；問題是空字串代表可以改。"""
    rows = []
    regex = None
    if mode == MODE_REGEX and pattern:
        try:
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as exc:
            return [(p, "", f"規則錯誤：{exc}") for p in paths]
    for path in paths:
        name = os.path.basename(path)
        stem, ext = os.path.splitext(name)
        try:
            if mode == MODE_REGEX:
                new = regex.sub(replacement, name) if regex else name
            elif mode == MODE_NAME_HASH:
                new = hashlib.sha256(name.encode("utf-8")).hexdigest() + ext
            else:
                new = content_hash(path) + ext
        except (OSError, re.error) as exc:
            rows.append((path, "", f"失敗：{exc}"))
            continue
        rows.append((path, new, ""))

    # 衝突檢查：同一個資料夾裡新檔名重複、或跟不在這批裡的既有檔案撞名
    seen = {}
    batch = {os.path.normcase(p) for p in paths}
    result = []
    for path, new, problem in rows:
        if not problem:
            folder = os.path.dirname(path)
            target = os.path.normcase(os.path.join(folder, new))
            if not new or any(c in new for c in '<>:"/\\|?*'):
                problem = "新檔名不合法"
            elif new == os.path.basename(path):
                problem = "不變"
            elif target in seen:
                problem = f"跟「{os.path.basename(seen[target])}」的新檔名重複"
            elif os.path.exists(target) and target not in batch:
                problem = "目標檔名已存在"
            seen.setdefault(target, path)
        result.append((path, new, problem))
    return result


class FileRenamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"File Renamer v{__version__}")
        self.root.geometry("980x620")
        self.root.minsize(760, 460)
        try:
            self.root.iconbitmap(resource_path("data", "FileRenamer.ico"))
        except tk.TclError:
            pass
        self.paths = []
        self.plan = []
        self.last_applied = []   # [(新路徑, 原路徑)]，給「復原」用
        self._build()
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self._on_drop)

    # ------------------------------------------------------------------ UI
    def _build(self):
        top = ttk.Frame(self.root, padding=(10, 10, 10, 0))
        top.pack(fill="x")
        ttk.Button(top, text="＋ 加入檔案", command=self._browse).pack(side="left")
        ttk.Button(top, text="移除選取", command=self._remove_selected).pack(side="left", padx=6)
        ttk.Button(top, text="清空", command=self._clear).pack(side="left")
        ttk.Label(top, text="（也可以把檔案直接拖進視窗）", foreground="#777").pack(side="left", padx=10)

        rule = ttk.LabelFrame(self.root, text="改名規則", padding=10)
        rule.pack(fill="x", padx=10, pady=8)
        self.mode = tk.StringVar(value=MODE_REGEX)
        ttk.Label(rule, text="方式").grid(row=0, column=0, sticky="w")
        mode_box = ttk.Combobox(rule, textvariable=self.mode, state="readonly", width=24,
                                values=[MODE_REGEX, MODE_NAME_HASH, MODE_CONTENT_HASH])
        mode_box.grid(row=0, column=1, sticky="w", padx=6)
        mode_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh())
        self.pattern = tk.StringVar()
        self.replacement = tk.StringVar()
        self.ignore_case = tk.BooleanVar()
        ttk.Label(rule, text="尋找（regex）").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.pattern_entry = ttk.Entry(rule, textvariable=self.pattern, width=40)
        self.pattern_entry.grid(row=1, column=1, sticky="we", padx=6, pady=(8, 0))
        ttk.Label(rule, text="取代成").grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.replace_entry = ttk.Entry(rule, textvariable=self.replacement, width=30)
        self.replace_entry.grid(row=1, column=3, sticky="we", padx=6, pady=(8, 0))
        ttk.Checkbutton(rule, text="不分大小寫", variable=self.ignore_case,
                        command=self._refresh).grid(row=1, column=4, padx=6, pady=(8, 0))
        ttk.Label(rule, text=r"例：尋找 ^IMG_(\d+)  取代成 照片_\1　　取代成可用 \1、\2 引用括號內容",
                  foreground="#777").grid(row=2, column=1, columnspan=4, sticky="w", pady=(4, 0))
        rule.columnconfigure(1, weight=1)
        rule.columnconfigure(3, weight=1)
        for var in (self.pattern, self.replacement):
            var.trace_add("write", lambda *_: self._refresh())

        table = ttk.Frame(self.root, padding=(10, 0))
        table.pack(fill="both", expand=True)
        cols = ("status", "old", "new", "folder")
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="extended")
        for col, text, width in (("status", "狀態", 150), ("old", "原檔名", 260), ("new", "新檔名", 260),
                                 ("folder", "資料夾", 220)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.tag_configure("bad", foreground="#c62828")
        self.tree.tag_configure("same", foreground="#888")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")
        self.summary = ttk.Label(bottom, text="")
        self.summary.pack(side="left")
        self.undo_btn = ttk.Button(bottom, text="↩ 復原上次改名", command=self._undo, state="disabled")
        self.undo_btn.pack(side="right")
        ttk.Button(bottom, text="套用改名", command=self._apply).pack(side="right", padx=6)

    # ------------------------------------------------------------------ 檔案清單
    def _add_paths(self, paths):
        known = {os.path.normcase(p) for p in self.paths}
        for p in paths:
            if os.path.isfile(p) and os.path.normcase(p) not in known:
                self.paths.append(p)
                known.add(os.path.normcase(p))
        self._refresh()

    def _on_drop(self, event):
        self._add_paths(self.root.tk.splitlist(event.data))

    def _browse(self):
        self._add_paths(filedialog.askopenfilenames(title="選擇要改名的檔案"))

    def _remove_selected(self):
        drop = {self.tree.index(i) for i in self.tree.selection()}
        self.paths = [p for i, p in enumerate(self.paths) if i not in drop]
        self._refresh()

    def _clear(self):
        self.paths = []
        self._refresh()

    # ------------------------------------------------------------------ 預覽與套用
    def _refresh(self):
        regex_mode = self.mode.get() == MODE_REGEX
        for entry in (self.pattern_entry, self.replace_entry):
            entry.configure(state="normal" if regex_mode else "disabled")
        if self.mode.get() == MODE_CONTENT_HASH and len(self.paths) > 200:
            self.summary.configure(text="計算內容雜湊中…")
            self.root.update_idletasks()
        self.plan = plan_renames(self.paths, self.mode.get(), self.pattern.get(), self.replacement.get(),
                                 self.ignore_case.get())
        self.tree.delete(*self.tree.get_children())
        for path, new, problem in self.plan:
            tag = "same" if problem == "不變" else ("bad" if problem else "")
            self.tree.insert("", "end", values=(problem or "✓ 會改名", os.path.basename(path), new,
                                                os.path.dirname(path)), tags=(tag,))
        ok = sum(1 for _, _, p in self.plan if not p)
        bad = sum(1 for _, _, p in self.plan if p and p != "不變")
        self.summary.configure(text=f"共 {len(self.plan)} 個檔案：{ok} 個會改名" + (f"、{bad} 個有問題" if bad else ""))

    def _apply(self):
        todo = [(path, new) for path, new, problem in self.plan if not problem]
        if not todo:
            messagebox.showinfo("沒有要改的", "目前沒有可以套用的改名（看「狀態」欄）。")
            return
        if not messagebox.askyesno("確認改名", f"要把 {len(todo)} 個檔案改名嗎？"):
            return
        done, failed = [], []
        for path, new in todo:
            target = os.path.join(os.path.dirname(path), new)
            try:
                os.rename(path, target)
                done.append((target, path))
            except OSError as exc:
                failed.append(f"{os.path.basename(path)}：{exc}")
        self.last_applied = done
        self.undo_btn.configure(state="normal" if done else "disabled")
        renamed = {os.path.normcase(old): new for new, old in done}
        self.paths = [renamed.get(os.path.normcase(p), p) for p in self.paths]
        self._refresh()
        if failed:
            messagebox.showwarning("部分失敗", f"成功 {len(done)} 個，失敗 {len(failed)} 個：\n\n" + "\n".join(failed[:20]))

    def _undo(self):
        failed = []
        for new, old in reversed(self.last_applied):
            try:
                os.rename(new, old)
            except OSError as exc:
                failed.append(f"{os.path.basename(new)}：{exc}")
        back = {os.path.normcase(new): old for new, old in self.last_applied}
        self.paths = [back.get(os.path.normcase(p), p) for p in self.paths]
        self.last_applied = []
        self.undo_btn.configure(state="disabled")
        self._refresh()
        if failed:
            messagebox.showwarning("部分無法復原", "\n".join(failed[:20]))


def main():
    root = TkinterDnD.Tk()   # 拖放要用 TkinterDnD 的視窗（舊版另外多開了一個空白的 tk.Tk）
    FileRenamerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
