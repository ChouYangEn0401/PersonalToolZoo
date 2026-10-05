"""Better File Finder —— 比檔案總管好用的檔案搜尋：檔名、副檔名、檔案內容。

查詢語法（不分大小寫）：
    報告 2024          兩個詞都要出現在檔名裡
    "季度 報告"        整段文字要原樣出現
    -草稿              檔名有「草稿」的不要
勾「模糊比對」時，詞不用完全出現，相似就算（打錯字也找得到）。
勾「搜尋檔案內容」時，文字檔的內容也會被搜尋，並顯示第一個符合的那一行。
"""

import fnmatch
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from tkinter import filedialog, ttk

from version import __version__

TEXT_LIMIT = 20 * 1024 * 1024       # 內容搜尋只看 20 MB 以下的檔案
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "$RECYCLE.BIN", "System Volume Information"}


@dataclass
class Query:
    words: list
    phrases: list
    excludes: list

    @classmethod
    def parse(cls, text):
        phrases = [p.lower() for p in re.findall(r'"([^"]+)"', text)]
        rest = re.sub(r'"[^"]*"', " ", text).split()
        excludes = [w[1:].lower() for w in rest if w.startswith("-") and len(w) > 1]
        words = [w.lstrip("+").lower() for w in rest if not w.startswith("-") and w.lstrip("+")]
        return cls(words, phrases, excludes)

    @property
    def empty(self):
        return not (self.words or self.phrases)


def parse_patterns(text):
    """「*.txt; md, .py」→ ['*.txt', '*.md', '*.py']；空白 = 全部。"""
    out = []
    for part in re.split(r"[;,\s]+", text.strip()):
        if not part:
            continue
        if not any(c in part for c in "*?["):
            part = "*." + part.lstrip("*.")
        out.append(part.lower())
    return out


def name_score(name, q, fuzzy):
    """檔名分數：0 = 不符合。完全相同 > 開頭相符 > 包含 > 模糊。"""
    low = name.lower()
    stem = os.path.splitext(low)[0]
    if any(x in low for x in q.excludes):
        return 0
    if any(p not in low for p in q.phrases):
        return 0
    if not q.words:
        return 2 if q.phrases else 0
    score = 0.0
    for w in q.words:
        if w == stem:
            score += 3
        elif low.startswith(w):
            score += 2.5
        elif w in low:
            score += 2
        elif fuzzy:
            ratio = max(SequenceMatcher(None, w, low[i:i + len(w) + 2]).ratio()
                        for i in range(max(1, len(low) - len(w) + 1)))
            if ratio < 0.7:
                return 0
            score += ratio
        else:
            return 0
    return score / len(q.words)


def content_hit(path, q):
    """回傳第一行符合的內容（截短），沒有就回傳 None。看起來是二進位檔就跳過。"""
    try:
        if os.path.getsize(path) > TEXT_LIMIT:
            return None
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    for enc in ("utf-8", "cp950", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return None
    needles = q.words + q.phrases
    if not needles:
        return None
    low = text.lower()
    if not all(n in low for n in needles) or any(x in low for x in q.excludes):
        return None
    for line in text.splitlines():
        if needles[0] in line.lower():
            line = line.strip()
            return line[:120] + ("…" if len(line) > 120 else "")
    return ""


def search(root, q, patterns, *, fuzzy=False, contents=False, folders=False, cancel=None, emit=None):
    """在背景執行緒跑；每找到一筆就 emit(("hit", (分數, 路徑, 是不是資料夾, 內容片段)))。"""
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if cancel is not None and cancel.is_set():
            return scanned
        names = [(d, True) for d in dirnames] if folders else []
        names += [(f, False) for f in filenames]
        for name, is_dir in names:
            scanned += 1
            if not is_dir and patterns and not any(fnmatch.fnmatch(name.lower(), p) for p in patterns):
                continue
            full = os.path.join(dirpath, name)
            score = name_score(name, q, fuzzy) if not q.empty else 1
            snippet = None
            if not score and contents and not is_dir:
                snippet = content_hit(full, q)
                if snippet is not None:
                    score = 1
            if score and emit:
                emit(("hit", (score, full, is_dir, snippet)))
        if emit and scanned % 500 < len(names):
            emit(("progress", scanned))
    return scanned


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class FileSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Better File Finder v{__version__}")
        self.root.geometry("1080x640")
        self.root.minsize(760, 420)
        self.events = queue.Queue()
        self.cancel = None
        self.rows = {}           # tree item → 完整路徑
        self.started = 0.0
        self._build()
        self.root.after(100, self._drain)

    def _build(self):
        form = ttk.Frame(self.root, padding=10)
        form.pack(fill="x")
        self.folder = tk.StringVar(value=os.path.expanduser("~"))
        self.text = tk.StringVar()
        self.patterns = tk.StringVar()
        self.fuzzy = tk.BooleanVar()
        self.contents = tk.BooleanVar()
        self.folders = tk.BooleanVar()

        ttk.Label(form, text="資料夾").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.folder).grid(row=0, column=1, columnspan=3, sticky="we", padx=6)
        ttk.Button(form, text="瀏覽…", command=self._pick).grid(row=0, column=4)
        ttk.Label(form, text="搜尋").grid(row=1, column=0, sticky="w", pady=(6, 0))
        entry = ttk.Entry(form, textvariable=self.text)
        entry.grid(row=1, column=1, sticky="we", padx=6, pady=(6, 0))
        entry.bind("<Return>", lambda _e: self._start())
        entry.focus_set()
        ttk.Label(form, text="副檔名").grid(row=1, column=2, sticky="e", pady=(6, 0))
        ttk.Entry(form, textvariable=self.patterns, width=18).grid(row=1, column=3, sticky="w", padx=6, pady=(6, 0))
        self.go = ttk.Button(form, text="搜尋", command=self._start)
        self.go.grid(row=1, column=4, pady=(6, 0))
        opts = ttk.Frame(form)
        opts.grid(row=2, column=1, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opts, text="模糊比對", variable=self.fuzzy).pack(side="left")
        ttk.Checkbutton(opts, text="搜尋檔案內容（文字檔）", variable=self.contents).pack(side="left", padx=12)
        ttk.Checkbutton(opts, text="也找資料夾", variable=self.folders).pack(side="left")
        ttk.Label(opts, text='　語法：兩個詞＝都要有、"整段文字"、-排除；副檔名例：txt, md 或 *.py',
                  foreground="#777").pack(side="left", padx=12)
        form.columnconfigure(1, weight=1)

        table = ttk.Frame(self.root, padding=(10, 0))
        table.pack(fill="both", expand=True)
        cols = ("name", "folder", "size", "modified", "match")
        self.tree = ttk.Treeview(table, columns=cols, show="headings")
        for col, text, width in (("name", "名稱", 260), ("folder", "所在資料夾", 330), ("size", "大小", 80),
                                 ("modified", "修改時間", 130), ("match", "符合的內容", 260)):
            self.tree.heading(col, text=text, command=lambda c=col: self._sort(c))
            self.tree.column(col, width=width, anchor="e" if col == "size" else "w")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self._open(reveal=False))
        self.tree.bind("<Return>", lambda _e: self._open(reveal=False))

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")
        self.status = ttk.Label(bottom, text="輸入關鍵字後按 Enter")
        self.status.pack(side="left")
        ttk.Button(bottom, text="在檔案總管中顯示", command=lambda: self._open(reveal=True)).pack(side="right")
        ttk.Button(bottom, text="開啟", command=lambda: self._open(reveal=False)).pack(side="right", padx=6)

    # ------------------------------------------------------------------ 搜尋
    def _pick(self):
        folder = filedialog.askdirectory(initialdir=self.folder.get() or None)
        if folder:
            self.folder.set(folder)

    def _start(self):
        if self.cancel is not None:          # 搜尋中再按一次 = 停止
            self.cancel.set()
            return
        folder = self.folder.get().strip()
        if not os.path.isdir(folder):
            self.status.configure(text="資料夾不存在")
            return
        q = Query.parse(self.text.get())
        patterns = parse_patterns(self.patterns.get())
        if q.empty and not patterns:
            self.status.configure(text="請輸入關鍵字或副檔名")
            return
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.cancel = threading.Event()
        self.started = time.time()
        self.go.configure(text="停止")
        args = (folder, q, patterns)
        kwargs = dict(fuzzy=self.fuzzy.get(), contents=self.contents.get(), folders=self.folders.get(),
                      cancel=self.cancel, emit=self.events.put)

        def worker():
            try:
                scanned = search(*args, **kwargs)
                self.events.put(("done", scanned))
            except Exception as exc:  # noqa: BLE001 — 顯示在狀態列，不要讓執行緒默默結束
                self.events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _drain(self):
        """把背景執行緒的結果搬到畫面上（Tk 只能在主執行緒操作）。"""
        try:
            for _ in range(500):
                kind, data = self.events.get_nowait()
                if kind == "hit":
                    self._add(*data)
                elif kind == "progress":
                    self.status.configure(text=f"搜尋中… 已看過 {data:,} 個項目，找到 {len(self.rows):,} 個")
                else:
                    stopped = self.cancel is not None and self.cancel.is_set()
                    self.cancel = None
                    self.go.configure(text="搜尋")
                    if kind == "error":
                        self.status.configure(text=f"錯誤：{data}")
                    else:
                        word = "已停止" if stopped else "完成"
                        self.status.configure(text=f"{word}：看過 {data:,} 個項目，找到 {len(self.rows):,} 個"
                                                   f"（{time.time() - self.started:.1f} 秒）")
                        self._sort("score")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _add(self, score, path, is_dir, snippet):
        try:
            st = os.stat(path)
            nbytes, mtime = (-1 if is_dir else st.st_size), st.st_mtime
        except OSError:            # 搜尋途中被刪掉或沒有權限
            nbytes, mtime = -1, 0
        size = human_size(nbytes) if nbytes >= 0 else ""
        modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime else ""
        name = os.path.basename(path) + ("\\" if is_dir else "")
        item = self.tree.insert("", "end", values=(name, os.path.dirname(path), size, modified, snippet or ""))
        self.rows[item] = (path, score, nbytes, mtime)

    def _sort(self, col):
        items = list(self.tree.get_children())
        if col == "score":
            items.sort(key=lambda i: -self.rows[i][1])
        elif col == "size":
            items.sort(key=lambda i: -self.rows[i][2])
        elif col == "modified":
            items.sort(key=lambda i: -self.rows[i][3])
        else:
            items.sort(key=lambda i: str(self.tree.set(i, col)).lower())
        for index, item in enumerate(items):
            self.tree.move(item, "", index)

    def _open(self, reveal):
        sel = self.tree.selection()
        if not sel:
            return
        path = self.rows[sel[0]][0]
        if reveal:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(path)


def main():
    root = tk.Tk()
    FileSearchApp(root)
    root.mainloop()


if __name__ == "__main__":
    # 舊版結尾有 input("按 Enter 鍵退出")：打包成沒有主控台的 exe 時 stdin 不存在，關視窗就崩潰
    sys.exit(main())
