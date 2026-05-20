import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import os
import uuid

root = tk.Tk()
root.title("Excel 合併工具 - v1")
root.geometry("900x800")

main_frame = tk.Frame(root)
main_frame.pack(fill=tk.BOTH, expand=1)

canvas = tk.Canvas(main_frame)
scrollbar = tk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
scrollable_frame = tk.Frame(canvas)

scrollable_frame.bind(
    "<Configure>",
    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
)

canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)

canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

# 儲存 DataFrame 和其唯一 ID
data_frames = {}

def add_excel_frame(df, sheet_name, file_path):
    uid = str(uuid.uuid4())
    frame = tk.Frame(scrollable_frame, bd=2, relief=tk.GROOVE, padx=10, pady=10)
    frame.pack(fill=tk.X, pady=5)

    header = tk.Frame(frame)
    header.pack(fill=tk.X)
    label = tk.Label(header, text=f"{os.path.basename(file_path)} - {sheet_name}", font=('Arial', 12, 'bold'))
    label.pack(side=tk.LEFT)

    def remove_frame():
        if messagebox.askyesno("確認", "是否要移除此資料？"):
            frame.destroy()
            del data_frames[uid]

    close_btn = tk.Button(header, text="❌ 移除", fg="red", command=remove_frame)
    close_btn.pack(side=tk.RIGHT)

    # 欄位選擇與刪除欄位列
    control_frame = tk.Frame(frame)
    control_frame.pack(fill=tk.X)

    columns = list(df.columns)
    selected_columns = tk.Variable(value=columns)
    listbox = tk.Listbox(control_frame, listvariable=selected_columns, selectmode=tk.MULTIPLE, height=5, exportselection=False)
    listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def update_status():
        rows, cols = df.shape
        status_label.config(text=f"📐 表格尺寸：{rows} x {cols}")

    def drop_selected_columns():
        selected = [listbox.get(i) for i in listbox.curselection()]
        if selected:
            df.drop(columns=selected, inplace=True, errors='ignore')
            refresh_treeview(df, tree)
            update_status()
            listbox.delete(0, tk.END)
            for col in df.columns:
                listbox.insert(tk.END, col)

    status_label = tk.Label(control_frame, text="📐 表格尺寸：0 x 0")
    status_label.pack(side=tk.LEFT, padx=10)
    drop_btn = tk.Button(control_frame, text="丟棄選中欄位", command=drop_selected_columns)
    drop_btn.pack(side=tk.RIGHT, padx=10)

    # 顯示資料表格
    tree = ttk.Treeview(frame, columns=list(df.columns), show='headings', height=8)
    for col in df.columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="w", width=100)

    for _, row in df.head(20).iterrows():
        tree.insert("", "end", values=list(row))

    tree.pack(fill=tk.X, pady=5)

    data_frames[uid] = df
    update_status()

def refresh_treeview(df, tree):
    tree.delete(*tree.get_children())
    tree["columns"] = list(df.columns)
    for col in df.columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="w", width=100)
    for _, row in df.head(20).iterrows():
        tree.insert("", "end", values=list(row))

def open_excel():
    file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
    if not file_path:
        return

    xls = pd.ExcelFile(file_path)
    if len(xls.sheet_names) > 1:
        select_window = tk.Toplevel(root)
        select_window.title("選擇 Sheet")

        sheet_vars = {}
        for sheet in xls.sheet_names:
            var = tk.BooleanVar(value=False)
            chk = tk.Checkbutton(select_window, text=sheet, variable=var)
            chk.pack(anchor='w')
            sheet_vars[sheet] = var

        def load_selected_sheets():
            for sheet, var in sheet_vars.items():
                if var.get():
                    df = xls.parse(sheet)
                    add_excel_frame(df, sheet, file_path)
            select_window.destroy()

        confirm_btn = tk.Button(select_window, text="載入選擇的 Sheet", command=load_selected_sheets)
        confirm_btn.pack(pady=10)
    else:
        df = xls.parse(xls.sheet_names[0])
        add_excel_frame(df, xls.sheet_names[0], file_path)

def merge_and_save():
    if not data_frames:
        messagebox.showinfo("提示", "尚未加入任何資料")
        return

    merged_df = pd.concat(list(data_frames.values()), ignore_index=True)
    merged_df.drop_duplicates(inplace=True)

    file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
    if file_path:
        merged_df.to_excel(file_path, index=False)
        messagebox.showinfo("完成", f"合併完成，檔案儲存於：\n{file_path}")

# 頂部按鈕列
btn_frame = tk.Frame(root)
btn_frame.pack(fill=tk.X, pady=5)

open_btn = tk.Button(btn_frame, text="📂 載入 Excel", command=open_excel)
open_btn.pack(side=tk.LEFT, padx=5)

merge_btn = tk.Button(btn_frame, text="📄 合併並儲存", command=merge_and_save)
merge_btn.pack(side=tk.LEFT, padx=5)

root.mainloop()
