import tkinter as tk
from sre_parse import State
from tkinter import ttk, filedialog
import pandas as pd
from tkinter import messagebox
import webbrowser


class ExcelComparer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Excel 字串比對工具")

        self.df = None
        self.checked_items = {}
        self.grouped_colors = {}
        self.a_column = None
        self.processed_df = pd.DataFrame() # 儲存已處理的完整資料
        self.processed_a_values = set() # 追蹤"打勾勾選項" 的 A 欄位值
        self.rejected_a_values = set() # 追蹤"叉叉選項" 的 A 欄位值

        self.tree1_font_size = 10 # 初始字體大小
        self.tree1_row_height = None # 初始行高 (由字體大小決定)

        self.create_widgets()

    def create_widgets(self):
        # 按鈕區
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=5)

        self.load_button = ttk.Button(button_frame, text="讀取 Excel", command=self.load_excel)
        self.load_button.pack(side=tk.LEFT, padx=5)

        self.save_button = ttk.Button(button_frame, text="存檔", command=self.show_save_options)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.run_button = ttk.Button(button_frame, text="執行操作", command=self.run_selection)
        self.run_button.pack(side=tk.LEFT, padx=5)

        self.redo_button = ttk.Button(button_frame, text="撤銷操作", command=self.redo_selection)
        self.redo_button.pack(side=tk.LEFT, padx=5)

        self.export_button = ttk.Button(button_frame, text="輸出", command=self.export_data)
        self.export_button.pack(side=tk.LEFT, padx=5)

        self.zoom_in_button = ttk.Button(button_frame, text="放大 Treeview1", command=self.zoom_in_tree1)
        self.zoom_in_button.pack(side=tk.LEFT, padx=5)
        self.zoom_out_button = ttk.Button(button_frame, text="縮小 Treeview1", command=self.zoom_out_tree1)
        self.zoom_out_button.pack(side=tk.LEFT, padx=5)

        # 選擇 A 欄位
        a_column_frame = ttk.Frame(self)
        a_column_frame.pack(pady=5)
        ttk.Label(a_column_frame, text="選擇 A 欄位:").pack(side=tk.LEFT)
        self.a_column_combo = ttk.Combobox(a_column_frame, state="readonly")
        self.a_column_combo.pack(side=tk.LEFT, padx=5)
        self.a_column_combo.bind("<<ComboboxSelected>>", self.group_by_a_column)
        # 選擇搜尋欄位
        self.search_col_index = -1  ## prevent null error
        search_column_frame = ttk.Frame(self)
        search_column_frame.pack(pady=5)
        ttk.Label(search_column_frame, text="選擇搜尋欄位:").pack(side=tk.LEFT)
        self.search_column_combo = ttk.Combobox(search_column_frame, state="readonly")
        self.search_column_combo.pack(side=tk.LEFT, padx=5)
        self.search_column_combo.bind("<<ComboboxSelected>>", self.set_search_column)

        # 上方 Treeview (原始資料)
        self.tree1_frame = ttk.Frame(self)
        self.tree1_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        self.tree1_scrollbar_y = ttk.Scrollbar(self.tree1_frame, orient="vertical")
        self.tree1_style = ttk.Style()
        self.tree1_style.configure("Treeview1.Treeview", font=('TkDefaultFont', self.tree1_font_size))
        self.tree1 = ttk.Treeview(self.tree1_frame, yscrollcommand=self.tree1_scrollbar_y.set, style="Treeview1.Treeview")
        self.tree1_scrollbar_y.config(command=self.tree1.yview)
        self.tree1_scrollbar_y.pack(side="right", fill="y")
        self.tree1.pack(side="left", fill="both", expand=True)
        self.tree1.bind("<Button-1>", self.on_tree1_click)
        self.tree1.bind("<Button-1>", self.sort_column, add='+') # 綁定排序事件
        self.shown_row_indexes = 0
        self.hidden_row_indexes = []

        # 狀態顯示
        self.status_label = ttk.Label(self, text="")
        self.status_label.pack(pady=5)

        # 下方 Treeview (已處理資料) 和欄位選擇區
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(pady=10, fill=tk.BOTH, expand=True, side=tk.LEFT)  # 靠左

        # 下方 Treeview
        self.tree2_frame = ttk.Frame(bottom_frame)
        self.tree2_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=2) # 垂直方向縮小 padding
        self.tree2_scrollbar_y = ttk.Scrollbar(self.tree2_frame, orient="vertical")
        self.tree2_style = ttk.Style()
        self.tree2 = ttk.Treeview(self.tree2_frame, yscrollcommand=self.tree2_scrollbar_y.set, style="Treeview2.Treeview") # 可以為 treeview2 設定不同樣式
        self.tree2_scrollbar_y.config(command=self.tree2.yview)
        self.tree2_scrollbar_y.pack(side="right", fill="y")
        self.tree2.pack(side="left", fill="both", expand=True)

        # 欄位選擇列表和按鈕
        list_frame = ttk.Frame(bottom_frame, width=150)
        list_frame.pack(side=tk.LEFT, padx=10, fill=tk.Y, pady=2) # 垂直方向縮小 padding

        ttk.Label(list_frame, text="所有欄位").pack(pady=2)
        self.available_columns_list = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, height=10)
        self.available_columns_list.pack(fill=tk.X, pady=2)

        button_list_frame = ttk.Frame(list_frame)
        button_list_frame.pack(pady=5)
        ttk.Button(button_list_frame, text="加入欄位", command=self.add_column_to_tree2).pack(fill=tk.X, pady=2)
        ttk.Button(button_list_frame, text="移除欄位", command=self.remove_column_from_tree2).pack(fill=tk.X, pady=2)
        ttk.Button(button_list_frame, text="順序上移", command=self.move_column_up_tree2).pack(fill=tk.X, pady=2)
        ttk.Button(button_list_frame, text="順序下移", command=self.move_column_down_tree2).pack(fill=tk.X, pady=2)

        ttk.Label(list_frame, text="顯示欄位 (下方)").pack(pady=2)
        self.displayed_columns_list = tk.Listbox(list_frame, height=10)
        self.displayed_columns_list.pack(fill=tk.X, pady=2)

        self.grid_columnconfigure(0, weight=1) # 讓主視窗的 column 擴展
        self.grid_rowconfigure(2, weight=1) # 讓 tree1_frame 的 row 擴展
        bottom_frame.grid_rowconfigure(0, weight=0) # 讓 bottom_frame 的 row 不要過度擴展

    def zoom_in_tree1(self):
        self.tree1_font_size += 2
        self.tree1_style.configure("Treeview1.Treeview", font=('TkDefaultFont', self.tree1_font_size))
        self.zoom_in_button.config(state="disabled")
        self.zoom_out_button.config(state="disabled")
        self.populate_tree1_data()  # 重新填充以應用樣式
    def zoom_out_tree1(self):
        self.tree1_font_size -= 2
        self.tree1_style.configure("Treeview1.Treeview", font=('TkDefaultFont', self.tree1_font_size))
        self.zoom_in_button.config(state="disabled")
        self.zoom_out_button.config(state="disabled")
        self.populate_tree1_data()  # 重新填充以應用樣式

    def load_excel(self):
        file_path = filedialog.askopenfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx;*.xls"), ("All files", "*.*")],
        )
        if file_path:
            try:
                self.df = pd.read_excel(file_path)
                self.shown_row_indexes = len(self.df)
                self.checked_items = {}  # 重置勾選狀態
                self.checked_groups = set()  # 重置勾選組
                self.processed_df = pd.DataFrame()  # 清空已處理資料
                self.processed_a_values = set()  # 清空已處理的 A 欄位值
                self.populate_tree1()
                self.populate_tree2()
                self.update_available_columns()
                self.status_label.config(text=f"已讀取檔案: {file_path}，，[ 請在上方\"A欄位\"選擇主要群組。 ]")
            except Exception as e:
                messagebox.showerror("錯誤", f"讀取檔案失敗: {e}")

    def update_available_columns(self):
        if self.df is not None:
            columns = self.df.columns.tolist()
            self.available_columns_list.delete(0, tk.END)
            for col in columns:
                self.available_columns_list.insert(tk.END, col)
            self.a_column_combo['values'] = columns # 選擇A欄位選項
            self.search_column_combo['values'] = columns # 更新搜尋欄位選項

    def populate_tree1(self):
        if self.df is not None:
            self.tree1.delete(*self.tree1.get_children())
            self.tree1["columns"] = list(self.df.columns) + ["人工檢查"]
            self.tree1.column("#0", width=0, stretch=tk.NO)
            for col in self.df.columns:
                self.tree1.column(col, anchor=tk.W)
                self.tree1.heading(col, text=col, command=lambda _col=col: self.sort_column(_col))
            self.tree1.column("人工檢查", anchor=tk.CENTER, width=100)
            self.tree1.heading("人工檢查", text="人工檢查")

            for index, row in self.df.iterrows():
                values = list(row.values) + [""]
                self.tree1.insert("", tk.END, iid=index, values=values)
                self.checked_items[index] = "" # 初始化檢查狀態

            self.update_status()
            if self.a_column:
                self.sort_tree1()

    def populate_tree1_data(self):
        self.tree1.delete(*self.tree1.get_children())
        self.shown_row_indexes = 0
        if self.df is not None and self.a_column:
            for index, row in self.df.iterrows():
                if row[self.a_column] not in self.processed_a_values and row[self.a_column] not in self.rejected_a_values:
                    check_mark = self.checked_items.get(index, "")
                    values = list(row.values) + [check_mark]
                    self.tree1.insert("", tk.END, iid=index, values=values, tags=(f"group_{row[self.a_column]}",))
                    self.shown_row_indexes += 1
                else:
                    self.hidden_row_indexes.append(index)
            self.sort_tree1()
        self.zoom_in_button.config(state="normal")
        self.zoom_out_button.config(state="normal")

    def sort_tree1(self, col=None):
        if self.df is not None and self.a_column:
            items = list(self.tree1.get_children())
            sort_info = getattr(self, '_sort_info_tree1', {})
            a_col_index = self.df.columns.get_loc(self.a_column)

            # 獲取 A 欄位的值和對應的 item ID
            group_map = {}
            for item in items:
                values = self.tree1.item(item, 'values')
                a_value = values[a_col_index]
                if a_value not in group_map:
                    group_map[a_value] = []
                group_map[a_value].append(item)

            sorted_items = []
            sorted_a_values = sorted(group_map.keys())  # 保持 A 欄位的排序順序

            for a_value in sorted_a_values:
                group_items = group_map[a_value]

                def sort_key_in_group(item):
                    values = self.tree1.item(item, 'values')
                    if col:
                        try:
                            sort_col_index = self.tree1["columns"].index(col)
                            return values[sort_col_index]
                        except ValueError:
                            return ""  # 返回空字串作為預設值
                    return None

                if col:
                    if col in sort_info:
                        sort_info[col]['reverse'] = not sort_info[col]['reverse']
                    else:
                        sort_info[col] = {'reverse': False}
                    group_items.sort(key=sort_key_in_group, reverse=sort_info.get(col, {}).get('reverse', False))

                sorted_items.extend(group_items)

            # 重新排列 Treeview 的項目
            for index, item in enumerate(sorted_items):
                self.tree1.move(item, '', index)

            self._sort_info_tree1 = sort_info

    def sort_column(self, col):
        self.sort_tree1(col)

    def group_by_a_column(self, event):
        self.a_column = self.a_column_combo.get()
        if self.df is not None and self.a_column in self.df.columns:
            unique_a_values = self.df[self.a_column].unique()
            color_cycle = ['#f0f0ff', '#e0ffe0', '#ffe0e0', '#f0e0e0', '#e0e0ff']  # 更多顏色可以自行添加
            self.grouped_colors = {value: color_cycle[i % len(color_cycle)] for i, value in enumerate(unique_a_values)}
            self.apply_row_colors()
            self.sort_tree1()
            self.update_status()
    def set_search_column(self, event):
        self.search_column = self.search_column_combo.get()
        if self.search_column:
            self.search_col_index = -1
            try:
                self.search_col_index = self.tree1["columns"].index(self.search_column)
            except ValueError:
                pass  # 如果欄位不再顯示，則忽略

    def apply_row_colors(self):
        if self.df is not None and self.a_column in self.df.columns:
            for item_id in self.tree1.get_children():
                try:
                    index = int(item_id)
                    if index in self.df.index:
                        a_value = self.df.loc[index, self.a_column]
                        color = self.grouped_colors.get(a_value, 'white')
                        self.tree1.tag_configure(f"group_{a_value}", background=color)
                        self.tree1.item(item_id, tags=(f"group_{a_value}",))
                except ValueError:
                    continue
                except KeyError:
                    continue

    def on_tree1_click(self, event):
        item = self.tree1.identify_row(event.y)
        column = self.tree1.identify_column(event.x)
        if item:
            if column == "#" + str(self.search_col_index + 1):
                values = self.tree1.item(item, 'values')
                if len(values) > self.search_col_index and values[self.search_col_index]:
                    search_term = values[self.search_col_index]
                    webbrowser.open_new_tab(f"https://www.google.com/search?q={search_term}")
                    return  # 如果執行了搜尋，則不再執行勾選邏輯
            if column == "#" + str(len(self.df.columns) + 1):
                current_check = self.checked_items.get(int(item), "")
                if current_check == "":
                    self.checked_items[int(item)] = "✅"  # 使用打勾 emoji
                    self.tree1.set(item, "人工檢查", "✅")
                elif current_check == "✅":
                    self.checked_items[int(item)] = "❌"  # 切換到打叉 emoji
                    self.tree1.set(item, "人工檢查", "❌")
                elif current_check == "❌":
                    self.checked_items[int(item)] = ""   # 清除標記
                    self.tree1.set(item, "人工檢查", "")

    def show_save_options(self):
        save_options_window = tk.Toplevel(self)
        save_options_window.title("選擇存檔選項")

        tree1_button = ttk.Button(save_options_window, text="存檔 Treeview1", command=lambda: [self.show_tree1_save_submenu(), save_options_window.destroy()])
        tree1_button.pack(pady=5, padx=10, fill=tk.X)

        tree2_button = ttk.Button(save_options_window, text="存檔 Treeview2", command=lambda: [self.save_treeview2(), save_options_window.destroy()])
        tree2_button.pack(pady=5, padx=10, fill=tk.X)
    def show_tree1_save_submenu(self):
        tree1_save_submenu = tk.Toplevel(self)
        tree1_save_submenu.title("選擇 Treeview1 存檔選項")

        save_all_button = ttk.Button(tree1_save_submenu, text="儲存原始檔案", command=lambda: [self.save_treeview1_all(), tree1_save_submenu.destroy()])
        save_all_button.pack(pady=5, padx=10, fill=tk.X)

        save_displayed_button = ttk.Button(tree1_save_submenu, text="儲存剩餘未處理", command=lambda: [self.save_treeview1_displayed(), tree1_save_submenu.destroy()])
        save_displayed_button.pack(pady=5, padx=10, fill=tk.X)


    def save_treeview1_all(self):
        if self.df is not None:
            save_df = self.df.copy()
            check_series = pd.Series(["" for _ in range(len(save_df))])
            for index, check in self.checked_items.items():
                if index in save_df.index:
                    check_series.loc[index] = check
            save_df['人工檢查'] = check_series

            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                title="儲存 Treeview1 所有資料"
            )
            if file_path:
                try:
                    save_df.to_excel(file_path, index=False)
                    self.status_label.config(text=f"Treeview1 所有資料已儲存至: {file_path}")
                except Exception as e:
                    messagebox.showerror("錯誤", f"儲存檔案失敗: {e}")
        else:
            messagebox.showinfo("提示", "Treeview1 尚未讀取任何檔案。")
    def save_treeview1_displayed(self):
        if self.df is not None and self.a_column is not None:
            displayed_cols_tree1 = list(self.tree1["columns"])
            if "#0" in displayed_cols_tree1:
                displayed_cols_tree1.remove("#0")

            rows_to_save = self.df[~self.df[self.a_column].isin(self.processed_a_values)].copy()
            columns_to_save = [col for col in displayed_cols_tree1 if col in rows_to_save.columns]
            save_df = rows_to_save[columns_to_save].copy()

            if "人工檢查" in displayed_cols_tree1:
                check_series = pd.Series(index=rows_to_save.index, dtype=object)
                for index, check in self.checked_items.items():
                    if index in rows_to_save.index:
                        check_series.loc[index] = check
                save_df["人工檢查"] = check_series.reindex(save_df.index, fill_value="")

            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                title="儲存 Treeview1 顯示資料"
            )
            if file_path:
                try:
                    save_df.to_excel(file_path, index=False)
                    self.status_label.config(text=f"Treeview1 顯示資料已儲存至: {file_path}")
                except Exception as e:
                    messagebox.showerror("錯誤", f"儲存檔案失敗: {e}")
        else:
            messagebox.showinfo("提示", "請先載入檔案並選擇 A 欄位。")
    def save_treeview2(self):
        if not self.processed_df.empty:
            columns_to_save = [col for col in self.displayed_columns_list.get(0, tk.END) if col in self.processed_df.columns]
            if columns_to_save:
                save_df = self.processed_df[columns_to_save].copy()
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".xlsx",
                    filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                    title="儲存已處理資料 (Treeview2)"
                )
                if file_path:
                    try:
                        save_df.to_excel(file_path, index=False)
                        self.status_label.config(text=f"Treeview2 資料已儲存至: {file_path}")
                    except Exception as e:
                        messagebox.showerror("錯誤", f"儲存檔案失敗: {e}")
            else:
                messagebox.showinfo("提示", "請先在下方選擇要儲存的欄位。")
        else:
            messagebox.showinfo("提示", "Treeview2 沒有已處理的資料可以儲存。")

    def export_data(self):
        if not self.processed_df.empty:
            columns_to_export = [col for col in self.displayed_columns_list.get(0, tk.END) if col in self.processed_df.columns]
            if columns_to_export:
                export_df = self.processed_df[columns_to_export].copy()
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".xlsx",
                    filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                    title="匯出已處理資料"
                )
                if file_path:
                    try:
                        export_df.to_excel(file_path, index=False)
                        self.status_label.config(text=f"已處理資料匯出至: {file_path}")
                    except Exception as e:
                        messagebox.showerror("錯誤", f"匯出檔案失敗: {e}")
                else:
                    messagebox.showinfo("提示", "請先在下方選擇要匯出的欄位。")
            else:
                messagebox.showinfo("提示", "請先在下方選擇要匯出的欄位。")
        else:
            messagebox.showinfo("提示", "沒有可供匯出的已處理資料。")

    def update_status(self, processed=None, pending=None):
        if self.df is not None and self.a_column:
            total_groups = len(self.df.groupby(self.a_column))
            pending_groups = total_groups - len(self.processed_a_values) - len(self.rejected_a_values)

            status_text = f"待處理 {pending_groups} 組 ({self.shown_row_indexes} 行)"
            processed_count = len(self.processed_a_values)
            rejected_count = len(self.rejected_a_values)

            status_parts = []
            if processed_count > 0:
                status_parts.append(f"已接受 {processed_count} 組")
            if rejected_count > 0:
                status_parts.append(f"已拒絕 {rejected_count} 組")
            if pending_groups > 0:
                status_parts.append(status_text)

            status_label_text = " / ".join(status_parts) if status_parts else f"待處理 {total_groups} 組 ({self.shown_row_indexes} 行)"


            shape_str = f"表格: {self.df.shape[0]}x{self.df.shape[1]}"
            unique_a_str = f"A 欄位組數: {total_groups}"

            self.status_label.config(text=f"{shape_str} | {unique_a_str} | {status_label_text}")
        else:
            self.status_label.config(text="尚未讀取檔案或選擇 A 欄位")

    def add_column_to_tree2(self):
        selected_columns = self.available_columns_list.curselection()
        self.displayed_columns_list.delete(0, tk.END)
        for index in selected_columns:
            self.displayed_columns_list.insert(tk.END, self.available_columns_list.get(index))
        self.update_tree2_columns()
        self.update_tree2_columns() ## to rescale again, brutal fix wrong scaling --> definitely not a good idea

    def remove_column_from_tree2(self):
        selected_indices = self.displayed_columns_list.curselection()
        for index in reversed(selected_indices):
            self.displayed_columns_list.delete(index)
        self.update_tree2_columns()

    def move_column_up_tree2(self):
        selected_index = self.displayed_columns_list.curselection()
        if selected_index and selected_index[0] > 0:
            current_value = self.displayed_columns_list.get(selected_index[0])
            self.displayed_columns_list.delete(selected_index[0])
            self.displayed_columns_list.insert(selected_index[0] - 1, current_value)
            self.displayed_columns_list.selection_clear(0, tk.END)
            self.displayed_columns_list.selection_set(selected_index[0] - 1)
        self.update_tree2_columns()

    def move_column_down_tree2(self):
        selected_index = self.displayed_columns_list.curselection()
        if selected_index and selected_index[0] < self.displayed_columns_list.size() - 1:
            current_value = self.displayed_columns_list.get(selected_index[0])
            self.displayed_columns_list.delete(selected_index[0])
            self.displayed_columns_list.insert(selected_index[0] + 1, current_value)
            self.displayed_columns_list.selection_clear(0, tk.END)
            self.displayed_columns_list.selection_set(selected_index[0] + 1)
        self.update_tree2_columns()

    def update_tree2_columns(self):
        displayed_cols = [self.displayed_columns_list.get(i) for i in range(self.displayed_columns_list.size())]
        self.tree2["columns"] = displayed_cols
        self.tree2.column("#0", width=0, stretch=tk.NO)
        for col in displayed_cols:
            self.tree2.column(col, anchor=tk.W)
            self.tree2.heading(col, text=col)
        self.populate_tree2()

    def populate_tree2(self):
        self.tree2.delete(*self.tree2.get_children())
        displayed_cols = [self.displayed_columns_list.get(i) for i in range(self.displayed_columns_list.size())]
        if not self.processed_df.empty and displayed_cols:
            for index, row in self.processed_df.iterrows():
                values = [row[col] for col in displayed_cols if col in self.processed_df.columns]
                self.tree2.insert("", tk.END, iid=str(index), values=values)

    def run_selection(self):
        if self.df is not None and self.a_column:
            grouped_data = self.df.groupby(self.a_column)
            a_values_to_process = set()
            a_values_to_reject = set()
            indices_to_move = []
            rejected_groups_data = {} # 儲存打叉叉的組資料

            for group_name, group in grouped_data:
                checked_rows = group[group.index.isin([idx for idx, check in self.checked_items.items() if check == "✅" and idx in group.index])]
                rejected_rows = group[group.index.isin([idx for idx, check in self.checked_items.items() if check == "❌" and idx in group.index])]

                if len(checked_rows) > 0 and group_name not in self.processed_a_values and group_name not in self.rejected_a_values:
                    indices_to_move.extend(checked_rows.index.tolist())
                    a_values_to_process.add(group_name)
                    for index_to_clear in checked_rows.index:
                        if index_to_clear in self.checked_items:
                            del self.checked_items[index_to_clear]
                elif len(rejected_rows) > 0 and group_name not in self.processed_a_values and group_name not in self.rejected_a_values:
                    rejected_groups_data[group_name] = group.copy() # 儲存打叉叉的組資料
                    indices_to_move.extend(rejected_rows.index.tolist())
                    a_values_to_reject.add(group_name)
                    for index_to_clear in rejected_rows.index:
                        if index_to_clear in self.checked_items:
                            del self.checked_items[index_to_clear]

            if indices_to_move:
                rows_to_move = self.df[self.df.index.isin(indices_to_move)].copy()
                rows_to_move['處理方式'] = rows_to_move[self.a_column].apply(lambda x: '拒絕' if x in a_values_to_reject else '接受')
                self.processed_df = pd.concat([self.processed_df, rows_to_move], ignore_index=True)
                self.processed_a_values.update(a_values_to_process)
                self.rejected_a_values.update(a_values_to_reject)
                self.df = self.df[~self.df.index.isin(indices_to_move)]
                self.populate_tree1_data()
                self.populate_tree2()
                self.apply_row_colors()
                self.sort_tree1()
                self.update_status()

                # 觸發數值更動流程
                if rejected_groups_data:
                    self.start_modify_values(rejected_groups_data)

        else:
            messagebox.showinfo("提示", "請先選擇 A 欄位或 勾選/打叉 項目。")

    def start_modify_values(self, rejected_groups_data):
        self.modify_data = {} # 用於儲存修改後的資料
        self.rejected_groups_for_modification = list(rejected_groups_data.keys())
        if self.rejected_groups_for_modification:
            self.current_modifying_group = self.rejected_groups_for_modification.pop(0)
            self.current_group_data = rejected_groups_data[self.current_modifying_group].copy()
            self.choose_columns_to_modify()
        else:
            messagebox.showinfo("提示", "沒有需要進行數值更動的項目。")

    def choose_columns_to_modify(self):
        modify_window = tk.Toplevel(self)
        modify_window.title(f"選擇要更動的欄位 - 組別: {self.current_modifying_group}")

        columns_to_show = [col for col in self.df.columns if col != self.a_column and col != "人工檢查"]
        if not columns_to_show:
            messagebox.showinfo("提示", "沒有可供更動的非 A 欄位。")
            return

        self.modify_column_var = tk.StringVar(modify_window)
        self.modify_column_var.set(columns_to_show[0]) # 預設選中第一個

        column_label = ttk.Label(modify_window, text="選擇要更動的欄位:")
        column_label.pack(pady=5)

        column_combo = ttk.Combobox(modify_window, textvariable=self.modify_column_var, values=columns_to_show, state="readonly")
        column_combo.pack(pady=5)

        modify_button = ttk.Button(modify_window, text="開始更動", command=self.start_value_modification)
        modify_button.pack(pady=10)

    def start_value_modification(self):
        selected_column = self.modify_column_var.get()
        if selected_column:
            self.modify_column = selected_column
            self.modify_group_rows = self.current_group_data.to_dict('index').items()
            self.modify_row_iterator = iter(self.modify_group_rows)
            self.show_modify_row_dialog()
        else:
            messagebox.showinfo("提示", "請先選擇要更動的欄位。")

    def show_modify_row_dialog(self):
        try:
            index, row_data = next(self.modify_row_iterator)
            modify_row_window = tk.Toplevel(self)
            modify_row_window.title(f"修改數值 - 行: {index}, 欄位: {self.modify_column}")

            current_value_label = ttk.Label(modify_row_window, text=f"目前值: {row_data.get(self.modify_column, '')}")
            current_value_label.pack(pady=5)

            new_value_entry = ttk.Entry(modify_row_window)
            new_value_entry.pack(pady=5)

            # 功能按鈕
            button_frame = ttk.Frame(modify_row_window)
            button_frame.pack(pady=5)

            def apply_operation(operation):
                current_values = self.current_group_data[self.modify_column]
                if operation == "平均":
                    try:
                        new_value_entry.insert(0, f"{current_values.mean()}")
                    except TypeError:
                        messagebox.showerror("錯誤", "該欄位包含非數值資料，無法計算平均值。")
                elif operation == "最小":
                    try:
                        new_value_entry.insert(0, f"{current_values.min()}")
                    except TypeError:
                        messagebox.showerror("錯誤", "該欄位包含無法比較的資料。")
                elif operation == "最大":
                    try:
                        new_value_entry.insert(0, f"{current_values.max()}")
                    except TypeError:
                        messagebox.showerror("錯誤", "該欄位包含無法比較的資料。")
                elif operation == "CapitalSentence":
                    if isinstance(row_data.get(self.modify_column, ''), str):
                        new_value_entry.delete(0, tk.END)
                        new_value_entry.insert(0, row_data.get(self.modify_column, '').capitalize())
                    else:
                        messagebox.showerror("錯誤", "該欄位不是字串，無法轉換為首字母大寫。")
                elif operation == "CapitalAllLetters":
                    if isinstance(row_data.get(self.modify_column, ''), str):
                        new_value_entry.delete(0, tk.END)
                        new_value_entry.insert(0, ' '.join([
                            x.capitalize() for x in row_data.get(self.modify_column, '').split(' ')
                        ]))
                    else:
                        messagebox.showerror("錯誤", "該欄位不是字串，無法轉換為首字母大寫。")
                elif operation == "Lower":
                    if isinstance(row_data.get(self.modify_column, ''), str):
                        new_value_entry.delete(0, tk.END)
                        new_value_entry.insert(0, row_data.get(self.modify_column, '').lower())
                    else:
                        messagebox.showerror("錯誤", "該欄位不是字串，無法轉換為小寫。")
                elif operation == "Upper":
                    if isinstance(row_data.get(self.modify_column, ''), str):
                        new_value_entry.delete(0, tk.END)
                        new_value_entry.insert(0, row_data.get(self.modify_column, '').upper())
                    else:
                        messagebox.showerror("錯誤", "該欄位不是字串，無法轉換為大寫。")

            ttk.Button(button_frame, text="平均", command=lambda: apply_operation("平均")).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="最小", command=lambda: apply_operation("最小")).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="最大", command=lambda: apply_operation("最大")).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Aa aa", command=lambda: apply_operation("CapitalSentence")).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Aa Aa", command=lambda: apply_operation("CapitalAllLetters")).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="aa", command=lambda: apply_operation("Lower")).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="AA", command=lambda: apply_operation("Upper")).pack(side=tk.LEFT, padx=2)

            def apply_new_value():
                new_value = new_value_entry.get()
                self.current_group_data.loc[index, self.modify_column] = new_value
                modify_row_window.destroy()
                self.show_modify_row_dialog()  # 顯示下一行

            ttk.Button(modify_row_window, text="完成", command=apply_new_value).pack(pady=10)

        except StopIteration:
            # 完成所有行的修改，將修改後的資料更新到 processed_df
            modified_group = self.current_group_data
            # 找到原始在 processed_df 中的對應組並更新
            a_value = modified_group.iloc[0][self.a_column]
            processed_group_index = self.processed_df[self.processed_df[self.a_column] == a_value].index
            if not processed_group_index.empty:
                self.processed_df.loc[processed_group_index, modified_group.columns] = modified_group.values

            messagebox.showinfo("提示", f"組別 '{self.current_modifying_group}' 的欄位 '{self.modify_column}' 修改完成。")

            if self.rejected_groups_for_modification:
                self.current_modifying_group = self.rejected_groups_for_modification.pop(0)
                # 重新從 processed_df 中獲取最新的組資料
                self.current_group_data = self.processed_df[
                    self.processed_df[self.a_column] == self.current_modifying_group].copy()
                self.modify_group_rows = self.current_group_data.to_dict('index').items()
                self.modify_row_iterator = iter(self.modify_group_rows)
                self.choose_columns_to_modify()  # 繼續修改下一個組
            else:
                self.populate_tree2()  # 所有組修改完成後更新 treeview2


    def redo_selection(self):
        selected_items = self.tree2.selection()
        if selected_items:
            indices_to_restore = []
            a_values_to_unreject = set()
            for item in selected_items:
                try:
                    original_index = int(item)
                    if original_index in self.processed_df.index:
                        a_value = self.processed_df.loc[original_index, self.a_column]
                        row_to_restore = self.processed_df.loc[[original_index]]
                        self.df = pd.concat([self.df, row_to_restore], ignore_index=True)
                        indices_to_restore.append(original_index)
                        if self.processed_df.loc[original_index, '處理方式'] == '拒絕':
                            a_values_to_unreject.add(a_value)
                except ValueError:
                    messagebox.showerror("錯誤", f"無法識別的項目 ID: {item}")
                    continue

            if indices_to_restore:
                self.processed_df = self.processed_df[~self.processed_df.index.isin(indices_to_restore)]
                self.processed_a_values = set(self.processed_df[self.a_column].unique()) if not self.processed_df.empty and self.a_column in self.processed_df.columns else set()
                self.rejected_a_values = self.rejected_a_values - a_values_to_unreject
                self.populate_tree1_data()
                self.populate_tree2()
                self.apply_row_colors()
                self.sort_tree1()
                self.update_status()
        else:
            messagebox.showinfo("提示", "請先在下方表格中選擇要撤銷決定的項目。")

if __name__ == "__main__":
    app = ExcelComparer()
    app.mainloop()
