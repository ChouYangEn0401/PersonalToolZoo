import hashlib
import os
import queue
import threading
import tkinter as tk
import zlib
from tkinter import ttk
from typing import Dict, Iterable, List, Optional, Set

from tkinterdnd2 import DND_FILES, TkinterDnD

from version import __version__

# --- 配置與常數 ---
ALGORITHMS = {
    "MD5": hashlib.md5,
    "SHA1": hashlib.sha1,
    "SHA256": hashlib.sha256,
}
COLUMNS = ("name", "MD5", "SHA1", "SHA256", "CRC32", "path")

# 配色方案：用於標記相同內容的檔案
COLOR_PALETTE = ["#e1f5fe", "#e8f5e9", "#fff3e0", "#fce4ec", "#f3e5f5", "#efebe9", "#f9fbe7", "#e0f2f1"]


class FileHasher:
    """封裝雜湊計算邏輯"""

    @staticmethod
    def get_hashes(file_path: str) -> Optional[Dict[str, str]]:
        if not os.path.isfile(file_path):
            return None

        hash_objs = {name: algo() for name, algo in ALGORITHMS.items()}
        crc = 0
        try:
            with open(file_path, 'rb') as f:
                # 使用 64KB Buffer 提升大檔處理效能
                for chunk in iter(lambda: f.read(65536), b""):
                    for obj in hash_objs.values():
                        obj.update(chunk)
                    crc = zlib.crc32(chunk, crc)
            result = {name: obj.hexdigest() for name, obj in hash_objs.items()}
            result["CRC32"] = format(crc & 0xFFFFFFFF, "08x")   # 壓縮檔、遊戲 ROM 常用 CRC32 校驗
            return result
        except (IOError, PermissionError):
            return None

    @staticmethod
    def expand(paths: Iterable[str]) -> List[str]:
        """拖進來的資料夾展開成裡面所有的檔案（含子資料夾）。"""
        files = []
        for path in paths:
            if os.path.isdir(path):
                for dirpath, _dirs, names in os.walk(path):
                    files.extend(os.path.join(dirpath, n) for n in sorted(names))
            elif os.path.isfile(path):
                files.append(path)
        return files

    @staticmethod
    def match(expected: str, hash_data: Dict[str, str]) -> Optional[str]:
        """貼上的雜湊值符合哪一種演算法（不分大小寫、忽略空白與冒號）；都不符合回傳 None。"""
        cleaned = "".join(expected.split()).replace(":", "").lower()
        if not cleaned:
            return None
        for name, value in hash_data.items():
            if value.lower() == cleaned:
                return name
        return None


class HashApp:
    def __init__(self, root: TkinterDnD.Tk):
        self.root = root
        self.root.title(f"檔案內容比對工具 (相同內容自動同色) v{__version__}")
        self.root.geometry("1180x620")

        # 狀態紀錄
        self.loaded_paths: Set[str] = set()  # 紀錄路徑，避免重複拉入同一個檔案路徑
        self.hash_to_color: Dict[str, str] = {}  # 紀錄 Hash 對應的顏色
        self.item_hashes: Dict[str, Dict[str, str]] = {}  # tree item → 這個檔案的所有雜湊
        self.results: "queue.Queue" = queue.Queue()
        self.pending = 0

        self._setup_ui()
        self._setup_dnd()
        self.root.after(100, self._drain)

    def _setup_ui(self):
        """建構介面"""
        # 工具欄
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        ttk.Label(toolbar, text="提示：相同底色的檔案代表內容完全一致 (SHA256 相同)；可以拖檔案或資料夾",
                  foreground="#666").pack(side=tk.LEFT)
        ttk.Button(toolbar, text="清空列表", command=self.clear_data).pack(side=tk.RIGHT)

        # 比對：貼上下載頁提供的雜湊值，看哪個檔案符合（舊版 HashMyFile 的功能）
        verify = ttk.Frame(self.root)
        verify.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(verify, text="比對雜湊：").pack(side=tk.LEFT)
        self.expected = tk.StringVar()
        entry = ttk.Entry(verify, textvariable=self.expected, width=70)
        entry.pack(side=tk.LEFT, padx=4)
        self.expected.trace_add("write", lambda *_: self._verify())
        self.verify_label = ttk.Label(verify, text="（貼上 MD5 / SHA1 / SHA256 / CRC32，符合的檔案會標綠）",
                                      foreground="#666")
        self.verify_label.pack(side=tk.LEFT, padx=8)

        # 表格區
        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.columns = COLUMNS
        self.tree = ttk.Treeview(table_frame, columns=self.columns, show="headings")
        self.tree.tag_configure("match", foreground="#1b8a3a", font=("Segoe UI", 9, "bold"))

        # 設置標題與排序
        for col in self.columns:
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by_column(c, False))
            width = {"SHA256": 350, "path": 350, "CRC32": 80}.get(col, 120)
            self.tree.column(col, width=width, anchor="w")

        # 捲軸
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.status = ttk.Label(self.root, text="把檔案或資料夾拖進表格", foreground="#666")
        self.status.pack(side=tk.BOTTOM, anchor="w", padx=10, pady=(0, 6))

    def _setup_dnd(self):
        """拖放綁定"""
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind('<<Drop>>', self._handle_drop)

    def _handle_drop(self, event):
        self.add_paths(self.root.tk.splitlist(event.data))

    def add_paths(self, paths: Iterable[str]):
        """在背景執行緒算雜湊：大檔案不會卡住視窗。"""
        todo = [p for p in FileHasher.expand(paths) if p not in self.loaded_paths]
        self.loaded_paths.update(todo)
        if not todo:
            return
        self.pending += len(todo)
        self.status.configure(text=f"計算中…剩 {self.pending} 個檔案")

        def worker():
            for path in todo:
                self.results.put((path, FileHasher.get_hashes(path)))

        threading.Thread(target=worker, daemon=True).start()

    def _drain(self):
        """把背景算好的結果放進表格（Tk 只能在主執行緒操作）。"""
        try:
            while True:
                path, data = self.results.get_nowait()
                self.pending -= 1
                if data:
                    self._insert_to_tree(path, data)
                else:
                    self.loaded_paths.discard(path)
                self.status.configure(text=f"計算中…剩 {self.pending} 個檔案" if self.pending
                                      else f"共 {len(self.item_hashes)} 個檔案")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _insert_to_tree(self, path: str, hash_data: Dict[str, str]):
        """插入資料並根據 Hash 給予顏色"""
        sha256 = hash_data['SHA256']

        # 如果這個 Hash 之前出現過，使用舊顏色；沒出現過則配新顏色
        if sha256 not in self.hash_to_color:
            new_color = COLOR_PALETTE[len(self.hash_to_color) % len(COLOR_PALETTE)]
            self.hash_to_color[sha256] = new_color
            self.tree.tag_configure(sha256, background=new_color)

        item = self.tree.insert('', tk.END, values=(
            os.path.basename(path),
            hash_data['MD5'],
            hash_data['SHA1'],
            sha256,
            hash_data['CRC32'],
            path
        ), tags=(sha256,))
        self.item_hashes[item] = hash_data
        self._verify()

    def _verify(self):
        """依「比對雜湊」欄更新每一列的標示。"""
        expected = self.expected.get()
        hits = []
        for item, hashes in self.item_hashes.items():
            algo = FileHasher.match(expected, hashes)
            tags = [hashes["SHA256"]] + (["match"] if algo else [])
            self.tree.item(item, tags=tags)
            if algo:
                hits.append(f"{self.tree.set(item, 'name')}（{algo}）")
        if not expected.strip():
            self.verify_label.configure(text="（貼上 MD5 / SHA1 / SHA256 / CRC32，符合的檔案會標綠）", foreground="#666")
        elif hits:
            self.verify_label.configure(text="✓ 符合：" + "、".join(hits), foreground="#1b8a3a")
        else:
            self.verify_label.configure(text="✗ 沒有檔案符合這個雜湊值", foreground="#c62828")

    def _sort_by_column(self, col: str, reverse: bool):
        """點擊 Header 排序"""
        l = [(self.tree.set(k, col).lower(), k) for k in self.tree.get_children('')]
        l.sort(reverse=reverse)
        for index, (_, k) in enumerate(l):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self._sort_by_column(col, not reverse))

    def clear_data(self):
        """重置所有狀態"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.loaded_paths.clear()
        self.hash_to_color.clear()
        self.item_hashes.clear()
        self._verify()
        self.status.configure(text="把檔案或資料夾拖進表格")


if __name__ == "__main__":
    app_root = TkinterDnD.Tk()
    app = HashApp(app_root)
    app_root.mainloop()
