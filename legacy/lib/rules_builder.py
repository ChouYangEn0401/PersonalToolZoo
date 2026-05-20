from remake.M2E1.GUI_ExtendTool.lib.rule_definitions import *
import pandas as pd
from tkinter import ttk
from remake.M2E1.GUI_ExtendTool.lib.rules import GroupByConditionRule, LeaveExtremaRule

def build_leave_rule(rule_key, group_by_cols, column):
    if group_by_cols:
        group_cols = group_by_cols
    else:
        # 沒有群組欄位時，視整體為一組（單一 group）
        return LeaveExtremaRule(column, rule_key, group_cols=None)
    return LeaveExtremaRule(column, rule_key, group_cols=group_cols)

def build_group_condition_rule(col, group_sel, param_entry, specific_entry):
    condition = group_sel.get()
    if condition == "SAME_CONTENT":
        return GroupByConditionRule(col, "SAME_CONTENT"), [col]
    elif condition == "SELF_SIMILARITY":
        val = float(param_entry.get())
        return GroupByConditionRule(col, "SELF_SIMILARITY", val), [col]
    elif condition == "SPECIFIC_CONTENT":
        vals = [v.strip() for v in specific_entry.get().split(",")]
        return GroupByConditionRule(col, "SPECIFIC_CONTENT", vals), [col]
    else:
        raise ValueError(f"未知的 group_condition: {condition}")

def build_rule_from_widget(value_widget):
    # 根據 widget 的值返回一個具體的規則對象
    if isinstance(value_widget, ttk.Combobox):  # 假設這是一個規則選擇器
        rule_key = value_widget.get()
        rule_class = RULE_REGISTRY[rule_key]["rule_class"]
        # 根據需要的參數進行構建，這裡的邏輯根據具體需要調整
        return rule_class()
    return None

def build_if_else_rule(df, col, operator_selector, param_entry, then_action_type, then_value, else_action_type, else_value):
    op = operator_selector.get()
    raw_thresh = param_entry.get()

    if col not in df.columns:
        print(f"警告：欄位 '{col}' 不存在於 DataFrame 中，跳過此 if-else 規則。")
        return None  # 返回 None 表示此規則無效

    if op == "similarity >":
        try:
            target, sim_thresh = raw_thresh.split(",")
            thresh = (target.strip(), float(sim_thresh.strip()))
        except Exception:
            raise ValueError("請輸入格式：文字,閾值，例如 Apple,0.85")
    elif pd.api.types.is_numeric_dtype(df[col]):
        try:
            thresh = float(raw_thresh)
        except ValueError:
            raise ValueError("請輸入有效的數值閾值")
    else:
        thresh = raw_thresh

    then_kind = then_action_type.get()  # 這行是出錯的地方
    else_kind = else_action_type.get()  # 這行也可能出錯
    then_val = then_value if then_kind == "set" else None
    else_val = else_value if else_kind == "set" else None

    # ... (處理 'rule' 動作的部分保持不變) ...

    return IfElseRule(col, op, thresh, (then_kind, then_val), (else_kind, else_val))


def build_basic_rule(df, rule_key, column, param_entry):
    rule_info = RULE_REGISTRY[rule_key]
    rule_class = rule_info["rule_class"]
    param_type = rule_info.get("param_type", "string_or_number")

    if param_type == "string_similarity":
        # 使用格式: Apple,0.85
        try:
            raw = param_entry.get()
            target, threshold = raw.split(",")
            return rule_class(column, target.strip(), float(threshold.strip()))
        except Exception:
            raise ValueError("請輸入格式為 '目標文字,閾值'，例如 Apple,0.85")
    else:
        param = param_entry.get()
        return rule_class(column, param)


def build_group_if_else_rule(
    df,
    group_by_cols,
    col, operator_selector, param_entry,
    then_action_type, then_value,
    else_action_type, else_value
):
    op = operator_selector.get()
    raw_thresh = param_entry.get()

    # 解析閾值
    if pd.api.types.is_numeric_dtype(df[col]):
        try:
            thresh = float(raw_thresh)
        except ValueError:
            raise ValueError("請輸入有效的數值閾值")
    else:
        thresh = raw_thresh

    # 處理 THEN 動作
    then_kind = then_action_type.get()
    if then_kind == "set-group":
        then_val = then_value  # 是一個子規則 widget，稍後 parse
    else:
        then_val = None

    # 處理 ELSE 動作
    else_kind = else_action_type.get()
    if else_kind == "set-group":
        else_val = else_value
    else:
        else_val = None

    # 組成 rule
    return GroupIfElseRule(
        group_by_cols=group_by_cols,
        target_col=col,
        operator=op,
        threshold=thresh,
        then_action=(then_kind, then_val),
        else_action=(else_kind, else_val)
    )

