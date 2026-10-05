import hashlib

from tkinterdnd2 import TkinterDnD, DND_FILES
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox

class FileRenamerApp:
    def __init__(self, root):
        self.root = TkinterDnD.Tk()  # 使用 TkinterDnD 啟用 DND
        self.root.title("DND File Renamer with Regular Expression")
        self.create_widgets()

    def create_widgets(self):
        # 左上和右上 Listbox（匹配檔案）
        self.left_listbox = self.create_listbox("Left: Original Files", 0, 0)
        self.right_listbox = self.create_listbox("Right: Renamed Files", 0, 2)

        # 匹配按鈕和應用按鈕
        match_btn = tk.Button(self.root, text="Generate Matches", command=self.rename_with_regular_expression_rule)
        match_btn.grid(row=1, column=0, padx=5, pady=5)

        apply_btn = tk.Button(self.root, text="Apply Renames", command=self.apply_renames)
        apply_btn.grid(row=1, column=2, padx=5, pady=5)
        hash_btn = tk.Button(self.root, text="Rename With Hash", command=self.rename_with_hash)
        hash_btn.grid(row=1, column=1, padx=5, pady=5)

        # 左下和右下 Listbox（不匹配檔案）
        self.unmatched_left_listbox = self.create_listbox("Left: Unmatched Files", 2, 0)
        self.unmatched_right_listbox = self.create_listbox("Right: Unmatched Files", 2, 2)

        # 切換匹配與不匹配的按鈕
        move_to_unmatched_btn = tk.Button(self.root, text="Move to Unmatched", command=self.move_to_unmatched)
        move_to_unmatched_btn.grid(row=3, column=0, padx=5, pady=5)

        move_to_matched_btn = tk.Button(self.root, text="Move to Matched", command=self.move_to_matched)
        move_to_matched_btn.grid(row=3, column=2, padx=5, pady=5)

        # 正則表達式與替換模式
        tk.Label(self.root, text="Regular Expression:").grid(row=4, column=0, sticky="e", padx=5, pady=5)
        self.regex_entry = tk.Entry(self.root, width=30)
        self.regex_entry.grid(row=4, column=2, sticky="w", padx=5, pady=5)

        tk.Label(self.root, text="Replacement Pattern:").grid(row=5, column=0, sticky="e", padx=5, pady=5)
        self.replacement_entry = tk.Entry(self.root, width=30)
        self.replacement_entry.grid(row=5, column=2, sticky="w", padx=5, pady=5)

        # 綁定拖放事件
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.handle_file_drop)

    def clear_lists(self, listbox):
        listbox.delete(0, tk.END)  # 清空左侧列表
        # self.left_listbox.delete(0, tk.END)  # 清空左侧列表
        # self.right_listbox.delete(0, tk.END)  # 清空右侧列表
    
    def create_listbox(self, title, row, column):
        frame = tk.Frame(self.root)
        frame.grid(row=row, column=column, columnspan=2, padx=10, pady=10)
        label = tk.Label(frame, text=title)
        label.grid(row=0, column=1, columnspan=2, sticky="nesw")
        listbox = tk.Listbox(frame, selectmode=tk.MULTIPLE, width=40, height=10)
        listbox.grid(row=1, column=0, columnspan=4)
        # 在初始化中加入清空按钮
        clear_button = tk.Button(frame, text="清空", command=lambda x=listbox: self.clear_lists(x))
        clear_button.grid(row=0, column=3)
        return listbox

    def handle_file_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        for file in files:
            if os.path.isfile(file) and (file not in self.left_listbox.get(0, tk.END)):
                self.left_listbox.insert(tk.END, file)

    def rename_with_hash(self):
        self.right_listbox.delete(0, tk.END)  # 清空右侧列表
        for file in self.left_listbox.get(0, tk.END):
            filename = os.path.basename(file)
            dirpath = os.path.dirname(file)
            try:
                # 使用SHA256哈希生成文件名
                hash_object = hashlib.sha256(filename.encode('utf-8'))
                hash_name = hash_object.hexdigest()  # 取得SHA256的十六进制表示
                # 保留文件扩展名
                ext = os.path.splitext(filename)[1]
                new_name = f"{hash_name}{ext}"
                print(f"Original: {filename} -> Renamed: {new_name}")  # 打印调试信息
                # 显示完整路径以保持一致
                new_full_path = os.path.join(dirpath, new_name)
                self.right_listbox.insert(tk.END, new_full_path)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to hash filename: {e}")
                return

    def rename_with_regular_expression_rule(self):
        regex = self.regex_entry.get()
        replacement = self.replacement_entry.get()

        self.right_listbox.delete(0, tk.END)  # 清空右侧列表
        for file in self.left_listbox.get(0, tk.END):
            filename = os.path.basename(file)
            try:
                # 使用re.sub進行文件名替換
                new_name = re.sub(regex, replacement, filename)
                print(f"Original: {filename} -> Renamed: {new_name}")  # 打印調試信息
                self.right_listbox.insert(tk.END, new_name)
            except re.error as e:
                messagebox.showerror("Error", f"Invalid Regular Expression: {e}")
                return

    def apply_renames(self):
        fails_list = []
        # 執行文件重命名
        for i, file in enumerate(self.left_listbox.get(0, tk.END)):
            new_name = self.right_listbox.get(i)
            dir_path = os.path.dirname(file)
            old_path = os.path.join(dir_path, os.path.basename(file))
            new_path = os.path.join(dir_path, new_name)
            try:
                print(f"Renaming: {old_path} -> {new_path}")  # 打印调试信息
                if not os.path.exists(new_path):
                    os.rename(old_path, new_path)  # 重命名文件
                else:
                    fails_list.append(old_path)
            except Exception as e:
                messagebox.showerror("Error", f"Could not rename {file}:\n{e}")
                fails_list.append(file)
        self.clear_lists(self.left_listbox)
        self.clear_lists(self.right_listbox)
        for file in fails_list:
            self.unmatched_left_listbox.insert(tk.END, file)

    def move_to_unmatched(self):
        selected_files = list(self.left_listbox.curselection())
        for index in reversed(selected_files):
            file = self.left_listbox.get(index)
            self.left_listbox.delete(index)
            self.unmatched_left_listbox.insert(tk.END, file)

    def move_to_matched(self):
        selected_files = list(self.unmatched_left_listbox.curselection())
        for index in reversed(selected_files):
            file = self.unmatched_left_listbox.get(index)
            self.unmatched_left_listbox.delete(index)
            self.left_listbox.insert(tk.END, file)

if __name__ == "__main__":
    root = tk.Tk()
    app = FileRenamerApp(root)
    root.mainloop()
