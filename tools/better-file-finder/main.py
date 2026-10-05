import traceback
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import fnmatch
from difflib import SequenceMatcher
import subprocess
import re


class FileSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件搜尋工具")

        self.folder_path = tk.StringVar()
        self.search_text = tk.StringVar()
        self.file_extension = tk.StringVar()
        self.include_content = tk.BooleanVar()
        self.include_content.set(False)
        self.result_list = []

        self._build_ui()

    def _build_ui(self):
        # 資料夾選擇
        tk.Label(self.root, text="選擇資料夾:").grid(row=0, column=0, sticky="w")
        tk.Entry(self.root, textvariable=self.folder_path, width=50).grid(row=0, column=1, padx=5)
        tk.Button(self.root, text="瀏覽", command=self._select_folder).grid(row=0, column=2)

        # 搜尋文字
        tk.Label(self.root, text="搜尋文字:").grid(row=1, column=0, sticky="w")
        tk.Entry(self.root, textvariable=self.search_text, width=50).grid(row=1, column=1, padx=5)

        # 文件類型
        tk.Label(self.root, text="文件類型(如: *.txt):").grid(row=2, column=0, sticky="w")
        tk.Entry(self.root, textvariable=self.file_extension, width=20).grid(row=2, column=1, sticky="w", padx=5)

        # 匹配內容選項
        tk.Checkbutton(self.root, text="匹配文件內容", variable=self.include_content).grid(row=3, column=1, sticky="w", padx=5)

        # 搜尋按鈕
        tk.Button(self.root, text="搜尋", command=self._search).grid(row=4, column=1, pady=10)

        # 結果顯示
        tk.Label(self.root, text="搜尋結果:").grid(row=5, column=0, sticky="w")
        self.result_listbox = tk.Listbox(self.root, width=50, height=20)
        self.result_listbox.grid(row=6, column=0, columnspan=2, padx=5, sticky="nsew")
        self.result_listbox.bind("<<ListboxSelect>>", self._show_details)

        # 詳細資料區域
        self.details_text = tk.Text(self.root, width=50, height=10, state="disabled")
        self.details_text.grid(row=6, column=2, padx=5, sticky="n")

        self.open_button = tk.Button(self.root, text="打開所在位置", command=self._open_in_explorer, state="disabled")
        self.open_button.grid(row=7, column=2, pady=10, sticky="n")

        # 調整佈局
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(6, weight=1)

    def _select_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.folder_path.set(folder_selected)

    def _search(self):
        folder = self.folder_path.get()
        query = self.search_text.get().strip()
        ext_filter = self.file_extension.get()
        include_content = self.include_content.get()

        if not folder:
            messagebox.showerror("錯誤", "請選擇資料夾！")
            return

        self.result_listbox.delete(0, tk.END)
        self.result_list = []

        # 處理查詢條件
        exact_match = re.findall(r'"(.*?)"', query)
        include_terms = [term.lstrip('+') for term in query.split() if term.startswith('+')]
        exclude_terms = [term.lstrip('-') for term in query.split() if term.startswith('-')]
        query_terms = [term for term in query.split() if not (term.startswith('+') or term.startswith('-'))]

        for root, dirs, files in os.walk(folder):
            # 根據搜尋條件過濾目錄和檔案
            for name in dirs + files:
                full_path = os.path.join(root, name)

                # 過濾副檔名
                if files and ext_filter:
                    normalized_ext = f"*.{ext_filter.lstrip('.')}"
                    if not fnmatch.fnmatch(name, normalized_ext):
                        continue

                # 完全匹配的條件
                if any(term == name for term in exact_match):
                    self.result_list.append((3, name, full_path))
                # 完全包含的條件
                elif any(term in name for term in query_terms):
                    self.result_list.append((2, name, full_path))
                # 最大匹配
                else:
                    match_score = self._match(" ".join(query_terms), name)
                    if match_score > 0:
                        self.result_list.append((match_score, name, full_path))

                # 檢查包含和排除條件
                if any(term not in name for term in exclude_terms):
                    continue
                if any(term in name for term in include_terms):
                    self.result_list.append((1, name, full_path))

        # 排序結果並顯示
        self.result_list.sort(reverse=True, key=lambda x: x[0])
        for _, file, _ in self.result_list:
            self.result_listbox.insert(tk.END, file)

    def _match(self, query, target):
        """匹配文件名稱，使用LCS計算相關性。"""
        return SequenceMatcher(None, query, target).ratio()

    def _show_details(self, event):
        selected_index = self.result_listbox.curselection()
        if selected_index:
            file_info = self.result_list[selected_index[0]]
            file_path = file_info[2]
            self.details_text.config(state="normal")
            self.details_text.delete(1.0, tk.END)
            self.details_text.insert(tk.END, f"完整路徑: {file_path}")
            self.details_text.config(state="disabled")
            self.open_button.config(state="normal")
            self.selected_file_path = file_path
        else:
            self.details_text.config(state="normal")
            self.details_text.delete(1.0, tk.END)
            self.details_text.config(state="disabled")
            self.open_button.config(state="disabled")
            self.selected_file_path = None

    def _open_in_explorer(self):
        if hasattr(self, "selected_file_path") and self.selected_file_path:
            folder = os.path.dirname(self.selected_file_path)
            subprocess.run(["explorer", folder], check=False)


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = FileSearchApp(root)
        root.mainloop()
    except Exception as e:
        print("\n[Error Occurred]")
        traceback.print_exc()
    finally:
        input("\n程序已結束。按 Enter 鍵退出...")
