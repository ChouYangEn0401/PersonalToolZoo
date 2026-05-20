import pandas as pd
from typing import Literal, List, Any, Type
from openpyxl.cell.rich_text import CellRichText
import numpy as np

## Cell Data Fetcher
def get_value_from_cell(
        sheet,
        row: int, col: int,
        expected_value: str = None, none_value_replacement=None,
        expected_type: Type = None,
    ) -> str:
    """
    從儲存格取得資料，並檢查值與型別是否符合預期。
    :param sheet: openpyxl 工作表
    :param row: 儲存格的列號（從1開始）
    :param col: 儲存格的欄號（從1開始）
    :param expected_value: 預期的儲存格內容值
    :param expected_type: 預期的儲存格內容型別
    :return: 儲存格的資料
    :raises: ValueError 或 TypeError 若資料不符合預期
    """
    val = sheet.cell(row=row, column=col).value

    # 如果是 CellRichText，直接轉換為字符串
    if isinstance(val, CellRichText):
        val = str(val)  # CellRichText 可以轉換為字符串

    if expected_value is not None and val != expected_value:
        raise ValueError(f"Cell ({row}, {col}) content does not match expected: '{expected_value}' vs now= '{val}'")

    if val is None and none_value_replacement is not None:
        val = none_value_replacement
    if expected_type is not None and type(val) != expected_type:
        raise TypeError(f"Cell ({row}, {col}) content's type does not match expected: '{expected_type}' vs now= '{type(val)}'")

    return expected_type(val) if expected_type is not None else val

def get_number_from_column_letter(col_letter: str) -> int:
    """
    將 Excel 欄位字母轉換為對應的數字編號
    """
    col_letter = col_letter.upper()
    result = 0
    for char in col_letter:
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result
def get_column_letter_from_value(col_number: int) -> str:
    """
    將 Excel 欄位數字轉換為對應的字母（例如 1 → 'A', 28 → 'AB'）
    """
    result = ""
    while col_number > 0:
        col_number -= 1
        result = chr(col_number % 26 + ord('A')) + result
        col_number //= 26
    return result

def multiple_sort_dataframe(
        df: pd.DataFrame,
        sort_by_cols: List[str], sorting_orders: List[Literal["a->z", "z->a", "custom"]] = None,
        custom_orders: List[List[Any]] = None
    ) -> pd.DataFrame:
    """
    根據指定的排序順序對 DataFrame 的多個欄位進行排序。

    Args:
        df (pd.DataFrame): 要排序的 DataFrame。
        sort_by_cols (List[str]): 要排序的欄位名稱列表。
        sorting_orders (List[Literal["a->z", "z->a", "custom"]], optional): 每個欄位的排序順序。
            sorting_order (Literal["a->z", "z->a", "custom"]): 排序順序。
                - "a->z": 升序 (預設)。
                - "z->a": 降序。
                - "custom": 使用 custom_order 進行自定義排序。
        custom_orders (List[List[str]], optional): 如果某個欄位需要自定義排序，則提供該欄位的自定義排序列表。
            當 sorting_order 為 "custom" 時必須提供。預設為 None。

    Returns:
        pd.DataFrame: 根據指定順序排序後的 DataFrame。
    """
    if len(sort_by_cols) != len(sorting_orders):
        print("錯誤：排序欄位數量與排序順序不匹配。返回原始 DataFrame。")
        return df

    for col in sort_by_cols:
        if col not in df.columns:
            print(f"警告：DataFrame 中沒有 '{col}' 欄位，無法進行排序。返回原始 DataFrame。")
            return df

    ascending = []
    for i, order in enumerate(sorting_orders):
        if order == "a->z":
            ascending.append(True)
        elif order == "z->a":
            ascending.append(False)
        elif order == "custom":
            if custom_orders is None or custom_orders[i] is None:
                print(f"錯誤：當 sorting_order 為 'custom' 時，必須提供 custom_order。返回原始 DataFrame。")
                return df
            else:
                # 自定義排序處理
                unique_values = df[sort_by_cols[i]].unique().tolist()
                if set(unique_values) - set(custom_orders[i]):
                    print(f"警告：custom_order 並未包含排序欄位 '{sort_by_cols[i]}' 的所有唯一值，排序結果可能不完整。")
                # 處理 NaN 值
                categorical_series = pd.Categorical(df[sort_by_cols[i]], categories=custom_orders[i], ordered=True)
                df[sort_by_cols[i]] = categorical_series
                ascending.append(True)  # 'custom' 排序也是升序的處理
        else:
            print(f"錯誤：未知的 sorting_order: '{order}'。請使用 'a->z', 'z->a' 或 'custom'。返回原始 DataFrame。")
            return df

    sorted_df = df.sort_values(by=sort_by_cols, ascending=ascending)
    return sorted_df
def sort_dataframe(df: pd.DataFrame, sort_by_col: str, sorting_order: Literal["a->z", "z->a", "custom"] = "a->z", custom_order: List[str] = None) -> pd.DataFrame:
    return multiple_sort_dataframe(df, [sort_by_col], [sorting_order], [custom_order])

def pick_and_reorder_then_rename_columns(df: pd.DataFrame, select_columns: list, rename_columns: dict = None) -> pd.DataFrame:
    """
    選擇指定的列並重新命名。選擇列的順序即為最終列的順序。

    Args:
        df: 要處理的 pandas DataFrame。
        select_columns: 一個列表，指定要保留的列及其順序。
        rename_columns: 一個字典，用於指定要重新命名的列，鍵是舊列名，值是新列名。默認為 None。

    Returns:
        處理後的 pandas DataFrame。
    """
    processed_df = df.copy()

    # 1. 選擇指定的列 (順序由 select_columns 決定)
    existing_select_columns = [col for col in select_columns if col in processed_df.columns]
    processed_df = processed_df[existing_select_columns]

    # 2. 重新命名列
    if rename_columns:
        # 確保 rename_columns 中的鍵存在於選定的列中
        columns_to_rename = {old: new for old, new in rename_columns.items() if old in processed_df.columns}
        processed_df = processed_df.rename(columns=columns_to_rename)

    return processed_df


if __name__=="__main__":
    data = {
        'name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve'],
        'age': [25, 30, 25, 30, 28],
    }
    df = pd.DataFrame(data)

    # 使用 sort_dataframe 函數對 `age` 排序
    sorted_df = sort_dataframe(df, sort_by_col='age', sorting_order='a->z')
    print("#1", sorted_df, '\n')

    # 然後對 `name` 進行排序
    sorted_df = sort_dataframe(sorted_df, sort_by_col='name', sorting_order='a->z')
    print("#2", sorted_df, '\n')

    # 顯示多重排序
    sorted_df = multiple_sort_dataframe(sorted_df, sort_by_cols=['age', 'name'], sorting_orders=['custom', 'z->a'], custom_orders=[[25, 30, 28], None])
    print("#3", sorted_df, '\n')

