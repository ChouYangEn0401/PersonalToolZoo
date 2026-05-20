import pandas as pd
from abc import ABC, abstractmethod
import threading
from tkinter import filedialog, messagebox, simpledialog


# ----------------- 抽象命令類別 -----------------
class Command(ABC):
    def __init__(self, app):
        self.app = app

    @abstractmethod
    def execute(self):
        pass


# ----------------- 具體命令類別 -----------------
class LoadExcelCommand(Command):
    def execute(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if file_path:
            threading.Thread(target=self._load_threaded, args=(file_path,), daemon=True).start()

    def _load_threaded(self, path):
        self.app.set_progress(indeterminate=True)
        try:
            if len(pd.ExcelFile(path).sheet_names) > 1:
                selected_sheet = self.app.simple_select("選擇工作表", pd.ExcelFile(path).sheet_names)
                if selected_sheet:
                    self.app.df = self.app.data_processor.read_excel_with_sheet(path, selected_sheet)
                else:
                    return
            else:
                self.app.df = self.app.data_processor.read_excel_with_sheet(path)

            self.app.df = self.app.df.astype(str)

            self.app.original_df = self.app.df.copy()
            self.app.refresh_table()
        except Exception as e:
            messagebox.showerror("錯誤", f"載入檔案失敗: {e}")
        finally:
            self.app.set_progress(0)


class SaveExcelCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "沒有資料可供儲存。")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if file_path:
            try:
                self.app.df.to_excel(file_path, index=False)
                messagebox.showinfo("儲存成功", f"檔案已儲存至 {file_path}")
            except Exception as e:
                messagebox.showerror("錯誤", f"儲存檔案失敗: {e}")


class RemoveDuplicateRowsCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        subset = self.app.simple_select_multiple("選擇去重依據的欄位 (可多選)", list(self.app.df.columns))
        if subset:
            new_df, removed_count = self.app.data_processor.remove_duplicates(self.app.df, subset=subset)
            if removed_count > 0:
                self.app.df = new_df
                self.app.refresh_table()
                messagebox.showinfo("完成", f"已刪除 {removed_count} 筆重複的列。")
            else:
                messagebox.showinfo("訊息", "沒有發現重複的列。")


class DeleteColumnsCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return
        cols = self.app.simple_select_multiple("選擇要刪除的欄位", list(self.app.df.columns))
        if cols:
            self.app.df = self.app.data_processor.delete_columns(self.app.df, cols)
            self.app.refresh_table()
            messagebox.showinfo("完成", f"已刪除 {len(cols)} 個欄位。")


class RenameColumnsCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return
        cols = self.app.simple_select_multiple("選擇要重新命名的欄位", list(self.app.df.columns))
        if not cols:
            return
        new_names = {}
        for col in cols:
            new_name = simpledialog.askstring("輸入", f"為「{col}」輸入新名稱", initialvalue=col)
            if new_name:
                new_names[col] = new_name
        if new_names:
            self.app.df = self.app.data_processor.rename_columns(self.app.df, new_names)
            self.app.refresh_table()
            messagebox.showinfo("完成", "欄位已重新命名。")


class ReorderColumnsCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return
        self.app.reorder_columns_dialog()


class MergeAppendCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何主資料。")
            return

        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if not path:
            return

        mode_options = [
            "左合併 (left-merge)", "右合併 (right-merge)", "內合併 (inner-merge)", "外合併 (outer-merge)",
            "直接附加 (append)", "左附加 (left-append)", "右附加 (right-append)",
            "內附加 (inner-append)", "外附加 (outer-append)"
        ]
        selected_mode = self.app.simple_select("選擇合併或附加模式", mode_options)

        df2 = self.app.data_processor.read_excel_with_sheet(path)

        on_cols = None
        if "merge" in selected_mode:
            key1 = self.app.simple_select("主資料的對應欄位", list(self.app.df.columns))
            key2 = self.app.simple_select("合併資料的對應欄位", list(df2.columns))
            on_cols = (key1, key2)

        try:
            self.app.set_progress(indeterminate=True)
            new_df = self.app.data_processor.merge_or_append(self.app.df, df2, selected_mode.split(" ")[0].lower(),
                                                             on_cols)
            self.app.df = new_df
            self.app.refresh_table()
            messagebox.showinfo("完成", "資料合併成功。")
        except Exception as e:
            messagebox.showerror("錯誤", f"合併失敗: {e}")
        finally:
            self.app.set_progress(0)


class DeleteRowsByReferenceCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if not path:
            return

        df2 = None
        self.app.set_progress(indeterminate=True)
        try:
            if len(pd.ExcelFile(path).sheet_names) > 1:
                selected_sheet = self.app.simple_select("選擇工作表", pd.ExcelFile(path).sheet_names)
                if selected_sheet:
                    df2 = self.app.data_processor.read_excel_with_sheet(path)
                else:
                    return
            else:
                df2 = self.app.data_processor.read_excel_with_sheet(path)
            df2 = df2.astype(str)
        except Exception as e:
            messagebox.showerror("錯誤", f"載入檔案失敗 1: {e}")
        finally:
            self.app.set_progress(0)

        mode = self.app.simple_select("選擇比對刪除模式", ["整列完全相同", "指定欄位相同", "手動指定欄位"])

        if df2 is None:
            messagebox.showerror("錯誤", f"載入檔案失敗 2")

        on_cols = None
        messagebox.showerror("錯誤", "此功能經回報似乎有點問題？")
        if mode == "指定欄位相同":
            common_cols = set(self.app.df.columns).intersection(set(df2.columns))
            if not common_cols:
                messagebox.showerror("錯誤", "兩份資料沒有共同欄位可比對。")
                return
            on_cols = self.app.simple_select_multiple("選擇比對欄位", list(common_cols))
            if not on_cols:
                return
        elif mode == "手動指定欄位":
            df_col = self.app.simple_select("選擇目前表格的欄位", list(self.app.df.columns))
            if not df_col:
                return

            df2_col = self.app.simple_select("選擇比對表格的欄位", list(df2.columns))
            if not df2_col:
                return

            on_cols = {df_col: df2_col}

        try:
            new_df, removed_count = self.app.data_processor.remove_rows_by_reference(
                self.app.df, df2, mode, on_cols
            )
            self.app.df = new_df
            self.app.refresh_table()
            messagebox.showinfo("完成", f"已刪除 {removed_count} 筆資料。")
        except Exception as e:
            messagebox.showerror("錯誤", f"刪除失敗: {e}")


class DeleteRowsByIndexCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        # 1. 讓使用者選擇包含索引的檔案
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if not path:
            return

        # 2. 讀取並選擇包含索引的欄位
        index_df = self.app.data_processor.read_excel_with_sheet(path)
        index_col = self.app.simple_select("選擇包含索引的欄位", list(index_df.columns))
        if not index_col:
            return

        # 3. 取得要刪除的索引清單
        indices_to_delete = index_df[index_col].tolist()

        # 4. 執行刪除
        original_count = len(self.app.df)
        try:
            self.app.df = self.app.df.drop(index=indices_to_delete, errors='ignore')
            removed_count = original_count - len(self.app.df)
            self.app.refresh_table()
            messagebox.showinfo("完成", f"已從原始資料中刪除 {removed_count} 筆資料。")
        except Exception as e:
            messagebox.showerror("錯誤", f"刪除失敗: {e}")


class FindDuplicatesInColumnCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        col = self.app.simple_select("選擇要檢查重複值的欄位", list(self.app.df.columns))
        if not col: return

        option = self.app.simple_select("選擇要顯示的資料", ["重複的", "不重複的"])

        target_df = self.app.data_processor.find_duplicates_in_column(self.app.df, col, option)
        summary = f"🔍 檢查欄位：{col}\n📄 顯示筆數：{len(target_df)} / {len(self.app.df)} 筆"
        self.app.show_table(target_df, f"{col} 欄位中 {option} 的資料列", summary)


class CompareColumnsCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        selected = self.app.simple_select_multiple("選擇兩個欄位進行比對", list(self.app.df.columns))
        if len(selected) != 2:
            messagebox.showerror("錯誤", "請選擇恰好兩個欄位。")
            return

        col1, col2 = selected
        option = self.app.simple_select("選擇要顯示的資料", ["相同", "不同"])

        target_df = self.app.data_processor.compare_columns(self.app.df, col1, col2, option)
        summary = f"🔍 比對欄位：{col1} vs {col2}\n📄 顯示筆數：{len(target_df)} / {len(self.app.df)} 筆"
        self.app.show_table(target_df, f"欄位 {col1} 與 {col2} {option} 的列", summary)


class DeleteAllNaNColumnsCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return
        new_df, removed_count = self.app.data_processor.delete_all_nan_columns(self.app.df)
        self.app.df = new_df
        self.app.refresh_table()
        messagebox.showinfo("完成", f"已刪除 {removed_count} 個全為 NaN 的欄位。")


class DeleteAllNaNRowsCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return
        new_df, removed_count = self.app.data_processor.delete_all_nan_rows(self.app.df)
        self.app.df = new_df
        self.app.refresh_table()
        messagebox.showinfo("完成", f"已刪除 {removed_count} 筆全為 NaN 的資料列。")


class DeleteRowsWithNaNInColumnCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return
        col = self.app.simple_select("選擇欄位", list(self.app.df.columns))
        if not col: return

        new_df, removed_count = self.app.data_processor.delete_rows_with_nan_in_column(self.app.df, col)
        self.app.df = new_df
        self.app.refresh_table()
        messagebox.showinfo("完成", f"已刪除 {removed_count} 筆「{col}」欄位為 NaN 的列。")


class DeleteRowsWithNaNInSubsetCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        # 讓使用者選擇欄位子集
        subset_cols = self.app.simple_select_multiple("選擇要檢查 NaN 的欄位 (需全部為 NaN)", list(self.app.df.columns))

        if not subset_cols:
            return

        # 呼叫 data_processor 進行處理
        new_df, removed_count = self.app.data_processor.delete_rows_with_nan_in_subset(self.app.df, subset_cols)

        # 更新 UI 並顯示結果
        self.app.df = new_df
        self.app.refresh_table()
        messagebox.showinfo("完成", f"已刪除 {removed_count} 筆在指定欄位中皆為 NaN 的列。")


class ClearSortCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return
        self.app.df = self.app.original_df.copy()
        self.app.refresh_table()
        self.app.build_sort_controls() # 重建排序 UI
        messagebox.showinfo("完成", "已清除排序，恢復原始順序。")


class AggregateCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        # 1. 選擇分組鍵
        groupby_cols = self.app.simple_select_multiple("選擇分組依據的欄位 (可多選)", list(self.app.df.columns))
        if not groupby_cols:
            return

        # 2. 選擇合併欄位
        agg_cols = self.app.simple_select_multiple("選擇要合併的欄位 (可多選)", [c for c in self.app.df.columns if c not in groupby_cols])
        if not agg_cols:
            messagebox.showwarning("警告", "請選擇要合併的欄位。")
            return

        # 3. 選擇分隔符號
        separator = simpledialog.askstring("輸入分隔符號", "請輸入合併時使用的分隔符號", initialvalue=",")
        if separator is None:
            return

        try:
            self.app.set_progress(indeterminate=True)
            # 呼叫 DataProcessor 執行合併
            new_df, removed_count = self.app.data_processor.aggregate_with_separator(
                self.app.df, groupby_cols, agg_cols, separator
            )
            self.app.df = new_df
            self.app.refresh_table()
            messagebox.showinfo("完成", f"已成功濃縮資料。")
        except Exception as e:
            messagebox.showerror("錯誤", f"資料濃縮失敗: {e}")
        finally:
            self.app.set_progress(0)


class PivotCommand(Command):
    def execute(self):
        if self.app.df.empty:
            messagebox.showwarning("警告", "尚未載入任何資料。")
            return

        # 1. 選擇索引 (新表格的列)
        index_cols = self.app.simple_select_multiple("選擇索引欄位 (可多選)", list(self.app.df.columns))
        if not index_cols:
            return

        # 2. 選擇新欄位名稱的來源欄位
        columns_col = self.app.simple_select("選擇新欄位名稱的來源欄位", [c for c in self.app.df.columns if c not in index_cols])
        if not columns_col:
            messagebox.showwarning("警告", "請選擇轉換成新欄位的來源。")
            return

        # 3. 選擇新欄位的值來源
        values_col = self.app.simple_select("選擇新欄位的值來源", [c for c in self.app.df.columns if c not in index_cols and c != columns_col])
        if not values_col:
            messagebox.showwarning("警告", "請選擇新欄位的值來源。")
            return

        # 4. 選擇聚合函數
        agg_func_options = ["sum", "mean", "count", "min", "max", "first", "last"]
        agg_func = self.app.simple_select("選擇聚合函數", agg_func_options)

        try:
            self.app.set_progress(indeterminate=True)
            new_df = self.app.data_processor.pivot_table(
                self.app.df, index_cols, columns_col, values_col, agg_func
            )
            self.app.df = new_df
            self.app.refresh_table()
            messagebox.showinfo("完成", "已成功建立透視表。")
        except Exception as e:
            messagebox.showerror("錯誤", f"建立透視表失敗: {e}")
        finally:
            self.app.set_progress(0)


# TODO: GroupAndFilterCommand 的邏輯較複雜，需要進一步拆分。
# class GroupAndFilterCommand(Command):
#     def execute(self):
#         ...