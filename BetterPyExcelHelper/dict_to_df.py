import pandas as pd

def dict_to_df(data):
    """
    自動判斷 dict 結構並轉成 DataFrame。
    支援兩種格式：
    1. 類似 {"col1": [val1, val2], "col2": [val3, val4]} → 正常 DataFrame
    2. 類似 {"row1": {"col1": val1, "col2": val2}, ...} → from_dict + orient='index'
    3. 單一列資料 {"col1": val1, "col2": val2} → 自動包成 list 處理
    """
    if not isinstance(data, dict):
        raise ValueError("輸入必須是 dict")

    # 類型 2：每個 value 是 dict，表示多行資料（以 key 為 index）
    if all(isinstance(v, dict) for v in data.values()):
        return pd.DataFrame.from_dict(data, orient='index')

    # 類型 3：每個 value 是 scalar，表示單筆資料
    elif all(not isinstance(v, (list, dict)) for v in data.values()):
        return pd.DataFrame([data])

    # 類型 1：每個 value 是 list，正常 DataFrame 格式
    else:
        return pd.DataFrame(data)
