from remake.M2E1.GUI_ExtendTool.lib.rules import LeaveMaxRule, LeaveMinRule
from remake.M2E1.GUI_ExtendTool.lib.rules import FilterEqualsRule, FilterGreaterThanRule, FilterSmallerThanRule
from remake.M2E1.GUI_ExtendTool.lib.rules import GroupByConditionRule, GroupIfElseRule
from remake.M2E1.GUI_ExtendTool.lib.rules import IfElseRule
from remake.M2E1.GUI_ExtendTool.lib.rules import SimilarityGreaterRule, FuzzySimilarityRule

RULE_REGISTRY = {
    "leave_max": {
        "label": "保留最大值",
        "rule_class": LeaveMaxRule,
        "column_count": 2, # group by column, target column
        "param_count": 0,
        "param_type": []
    },
    "leave_min": {
        "label": "保留最小值",
        "rule_class": LeaveMinRule,
        "column_count": 2,
        "param_count": 0,
        "param_type": []
    },
    "filter_greater_than": {
        "label": "過濾數值 > X",
        "rule_class": FilterGreaterThanRule,
        "column_count": 1,
        "param_count": 1,
        "param_type": "number"
    },
    "filter_smaller_than": {
        "label": "過濾數值 < X",
        "rule_class": FilterSmallerThanRule,
        "column_count": 1,
        "param_count": 1,
        "param_type": "number"
    },
    "filter_equals": {
        "label": "過濾數值 == X",
        "rule_class": FilterEqualsRule,
        "column_count": 1,
        "param_count": 1,
        "param_type": "string_or_number"
    },
    "group_condition": {
        "label": "條件群組",
        "rule_class": GroupByConditionRule,
        "columns": 1,
        "params": 1,
        "param_type": "group_condition_selector"
    },
    "if_else_condition": {
        "rule_class": IfElseRule,
        "param_type": "if_else"
    },
    "similarity >": {
        "label": "相似度大於",
        "rule_class": SimilarityGreaterRule,
        "param_type": "string_similarity",
        "column_count": 1,
        "param_count": 1
    },
    "fuzzy similarity >": {
        "label": "模糊相似度大於",
        "rule_class": FuzzySimilarityRule,
        "param_type": "string_similarity",
        "column_count": 1,
        "param_count": 1
    },
    "group_if_else_condition": {
        "label": "群組條件判斷",
        "rule_class": GroupIfElseRule,
        "param_type": "group_if_else"
    },
}