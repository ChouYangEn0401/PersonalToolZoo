import hashlib
import os
import tkinter as tk
from tkinter import ttk, messagebox
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
        self.all_data: list = []  # 紀錄所有檔案資料，用於篩選功能

        self._setup_ui()
        self._setup_dnd()

    def _setup_ui(self):
        """建構介面"""
        # 工具欄
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        ttk.Label(toolbar, text="提示：相同底色的檔案代表內容完全一致 (SHA256 相同)", foreground="#666").pack(side=tk.LEFT)
        ttk.Button(toolbar, text="清空列表", command=self.clear_data).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="僅顯示重複項目", command=self._filter_duplicates).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="恢復顯示全部", command=self._show_all).pack(side=tk.RIGHT, padx=2)

        # 表格區
        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.columns = ("name", "MD5", "SHA1", "SHA256", "path", "open", "delete")
        self.tree = ttk.Treeview(table_frame, columns=self.columns, show="headings")

        # 設置標題與排序
        for col in self.columns:
            if col == "open":
                display_name = "📂 開啟"
            elif col == "delete":
                display_name = "🗑️ 刪除"
            else:
                display_name = col
                
            self.tree.heading(col, text=display_name, command=lambda c=col: self._sort_by_column(c, False))
            
            if col in ["open", "delete"]:
                width = 80
                anchor = "center"
            elif col in ["SHA256", "path"]:
                width = 350
                anchor = "w"
            else:
                width = 120
                anchor = "w"
            self.tree.column(col, width=width, anchor=anchor)

        self.tree.bind("<Button-1>", self._on_tree_click)

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

        item_values = (
            os.path.basename(path),
            hash_data['MD5'],
            hash_data['SHA1'],
            sha256,
            path,
            "📂 開啟",
            "❌ 刪除"
        )
        self.all_data.append({"values": item_values, "tags": (sha256,)})
        self.tree.insert('', tk.END, values=item_values, tags=(sha256,))

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
        self.all_data.clear()

    def _on_tree_click(self, event):
        """處理表格點擊事件"""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            item_id = self.tree.identify_row(event.y)
            values = self.tree.item(item_id, 'values')
            if not values:
                return
            
            path = values[4]  # path 欄位索引為 4
            
            # 開啟欄位 (#6)
            if column == "#6":
                if os.path.exists(path):
                    folder = os.path.dirname(os.path.abspath(path))
                    os.startfile(folder)
            
            # 刪除欄位 (#7)
            elif column == "#7":
                self._delete_file_workflow(item_id, path)

    def _delete_file_workflow(self, item_id, path):
        """執行刪除檔案流程，包含三次確認"""
        filename = os.path.basename(path)
        
        # 第一次確認
        if not messagebox.askyesno("刪除確認 (1/3)", f"確定要刪除檔案嗎？\n{filename}"):
            return
            
        # 第二次確認
        if not messagebox.askyesno("刪除確認 (2/3)", "這會永久刪除檔案，無法從資源回收筒恢復！\n你真的確定嗎？"):
            return
            
        # 第三次確認
        if not messagebox.askyesno("最後確認 (3/3)", "最後一次機會：刪除後將無法找回。\n執行刪除？"):
            return

        try:
            if os.path.exists(path):
                os.remove(path)
                messagebox.showinfo("成功", f"檔案已刪除：\n{filename}")
                
                # 從介面移除
                self.tree.delete(item_id)
                
                # 從內部紀錄移除，避免重新整理時又跑出來
                self.all_data = [d for d in self.all_data if d["values"][4] != path]
                if path in self.loaded_paths:
                    self.loaded_paths.remove(path)
            else:
                messagebox.showwarning("錯誤", "檔案不存在，可能已被刪除。")
                self.tree.delete(item_id)
        except Exception as e:
            messagebox.showerror("刪除失敗", f"無法刪除檔案：\n{str(e)}")

    def _filter_duplicates(self):
        """僅保留重複的檔案 (SHA256 相同的)"""
        # 統計 Hash 出現次數
        hash_counts = {}
        for item in self.all_data:
            sha256 = item["values"][3]
            hash_counts[sha256] = hash_counts.get(sha256, 0) + 1

        # 清空目前表格並重新填入
        for item in self.tree.get_children():
            self.tree.delete(item)

        for item in self.all_data:
            sha256 = item["values"][3]
            if hash_counts[sha256] > 1:
                self.tree.insert('', tk.END, values=item["values"], tags=item["tags"])

    def _show_all(self):
        """顯示所有已載入檔案"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        for item in self.all_data:
            self.tree.insert('', tk.END, values=item["values"], tags=item["tags"])


if __name__ == "__main__":
    app_root = TkinterDnD.Tk()
    app = HashApp(app_root)
    app_root.mainloop()