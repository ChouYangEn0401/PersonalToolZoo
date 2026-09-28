"""Multi-table combine + set operations (GUI-free), for the 合併 tab.

Ported from the old Merger (concat) and TableComparator (交集/差集/聯集). Set ops
operate on the columns common to the participating tables (like the original),
unless an explicit ``on`` list is given.
"""
from __future__ import annotations

from functools import reduce
from typing import List, Optional

import pandas as pd


def _common_cols(dfs: List[pd.DataFrame]) -> list:
    if not dfs:
        return []
    common = set(dfs[0].columns)
    for d in dfs[1:]:
        common &= set(d.columns)
    # preserve first table's column order
    return [c for c in dfs[0].columns if c in common]


def concat_all(dfs: List[pd.DataFrame], mode: str = "append_direct",
               drop_duplicates: bool = False) -> pd.DataFrame:
    """Stack multiple tables. mode: append_direct (union of columns) or
    append_inner (only common columns)."""
    if not dfs:
        return pd.DataFrame()
    if mode == "append_inner":
        cols = _common_cols(dfs)
        out = pd.concat([d[cols] for d in dfs], ignore_index=True)
    else:
        out = pd.concat(dfs, ignore_index=True, sort=False)
    if drop_duplicates:
        out = out.drop_duplicates(ignore_index=True)
    return out


def union(dfs: List[pd.DataFrame], on: Optional[list] = None,
          drop_duplicates: bool = True) -> pd.DataFrame:
    cols = on or _common_cols(dfs)
    out = pd.concat([d[cols] for d in dfs], ignore_index=True)
    return out.drop_duplicates(ignore_index=True) if drop_duplicates else out


def intersection(dfs: List[pd.DataFrame], on: Optional[list] = None) -> pd.DataFrame:
    if not dfs:
        return pd.DataFrame()
    cols = on or _common_cols(dfs)
    frames = [d[cols].drop_duplicates() for d in dfs]
    return reduce(lambda a, b: pd.merge(a, b, on=cols, how="inner"), frames).reset_index(drop=True)


def difference(main: pd.DataFrame, others: List[pd.DataFrame],
               on: Optional[list] = None) -> pd.DataFrame:
    """Rows of *main* not present in any of *others* (on common/selected cols)."""
    cols = on or _common_cols([main] + list(others))
    if not others:
        return main[cols].drop_duplicates(ignore_index=True)
    sub = pd.concat([d[cols] for d in others], ignore_index=True).drop_duplicates()
    merged = pd.merge(main[cols].drop_duplicates(), sub, on=cols, how="left", indicator=True)
    return merged[merged["_merge"] == "left_only"].drop(columns="_merge").reset_index(drop=True)
