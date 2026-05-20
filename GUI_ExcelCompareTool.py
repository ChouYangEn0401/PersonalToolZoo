import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
import pandas as pd
from openpyxl import load_workbook
import os
import random
from tkinterdnd2 import DND_FILES, TkinterDnD


# 顏色生成器
def get_distinct_color():
    base_colors = [
        "#FFCDD2", "#F8BBD0", "#E1BEE7", "#D1C4E9",
        "#C5CAE9", "#BBDEFB", "#B3E5FC", "#B2EBF2",
        "#B2DFDB", "#C8E6C9", "#DCEDC8", "#F0F4C3",
        "#FFF9C4", "#FFECB3", "#FFE0B2", "#FFCCBC"
    ]
    random.shuffle(base_colors)
    for color in base_colors:
        yield color


color_generator = get_distinct_color()

class ExcelTableFrame(tk.Frame):
    def __init__(self, parent, dataframe, filename, main_canvas, *args, **kwargs):
        super().__init__(parent, *args, relief=tk.RIDGE, bd=2, **kwargs)
        self.parent = parent
        self.filename = filename
        self.dataframe = dataframe
        self.main_canvas = main_canvas
        self.compare_cols = list(dataframe.columns)
        self.show_cols = []
        self.hide_cols = []
        self.status = tk.StringVar(value="ignore")  # main / sub / ignore
        self.bgcolor = next(color_generator)
        self.table_frames = []
        self.init_ui()

    def init_ui(self):
        header = tk.Frame(self)
        header.pack(fill=tk.X)
        tk.OptionMenu(header, self.status, "main", "sub", "ignore").pack(side=tk.LEFT)
        tk.Label(header, text=os.path.basename(self.filename), font=('Arial', 12, 'bold')).pack(side=tk.LEFT, padx=5)
        tk.Button(header, text="X", command=self.destroy, fg='red').pack(side=tk.RIGHT, padx=5)

        move_btns_controls = tk.Frame(self)
        move_btns_controls.pack(fill=tk.X)

        self.compare_list = self.create_listbox(move_btns_controls, "可比較欄位", self.compare_cols)
        self.compare_list.pack(side=tk.LEFT, padx=5)
        tk.Button(move_btns_controls, text=">> 不比較", command=self.not_to_compare).pack(side=tk.LEFT, padx=5)
        tk.Button(move_btns_controls, text="<< 比較", command=self.to_compare).pack(side=tk.LEFT, padx=5)
        self.show_list = self.create_listbox(move_btns_controls, "要顯示欄位", self.show_cols)
        self.show_list.pack(side=tk.LEFT, padx=5)
        tk.Button(move_btns_controls, text="> 不顯示", command=self.to_hide).pack(side=tk.LEFT, padx=5)
        tk.Button(move_btns_controls, text="< 顯示", command=self.to_show).pack(side=tk.LEFT, padx=5)
        self.hide_list = self.create_listbox(move_btns_controls, "不顯示欄位", self.hide_cols)
        self.hide_list.pack(side=tk.LEFT, padx=5)

        # ----------- 表格顯示區域 + Scrollable Canvas ------------
        scroll_container = tk.Frame(self)
        scroll_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(scroll_container, borderwidth=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vscroll = tk.Scrollbar(scroll_container, orient=tk.VERTICAL, command=self.canvas.yview)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.configure(yscrollcommand=vscroll.set)

        # 實際載入表格用的容器（會被 canvas 包起來）
        self.tables_area = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.tables_area, anchor="nw")

        # 滾動區域自動調整
        def on_configure(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.canvas.itemconfig(self.canvas_window, width=self.canvas.winfo_width())

        self.tables_area.bind("<Configure>", on_configure)

        # 滑鼠滾輪控制垂直捲動
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # 表格載入
        self.build_table_view()

    def create_listbox(self, parent, label_text, items):
        frame = tk.Frame(parent)
        frame.pack(side=tk.LEFT, padx=5)
        tk.Label(frame, text=label_text).pack()
        lb = tk.Listbox(frame, selectmode=tk.MULTIPLE, exportselection=False, height=10, width=20)
        lb.pack()
        for item in items:
            lb.insert(tk.END, item)
        return lb

    def update_lists(self):
        for lb in [self.compare_list, self.show_list, self.hide_list]:
            lb.delete(0, tk.END)
        for col in self.compare_cols:
            self.compare_list.insert(tk.END, col)
        for col in self.show_cols:
            self.show_list.insert(tk.END, col)
        for col in self.hide_cols:
            self.hide_list.insert(tk.END, col)

    def to_show(self):
        selected = [self.hide_list.get(i) for i in self.hide_list.curselection()]
        self.show_cols = [col for col in self.show_cols if col not in selected]
        self.show_cols.extend(selected)
        self.update_lists()

    def to_hide(self):
        selected = [self.show_list.get(i) for i in self.show_list.curselection()]
        self.show_cols = [col for col in self.show_cols if col not in selected]
        self.hide_cols.extend(selected)
        self.update_lists()

    def to_compare(self):
        selected = [self.show_list.get(i) for i in self.show_list.curselection()]
        self.compare_cols.extend(selected)
        self.hide_cols = [col for col in self.hide_cols if col not in selected]
        self.update_lists()

    def not_to_compare(self):
        selected = [self.compare_list.get(i) for i in self.compare_list.curselection()]
        self.compare_cols = [col for col in self.compare_cols if col not in selected]
        self.show_cols.extend(selected)
        self.update_lists()

    def build_table_view(self):
        # 單一表格的區塊（可以擴充放多個）
        container = tk.Frame(self.tables_area)
        container.pack(fill=tk.BOTH, expand=True, pady=5)

        # 捲軸
        vscroll = tk.Scrollbar(container, orient=tk.VERTICAL)
        hscroll = tk.Scrollbar(container, orient=tk.HORIZONTAL)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        # Treeview 表格
        tree = ttk.Treeview(
            container,
            columns=self.dataframe.columns.tolist(),
            show="headings",
            yscrollcommand=vscroll.set,
            xscrollcommand=hscroll.set
        )
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 綁定捲軸
        vscroll.config(command=tree.yview)
        hscroll.config(command=tree.xview)

        # 設定表頭欄位
        for col in self.dataframe.columns:
            tree.heading(col, text=col, anchor="w")
            tree.column(col, width=120, anchor="w", stretch=False)

        # 填入資料列
        for _, row in self.dataframe.iterrows():
            tree.insert("", tk.END, values=row.tolist())

        # 強制 Treeview 支援捲動（其實前面已設定）
        tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)


class DragDropFrame(tk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text="拖拉 Excel 檔案到這裡", width=400, height=100, bg='lightyellow')
        self.pack_propagate(False)
        self.pack(pady=10, padx=10, fill='x')

        self.label = tk.Label(self, text="拖拉 Excel 檔案到此區（或點我選擇）", bg='lightyellow')
        self.label.pack(expand=True)

        self.label.bind("<Button-1>", self.on_click)

        self.label.drop_target_register(DND_FILES)
        self.label.dnd_bind("<<Drop>>", self.on_drop)

    def on_click(self, event):
        filenames = filedialog.askopenfilenames(
            filetypes=[("Excel files", "*.xlsx *.xls")],
            parent=self
        )
        for filename in filenames:
            self.load_excel(filename)

    def on_drop(self, event):
        files = self.master.tk.splitlist(event.data)
        for filename in files:
            if filename.lower().endswith((".xls", ".xlsx")):
                self.load_excel(filename)

    def load_excel(self, filename):
        try:
            wb = load_workbook(filename=filename, read_only=True)
            sheets = wb.sheetnames
            SheetSelectPopup(self.master, filename, sheets)
        except Exception as e:
            messagebox.showerror("讀取錯誤", f"讀取檔案時發生錯誤：{e}")



class SheetSelectPopup(simpledialog.Dialog):
    def __init__(self, parent, filepath, sheetnames):
        self.filepath = filepath
        self.sheetnames = sheetnames
        self.selected_sheet = tk.StringVar()
        super().__init__(parent, title="選擇工作表")

    def body(self, master):
        tk.Label(master, text="請選擇要載入的工作表：").pack(padx=10, pady=10)
        self.dropdown = ttk.Combobox(master, textvariable=self.selected_sheet, values=self.sheetnames, state="readonly")
        self.dropdown.pack(padx=10)
        self.dropdown.current(0)
        return self.dropdown

    def apply(self):
        sheet = self.selected_sheet.get()
        try:
            df = pd.read_excel(self.filepath, sheet_name=sheet)
            print(f"[DEBUG] 讀取成功：{df.shape} 筆")  # 可移除
            self.parent.display_excel_table(df, self.filepath)
        except Exception as e:
            messagebox.showerror("讀取錯誤", f"無法讀取該工作表：{e}")


import tkinter as tk
from tkinter import ttk, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
import pandas as pd
import random


# 定義顏色生成器
def generate_color():
    return f"#{random.randint(0, 0xFFFFFF):06x}"


class ExcelComparatorApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Excel 表格比較工具")
        self.geometry("1400x800")
        self.table_frames = []
        self.result_df = None
        self.create_widgets()

    def create_widgets(self):
        self.drag_drop = DragDropFrame(self)

        # 比較按鈕區
        btns = tk.Frame(self)
        btns.pack(pady=5)
        tk.Button(btns, text="總顯示", command=self.show_all).pack(side=tk.LEFT, padx=3)
        tk.Button(btns, text="顯示交集", command=self.show_intersection).pack(side=tk.LEFT, padx=3)
        tk.Button(btns, text="主表-交集", command=self.show_main_minus).pack(side=tk.LEFT, padx=3)
        tk.Button(btns, text="附表-交集", command=self.show_sub_minus).pack(side=tk.LEFT, padx=3)
        tk.Button(btns, text="顯示聯集", command=self.show_union).pack(side=tk.LEFT, padx=3)
        tk.Button(btns, text="合併附表到主表", command=self.merge_subs).pack(side=tk.LEFT, padx=3)
        tk.Button(btns, text="匯出結果", command=self.export_result).pack(side=tk.LEFT, padx=3)

        # -------- 表格展示區，使用 Scrollable Canvas --------
        container = tk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(container)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.tables_area = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.tables_area, anchor="nw")

        def on_configure(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.canvas.itemconfig(self.canvas_window, width=self.canvas.winfo_width())

        self.tables_area.bind("<Configure>", on_configure)

        # ✅ 支援滑鼠滾輪捲動（Windows/macOS/Linux）
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))  # Windows/macOS
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))  # Linux 上滾
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))  # Linux 下滾

        # -------- 結果表格 --------
        self.result_label = tk.Label(self, text="比較結果：", font=('Arial', 12, 'bold'))
        self.result_label.pack()

        # 使用 Treeview 來顯示結果
        self.result_tree = ttk.Treeview(self, show="headings")
        self.result_tree.pack(fill=tk.BOTH, expand=True)

    def display_excel_table(self, df, filename):
        frame = ExcelTableFrame(self.tables_area, df, filename, self.canvas)
        frame.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)
        self.table_frames.append(frame)

    def get_main_table(self):
        mains = [t for t in self.table_frames if t.status.get() == "main"]
        if len(mains) != 1:
            messagebox.showerror("錯誤", "請選擇一份主表 (只能有一份)")
            return None
        return mains[0]

    def get_sub_tables(self):
        return [t for t in self.table_frames if t.status.get() == "sub"]

    def get_common_columns(self):
        tables = [t for t in self.table_frames if t.status.get() != "ignore"]
        if not tables:
            return []
        sets = [set(t.compare_cols) for t in tables]
        return list(set.intersection(*sets))

    def show_result(self, df, highlight=None):
        # 清空現有的 Treeview
        for col in self.result_tree["columns"]:
            self.result_tree.heading(col, text=col)
        for row in self.result_tree.get_children():
            self.result_tree.delete(row)

        if df is None or df.empty:
            messagebox.showinfo("提示", "沒有結果")
            return

        self.result_df = df

        # 插入資料
        for idx, row in df.iterrows():
            tags = []
            values = list(row)
            if highlight:
                tags = [highlight.get(f"I{idx}", "default")]
            self.result_tree.insert("", "end", values=values, tags=tags)

        # 設定顏色
        self.apply_colors()

    def apply_colors(self):
        # 設定標題列顏色
        self.result_tree.tag_configure("default", background="white")
        self.result_tree.tag_configure("intersect", background="lightgreen")
        self.result_tree.tag_configure("main", background="lightblue")
        self.result_tree.tag_configure("sub", background="lightyellow")

        # 設定行顏色
        for idx, row in self.result_df.iterrows():
            tag = "default"
            if row.get("_merge") == "both":
                tag = "intersect"
            elif row.get("_merge") == "left_only":
                tag = "main"
            elif row.get("_merge") == "right_only":
                tag = "sub"
            self.result_tree.item(self.result_tree.get_children()[idx], tags=(tag,))

    def show_all(self):
        main = self.get_main_table()
        if not main:
            return
        df = main.dataframe[main.compare_cols]
        self.show_result(df)

    def show_intersection(self):
        main = self.get_main_table()
        subs = self.get_sub_tables()
        if not main or not subs:
            return
        common_cols = self.get_common_columns()
        main_df = main.dataframe[common_cols]
        result_df = main_df.copy()
        for sub in subs:
            sub_df = sub.dataframe[common_cols]
            result_df = pd.merge(result_df, sub_df)
        self.show_result(result_df)

    def show_main_minus(self):
        main = self.get_main_table()
        subs = self.get_sub_tables()
        if not main or not subs:
            return
        common_cols = self.get_common_columns()
        main_df = main.dataframe[common_cols]
        union_subs = pd.concat([s.dataframe[common_cols] for s in subs])
        result = pd.merge(main_df, union_subs, how='outer', indicator=True)
        result_df = result[result['_merge'] == 'left_only'].drop(columns=['_merge'])
        result_df["_merge"] = "left_only"
        self.show_result(result_df)


    def show_sub_minus(self):
        main = self.get_main_table()
        subs = self.get_sub_tables()
        if not main or not subs:
            return
        common_cols = self.get_common_columns()
        main_df = main.dataframe[common_cols]
        union_subs = pd.concat([s.dataframe[common_cols] for s in subs])
        result = pd.merge(union_subs, main_df, how='outer', indicator=True)
        result_df = result[result['_merge'] == 'left_only'].drop(columns=['_merge'])
        result_df["_merge"] = "right_only"
        self.show_result(result_df)


    def show_union(self):
        tables = [t for t in self.table_frames if t.status.get() != "ignore"]
        if not tables:
            return
        common_cols = self.get_common_columns()
        union_df = pd.concat([t.dataframe[common_cols] for t in tables])
        self.show_result(union_df)


    def merge_subs(self):
        main = self.get_main_table()
        subs = self.get_sub_tables()
        if not main or not subs:
            return
        common_cols = self.get_common_columns()
        main_df = main.dataframe[common_cols]
        subs_df = pd.concat([s.dataframe[common_cols] for s in subs])
        combined = pd.concat([main_df, subs_df])
        self.show_result(combined)


    def export_result(self):
        if self.result_df is None:
            messagebox.showinfo("提示", "沒有結果可以匯出")
            return
        filepath = tk.filedialog.asksaveasfilename(defaultextension=".xlsx")
        if filepath:
            self.result_df.to_excel(filepath, index=False)
            messagebox.showinfo("完成", f"結果已匯出至 {filepath}")


if __name__ == "__main__":
    app = ExcelComparatorApp()
    app.mainloop()

"""
我想要比較兩份表格之間的差異，能不能給我一篇gui python code。
我希望把excel拉進去tkinter視窗裡面的檔案拖拉frame(要變色處理一下)，然後，接下來掉一個popup，讓我選要載入的sheet。
接著就會把excel載入在下方的一個表格空間裡面。(顯格顯示器，要有水平垂直拉把可瀏覽全部)。
然後，我拉入幾個檔案，就會有幾個表格顯示器，分別顯示我選擇載入那些檔案。

然後接下來我就會希望你來幫我做點有趣的事情。
1. 我希望每個表格旁邊有一個list顯示所有column，如果之後某欄位參加比較就留在這裡，如果不要可以用一個按鈕把她加入下一個list，表示會顯示的欄位，然後如果某些欄位也不想顯示，可以把牠們放進去最後一個list裡面。所以等於每個筆格顯示器上面都會有這三個list幫忙控制這一份excel檔。然後可以透過按鈕來做到">右移""<左移"道不同list。
2. 美個表格顯示區會有一個"X"，如果按錯檔案，可以刪除表單(不是刪檔案喔)。然後也有一個選擇器可以選"此作為主表"、"此作為附表"、"不參與比較"的選擇區。"主表"只能有一張，表示以他為主，其他人跟他比。"附表"可以多張用來多重比較"。"不參與比較"就比較的時候不管他。
3. 接下來說說按鈕清單。按鈕清單裡面有用來比較的各種方式"總顯示"、"顯示交集"、"顯示主表-交集"、"顯示附表-交集"、"顯示聯集"、"合併附表到主表"。
4. 然後為了讓我方便檢查，執行這些動作以後當然要顯示在一個結果表區，顯示"動作的結果"，每次執行新動作就會更新。然後這裡尤為重要。因為我可能戶很多表格進行比較，因此我會希望有顏色區別。主表在顯示區要以"淡藍色底色"顯示，"交集部分"要以"淡綠色底色"顯示。附表隨機即可，但顏色不要彼此重複。然後column也要注意header，"交集部分"以"綠色粗體"顯示，"主表欄位"以"藍色顯示"，其他也一樣隨機即可，不要重複。那當然是，每張表自己同色。那有些模式可能某些東西不顯示，那自然就不用顯示，但顏色規則一樣不可混。然後雖然我說隨機，但還是會希望以紅色系列為主。
5. 最後讓我可以匯出結果表按鈕。
"""
