"""Pure table operations + their registry entries.

Every function here is GUI-free: it takes a DataFrame (and plain params) and
returns a DataFrame. That is what lets the GUI controller and the CLI call the
*same* code. Read-only "query" ops (e.g. find duplicates) also return a table
for display but are not meant to replace the session data.

Phase 1 ships a representative set that exercises every :class:`Param` kind and
both result types. The remaining FastEditor operations (merge-append,
reference-based row deletion, aggregate, …) plug in the same way during the
fill-in phase.
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


def reorder_columns(df, order):
    ordered = [c for c in order if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]


def rename_column(df, column, new_name):
    return df.rename(columns={column: new_name})


# ── row ops ───────────────────────────────────────────────────────────
def dedup(df, subset=None):
    return df.drop_duplicates(subset=(list(subset) if subset else None))


def drop_empty_rows(df):
    return df.dropna(how="all")


def drop_empty_cols(df):
    return df.dropna(axis=1, how="all")


def drop_na_rows_in_column(df, column):
    return df.dropna(subset=[column]) if column in df.columns else df


def sort_values(df, column, ascending=True):
    return df.sort_values(by=column, ascending=ascending, kind="mergesort")


_FILTER_OPS = ("包含", "不包含", "等於", "不等於", "大於", "小於", "為空", "不為空")


def filter_rows(df, column, op, value=""):
    if column not in df.columns:
        return df
    s = df[column]
    if op == "包含":
        mask = s.astype(str).str.contains(str(value), case=False, na=False)
    elif op == "不包含":
        mask = ~s.astype(str).str.contains(str(value), case=False, na=False)
    elif op == "等於":
        mask = s.astype(str) == str(value)
    elif op == "不等於":
        mask = s.astype(str) != str(value)
    elif op == "大於":
        mask = pd.to_numeric(s, errors="coerce") > float(value)
    elif op == "小於":
        mask = pd.to_numeric(s, errors="coerce") < float(value)
    elif op == "為空":
        mask = s.isna()
    elif op == "不為空":
        mask = s.notna()
    else:
        return df
    return df[mask]


# ── read-only queries ─────────────────────────────────────────────────
def find_duplicates(df, column):
    """Rows whose *column* value is duplicated (read-only view)."""
    if column not in df.columns:
        return df.iloc[0:0]
    return df[df.duplicated(subset=[column], keep=False)].sort_values(by=column, kind="mergesort")


# ── reshape ───────────────────────────────────────────────────────────
def pivot(df, index, columns, values, aggfunc="sum"):
    return pd.pivot_table(df, index=index, columns=columns, values=values,
                          aggfunc=aggfunc).reset_index()


# ── registry entries (shared by GUI + CLI) ─────────────────────────────
register(Operation("drop_columns", drop_columns, "刪除欄位",
                   [Param("columns", "columns", "要刪除的欄位")], group="欄位"))
register(Operation("keep_columns", keep_columns, "只保留欄位",
                   [Param("columns", "columns", "要保留的欄位")], group="欄位"))
register(Operation("reorder_columns", reorder_columns, "欄位重排",
                   [Param("order", "columns", "新順序")], group="欄位"))
register(Operation("rename_column", rename_column, "重新命名欄位",
                   [Param("column", "column", "欄位"),
                    Param("new_name", "text", "新名稱")], group="欄位"))

register(Operation("dedup", dedup, "去除重複列",
                   [Param("subset", "columns", "依這些欄位判斷（留空=整列）", required=False)],
                   group="列"))
register(Operation("drop_empty_rows", drop_empty_rows, "刪除整列皆空的列", [], group="列"))
register(Operation("drop_empty_cols", drop_empty_cols, "刪除整欄皆空的欄", [], group="欄位"))
register(Operation("drop_na_rows_in_column", drop_na_rows_in_column, "刪除某欄為空的列",
                   [Param("column", "column", "欄位")], group="列"))
register(Operation("sort_values", sort_values, "排序",
                   [Param("column", "column", "依此欄位"),
                    Param("ascending", "bool", "升冪", default=True)], group="列"))
register(Operation("filter_rows", filter_rows, "篩選",
                   [Param("column", "column", "欄位"),
                    Param("op", "choice", "條件", default="包含", choices=list(_FILTER_OPS)),
                    Param("value", "text", "值", required=False)], group="列"))

register(Operation("find_duplicates", find_duplicates, "檢查某欄重複值",
                   [Param("column", "column", "欄位")], result="query", group="分析"))
register(Operation("pivot", pivot, "建立透視表",
                   [Param("index", "column", "索引欄"),
                    Param("columns", "column", "欄位欄"),
                    Param("values", "column", "值欄"),
                    Param("aggfunc", "choice", "聚合", default="sum",
                          choices=["sum", "mean", "count", "max", "min"])],
                   result="table", group="分析"))
