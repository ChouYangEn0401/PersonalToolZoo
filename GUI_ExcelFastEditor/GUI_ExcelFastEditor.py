import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import pandas as pd
import threading
import time


class ExcelEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel 編輯 GUI 小工具 v1")
        self.df = pd.DataFrame()
        self.sort_vars = {}

        self.build_ui()

    def create_buttons(self, frame):
        # 這是你的按鈕列表
        buttons = [
            ("讀取 Excel", self.load_excel),
            ("合併資料表", self.merge_or_append_data),
            ("根據另一份資料刪除資料", self.remove_rows_by_reference),
            ("刪除重複列", self.remove_duplicate_rows),
            ("刪除欄位", self.delete_columns),
            ("刪除全為 NaN 的欄位", self.delete_all_nan_columns),
            ("刪除全為 NaN 的列", self.delete_all_nan_rows),
            ("刪除某欄為 NaN 的列", self.delete_rows_with_nan_in_column),
            ("重新命名欄位", self.rename_columns),
            ("欄位重新排序", self.reorder_columns),
            ("特定欄位條件去重", self.group_and_filter),
            ("兩欄位比對重複值，顯示結果", self.compare_columns),
            ("檢查某欄位重複值，顯示結果", self.find_duplicates_in_column),
            ("儲存檔案", self.save_excel),
        ]
        for text, command in buttons:
            tk.Button(frame, text=text, command=command).pack(side=tk.LEFT)

    def build_button_frame(self, parent_frame):
        # 建立外層 Frame 裝載 Canvas 和 Scrollbar
        outer_frame = tk.Frame(parent_frame)
        outer_frame.pack(fill=tk.X, expand=True)

        # 建立 Canvas 來支持滾動
        self.canvas = tk.Canvas(outer_frame, height=50)
        self.canvas.pack(side=tk.TOP, fill=tk.X, expand=True)

        # 建立 Scrollbar 並與 Canvas 關聯（注意：父層是 outer_frame）
        self.scrollbar = tk.Scrollbar(outer_frame, orient="horizontal", command=self.canvas.xview)
        self.scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.configure(xscrollcommand=self.scrollbar.set)

        # 建立 Frame 並放進 Canvas 中
        self.button_frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.button_frame, anchor="nw")

        # 加入所有按鈕
        self.create_buttons(self.button_frame)

        # 更新 scrollregion
        self.button_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def build_ui(self):
        # 主架構劃分：上 = 按鈕區, 中 = 表格+排序控制, 下 = 狀態列 + 進度條
        # 上方功能列（你覺得不美但先保留 XD）
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        self.build_button_frame(top_frame)

        # 中央主區塊（表格區 + 排序區）
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 表格區：使用 Canvas 以支援 Scrollable Frame
        table_container = tk.Frame(main_frame)
        table_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(table_container)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scroll_y = tk.Scrollbar(table_container, orient="vertical", command=self.canvas.yview)
        self.scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.scroll_x = tk.Scrollbar(self.root, orient="horizontal", command=self.canvas.xview)
        self.scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)
        self.canvas.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.table_frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.table_frame, anchor="nw")

        self.table = None

        # 右側排序區（佔 1/4）
        self.sort_panel = tk.Frame(main_frame, padx=10, pady=10, relief=tk.RIDGE, bd=2)
        self.sort_panel.pack(side=tk.RIGHT, fill=tk.Y)
        tk.Label(self.sort_panel, text="排序控制", font=("Arial", 12, "bold")).pack()

        self.sort_controls_frame = tk.Frame(self.sort_panel)
        self.sort_controls_frame.pack(fill=tk.Y, expand=True)
        tk.Button(self.sort_panel, text="套用排序", command=self.apply_sort).pack(pady=10)

        # 底部狀態列（顯示維度 + 進度條）
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_label = tk.Label(bottom_frame, text="📐 表格尺寸：0 x 0")
        self.status_label.pack(side=tk.LEFT, padx=10)

        self.progress = ttk.Progressbar(bottom_frame, mode='determinate', length=300)
        self.progress.pack(side=tk.RIGHT, padx=10, pady=5, fill=tk.X, expand=True)


    def delete_all_nan_columns(self):
        before_cols = self.df.shape[1]
        self.df.dropna(axis=1, how='all', inplace=True)
        after_cols = self.df.shape[1]
        self.refresh_table()
        messagebox.showinfo("完成", f"已刪除 {before_cols - after_cols} 個全為 NaN 的欄位。")

    def delete_all_nan_rows(self):
        before_rows = self.df.shape[0]
        self.df.dropna(axis=0, how='all', inplace=True)
        after_rows = self.df.shape[0]
        self.refresh_table()
        messagebox.showinfo("完成", f"已刪除 {before_rows - after_rows} 筆全為 NaN 的資料列。")

    def delete_rows_with_nan_in_column(self):
        if self.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        col = self.simple_select("選擇欄位", list(self.df.columns))
        if not col:
            return

        before_rows = self.df.shape[0]
        self.df = self.df[self.df[col].notna()]
        after_rows = self.df.shape[0]
        self.refresh_table()
        messagebox.showinfo("完成", f"已刪除 {before_rows - after_rows} 筆「{col}」欄位為 NaN 的列。")

    def set_progress(self, value=None, indeterminate=False):
        if indeterminate:
            self.progress.config(mode='indeterminate')
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.config(mode='determinate')
            if value is not None:
                self.progress["value"] = value
            else:
                self.progress["value"] = 0
        self.root.update_idletasks()

    def update_status(self):
        rows, cols = self.df.shape
        self.status_label.config(text=f"📐 表格尺寸：{rows} x {cols}")

    def _show_table(self, df, title, summary_text):
        self.last_checked_df = df  # 用來記錄最後檢查的結果

        win = tk.Toplevel(self.root)
        win.title(title)

        summary_label = tk.Label(win, text=summary_text, justify="left", font=("Arial", 11), fg="blue")
        summary_label.pack(anchor="w", padx=10, pady=5)

        frame = tk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(frame, columns=list(df.columns), show="headings")
        tree.pack(fill=tk.BOTH, expand=True)

        sort_state = {"col": None, "reverse": False}

        def sort_by(col):
            reverse = not (sort_state["col"] == col and not sort_state["reverse"])
            sort_state["col"] = col
            sort_state["reverse"] = reverse
            sorted_df = df.sort_values(by=col, ascending=not reverse)
            rebuild_tree(sorted_df)

        def rebuild_tree(df_to_show):
            for i in tree.get_children():
                tree.delete(i)
            for row in df_to_show.itertuples(index=False):
                tree.insert("", "end", values=row)

        for col in df.columns:
            tree.heading(col, text=col, command=lambda c=col: sort_by(c))
            tree.column(col, width=120, anchor=tk.W)

        rebuild_tree(df)

        # 加入儲存和刪除按鈕
        button_frame = tk.Frame(win)
        button_frame.pack(pady=5)

        def save_checked():
            save_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
            if save_path:
                df.to_excel(save_path, index=False)
                messagebox.showinfo("儲存成功", f"已儲存至 {save_path}")

        def remove_from_raw():
            if "原始索引" in df.columns:
                idx_to_remove = df["原始索引"].tolist()
                self.df.drop(index=idx_to_remove, inplace=True)
                self.refresh_table()
                messagebox.showinfo("已刪除", "已從原始資料中刪除顯示的列。")
                win.destroy()
            else:
                messagebox.showwarning("錯誤", "找不到原始索引，無法刪除。")

        tk.Button(button_frame, text="💾 儲存這些資料", command=save_checked).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="🗑 從原始資料刪除這些列", command=remove_from_raw).pack(side=tk.LEFT, padx=5)

        # 垂直滾動條
        ysb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscroll=ysb.set)

    def find_duplicates_in_column(self):
        if self.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        # 選擇要檢查重複的欄位
        col = self.simple_select("選擇要檢查重複值的欄位", list(self.df.columns))
        if not col:
            return

        # 讓使用者決定要顯示 重複 或 不重複
        option = self.simple_select("選擇要顯示的資料", ["重複的", "不重複的"])
        dup_mask = self.df.duplicated(subset=[col], keep=False)

        if option == "重複的":
            target_rows = self.df[dup_mask].copy()
            label = "重複的"
        else:
            target_rows = self.df[~dup_mask].copy()
            label = "不重複的"

        # 加入原始索引
        target_rows.insert(0, "原始索引", target_rows.index)

        # 統計
        total = len(self.df)
        count = len(target_rows)
        percentage = round((count / total) * 100, 2) if total > 0 else 0

        summary = f"🔍 檢查欄位：{col}\n📄 顯示筆數：{count} / {total} 筆\n📊 佔比：{percentage}%"
        self._show_table(target_rows, f"{col} 欄位中 {label} 的資料列", summary)

    def compare_columns(self):
        if self.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        # 選擇要比對的兩個欄位
        selected = self.simple_select_multiple("選擇兩個欄位進行比對", list(self.df.columns))
        if len(selected) != 2:
            messagebox.showerror("錯誤", "請選擇恰好兩個欄位。")
            return

        col1, col2 = selected

        # 比對欄位
        comparison_result = self.df[col1] == self.df[col2]

        # 讓使用者決定要看 相同 還是 不同
        option = self.simple_select("選擇要顯示的資料", ["相同", "不同"])
        if option == "相同":
            target_rows = self.df[comparison_result].copy()
            match_type = "相同"
        else:
            target_rows = self.df[~comparison_result].copy()
            match_type = "不同"

        # 原始索引儲存下來
        target_rows.insert(0, "原始索引", target_rows.index)

        # 統計資訊
        total = len(self.df)
        count = len(target_rows)
        percentage = round((count / total) * 100, 2) if total > 0 else 0

        summary = f"🔍 比對欄位：{col1} vs {col2}\n📄 顯示筆數：{count} / {total} 筆\n📊 佔比：{percentage}%"
        title = f"欄位 {col1} 與 {col2} {match_type} 的列"
        self._show_table(target_rows, title, summary)


    def refresh_table(self):
        if self.table:
            self.table.destroy()

        self.table = ttk.Treeview(self.table_frame, columns=list(self.df.columns), show="headings")
        for col in self.df.columns:
            self.table.heading(col, text=col)
            self.table.column(col, width=100, anchor=tk.W)

        for row in self.df.itertuples(index=False):
            self.table.insert("", "end", values=row)

        self.table.pack(fill=tk.BOTH, expand=True)
        self.table_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

        self.build_sort_controls()
        self.update_status()

    def build_sort_controls(self):
        for widget in self.sort_controls_frame.winfo_children():
            widget.destroy()
        self.sort_vars.clear()
        options = ["無排序", "A → Z", "Z → A"]
        for col in self.df.columns:
            row = tk.Frame(self.sort_controls_frame)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=col, width=15, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value="無排序")
            ttk.Combobox(row, values=options, textvariable=var, state="readonly", width=8).pack(side=tk.RIGHT)
            self.sort_vars[col] = var

    def apply_sort(self):
        sort_columns, ascending = [], []
        for col, var in self.sort_vars.items():
            val = var.get()
            if val == "A → Z":
                sort_columns.append(col)
                ascending.append(True)
            elif val == "Z → A":
                sort_columns.append(col)
                ascending.append(False)

        if sort_columns:
            try:
                self.set_progress(indeterminate=True)
                self.df.sort_values(by=sort_columns, ascending=ascending, inplace=True, ignore_index=True)
                self.refresh_table()
            finally:
                self.set_progress(0)

    def threaded_load(self, path):
        self.set_progress(indeterminate=True)
        self.df = self.read_excel_with_sheet(path)
        self.refresh_table()
        self.set_progress(0)

    def load_excel(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if file_path:
            threading.Thread(target=self.threaded_load, args=(file_path,), daemon=True).start()

    def read_excel_with_sheet(self, path):
        xls = pd.ExcelFile(path)
        if len(xls.sheet_names) == 1:
            return pd.read_excel(xls, sheet_name=0)
        selected = self.simple_select("選擇工作表", xls.sheet_names)
        return pd.read_excel(xls, sheet_name=selected)

    def delete_columns(self):
        cols = self.simple_select_multiple("選擇要刪除的欄位", list(self.df.columns))
        if cols:
            self.df.drop(columns=cols, inplace=True)
            self.refresh_table()

    def rename_columns(self):
        cols = self.simple_select_multiple("選擇要重新命名的欄位", list(self.df.columns))
        if not cols:
            return
        new_names = {}
        for col in cols:
            new_name = self.simple_input(f"為「{col}」輸入新名稱", default=col)
            if new_name:
                new_names[col] = new_name
        if new_names:
            self.df.rename(columns=new_names, inplace=True)
            self.refresh_table()

    def remove_rows_by_reference(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if not path:
            return

        df2 = self.read_excel_with_sheet(path)

        # 使用者選擇比對模式
        mode = self.simple_select("選擇比對刪除模式", [
            "整列完全相同 - 刪除",
            "指定欄位相同 - 刪除"
        ])

        if mode == "整列完全相同 - 刪除":
            merged = self.df.merge(df2, how="left", indicator=True)
            self.df = merged[merged["_merge"] == "left_only"].drop(columns="_merge")
            messagebox.showinfo("完成", "已刪除與另一份資料完全相同的列。")

        elif mode == "指定欄位相同 - 刪除":
            # 選擇用來比對的欄位
            common_cols = set(self.df.columns).intersection(set(df2.columns))
            if not common_cols:
                messagebox.showerror("錯誤", "兩份資料沒有共同欄位可比對。")
                return

            subset_cols = self.simple_select_multiple("選擇比對欄位", list(common_cols))
            if not subset_cols:
                return

            df_filtered = self.df.merge(df2[subset_cols].drop_duplicates(),
                                        on=subset_cols,
                                        how="left",
                                        indicator=True)
            self.df = df_filtered[df_filtered["_merge"] == "left_only"].drop(columns="_merge")
            messagebox.showinfo("完成", f"已刪除欄位 {', '.join(subset_cols)} 相同的列。")

        self.refresh_table()


    def merge_or_append_data(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if not path:
            return

        try:
            df2 = self.read_excel_with_sheet(path)

            # 模式選擇
            mode_options = [
                "左合併 (left-merge)：以主資料為主，合併有對應值的資料",
                "右合併 (right-merge)：以合併資料為主，主資料中有對應才會合併",
                "內合併 (inner-merge)：只保留雙方都對得上的資料列",
                "外合併 (outer-merge)：保留所有資料，對不上的以 NaN 填補",
                "直接附加 (append)：兩張表直接上下合併（欄位需一致）",
                "左附加 (left-append)：以主資料欄位為主，其他欄位捨棄",
                "右附加 (right-append)：以合併資料欄位為主，補上缺的欄位",
                "內附加 (inner-append)：只附加雙方欄位相同的資料",
                "外附加 (outer-append)：合併所有欄位，不存在的補 NaN",
            ]

            selected_mode = self.simple_select("選擇合併或附加模式", mode_options)

            if selected_mode.startswith("左合併"):
                key1 = self.simple_select("主資料的對應欄位", list(self.df.columns))
                key2 = self.simple_select("合併資料的對應欄位", list(df2.columns))
                self.set_progress(indeterminate=True)
                self.df = pd.merge(self.df, df2, left_on=key1, right_on=key2, how="left")
                self.clean_merged_columns(key1, key2)

            elif selected_mode.startswith("右合併"):
                key1 = self.simple_select("主資料的對應欄位", list(self.df.columns))
                key2 = self.simple_select("合併資料的對應欄位", list(df2.columns))
                self.set_progress(indeterminate=True)
                self.df = pd.merge(self.df, df2, left_on=key1, right_on=key2, how="right")
                self.clean_merged_columns(key1, key2)

            elif selected_mode.startswith("內合併"):
                key1 = self.simple_select("主資料的對應欄位", list(self.df.columns))
                key2 = self.simple_select("合併資料的對應欄位", list(df2.columns))
                self.set_progress(indeterminate=True)
                self.df = pd.merge(self.df, df2, left_on=key1, right_on=key2, how="inner")
                self.clean_merged_columns(key1, key2)

            elif selected_mode.startswith("外合併"):
                key1 = self.simple_select("主資料的對應欄位", list(self.df.columns))
                key2 = self.simple_select("合併資料的對應欄位", list(df2.columns))
                self.set_progress(indeterminate=True)
                self.df = pd.merge(self.df, df2, left_on=key1, right_on=key2, how="outer")
                self.clean_merged_columns(key1, key2)

            elif selected_mode.startswith("直接附加"):
                self.set_progress(indeterminate=True)
                self.df = pd.concat([self.df, df2], ignore_index=True)

            elif selected_mode.startswith("左附加"):
                df2_trimmed = df2[self.df.columns.intersection(df2.columns)]
                self.df = pd.concat([self.df, df2_trimmed], ignore_index=True)

            elif selected_mode.startswith("右附加"):
                for col in df2.columns:
                    if col not in self.df.columns:
                        self.df[col] = None
                self.df = pd.concat([self.df, df2], ignore_index=True)

            elif selected_mode.startswith("內附加"):
                common_cols = list(set(self.df.columns) & set(df2.columns))
                self.df = pd.concat([self.df[common_cols], df2[common_cols]], ignore_index=True)

            elif selected_mode.startswith("外附加"):
                self.df = pd.concat([self.df, df2], ignore_index=True, sort=False)

            self.refresh_table()

        finally:
            self.set_progress(0)

    def clean_merged_columns(self, left_on, right_on):
        # 清除合併後多餘的欄位
        if f"{right_on}_x" in self.df.columns:
            self.df.drop(columns=[f"{right_on}_x"], inplace=True)
        if f"{right_on}_y" in self.df.columns:
            self.df.drop(columns=[f"{right_on}_y"], inplace=True)

    def remove_duplicate_rows(self):
        # 檢查是否有重複的行
        if self.df.duplicated().any():
            # 刪除重複的行，只保留第一次出現的行
            self.df.drop_duplicates(inplace=True)
            # 更新顯示
            self.refresh_table()
            messagebox.showinfo("訊息", "重複的列已刪除。")
        else:
            messagebox.showinfo("訊息", "沒有發現重複的列。")

    def reorder_columns(self):
        # 創建新視窗
        top_frame = tk.Toplevel(self.root)
        top_frame.title("欄位重新排序")

        # 顯示當前所有欄位
        columns = list(self.df.columns)

        # 創建Listbox顯示欄位順序
        listbox = tk.Listbox(top_frame, selectmode=tk.SINGLE)
        for column in columns:
            listbox.insert(tk.END, column)
        listbox.pack(padx=10, pady=10)

        # 添加"向上"和"向下"按鈕來移動欄位
        def move_up():
            try:
                selected_index = listbox.curselection()[0]
                if selected_index > 0:
                    item = listbox.get(selected_index)
                    listbox.delete(selected_index)
                    listbox.insert(selected_index - 1, item)
                    listbox.select_set(selected_index - 1)
            except IndexError:
                pass

        def move_down():
            try:
                selected_index = listbox.curselection()[0]
                if selected_index < len(columns) - 1:
                    item = listbox.get(selected_index)
                    listbox.delete(selected_index)
                    listbox.insert(selected_index + 1, item)
                    listbox.select_set(selected_index + 1)
            except IndexError:
                pass

        # 向上按鈕
        up_button = tk.Button(top_frame, text="向上", command=move_up)
        up_button.pack(side=tk.LEFT, padx=10, pady=5)

        # 向下按鈕
        down_button = tk.Button(top_frame, text="向下", command=move_down)
        down_button.pack(side=tk.LEFT, padx=10, pady=5)

        # 確定按鈕
        def confirm():
            # 獲取調整後的順序
            new_order = [listbox.get(i) for i in range(len(columns))]
            # 根據新的順序重新排列 DataFrame
            self.df = self.df[new_order]
            self.refresh_table()  # 更新顯示
            messagebox.showinfo("訊息", "欄位順序已更新。")
            top_frame.destroy()  # 關閉視窗

        confirm_button = tk.Button(top_frame, text="確定", command=confirm)
        confirm_button.pack(side=tk.LEFT, padx=10, pady=5)

    def group_and_filter(self):
        # 選擇要進行去重的欄位 X
        col_to_deduplicate = self.simple_select("選擇要進行去重的欄位", list(self.df.columns))
        if not col_to_deduplicate:
            return

        # 讓使用者選擇要依照哪些欄位進行條件篩選
        group_cols = self.simple_select_multiple("選擇要依據條件篩選的欄位", list(self.df.columns))
        if not group_cols:
            return

        # 設置條件篩選規則
        conditions = []
        for col in group_cols:
            condition = self.simple_select(f"選擇 {col} 欄位的篩選條件",
                                           ["大於", "小於", "等於", "最大值", "最小值", "True/False", "特定字"])
            conditions.append((col, condition))

        # 遍歷選擇的條件，對資料進行篩選
        filtered_df = self.df.copy()  # 保存原始資料
        for col, condition in conditions:
            if condition == "大於":
                value = self.simple_input(f"輸入 {col} 欄位要篩選的大於值")
                self.df = self.df[self.df[col] > float(value)]
            elif condition == "小於":
                value = self.simple_input(f"輸入 {col} 欄位要篩選的小於值")
                self.df = self.df[self.df[col] < float(value)]
            elif condition == "等於":
                value = self.simple_input(f"輸入 {col} 欄位要篩選的值")
                self.df = self.df[self.df[col] == value]
            elif condition == "最大值":
                max_value = self.df[col].max()
                self.df = self.df[self.df[col] == max_value]
            elif condition == "最小值":
                min_value = self.df[col].min()
                self.df = self.df[self.df[col] == min_value]
            elif condition == "True/False":
                value = self.simple_select("選擇 True 或 False", ["True", "False"])
                self.df = self.df[self.df[col] == (value == "True")]
            elif condition == "特定字":
                value = self.simple_input(f"輸入 {col} 欄位要篩選的特定字")
                self.df = self.df[self.df[col].str.contains(value, na=False)]

        # 計算哪些資料被丟掉
        dropped_rows = filtered_df[~filtered_df.index.isin(self.df.index)]

        # 儲存被丟掉的資料到檔案
        if not dropped_rows.empty:
            dropped_rows.to_excel("dropped_data.xlsx", index=False)

        # 根據選擇的欄位進行分組，對每組內資料進行處理
        self.df = self.df.groupby(col_to_deduplicate).apply(self.custom_deduplicate_logic, group_cols)

        # 更新表格顯示
        self.refresh_table()

        # 顯示完成通知
        messagebox.showinfo("操作完成", "資料處理完成，丟掉的資料已儲存至 dropped_data.xlsx 檔案中。")

    def custom_deduplicate_logic(self, group, group_cols):
        """
        自定義的去重邏輯，根據指定的條件來處理每個小組。
        假設每個小組會根據 `group_cols` 中的欄位來進行去重
        """
        for col in group_cols:
            condition = self.simple_select(f"選擇 {col} 欄位的處理方式", ["最大值", "最小值"])
            if condition == "最大值":
                group = group[group[col] == group[col].max()]
            elif condition == "最小值":
                group = group[group[col] == group[col].min()]
        return group

    def save_excel(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if file_path:
            self.df.to_excel(file_path, index=False)
            messagebox.showinfo("儲存成功", f"檔案已儲存至 {file_path}")

    def simple_input(self, prompt, default=""):
        return simpledialog.askstring("輸入", prompt, initialvalue=default)

    def simple_select(self, title, options):
        win = tk.Toplevel(self.root)
        win.title(title)

        var = tk.StringVar(value=options[0])
        max_width = max(len(s) for s in options)
        dropdown = ttk.Combobox(win, textvariable=var, values=options, width=max_width*2)
        dropdown.pack(padx=10, pady=10)

        def confirm():
            win.selected = var.get()
            win.destroy()

        tk.Button(win, text="確定", command=confirm).pack(pady=5)
        self.root.wait_window(win)
        return getattr(win, 'selected', None)

    def simple_select_multiple(self, prompt, options):
        win = tk.Toplevel(self.root)
        win.title(prompt)
        tk.Label(win, text=prompt).pack(padx=10, pady=10)

        # 創建 Listbox 控件並插入選項
        listbox = tk.Listbox(win, selectmode=tk.MULTIPLE)
        for option in options:
            listbox.insert(tk.END, option)
        listbox.pack(padx=10, pady=5)

        # 用來保存選擇的項目
        selected_items = []

        # 定義 submit 函數
        def submit():
            nonlocal selected_items
            try:
                # 確保 Listbox 控件存在且有效
                if not listbox.winfo_exists():
                    raise ValueError("Listbox 已經不存在")

                # 確保選擇項目有效
                selected_items = [listbox.get(i) for i in listbox.curselection()]

                # 關閉視窗
                win.destroy()
            except Exception as e:
                print(f"出現錯誤: {e}")
                messagebox.showerror("錯誤", "無法取得選擇項目，請確保 Listbox 仍然有效。")
                win.destroy()  # 關閉視窗

        # 創建確定按鈕並綁定 submit
        tk.Button(win, text="確定", command=submit).pack(pady=5)

        win.grab_set()  # 使視窗成為模態
        win.wait_window()  # 等待視窗關閉

        # 返回選擇的項目
        return selected_items


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1400x800")
    app = ExcelEditor(root)
    root.mainloop()
