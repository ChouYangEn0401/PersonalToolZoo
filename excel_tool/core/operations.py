"""Pure table operations + registry entries — the full FastEditor-parity set.

Every function is GUI-free (DataFrame in, DataFrame out) so the GUI controller,
the CLI and any external script call the *same* code. Logic is ported faithfully
from the original GUI_ExcelFastEditor/data_processor.py, with a few additions
(generic row filter). Multi-criteria sort and rule cleaning have bespoke UIs and
live in their own modules; the rest are registered here with param specs so the
GUI dialog and the CLI can be generated from one source of truth.
"""
from __future__ import annotations

import pandas as pd

from .registry import Operation, Param, register


# ── column ops ────────────────────────────────────────────────────────
def drop_columns(df, columns):
    return df.drop(columns=[c for c in columns if c in df.columns], errors="ignore")


def keep_columns(df, columns):
    keep = [c for c in columns if c in df.columns]
    return df[keep] if keep else df


def rename_columns(df, mapping):
    return df.rename(columns=dict(mapping))


def reorder_columns(df, order):
    ordered = [c for c in order if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]


def drop_all_nan_columns(df):
    return df.dropna(axis=1, how="all")


# ── row ops ───────────────────────────────────────────────────────────
def dedup(df, subset=None, keep="first"):
    return df.drop_duplicates(subset=(list(subset) if subset else None), keep=keep)


def drop_all_nan_rows(df):
    return df.dropna(axis=0, how="all")


def drop_nan_rows_in_column(df, column):
    return df[df[column].notna()] if column in df.columns else df


def drop_nan_rows_in_subset(df, subset):
    # remove rows where ALL the given columns are NaN (faithful to how='all')
    cols = [c for c in subset if c in df.columns]
    return df.dropna(subset=cols, how="all") if cols else df


_FILTER_OPS = ("包含", "不包含", "等於", "不等於", "大於", "小於", "為空", "不為空")


def _cond_mask(df, column, op, value=""):
    """Boolean mask for a single condition (shared by filter + condition-clean)."""
    s = df[column]
    if op == "包含":
        return s.astype(str).str.contains(str(value), case=False, na=False)
    if op == "不包含":
        return ~s.astype(str).str.contains(str(value), case=False, na=False)
    if op == "等於":
        return s.astype(str) == str(value)
    if op == "不等於":
        return s.astype(str) != str(value)
    if op == "大於":
        return pd.to_numeric(s, errors="coerce") > float(value)
    if op == "小於":
        return pd.to_numeric(s, errors="coerce") < float(value)
    if op == "為空":
        return s.isna()
    if op == "不為空":
        return s.notna()
    return pd.Series(True, index=df.index)


def filter_rows(df, column, op, value=""):
    if column not in df.columns:
        return df
    return df[_cond_mask(df, column, op, value)]


def clean_by_conditions(df, conditions, combine="AND", action="keep"):
    """Multi-condition clean. conditions: list of {'column','op','value'}.
    combine: 'AND'/'OR'; action: 'keep'/'drop' the rows that match."""
    conds = [c for c in conditions if c.get("column") in df.columns]
    if not conds:
        return df
    masks = [_cond_mask(df, c["column"], c["op"], c.get("value", "")) for c in conds]
    combined = masks[0]
    for m in masks[1:]:
        combined = (combined & m) if combine == "AND" else (combined | m)
    return df[combined] if action == "keep" else df[~combined]


def leave_group_extreme(df, group_by, column, which="max"):
    """Keep only the rows whose *column* equals the per-group max/min."""
    if column not in df.columns or not group_by:
        return df
    vals = pd.to_numeric(df[column], errors="coerce")
    ext = vals.groupby([df[c] for c in group_by]).transform("max" if which == "max" else "min")
    return df[vals == ext]


def sort_values_multi(df, criteria):
    """criteria: list of {'column','ascending':bool,'mode':'文字排序'|'數值排序'}."""
    tmp = df.copy()
    cols, asc = [], []
    for crit in criteria:
        col = crit["column"]
        if crit.get("mode") == "數值排序":
            tmp[col] = pd.to_numeric(tmp[col], errors="coerce")
        cols.append(col)
        asc.append(bool(crit.get("ascending", True)))
    if not cols:
        return df
    return tmp.sort_values(by=cols, ascending=asc, ignore_index=True, na_position="first")


# ── read-only queries ─────────────────────────────────────────────────
def find_duplicates_in_column(df, column, which="重複的"):
    if column not in df.columns:
        return df.iloc[0:0]
    dup_mask = df.duplicated(subset=[column], keep=False)
    target = df[dup_mask] if which == "重複的" else df[~dup_mask]
    target = target.copy()
    target.insert(0, "原始索引", target.index)
    return target


def compare_two_columns(df, col1, col2, which="不同"):
    if col1 not in df.columns or col2 not in df.columns:
        return df.iloc[0:0]
    same = df[col1].fillna("") == df[col2].fillna("")
    target = df[same] if which == "相同" else df[~same]
    target = target.copy()
    target.insert(0, "原始索引", target.index)
    return target


# ── reshape ───────────────────────────────────────────────────────────
def aggregate_with_separator(df, group_by, agg_columns, separator=","):
    agg_cols = list(agg_columns)
    agg_dict = {col: (lambda x: separator.join(x.astype(str))) for col in agg_cols}
    other = [c for c in df.columns if c not in group_by and c not in agg_cols]
    for col in other:
        agg_dict[col] = "first"
    return df.groupby(list(group_by), as_index=False).agg(agg_dict)


def pivot(df, index, columns, values, aggfunc="sum"):
    p = pd.pivot_table(df, index=index, columns=columns, values=values, aggfunc=aggfunc)
    p.reset_index(inplace=True)
    p.columns = [" ".join(str(s).strip() for s in col if s) if isinstance(col, tuple) else str(col)
                 for col in p.columns.values]
    return p


# ── two-table ops (need `other` DataFrame) ────────────────────────────
def merge_append(df, other, mode="append_direct", on=None):
    if mode == "append_direct":
        return pd.concat([df, other], ignore_index=True)
    if mode == "append_inner":
        common = df.columns.intersection(other.columns)
        return pd.concat([df[common], other[common]], ignore_index=True)
    if mode == "append_outer":
        return pd.concat([df, other], ignore_index=True, sort=False)
    # join: mode in inner/left/right/outer, on = [left_key, right_key]
    keys = on or []
    lk = keys[0] if keys else df.columns[0]
    rk = keys[1] if len(keys) > 1 else lk
    return pd.merge(df, other, left_on=lk, right_on=rk, how=mode)


def delete_rows_by_reference(df, other, mode="指定欄位相同", on=None):
    if mode == "整列完全相同":
        merged = df.merge(other, how="left", indicator=True)
        return merged[merged["_merge"] == "left_only"].drop(columns="_merge")
    if mode == "指定欄位相同":
        cols = on or []
        keep = df.merge(other[cols].drop_duplicates(), on=cols, how="left", indicator=True)
        return keep[keep["_merge"] == "left_only"].drop(columns="_merge")
    # 手動指定欄位: on = {left_col: right_col}
    mapping = dict(on or {})
    lcol, rcol = next(iter(mapping.items()))
    other2 = other.rename(columns={rcol: lcol})
    merged = df.merge(other2[[lcol]].drop_duplicates(), on=lcol, how="left", indicator=True)
    return merged[merged["_merge"] == "left_only"].drop(columns="_merge")


# ── registry (shared by GUI + CLI) ────────────────────────────────────
def _reg():
    register(Operation("drop_columns", drop_columns, "刪除欄位",
                       [Param("columns", "columns", "要刪除的欄位")], group="欄位"))
    register(Operation("keep_columns", keep_columns, "只保留欄位",
                       [Param("columns", "columns", "要保留的欄位")], group="欄位"))
    register(Operation("rename_columns", rename_columns, "重新命名欄位",
                       [Param("mapping", "mapping", "欄位改名（舊→新）")], group="欄位"))
    register(Operation("reorder_columns", reorder_columns, "欄位重新排序",
                       [Param("order", "columns", "新順序")], group="欄位"))
    register(Operation("drop_all_nan_columns", drop_all_nan_columns, "刪除全為空的欄", [], group="欄位"))

    register(Operation("dedup", dedup, "刪除重複列",
                       [Param("subset", "columns", "依這些欄位判斷（留空=整列）", required=False)],
                       group="列"))
    register(Operation("drop_all_nan_rows", drop_all_nan_rows, "刪除全為空的列", [], group="列"))
    register(Operation("drop_nan_rows_in_column", drop_nan_rows_in_column, "刪除某欄為空的列",
                       [Param("column", "column", "欄位")], group="列"))
    register(Operation("drop_nan_rows_in_subset", drop_nan_rows_in_subset, "刪除指定欄位皆為空的列",
                       [Param("subset", "columns", "這些欄位皆空才刪")], group="列"))
    register(Operation("filter_rows", filter_rows, "篩選列",
                       [Param("column", "column", "欄位"),
                        Param("op", "choice", "條件", default="包含", choices=list(_FILTER_OPS)),
                        Param("value", "text", "值", required=False)], group="列"))

    register(Operation("find_duplicates_in_column", find_duplicates_in_column, "檢查某欄重複值",
                       [Param("column", "column", "欄位"),
                        Param("which", "choice", "顯示", default="重複的", choices=["重複的", "不重複的"])],
                       result="query", group="分析"))
    register(Operation("compare_two_columns", compare_two_columns, "兩欄位比對",
                       [Param("col1", "column", "欄位1"), Param("col2", "column", "欄位2"),
                        Param("which", "choice", "顯示", default="不同", choices=["不同", "相同"])],
                       result="query", group="分析"))

    register(Operation("leave_group_extreme", leave_group_extreme, "保留分組極值",
                       [Param("group_by", "columns", "分組欄位"),
                        Param("column", "column", "比較欄位（數值）"),
                        Param("which", "choice", "保留", default="max", choices=["max", "min"])],
                       group="清理"))

    register(Operation("aggregate_with_separator", aggregate_with_separator, "合併濃縮資料",
                       [Param("group_by", "columns", "分組欄位"),
                        Param("agg_columns", "columns", "要合併的欄位"),
                        Param("separator", "text", "分隔符號", default=",")],
                       group="重塑", help="aggregate"))
    register(Operation("pivot", pivot, "建立透視表",
                       [Param("index", "columns", "索引欄"),
                        Param("columns", "column", "欄位欄"),
                        Param("values", "column", "值欄"),
                        Param("aggfunc", "choice", "聚合", default="sum",
                              choices=["sum", "mean", "count", "max", "min"])],
                       group="重塑", help="pivot"))

    register(Operation("merge_append", merge_append, "合併資料表（另一檔）",
                       [Param("other", "table", "另一份資料"),
                        Param("mode", "choice", "方式", default="append_direct",
                              choices=["append_direct", "append_inner", "append_outer",
                                       "inner", "left", "right", "outer"]),
                        Param("on", "columns", "join 鍵（左,右；append 免填）", required=False)],
                       group="雙表"))
    register(Operation("delete_rows_by_reference", delete_rows_by_reference, "依另一份資料刪列",
                       [Param("other", "table", "參考資料"),
                        Param("mode", "choice", "比對方式", default="指定欄位相同",
                              choices=["整列完全相同", "指定欄位相同"]),
                        Param("on", "columns", "指定欄位（mode=指定欄位相同）", required=False)],
                       group="雙表"))


_reg()
