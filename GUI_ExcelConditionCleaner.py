import pandas as pd
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from legacy.lib.engine import RuleEngine
from legacy.lib.rule_definitions import RULE_REGISTRY
from legacy.lib.rules import GroupIfElseRule
from legacy.lib.rules_builder import (
    build_leave_rule, build_group_condition_rule,
    build_if_else_rule, build_basic_rule,
    build_group_if_else_rule
)
import uuid


FONT = ("Microsoft JhengHei", 12)

class DynamicExcelEditorGUI:
    def __init__(self, root, df):
        self.root = root
        self.original_df = df.copy()
        self.df = df.copy()
        self.engine = RuleEngine()
        self.root.title("Excel Editor")
        self.root.geometry("1300x750")

        self.rule_rows = []
        self.group_by_columns = []

        self.refreshing = False
        self.rules_frame = None
        self.create_gui()

    @staticmethod
    def __setup_scrollable_frame(control_frame):
        canvas_frame = tk.Frame(control_frame)
        canvas_frame.pack(fill="x", pady=5)

        canvas = tk.Canvas(canvas_frame)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
        scrollbar.pack(side="bottom", fill="x")
        canvas.configure(xscrollcommand=scrollbar.set)

        scrollable_frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        return canvas_frame

    def create_gui(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill="both", expand=False)

        self.table = ttk.Treeview(top_frame, columns=list(self.df.columns), show="headings", height=10)
        for col in self.df.columns:
            self.table.heading(col, text=col)
            self.table.column(col, anchor="w", width=150)
        self.table.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(top_frame, orient="vertical", command=self.table.yview)
        scrollbar.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scrollbar.set)

        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=10)

        btn_frame = tk.Frame(control_frame)
        btn_frame.pack(fill="x")

        self.original_df_label = tk.Label(btn_frame, text="")
        self.original_df_label.pack(side="left", padx=10)
        self.df_label = tk.Label(btn_frame, text="")
        self.df_label.pack(side="left", padx=10)
        tk.Button(btn_frame, text="讀取 Excel", command=self.read_excel_file).pack(side="left", padx=5)
        tk.Button(btn_frame, text="新增規則", command=self.add_rule_row).pack(side="left", padx=5)
        tk.Button(btn_frame, text="應用所有規則", command=self.apply_all_rules).pack(side="left", padx=5)
        tk.Button(btn_frame, text="還原資料 (Redo)", command=self.reset_data).pack(side="left", padx=5)
        tk.Button(btn_frame, text="顯示結果", command=self.show_result).pack(side="left", padx=5)
        tk.Button(btn_frame, text="匯出當前表單", command=self.export_excel).pack(side="left", padx=5)

        self.rules_frame = tk.Frame(control_frame)
        self.rules_frame.pack(fill="both", expand=True, pady=5)

        self.refresh_table()

    def read_excel_file(self):
        filepath = filedialog.askopenfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if filepath:
            try:
                df = pd.read_excel(filepath)  # 移除錯誤的 index=False
                self.df = df
                self.reset_table_with_new_df()
                messagebox.showinfo("成功", "載入新資料")
                if messagebox.askyesno("詢問", "是否將此資料設定為新的還原點？設定後之後所有操作都可還原到此狀態，若否則會回復至上一次的資料檔。"):
                    self.original_df = df.copy()
                    self.show_table_info_in_text()
            except Exception as e:
                messagebox.showerror("錯誤", f"無法讀取 Excel 檔案：{e}")

    def show_table_info_in_text(self):
        self.original_df_label.config(text=f"還原資料：{self.original_df.shape[0]} 列 x {self.original_df.shape[1]} 欄")
        self.df_label.config(text=f"當前資料：{self.df.shape[0]} 列 x {self.df.shape[1]} 欄")

    def reset_table_with_new_df(self):
        # 先清除現有欄位與資料
        self.table.delete(*self.table.get_children())

        # 重新設定欄位
        columns = list(self.df.columns)
        self.table["columns"] = columns
        self.table["show"] = "headings"  # 顯示表頭

        # 設定每個欄位的表頭文字
        for col in columns:
            self.table.heading(col, text=col)
            self.table.column(col, width=100)  # 可自訂欄寬

        # 插入資料列
        for _, row in self.df.iterrows():
            self.table.insert("", "end", values=list(row))

        # 更新
        self.refresh_table()
        self.show_table_info_in_text()

    def refresh_table(self):
        self.table.delete(*self.table.get_children())
        for _, row in self.df.iterrows():
            self.table.insert("", "end", values=list(row))
        self.show_table_info_in_text()

    def reset_data(self):
        self.df = self.original_df.copy()
        self.refresh_table()
        messagebox.showinfo("還原", "已還原為原始資料")

    def export_excel(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if filepath:
            self.df.to_excel(filepath, index=False)
            messagebox.showinfo("成功", f"已匯出至 {filepath}")

    def add_rule_row(self, parent_frame=None):
        if not parent_frame:
            parent_frame = self.rules_frame

        row_id = str(uuid.uuid4())  # 為每個 row 生成唯一的 ID
        row = tk.Frame(parent_frame)
        # row = self.__setup_scrollable_frame(parent_frame) ## future
        row.pack(fill="x", pady=2, padx=20 if parent_frame != self.rules_frame else 0)
        row.then_subrule = None
        row.else_subrule = None
        row.row_id = row_id  # 設定唯一的 row_id

        # IF 部分 Frame
        if_frame = tk.Frame(row)
        if_frame.pack(fill="x")

        del_btn = tk.Button(if_frame, text="❌", font=FONT, fg="red", command=lambda: self.delete_rule_row(row))
        del_btn.pack(side="left", padx=3)

        col_box = ttk.Combobox(if_frame, values=list(self.df.columns), width=15)
        col_box.set("欄位")
        col_box.pack(side="left")

        op_box = ttk.Combobox(if_frame, values=list(RULE_REGISTRY.keys()), width=20)
        op_box.set("操作")
        op_box.pack(side="left")

        if_label = tk.Label(if_frame, text="IF", font=FONT)
        if_label.pack(side="left", padx=3)
        if_label.pack_forget()

        operator_selector = ttk.Combobox(
            if_frame,
            values=[
                "==", "!=", ">", "<", ">=", "<=",
                "is unique", "is not unique", "is nan", "is not nan",
                "is str", "is number",
                "contains", "startswith", "endswith", "match_regex", "similarity(word) > (value)"
            ],
            width=12,
            font=FONT
        )
        operator_selector.set("==")
        operator_selector.pack_forget()

        param_entry = tk.Entry(if_frame, width=20, font=FONT)
        param_entry.pack_forget()

        then_action_type = ttk.Combobox(if_frame, values=["keep", "drop", "set", "rule"], width=6, font=FONT)
        then_action_type.set("keep")
        then_action_type.pack_forget()

        then_value = tk.Entry(if_frame, width=10, font=FONT)
        then_value.pack_forget()

        # 新增 group_then_action_type
        group_then_action_type = ttk.Combobox(if_frame, values=["keep-group", "drop-group", "set-group"], width=10, font=FONT)
        group_then_action_type.set("keep-group")
        group_then_action_type.pack_forget()

        # ELSE 部分 Frame
        else_frame = tk.Frame(row)
        else_frame.pack(fill="x", padx=50)

        else_label = tk.Label(else_frame, text="ELSE", font=FONT)
        else_label.pack(side="left", padx=3)
        else_label.pack_forget()

        else_action_type = ttk.Combobox(else_frame, values=["keep", "drop", "set", "rule"], width=6, font=FONT)
        else_action_type.set("drop")
        else_action_type.pack_forget()

        else_value = tk.Entry(else_frame, width=10, font=FONT)
        else_value.pack_forget()

        # 新增 group_else_action_type
        group_else_action_type = ttk.Combobox(else_frame, values=["keep-group", "drop-group", "set-group"], width=10, font=FONT)
        group_else_action_type.set("drop-group")
        group_else_action_type.pack_forget()

        # ELSE 子規則容器
        else_subrule_frame = tk.Frame(else_frame)
        else_subrule_frame.pack(fill="x")
        else_subrule_frame.pack_forget()

        group_selector = ttk.Combobox(if_frame, values=["SAME_CONTENT", "SELF_SIMILARITY", "SPECIFIC_CONTENT"],
                                      font=FONT, width=20)
        group_selector.set("SAME_CONTENT")
        group_selector.pack_forget()

        specific_entry = tk.Entry(if_frame, width=20, font=FONT)
        specific_entry.pack_forget()

        then_subrule_frame = tk.Frame(if_frame)
        then_subrule_frame.pack(fill="x")
        then_subrule_frame.pack_forget()

        # 事件與刷新邏輯
        def hide_all_optional():
            operator_selector.pack_forget()
            param_entry.pack_forget()
            group_selector.pack_forget()
            specific_entry.pack_forget()
            then_action_type.pack_forget()
            then_value.pack_forget()
            if_label.pack_forget()
            else_label.pack_forget()
            else_action_type.pack_forget()
            else_value.pack_forget()
            then_subrule_frame.pack_forget()
            else_subrule_frame.pack_forget()
            group_then_action_type.pack_forget()
            group_else_action_type.pack_forget()

        def refresh_view():
            if self.refreshing:
                return
            self.refreshing = True
            try:
                hide_all_optional()
                rule_key = op_box.get()
                param_type = RULE_REGISTRY.get(rule_key, {}).get("param_type", "")

                if param_type == "group_condition_selector":
                    group_selector.pack(side="left", padx=3)
                    if group_selector.get() == "SPECIFIC_CONTENT":
                        specific_entry.pack(side="left", padx=3)

                elif param_type == "if_else":
                    if_label.config(text="IF")
                    if_label.pack(side="left", padx=3)
                    operator_selector.pack(side="left", padx=3)
                    op = operator_selector.get()
                    if op in ["==", "!=", ">", "<", ">=", "<="]:
                        param_entry.pack(side="left", padx=3)

                    then_action_type.pack(side="left", padx=3)
                    if then_action_type.get() == "set":
                        then_value.pack(side="left", padx=3)
                    elif then_action_type.get() == "rule":
                        then_subrule_frame.pack(fill="x")
                        if not row.then_subrule:
                            row.then_subrule = self.add_rule_row(parent_frame=then_subrule_frame)

                    else_label.config(text="ELSE")
                    else_label.pack(side="left", padx=3)
                    else_action_type.pack(side="left", padx=3)

                    if else_action_type.get() == "set":
                        else_value.pack(side="left", padx=3)
                    elif else_action_type.get() == "rule":
                        else_subrule_frame.pack(fill="x")
                        if not row.else_subrule:
                            row.else_subrule = self.add_rule_row(parent_frame=else_subrule_frame)

                elif param_type == "group_if_else":
                    if_label.config(text="IF (Group)")
                    if_label.pack(side="left", padx=3)
                    operator_selector.pack(side="left", padx=3)
                    op = operator_selector.get()
                    if op in ["==", "!=", ">", "<", ">=", "<="]:
                        param_entry.pack(side="left", padx=3)

                    group_then_action_type.pack(side="left", padx=3)
                    if group_then_action_type.get() == "set-group":
                        then_subrule_frame.pack(fill="x")
                        if not row.then_subrule:
                            row.then_subrule = self.add_rule_row(parent_frame=then_subrule_frame)
                    else:
                        then_subrule_frame.pack_forget()

                    else_label.config(text="ELSE (Group)")
                    else_label.pack(side="left", padx=3)
                    group_else_action_type.pack(side="left", padx=3)
                    if group_else_action_type.get() == "set-group":
                        else_subrule_frame.pack(fill="x")
                        if not row.else_subrule:
                            row.else_subrule = self.add_rule_row(parent_frame=else_subrule_frame)
                    else:
                        else_subrule_frame.pack_forget()


                elif param_type == "string_similarity":
                    param_entry.pack(side="left", padx=3)
                    param_entry.delete(0, tk.END)
                    param_entry.insert(0, "目標字串,閾值")

                elif param_type in ["number", "string", "string_or_number"]:
                    param_entry.pack(side="left", padx=3)

            finally:
                self.refreshing = False

        op_box.bind("<<ComboboxSelected>>", lambda e: refresh_view())
        operator_selector.bind("<<ComboboxSelected>>", lambda e: refresh_view())
        then_action_type.bind("<<ComboboxSelected>>", lambda e: refresh_view())
        else_action_type.bind("<<ComboboxSelected>>", lambda e: refresh_view())
        group_selector.bind("<<ComboboxSelected>>", lambda e: refresh_view())
        group_then_action_type.bind("<<ComboboxSelected>>", lambda e: refresh_view())
        group_else_action_type.bind("<<ComboboxSelected>>", lambda e: refresh_view())

        refresh_view()

        self.rule_rows.append((
            row, col_box, op_box, param_entry, group_selector, specific_entry,
            operator_selector, then_action_type, then_value,
            else_action_type, else_value, row.then_subrule, row.else_subrule,
            group_then_action_type, group_else_action_type
        ))

        return row

    def delete_rule_row(self, row_frame):
        for item in self.rule_rows:
            if item[0] == row_frame:
                self.rule_rows.remove(item)
                break
        row_frame.destroy()

    def apply_all_rules(self):
        self.engine.clear()
        df = self.df.copy()
        group_by_cols = []
        rules_to_apply = []

        def parse_rule(
                col_box, op_box, param_entry, group_sel, specific_entry,
                operator_selector, then_action_type, then_value_widget,
                else_action_type, else_value_widget, then_subrule_widget=None, else_subrule_widget=None,
                group_then_action_type_widget=None, group_else_action_type_widget=None  # 接收新的 widget
        ):
            rule_key = op_box.get()
            col = col_box.get()

            if rule_key in ["leave_max", "leave_min"]:
                return build_leave_rule(rule_key, group_by_cols, col)

            elif rule_key == "group_condition":
                rule, new_group_cols = build_group_condition_rule(col, group_sel, param_entry, specific_entry)
                group_by_cols.extend(new_group_cols)
                return rule



            elif rule_key == "if_else_condition":
                then_val = then_value_widget.get() if then_action_type.get() == "set" else None
                if then_action_type.get() == "rule" and then_subrule_widget:
                    subrule = next((item for item in self.rule_rows if item[0] == then_subrule_widget), None)
                    if subrule:
                        subrule_instance = parse_rule(*subrule)
                        then_val = subrule_instance
                else_val = else_value_widget.get() if else_action_type.get() == "set" else None
                if else_action_type.get() == "rule" and else_subrule_widget:
                    subrule = next((item for item in self.rule_rows if item[0] == else_subrule_widget), None)
                    if subrule:
                        subrule_instance = parse_rule(*subrule)
                        else_val = subrule_instance
                return build_if_else_rule(
                    df, col, operator_selector, param_entry,
                    then_action_type, then_val,
                    else_action_type, else_val
                )

            elif rule_key == "group_if_else_condition":
                op = operator_selector.get()
                raw_thresh = param_entry.get()
                thresh = self._parse_threshold(df, col, op, raw_thresh)
                then_kind = group_then_action_type_widget.get()  # 使用新的 widget
                then_val = None
                if then_kind == "set-group" and then_subrule_widget:
                    sub_rules = [item for item in self.rule_rows if item[0] == then_subrule_widget]
                    if sub_rules:
                        then_val = [parse_rule(*sub_rules[0])]  # 遞迴解析子規則
                    else:
                        raise ValueError("Then 子規則未定義")
                else_kind = group_else_action_type_widget.get()  # 使用新的 widget
                else_val = None
                if else_kind == "set-group" and else_subrule_widget:
                    sub_rules = [item for item in self.rule_rows if item[0] == else_subrule_widget]
                    if sub_rules:
                        else_val = [parse_rule(*sub_rules[0])]  # 遞迴解析子規則
                    else:
                        raise ValueError("Else 子規則未定義")

                return GroupIfElseRule(
                    group_by_cols=list(group_by_cols),  # 傳遞當前的群組欄位
                    target_col=col,
                    operator=op,
                    threshold=thresh,
                    then_action=(then_kind, then_val),
                    else_action=(else_kind, else_val)
                )

            else:
                return build_basic_rule(df, rule_key, col, param_entry)

        # try:
        if True:
            for (
                    row, col_box, op_box, param_entry, group_sel, specific_entry,
                    operator_selector, then_action_type, then_value_widget, else_action_type, else_value_widget,
                    then_subrule, else_subrule, group_then_action_type_widget, group_else_action_type_widget
            ) in self.rule_rows:
                rule = parse_rule(
                    col_box, op_box, param_entry, group_sel, specific_entry,
                    operator_selector, then_action_type, then_value_widget, else_action_type, else_value_widget,
                    then_subrule, else_subrule, group_then_action_type_widget, group_else_action_type_widget
                )
                if rule:
                    rules_to_apply.append(rule)

            # 先應用群組規則，再應用其他規則
            for rule in rules_to_apply:
                if isinstance(rule, GroupIfElseRule):
                    df = rule.apply(df)
            for rule in rules_to_apply:
                if not isinstance(rule, GroupIfElseRule):
                    df = rule.apply(df)

            self.df = df
            messagebox.showinfo("完成", "成功應用所有規則")
            self.refresh_table()
        # except Exception as e:
        else:
            messagebox.showerror("錯誤", str(e))

    def _parse_threshold(self, df, col, op, raw_thresh):
        if op == "similarity >":
            try:
                target, sim_thresh = raw_thresh.split(",")
                return (target.strip(), float(sim_thresh.strip()))
            except Exception:
                raise ValueError("請輸入格式：文字,閾值，例如 Apple,0.85")
        elif pd.api.types.is_numeric_dtype(df[col]):
            try:
                return float(raw_thresh)
            except ValueError:
                raise ValueError("請輸入有效的數值")
        else:
            return raw_thresh


    def show_result(self):
        print(self.df)
        messagebox.showinfo("結果", str(self.df.head()))

class ScrollableFrame(tk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)

        canvas = tk.Canvas(self)
        v_scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        h_scrollbar = tk.Scrollbar(self, orient="horizontal", command=canvas.xview)  # 水平滾動條
        self.scrollable_window = tk.Frame(canvas)

        self.scrollable_window.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_window, anchor="nw")
        canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")  # 水平滾動條放在底部

        self.canvas = canvas
        self.frame = self.scrollable_window


# 主程式入口
if __name__ == "__main__":
    data = [
        {"ORGNAME": "apple", "AC": "Apple", "Score": 0.97},
        {"ORGNAME": "apple", "AC": "Apple", "Score": 0.66},
        {"ORGNAME": "apple", "AC": "APLE", "Score": 0.80},
        {"ORGNAME": "apple", "AC": "APLE", "Score": 0.99},
        {"ORGNAME": "apple", "AC": "APLE", "Score": 0.33},
        {"ORGNAME": "banana", "AC": "Banana", "Score": 0.91},
        {"ORGNAME": "banana", "AC": "Banana", "Score": 0.85},
        {"ORGNAME": "banana", "AC": "BANA", "Score": 0.92},
        {"ORGNAME": "catty", "AC": "CAT", "Score": 1.0},
    ]

    df = pd.DataFrame(data)
    root = tk.Tk()
    app = DynamicExcelEditorGUI(root, df)
    root.mainloop()
