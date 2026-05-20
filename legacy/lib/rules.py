from abc import ABC, abstractmethod
import pandas as pd
from remake.M2E1.GUI_ExtendTool.lib.rule_operators import OPERATOR_FUNCTIONS


class BaseRule(ABC):
    @abstractmethod
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        pass
    @abstractmethod
    def describe(self) -> str:
        pass


class LeaveExtremaRule(BaseRule):
    def __init__(self, column, mode="leave_max", group_cols=None):
        self.column = column
        self.mode = mode # "leave_max" or "leave_min"
        self.group_cols = group_cols # 可以為 None，表示整體一組
    def apply(self, df):
        if self.group_cols:
            if self.mode == "leave_max":
                idx = df.groupby(self.group_cols, group_keys=False)[self.column].idxmax()
            elif self.mode == "leave_min":
                idx = df.groupby(self.group_cols, group_keys=False)[self.column].idxmin()
            else:
                raise ValueError(f"Unknown mode: {self.mode}")
        else:
            if self.mode == "leave_max":
                idx = [df[self.column].idxmax()]
            elif self.mode == "leave_min":
                idx = [df[self.column].idxmin()]
            else:
                raise ValueError(f"Unknown mode: {self.mode}")

        return df.loc[idx].reset_index(drop=True)
    def describe(self):
        group_info = f" grouped by {self.group_cols}" if self.group_cols else " without grouping"
        return f"{self.mode.upper()} on '{self.column}'{group_info}"


class LeaveMaxRule(BaseRule):
    def __init__(self, group_by_columns, target_column):
        self.group_by_columns = group_by_columns
        self.target_column = target_column
    def apply(self, df):
        idx = df.groupby(self.group_by_columns)[self.target_column].idxmax()
        return df.loc[idx].reset_index(drop=True)
    def describe(self):
        return f"Leave max value by group {self.group_by_columns} on '{self.target_column}'"
class LeaveMinRule(BaseRule):
    def __init__(self, group_by_columns, target_column):
        self.group_by_columns = group_by_columns
        self.target_column = target_column
    def apply(self, df):
        idx = df.groupby(self.group_by_columns)[self.target_column].idxmin()
        return df.loc[idx].reset_index(drop=True)
    def describe(self):
        return f"Leave min value by group {self.group_by_columns} on '{self.target_column}'"

class FilterGreaterThanRule(BaseRule):
    def __init__(self, column, threshold):
        self.column = column
        self.threshold = threshold
    def apply(self, df):
        # 處理數字類型的情況
        if pd.api.types.is_numeric_dtype(df[self.column]):
            threshold = float(self.threshold)
            condition = df[self.column] > threshold
        else:
            # 處理文字類型的情況，根據字典順序進行比較
            condition = df[self.column].str > str(self.threshold)
        return df[condition].reset_index(drop=True)
    def describe(self):
        return f"Filter '{self.column}' > {self.threshold}"
class FilterSmallerThanRule(BaseRule):
    def __init__(self, column, threshold):
        self.column = column
        self.threshold = threshold
    def apply(self, df):
        # 處理數字類型的情況
        if pd.api.types.is_numeric_dtype(df[self.column]):
            threshold = float(self.threshold)
            condition = df[self.column] < threshold
        else:
            # 處理文字類型的情況，根據字典順序進行比較
            condition = df[self.column].str < str(self.threshold)
        return df[condition].reset_index(drop=True)
    def describe(self):
        return f"Filter '{self.column}' < {self.threshold}"
class FilterEqualsRule(BaseRule):
    def __init__(self, column, value):
        self.column = column
        try:
            self.value = float(value) if '.' in str(value) else int(value)
        except:
            self.value = value
    def apply(self, df):
        return df[df[self.column] == self.value]
    def describe(self):
        return f"Filter '{self.column}' == {self.value}"

class GroupByConditionRule(BaseRule):
    def __init__(self, column, condition_type, condition_value=None):
        self.column = column
        self.condition_type = condition_type
        self.condition_value = condition_value
    def apply(self, df):
        if self.condition_type == "SAME_CONTENT":
            return df
        elif self.condition_type.startswith("SELF_SIMILARITY"):
            from difflib import SequenceMatcher
            threshold = float(self.condition_value) / 100
            groups = []
            seen = set()
            for idx, val in df[self.column].items():
                if idx in seen:
                    continue
                group = [idx]
                seen.add(idx)
                for jdx, cmp in df[self.column].items():
                    if jdx == idx or jdx in seen:
                        continue
                    sim = SequenceMatcher(None, str(val), str(cmp)).ratio()
                    if sim >= threshold:
                        group.append(jdx)
                        seen.add(jdx)
                groups.append(df.loc[group])
            return pd.concat(groups)
        elif self.condition_type == "SPECIFIC_CONTENT":
            return df[df[self.column].isin(self.condition_value)]
        else:
            return df
    def describe(self):
        return f"Group '{self.column}' by {self.condition_type} ({self.condition_value})"

class IfElseRule(BaseRule):
    def __init__(self, column, operator, threshold, then_action, else_action):
        self.column = column
        self.operator = operator
        self.threshold = threshold
        self.then_action = then_action # tuple: (action_type, value or rule)
        self.else_action = else_action # tuple: (action_type, value or rule)

    def apply(self, df):
        if self.operator not in OPERATOR_FUNCTIONS:
            raise ValueError(f"Unknown operator: {self.operator}")
        func = OPERATOR_FUNCTIONS[self.operator]
        condition = func(df[self.column], self.threshold)

        # then / else 動作
        def apply_action(df_subset, action):
            kind, val_or_rule = action
            if kind == "keep":
                return df_subset
            elif kind == "drop":
                return pd.DataFrame(columns=df.columns)
            elif kind == "set":
                df_subset = df_subset.copy()
                df_subset[self.column] = val_or_rule
                return df_subset
            elif isinstance(val_or_rule, BaseRule):
                return val_or_rule.apply(df_subset)
            else:
                raise ValueError(f"Unknown action: {kind}")

        df_true = apply_action(df[condition], self.then_action)
        df_false = apply_action(df[~condition], self.else_action)

        return pd.concat([df_true, df_false], ignore_index=True)
    def describe(self):
        return (
            f"If {self.column} {self.operator} {self.threshold} then "
            f"{self.then_action[0]} {self.then_action[1] if self.then_action[0] == 'set' else ''} "
            f"else {self.else_action[0]} {self.else_action[1] if self.else_action[0] == 'set' else ''}"
        )

class SimilarityGreaterRule(BaseRule):
    def __init__(self, column, target_string, threshold):
        self.column = column
        self.target_string = target_string
        self.threshold = threshold
    def apply(self, df):
        from difflib import SequenceMatcher
        condition = df[self.column].astype(str).apply(
            lambda x: SequenceMatcher(None, x, self.target_string).ratio() > self.threshold
        )
        return df[condition].copy()
    def describe(self):
        return f"保留 {self.column} 與 '{self.target_string}' 相似度大於 {self.threshold}"


from fuzzywuzzy import fuzz
class FuzzySimilarityRule(BaseRule):
    def __init__(self, column, target_string, threshold):
        self.column = column
        self.target_string = target_string
        self.threshold = threshold
    def apply(self, df):
        condition = df[self.column].astype(str).apply(
            lambda x: fuzz.ratio(x, self.target_string) > self.threshold
            # 你之後可透過修改支援：
            #     fuzzy.partial_ratio
            #     token_sort_ratio
            #     token_set_ratio
        )
        return df[condition].copy()
    def describe(self):
        return f"保留 {self.column} 與 '{self.target_string}' 的模糊相似度 > {self.threshold}"


class GroupIfElseRule:
    def __init__(self, group_by_cols, target_col, operator, threshold, then_action, else_action):
        self.group_by_cols = group_by_cols
        self.target_col = target_col
        self.operator = operator
        self.threshold = threshold
        self.then_action = then_action  # (action_type: str, value: Any)
        self.else_action = else_action  # (action_type: str, value: Any)
    def _check_condition(self, val):
        try:
            if self.operator == "==":
                return val == self.threshold
            elif self.operator == "!=":
                return val != self.threshold
            elif self.operator == ">":
                return val > self.threshold
            elif self.operator == "<":
                return val < self.threshold
            elif self.operator == ">=":
                return val >= self.threshold
            elif self.operator == "<=":
                return val <= self.threshold
            else:
                return False
        except:
            return False
    def _apply_action(self, group_df, action_type, action_value):
        if action_type == "keep-group":
            return group_df
        elif action_type == "drop-group":
            return pd.DataFrame(columns=group_df.columns) # 這裡會返回一個空的 DataFrame，但保留了欄位
        elif action_type == "set-group":
            if isinstance(action_value, list):
                temp_df = group_df.copy()
                for sub_rule in action_value:
                    if hasattr(sub_rule, "apply"):
                        temp_df = sub_rule.apply(temp_df)
                    else:
                        raise ValueError("set-group 的子規則無效")
                return temp_df
            else:
                raise ValueError("set-group 的子規則必須是規則列表")
        else:
            raise ValueError(f"未知的 group 動作類型: {action_type}")
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.group_by_cols or self.target_col not in df.columns:
            raise ValueError("GroupIfElseRule 設定不完整")
        grouped = df.groupby(self.group_by_cols, group_keys=False)
        result = []
        for _, group_df in grouped:
            matched = any(self._check_condition(val) for val in group_df[self.target_col])
            if matched:
                result.append(self._apply_action(group_df, *self.then_action))
            else:
                result.append(self._apply_action(group_df, *self.else_action))
        return pd.concat(result, ignore_index=True)
    def describe(self):
        return f"GroupIfElse: if any({self.target_col} {self.operator} {self.threshold}) in group " \
               f"then {self.then_action[0]} else {self.else_action[0]}"



