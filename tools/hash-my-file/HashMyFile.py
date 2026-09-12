import hashlib
import os
import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, Set
from tkinterdnd2 import DND_FILES, TkinterDnD

# --- 配置與常數 ---
ALGORITHMS = {
    "MD5": hashlib.md5,
    "SHA1": hashlib.sha1,
    "SHA256": hashlib.sha256,
}

# 配色方案：用於標記相同內容的檔案
COLOR_PALETTE = ["#e1f5fe", "#e8f5e9", "#fff3e0", "#fce4ec", "#f3e5f5", "#efebe9", "#f9fbe7", "#e0f2f1"]


class FileHasher:
    """封裝雜湊計算邏輯"""

    @staticmethod
    def get_hashes(file_path: str) -> Optional[Dict[str, str]]:
        if not os.path.isfile(file_path):
            return None

        hash_objs = {name: algo() for name, algo in ALGORITHMS.items()}
        try:
            with open(file_path, 'rb') as f:
                # 使用 64KB Buffer 提升大檔處理效能
                for chunk in iter(lambda: f.read(65536), b""):
                    for obj in hash_objs.values():
                        obj.update(chunk)
            return {name: obj.hexdigest() for name, obj in hash_objs.items()}
        except (IOError, PermissionError):
            return None


class HashApp:
    def __init__(self, root: TkinterDnD.Tk):
        self.root = root
        self.root.title("檔案內容比對工具 (相同內容自動同色)")
        self.root.geometry("1100x600")

        # 狀態紀錄
        self.loaded_paths: Set[str] = set()  # 紀錄路徑，避免重複拉入同一個檔案路徑
        self.hash_to_color: Dict[str, str] = {}  # 紀錄 Hash 對應的顏色

        self._setup_ui()
        self._setup_dnd()

    def _setup_ui(self):
        """建構介面"""
        # 工具欄
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        ttk.Label(toolbar, text="提示：相同底色的檔案代表內容完全一致 (SHA256 相同)", foreground="#666").pack(
            side=tk.LEFT)
        ttk.Button(toolbar, text="清空列表", command=self.clear_data).pack(side=tk.RIGHT)

        # 表格區
        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.columns = ("name", "MD5", "SHA1", "SHA256", "path")
        self.tree = ttk.Treeview(table_frame, columns=self.columns, show="headings")

        # 設置標題與排序
        for col in self.columns:
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by_column(c, False))
            width = 350 if col in ["SHA256", "path"] else 120
            self.tree.column(col, width=width, anchor="w")

        # 捲軸
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _setup_dnd(self):
        """拖放綁定"""
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind('<<Drop>>', self._handle_drop)

    def _handle_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        for path in paths:
            # 改為檢查「路徑」是否重複
            if path in self.loaded_paths:
                continue

            data = FileHasher.get_hashes(path)
            if data:
                self.loaded_paths.add(path)
                self._insert_to_tree(path, data)

    def _insert_to_tree(self, path: str, hash_data: Dict[str, str]):
        """插入資料並根據 Hash 給予顏色"""
        sha256 = hash_data['SHA256']

        # 如果這個 Hash 之前出現過，使用舊顏色；沒出現過則配新顏色
        if sha256 not in self.hash_to_color:
            new_color = COLOR_PALETTE[len(self.hash_to_color) % len(COLOR_PALETTE)]
            self.hash_to_color[sha256] = new_color
            self.tree.tag_configure(sha256, background=new_color)

        self.tree.insert('', tk.END, values=(
            os.path.basename(path),
            hash_data['MD5'],
            hash_data['SHA1'],
            sha256,
            path
        ), tags=(sha256,))

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


if __name__ == "__main__":
    app_root = TkinterDnD.Tk()
    app = HashApp(app_root)
    app_root.mainloop()