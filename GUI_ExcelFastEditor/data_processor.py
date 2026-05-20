import pandas as pd


class DataProcessor:
    """
    負責所有 Pandas 資料處理的核心邏輯。
    """

    def read_excel_with_sheet(self, path, sheet_name=None):
        try:
            if sheet_name:
                return pd.read_excel(path, sheet_name=sheet_name)
            xls = pd.ExcelFile(path)
            return pd.read_excel(xls, sheet_name=0)
        except Exception as e:
            return None

    def merge_or_append(self, df1, df2, mode, on_cols=None):
        if mode == "append_direct":
            return pd.concat([df1, df2], ignore_index=True)
        elif mode == "append_left":
            common_cols = df1.columns.intersection(df2.columns)
            return pd.concat([df1, df2[common_cols]], ignore_index=True)
        elif mode == "append_right":
            return pd.concat([df1.reindex(columns=df2.columns), df2], ignore_index=True)
        elif mode == "append_inner":
            common_cols = df1.columns.intersection(df2.columns)
            return pd.concat([df1[common_cols], df2[common_cols]], ignore_index=True)
        elif mode == "append_outer":
            return pd.concat([df1, df2], ignore_index=True, sort=False)
        else:
            return pd.merge(df1, df2, left_on=on_cols[0], right_on=on_cols[1], how=mode)

    def remove_duplicates(self, df, subset=None, keep='first'):
        if subset:
            # 依據指定欄位去重
            if not df.duplicated(subset=subset).any():
                return df.copy(), 0
            df = df.copy()
            before_rows = df.shape[0]
            df.drop_duplicates(subset=subset, keep=keep, inplace=True)
            return df, before_rows - df.shape[0]
        else:
            # 整行去重
            if not df.duplicated().any():
                return df.copy(), 0
            df = df.copy()
            before_rows = df.shape[0]
            df.drop_duplicates(inplace=True)
            return df, before_rows - df.shape[0]

    def find_duplicates_in_column(self, df, col, option):
        dup_mask = df.duplicated(subset=[col], keep=False)
        if option == "重複的":
            target_df = df[dup_mask].copy()
        else:
            target_df = df[~dup_mask].copy()

        target_df.insert(0, "原始索引", target_df.index)
        return target_df

    def remove_rows_by_reference(self, df1, df2, mode, on_cols=None):
        before_rows = df1.shape[0]

        result_df = None
        if mode == "整列完全相同":
            merged = df1.merge(df2, how="left", indicator=True)
            result_df = merged[merged["_merge"] == "left_only"].drop(columns="_merge")
        elif mode == "指定欄位相同":
            df_filtered = df1.merge(df2[on_cols].drop_duplicates(),
                                    on=on_cols,
                                    how="left",
                                    indicator=True)
            result_df = df_filtered[df_filtered["_merge"] == "left_only"].drop(columns="_merge")
        elif mode == "手動指定欄位":
            # 取得 df1 和 df2 中需要比對的單一欄位名稱
            df1_col_name = list(on_cols.keys())[0]
            df2_col_name = list(on_cols.values())[0]

            # 為了比對，暫時將 df2 中被選中的欄位重新命名為與 df1 相同
            df2_renamed = df2.rename(columns={df2_col_name: df1_col_name})

            # 執行合併並篩選
            merged = df1.merge(df2_renamed[[df1_col_name]].drop_duplicates(),
                               on=df1_col_name,
                               how="left",
                               indicator=True)
            result_df = merged[merged["_merge"] == "left_only"].drop(columns="_merge")

        removed_count = before_rows - result_df.shape[0]
        return result_df, removed_count

    def compare_columns(self, df, col1, col2, option):
        comparison_result = df[col1].fillna('') == df[col2].fillna('')  # 處理 NaN 值
        if option == "相同":
            target_df = df[comparison_result].copy()
        else:
            target_df = df[~comparison_result].copy()

        target_df.insert(0, "原始索引", target_df.index)
        return target_df

    def delete_columns(self, df, cols_to_delete):
        return df.drop(columns=cols_to_delete)

    def rename_columns(self, df, old_new_names):
        return df.rename(columns=old_new_names)

    def reorder_columns(self, df, new_order):
        return df[new_order]

    def sort_data(self, df, sort_criteria):
        """
        根據排序條件對 DataFrame 進行排序。
        sort_criteria 格式: [{'column': '欄位名', 'ascending': True/False, 'mode': '文字排序'/'數值排序'}]
        """
        # 複製一份 DataFrame，避免影響原始資料
        temp_df = df.copy()

        sort_columns = []
        ascending_list = []

        for crit in sort_criteria:
            col = crit['column']
            ascending = crit['ascending']
            mode = crit['mode']

            # 根據模式轉換資料類型
            if mode == "數值排序":
                # 使用 to_numeric 轉換，errors='coerce' 會將無法轉換的值變成 NaN
                temp_df[col] = pd.to_numeric(temp_df[col], errors='coerce')

            sort_columns.append(col)
            ascending_list.append(ascending)

        # 使用 sort_values 進行多重排序
        return temp_df.sort_values(by=sort_columns, ascending=ascending_list, inplace=False, ignore_index=True, na_position='first')

    def delete_all_nan_columns(self, df):
        before_cols = df.shape[1]
        new_df = df.dropna(axis=1, how='all')
        return new_df, before_cols - new_df.shape[1]

    def delete_all_nan_rows(self, df):
        before_rows = df.shape[0]
        new_df = df.dropna(axis=0, how='all')
        return new_df, before_rows - new_df.shape[0]

    def delete_rows_with_nan_in_column(self, df, column):
        before_rows = df.shape[0]
        new_df = df[df[column].notna()]
        return new_df, before_rows - new_df.shape[0]

    def delete_rows_with_nan_in_subset(self, df, subset_cols):
        before_rows = df.shape[0]
        # 使用 how='all' 確保只刪除所有指定欄位皆為 NaN 的列
        new_df = df.dropna(subset=subset_cols, how='all')
        return new_df, before_rows - new_df.shape[0]

    def aggregate_with_separator(self, df, groupby_cols, agg_cols, separator):
        """
        根據 groupby_cols 進行分組，並將 agg_cols 的值用分隔符號合併。
        """
        before_rows = len(df)

        # 確保 agg_cols 是一個列表
        if not isinstance(agg_cols, list):
            agg_cols = [agg_cols]

        # 創建一個字典，指定每個聚合欄位使用的函數
        agg_dict = {col: lambda x: separator.join(x.astype(str)) for col in agg_cols}

        # 處理其餘非聚合欄位，取第一個值
        other_cols = [col for col in df.columns if col not in groupby_cols and col not in agg_cols]
        for col in other_cols:
            agg_dict[col] = 'first'

        # 執行分組與聚合
        aggregated_df = df.groupby(groupby_cols, as_index=False).agg(agg_dict)

        removed_count = before_rows - len(aggregated_df)
        return aggregated_df, removed_count

    def pivot_table(self, df, index_cols, columns_col, values_col, agg_func):
        """
        創建一個透視表。
        """
        pivoted_df = pd.pivot_table(
            df,
            index=index_cols,
            columns=columns_col,
            values=values_col,
            aggfunc=agg_func
        )
        # 重置索引，讓索引欄位變回一般欄位
        pivoted_df.reset_index(inplace=True)
        # 處理多層級欄位名稱
        pivoted_df.columns = [
            ' '.join(str(s).strip() for s in col if s) for col in pivoted_df.columns.values
        ]
        return pivoted_df
