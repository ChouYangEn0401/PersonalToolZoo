import pandas as pd
import re
from difflib import SequenceMatcher

def op_eq(series, val): return series == val
def op_neq(series, val): return series != val
def op_gt(series, val): return series > val
def op_lt(series, val): return series < val
def op_ge(series, val): return series >= val
def op_le(series, val): return series <= val
def op_is_unique(series, _): return ~series.duplicated(keep=False)
def op_is_not_unique(series, _): return series.duplicated(keep=False)
def op_is_nan(series, _): return series.isna()
def op_is_not_nan(series, _): return ~series.isna()
def op_is_str(series, _): return series.apply(lambda x: isinstance(x, str))
def op_is_number(series, _): return series.apply(lambda x: isinstance(x, (int, float)))
def op_contains(series, val): return series.astype(str).str.contains(str(val), na=False)
def op_startswith(series, val): return series.astype(str).str.startswith(str(val), na=False)
def op_endswith(series, val): return series.astype(str).str.endswith(str(val), na=False)
def op_regex(series, val): return series.astype(str).str.contains(val, na=False, regex=True)
def op_similarity_gt(series, val): # val 是 (target_string, threshold)
    target, thresh = val
    return series.astype(str).apply(lambda x: SequenceMatcher(None, x, target).ratio() > thresh)

OPERATOR_FUNCTIONS = {
    "==": op_eq,
    "!=": op_neq,
    ">": op_gt,
    "<": op_lt,
    ">=": op_ge,
    "<=": op_le,
    "is unique": op_is_unique,
    "is not unique": op_is_not_unique,
    "is nan": op_is_nan,
    "is not nan": op_is_not_nan,
    "is str": op_is_str,
    "is number": op_is_number,
    "contains": op_contains,
    "startswith": op_startswith,
    "endswith": op_endswith,
    "regex": op_regex,
    "similarity >": op_similarity_gt,
}

