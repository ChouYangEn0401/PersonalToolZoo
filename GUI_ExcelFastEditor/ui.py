import tkinter as tk
from tkinter import ttk

from remake.M2E1.GUI_ExcelFastEditor.data_processor import DataProcessor
from remake.M2E1.GUI_ExcelFastEditor.commands import *


class ExcelEditorUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel 編輯 GUI 小工具 v2 - 重構版")
        self.df = pd.DataFrame()
        self.original_df = pd.DataFrame()  # 備份原始資料
        self.data_processor = DataProcessor()
        self.sort_criteria = []  # 存放排序條件 [(欄位, 順序), ...]

        # 實例化所有命令物件
        self.commands = {
            "讀取 Excel": [0, 0, "#DDEEFF", LoadExcelCommand(self)],
            "儲存檔案": [0, 1, "#DDEEFF", SaveExcelCommand(self)],
            "合併資料表": [0, 2, "#FFFACD", MergeAppendCommand(self)],
            "根據另一份資料刪除資料": [0, 3, "#FFFACD", DeleteRowsByReferenceCommand(self)],
            "多選刪除欄位": [1, 0, "#E0F5E0", DeleteColumnsCommand(self)],
            "刪除全為 NaN 的欄": [1, 1, "#E0F5E0", DeleteAllNaNColumnsCommand(self)],
            "重新命名欄位": [1, 2, "#E0F5E0", RenameColumnsCommand(self)],
            "欄位重新排序": [1, 3, "#E0F5E0", ReorderColumnsCommand(self)],
            "刪除重複列(多欄組合去重)": [2, 0, "#E0F5E0", RemoveDuplicateRowsCommand(self)],
            "刪除全為 NaN 的列": [2, 1, "#E0F5E0", DeleteAllNaNRowsCommand(self)],
            "刪除某欄為 NaN 的列": [2, 2, "#E0F5E0", DeleteRowsWithNaNInColumnCommand(self)],
            "刪除指定欄位皆為 NaN 的列": [2, 3, "#E0F5E0", DeleteRowsWithNaNInSubsetCommand(self)],
            "用另一份檔案指定idx欄位刪除列": [2, 4, "#F0F8D7", DeleteRowsByIndexCommand(self)],
            "兩欄位比對重複值，顯示結果": [3, 0, "#E6E6FA", CompareColumnsCommand(self)],
            "檢查某欄位重複值，顯示結果": [3, 1, "#E6E6FA", FindDuplicatesInColumnCommand(self)],
            "合併濃縮資料": [4, 0, "#F5DEB3", AggregateCommand(self)],
            "建立透視表": [4, 1, "#F5DEB3", PivotCommand(self)],
        }

        self.build_ui()
        self.build_help_data()

    def build_help_data(self):
        self.help_data = {
            "建立透視表": {
                'summary': '此功能會將資料表依據您選擇的欄位進行分組，並將其他指定欄位的值使用分隔符號合併成一個字串。這能將一對多的資料關係轉換為一對一，以便於分析。',
                'input_df': pd.DataFrame({
                    '訂單ID': [101, 101, 102, 102, 102],
                    '產品': ['T-Shirt', 'T-Shirt', '帽子', '帽子', '帽子'],
                    '顏色': ['紅色', '藍色', '黑色', '白色', '灰色']
                }),
                'steps': [
                    '在對話框中選擇「訂單ID」與「產品」作為分組欄位。',
                    '選擇「顏色」作為要合併的欄位。',
                    '輸入逗號「,」作為分隔符號。',
                    '點擊確定後，程式會自動將同一筆訂單的顏色合併。'
                ],
                'output_df': pd.DataFrame({
                    '訂單ID': [101, 102],
                    '產品': ['T-Shirt', '帽子'],
                    '顏色': ['紅色,藍色', '黑色,白色,灰色']
                })
            },
            "合併濃縮資料": {
                'summary': '透視表功能將一個欄位中的類別轉換為多個新的欄位，並對其進行聚合計算。這能讓您從不同角度總結資料，快速產生摘要報告。',
                'input_df': pd.DataFrame({
                    '區域': ['東', '東', '西', '西'],
                    '產品': ['A', 'B', 'A', 'C'],
                    '銷售額': [100, 150, 200, 50]
                }),
                'steps': [
                    '在對話框中選擇「區域」作為索引 (index) 欄位。',
                    '選擇「產品」作為欄位 (columns) 欄位。',
                    '選擇「銷售額」作為值 (values) 欄位。',
                    '選擇「sum」作為聚合函數。'
                ],
                'output_df': pd.DataFrame({
                    '區域': ['東', '西'],
                    'A': [100, 200],
                    'B': [150, float('nan')],
                    'C': [float('nan'), 50]
                })
            }
        }

    def build_ui(self):
        # 主架構劃分
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X)
        self.build_button_frame(top_frame)
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 表格區
        table_container = tk.Frame(main_frame)
        table_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(table_container)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scroll_y = ttk.Scrollbar(table_container, orient="vertical", command=self.canvas.yview)
        self.scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.scroll_x = ttk.Scrollbar(self.root, orient="horizontal", command=self.canvas.xview)
        self.scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)
        self.canvas.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.table_frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.table_frame, anchor="nw")
        self.table = None

        # 右側排序區
        self.sort_panel = ttk.Frame(main_frame, padding=10, relief="groove")
        self.sort_panel.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Label(self.sort_panel, text="排序控制", font=("Arial", 12, "bold")).pack(pady=5)
        self.build_sort_controls()

        # 底部狀態列
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_label = ttk.Label(bottom_frame, text="📐 表格尺寸：0 x 0")
        self.status_label.pack(side=tk.LEFT, padx=10)

        self.progress = ttk.Progressbar(bottom_frame, mode='determinate', length=300)
        self.progress.pack(side=tk.RIGHT, padx=10, pady=5, fill=tk.X, expand=True)

    def create_buttons(self, frame):
        for text, command_pars in self.commands.items():
            row, col, color, command_obj = command_pars
            # 創建一個帶有背景色的 Frame
            btn_frame = tk.Frame(frame, bg=color, relief="groove", bd=2)
            btn_frame.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")

            # 將按鈕放入這個 Frame 中
            button = ttk.Button(btn_frame, text=text, command=command_obj.execute)
            button.pack(fill="both", expand=True, padx=2, pady=2)
            button.bind("<Button-3>", lambda event, name=text: self.show_command_help(name, self.help_data.get(name)))

        # 讓按鈕在寬度上平均分佈
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=1)
        frame.grid_columnconfigure(3, weight=1)
        frame.grid_columnconfigure(4, weight=1)
        frame.grid_columnconfigure(5, weight=1)

    def build_button_frame(self, parent_frame):

        def on_mousewheel_y(event):
            self.canvas_buttons.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_mousewheel_x(event):
            self.canvas_buttons.xview_scroll(int(-1 * (event.delta / 120)), "units")

        outer_frame = tk.Frame(parent_frame)
        outer_frame.pack(fill=tk.X, expand=True)

        self.canvas_buttons = tk.Canvas(outer_frame, height=150)  # 調整高度
        self.canvas_buttons.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)  # 將canvas_buttons放在左側

        # 新增垂直捲軸
        self.scrollbar_buttons_y = ttk.Scrollbar(outer_frame, orient="vertical", command=self.canvas_buttons.yview)
        self.scrollbar_buttons_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.scrollbar_buttons_x = ttk.Scrollbar(parent_frame, orient="horizontal", command=self.canvas_buttons.xview)
        self.scrollbar_buttons_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas_buttons.configure(
            yscrollcommand=self.scrollbar_buttons_y.set,
            xscrollcommand=self.scrollbar_buttons_x.set
        )

        # 綁定滑鼠滾輪事件
        self.canvas_buttons.bind("<MouseWheel>", on_mousewheel_y)
        self.canvas_buttons.bind("<Shift-MouseWheel>", on_mousewheel_x)

        self.button_frame = tk.Frame(self.canvas_buttons)
        self.canvas_buttons.create_window((0, 0), window=self.button_frame, anchor="nw")

        self.create_buttons(self.button_frame)
        self.button_frame.update_idletasks()
        self.canvas_buttons.config(scrollregion=self.canvas_buttons.bbox("all"))

    def refresh_table(self):
        if self.table:
            self.table.destroy()
        if self.df.empty:
            self.table = ttk.Label(self.table_frame, text="請先讀取 Excel 檔案")
            self.table.pack(padx=20, pady=20)
            self.update_status()
            self.build_sort_controls()  # 呼叫這個函數來更新右側面板
            return

        self.table = ttk.Treeview(self.table_frame, columns=list(self.df.columns), show="headings")
        for col in self.df.columns:
            self.table.heading(col, text=col)
            self.table.column(col, width=100, anchor=tk.W)

        # 限制顯示數量，避免程式卡頓
        for row in self.df.itertuples(index=False):
            self.table.insert("", "end", values=row)

        self.table.pack(fill=tk.BOTH, expand=True)
        self.table_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

        self.build_sort_controls()
        self.update_status()
        self.build_sort_controls()  # 再次呼叫，確保右側面板與表格欄位相符

    def build_sort_controls(self):
        # 重寫排序控制區塊
        for widget in self.sort_panel.winfo_children():
            widget.destroy()

        if self.df.empty:
            ttk.Label(self.sort_panel, text="排序控制", font=("Arial", 12, "bold")).pack()
            ttk.Label(self.sort_panel, text="請先載入資料以進行排序。").pack(pady=10)
            return

        # 排序清單區塊
        ttk.Label(self.sort_panel, text="排序層級 (依序)", font=("Arial", 10, "bold")).pack(anchor="w")

        sort_frame = tk.Frame(self.sort_panel)
        sort_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.sort_listbox = tk.Listbox(sort_frame, selectmode=tk.SINGLE, width=25, height=10)
        self.sort_listbox.pack(side=tk.LEFT, fill=tk.Y, expand=True)

        # 排序清單的滾動條
        sort_scrollbar = ttk.Scrollbar(sort_frame, orient="vertical", command=self.sort_listbox.yview)
        sort_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.sort_listbox.configure(yscrollcommand=sort_scrollbar.set)

        self.update_sort_listbox()  # 初始填充列表

        # 排序操作按鈕
        sort_buttons_frame = ttk.Frame(self.sort_panel)
        sort_buttons_frame.pack(pady=5)

        ttk.Button(sort_buttons_frame, text="▲ 上移", command=self.move_sort_item_up).pack(side=tk.LEFT, padx=2)
        ttk.Button(sort_buttons_frame, text="▼ 下移", command=self.move_sort_item_down).pack(side=tk.LEFT, padx=2)

        # 排序方向切換按鈕
        ttk.Button(sort_buttons_frame, text="⇅ 切換方向", command=self.toggle_sort_direction).pack(side=tk.LEFT, padx=2)

        # 新增/移除排序欄位
        ttk.Separator(self.sort_panel, orient="horizontal").pack(fill=tk.X, pady=5)
        ttk.Label(self.sort_panel, text="新增排序欄位", font=("Arial", 10, "bold")).pack(anchor="w")

        select_col_frame = ttk.Frame(self.sort_panel)
        select_col_frame.pack(fill=tk.X)

        self.sort_col_var = tk.StringVar()
        self.sort_col_combobox = ttk.Combobox(select_col_frame, textvariable=self.sort_col_var, state="readonly")
        self.sort_col_combobox['values'] = list(self.df.columns)
        self.sort_col_combobox.pack(side=tk.LEFT, padx=2)

        self.sort_mode_var = tk.StringVar(value="文字排序")
        sort_mode_combobox = ttk.Combobox(select_col_frame, textvariable=self.sort_mode_var,
                                          values=["文字排序", "數值排序"], state="readonly", width=8)
        sort_mode_combobox.pack(side=tk.LEFT, padx=2)

        add_sort_btn = ttk.Button(select_col_frame, text="新增", command=self.add_sort_criteria)
        add_sort_btn.pack(side=tk.LEFT, padx=2)

        # 移除選中的排序條件
        remove_sort_btn = ttk.Button(self.sort_panel, text="移除選中的排序條件", command=self.remove_sort_criteria)
        remove_sort_btn.pack(fill=tk.X, pady=5)

        # 套用排序按鈕
        ttk.Separator(self.sort_panel, orient="horizontal").pack(fill=tk.X, pady=5)
        ttk.Button(self.sort_panel, text="套用排序", command=self.apply_sort).pack(fill=tk.X)
        ttk.Button(self.sort_panel, text="清除排序", command=ClearSortCommand(self).execute).pack(fill=tk.X, pady=5)

    def add_sort_criteria(self):
        col = self.sort_col_var.get()
        sort_mode = self.sort_mode_var.get()
        if col and col not in [c['column'] for c in self.sort_criteria]:
            self.sort_criteria.append({'column': col, 'ascending': True, 'mode': sort_mode})
            self.update_sort_listbox()

    def remove_sort_criteria(self):
        try:
            index = self.sort_listbox.curselection()[0]
            del self.sort_criteria[index]
            self.update_sort_listbox()
        except IndexError:
            messagebox.showwarning("警告", "請先選擇要移除的排序條件。")

    def move_sort_item_up(self):
        try:
            index = self.sort_listbox.curselection()[0]
            if index > 0:
                self.sort_criteria[index], self.sort_criteria[index - 1] = self.sort_criteria[index - 1], \
                self.sort_criteria[index]
                self.update_sort_listbox()
                self.sort_listbox.select_set(index - 1)
        except IndexError:
            pass

    def move_sort_item_down(self):
        try:
            index = self.sort_listbox.curselection()[0]
            if index < len(self.sort_criteria) - 1:
                self.sort_criteria[index], self.sort_criteria[index + 1] = self.sort_criteria[index + 1], \
                self.sort_criteria[index]
                self.update_sort_listbox()
                self.sort_listbox.select_set(index + 1)
        except IndexError:
            pass

    def toggle_sort_direction(self):
        try:
            index = self.sort_listbox.curselection()[0]
            crit = self.sort_criteria[index]
            crit['ascending'] = not crit['ascending']
            self.update_sort_listbox()
            self.sort_listbox.select_set(index)
        except IndexError:
            pass

    def update_sort_listbox(self):
        self.sort_listbox.delete(0, tk.END)
        for crit in self.sort_criteria:
            direction = "A → Z" if crit['ascending'] else "Z → A"
            mode_text = " (數值)" if crit['mode'] == "數值排序" else ""
            self.sort_listbox.insert(tk.END, f"{crit['column']} ({direction}){mode_text}")

    def apply_sort(self):
        if not self.sort_criteria:
            messagebox.showinfo("訊息", "請先新增排序欄位。")
            return

        try:
            self.set_progress(indeterminate=True)
            # 傳遞完整的排序條件列表
            self.df = self.data_processor.sort_data(self.original_df, self.sort_criteria)
            self.refresh_table()
            messagebox.showinfo("完成", "排序已套用。")
        except Exception as e:
            messagebox.showerror("錯誤", f"排序失敗: {e}")
        finally:
            self.set_progress(0)

    def simple_select(self, title, options):
        win = tk.Toplevel(self.root)
        win.title(title)
        var = tk.StringVar(value=options[0])
        dropdown = ttk.Combobox(win, textvariable=var, values=options, state="readonly", width=30)
        dropdown.pack(padx=10, pady=10)

        def confirm():
            win.selected = var.get()
            win.destroy()

        ttk.Button(win, text="確定", command=confirm).pack(pady=5)
        win.grab_set()
        self.root.wait_window(win)
        return getattr(win, 'selected', None)

    def simple_select_multiple(self, prompt, options):
        win = tk.Toplevel(self.root)
        win.title(prompt)
        tk.Label(win, text=prompt).pack(padx=10, pady=10)
        listbox = tk.Listbox(win, selectmode=tk.MULTIPLE, width=50)
        for option in options:
            listbox.insert(tk.END, option)
        listbox.pack(padx=10, pady=5)
        selected_items = []

        def submit():
            nonlocal selected_items
            try:
                selected_items = [listbox.get(i) for i in listbox.curselection()]
                win.destroy()
            except Exception:
                messagebox.showerror("錯誤", "無法取得選擇項目。")
                win.destroy()

        ttk.Button(win, text="確定", command=submit).pack(pady=5)
        win.grab_set()
        win.wait_window()
        return selected_items

    def show_table(self, df, title, summary_text):
        win = tk.Toplevel(self.root)
        win.title(title)
        summary_label = ttk.Label(win, text=summary_text, justify="left", font=("Arial", 11), foreground="blue")
        summary_label.pack(anchor="w", padx=10, pady=5)
        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(frame, columns=list(df.columns), show="headings")
        tree.pack(fill=tk.BOTH, expand=True)
        for col in df.columns:
            tree.heading(col, text=col)
            tree.column(col, width=120, anchor=tk.W)
        for row in df.itertuples(index=False):
            tree.insert("", "end", values=row)
        ysb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscroll=ysb.set)

        button_frame = ttk.Frame(win)
        button_frame.pack(pady=5)

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

    def reorder_columns_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("欄位重新排序")
        columns = list(self.df.columns)
        listbox = tk.Listbox(win, selectmode=tk.SINGLE, width=30)
        for col in columns:
            listbox.insert(tk.END, col)
        listbox.pack(padx=10, pady=10, side=tk.LEFT, fill=tk.Y)

        def move_up():
            try:
                idx = listbox.curselection()[0]
                if idx > 0:
                    item = listbox.get(idx)
                    listbox.delete(idx)
                    listbox.insert(idx - 1, item)
                    listbox.select_set(idx - 1)
            except IndexError:
                pass

    def show_command_help(self, command_name, help_data):
        """
        顯示指定命令的說明視窗。
        :param command_name: 按鈕的名稱（例如 "合併濃縮資料"）
        :param help_data: 包含範例資料和操作步驟的字典。
        """
        win = tk.Toplevel(self.root)
        win.title(f"說明：{command_name}")
        win.geometry("800x600")

        # 創建一個帶有滾動條的框架
        main_frame = tk.Frame(win)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 標題
        ttk.Label(scrollable_frame, text=f"指令說明：{command_name}", font=("Arial", 14, "bold")).pack(pady=5,
                                                                                                      anchor="w")

        # 總結說明
        ttk.Label(scrollable_frame, text=help_data['summary'], wraplength=750, justify="left").pack(pady=5, anchor="w")

        # 原始資料表格 (Example)
        ttk.Label(scrollable_frame, text="✅ 範例輸入表格：", font=("Arial", 12, "bold")).pack(pady=5, anchor="w")
        self.create_help_table(scrollable_frame, help_data['input_df'])

        # 操作步驟 (Step-by-step)
        ttk.Label(scrollable_frame, text="🚀 操作流程：", font=("Arial", 12, "bold")).pack(pady=5, anchor="w")

        step_frame = ttk.Frame(scrollable_frame)
        step_frame.pack(fill=tk.X, pady=5, padx=10, anchor="w")
        for i, step in enumerate(help_data['steps']):
            ttk.Label(step_frame, text=f"• 第 {i + 1} 步：{step}", wraplength=700, justify="left").pack(anchor="w")

        # 結果資料表格 (Result)
        ttk.Label(scrollable_frame, text="🎉 預期輸出表格：", font=("Arial", 12, "bold")).pack(pady=5, anchor="w")
        self.create_help_table(scrollable_frame, help_data['output_df'])

        # win.grab_set()

    def create_help_table(self, parent_frame, df):
        """
        在說明視窗中建立一個只顯示不互動的表格。
        """
        tree = ttk.Treeview(parent_frame, columns=list(df.columns), show="headings", height=min(len(df), 10))
        for col in df.columns:
            tree.heading(col, text=col)
            tree.column(col, width=100, anchor=tk.W)
        for row in df.itertuples(index=False):
            tree.insert("", "end", values=row)
        tree.pack(fill=tk.X, padx=10, pady=5)

