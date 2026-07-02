"""Pure diff computation for the 比對雙檔 tab (GUI-free, headless-testable).

Reproduces the three modes of the old GUI_ExcelDiffVisualizationTool:
  compute_single   — merged one-table diff
  compute_neighbor — interleaved L:col / R:col
  compute_two_side — two aligned tables + change-type styling

Each returns plain-text DataFrame(s) plus a ``{(row_position, col_name): style}``
map that the GUI colouring layer applies to the visible label pool.
"""
from __future__ import annotations

import pandas as pd

KEY_COL = "主鍵"

# ── colours ───────────────────────────────────────────────────────────
WHITE = "#ffffff"
DELETED_BG = "#ffdddd"
ADDED_BG = "#ddffdd"
MODIFIED_BG = "#ffffcc"
GREY_BG = "#dddddd"
L_HEADER = "#d0e0ff"
R_HEADER = "#ffe0d0"
CHANGED_HEADER = "#fdf3d0"
DEFAULT_HEADER = "#dddddd"

# Two-Side per-change-type styles (bg + fg + optional font), faithful to the
# original GUI_ExcelDiffVisualizationTool STYLE table.
M3 = {
    "added":       {"bg": "#cfc", "fg": "#008800", "font": ("TkDefaultFont", 11, "bold")},
    "deleted":     {"bg": "#fcc", "fg": "#aa0000", "font": ("TkDefaultFont", 11, "bold")},
    "grey":        {"bg": "#eee", "fg": "#999999"},
    "changed":     {"bg": "#ddf", "fg": "#0000ff", "font": ("TkDefaultFont", 11, "bold")},
    "identical":   {"bg": "#fff9cc", "fg": "#cc8800"},
    "na_added":    {"bg": "#287f5d", "fg": "#98ea60", "font": ("TkDefaultFont", 11, "bold", "underline")},
    "na_deleted":  {"bg": "#9a4037", "fg": "#ff3333", "font": ("TkDefaultFont", 11, "bold", "underline")},
    "left_changed": {"bg": "#eef", "fg": "#000000", "font": ("TkDefaultFont", 11, "bold")},
    "default":     {"bg": WHITE, "fg": "#000000"},
}


def _is_empty(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v) == ""


def _txt(v) -> str:
    return "" if _is_empty(v) else str(v)


def prep(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Index by *key*; drop empty-key rows and de-dup keys (avoids .at multi-hit)."""
    out = df.copy().dropna(subset=[key])
    if out[key].astype(str).duplicated().any():
        out = out.drop_duplicates(subset=[key], keep="first")
    out = out.set_index(key)
    out.index = out.index.astype(str)
    return out


def _keys(L, R):
    return [str(k) for k in L.index.union(R.index)]


def _cols(L, R):
    return [c for c in L.columns.union(R.columns)]


def compute_single(dfl, dfr, key_l, key_r):
    L, R = prep(dfl, key_l), prep(dfr, key_r)
    keys, cols = _keys(L, R), _cols(L, R)
    styles, rows = {}, []
    for i, k in enumerate(keys):
        rec = {KEY_COL: k}
        for col in cols:
            vl = L.at[k, col] if (k in L.index and col in L.columns) else None
            vr = R.at[k, col] if (k in R.index and col in R.columns) else None
            tl, tr = _txt(vl), _txt(vr)
            if tl != tr:
                if tl and not tr:
                    rec[col] = tl; styles[(i, col)] = {"bg": DELETED_BG}
                elif not tl and tr:
                    rec[col] = tr; styles[(i, col)] = {"bg": ADDED_BG}
                else:
                    rec[col] = f"{tl[:8]} → {tr[:8]}"; styles[(i, col)] = {"bg": MODIFIED_BG}
            else:
                rec[col] = tl
        rows.append(rec)
    return pd.DataFrame(rows, columns=[KEY_COL] + cols), styles, {}


def compute_neighbor(dfl, dfr, key_l, key_r):
    L, R = prep(dfl, key_l), prep(dfr, key_r)
    keys, cols = _keys(L, R), _cols(L, R)
    out_cols, header = [KEY_COL], {}
    for col in cols:
        lc, rc = f"L:{col}", f"R:{col}"
        out_cols += [lc, rc]
        header[lc], header[rc] = {"bg": L_HEADER}, {"bg": R_HEADER}
    styles, rows = {}, []
    for i, k in enumerate(keys):
        only_left = k in L.index and k not in R.index
        only_right = k in R.index and k not in L.index
        row_bg = GREY_BG if (only_left or only_right) else WHITE
        rec = {KEY_COL: k}
        if row_bg != WHITE:
            styles[(i, KEY_COL)] = {"bg": row_bg}
        for col in cols:
            vl = L.at[k, col] if (k in L.index and col in L.columns) else None
            vr = R.at[k, col] if (k in R.index and col in R.columns) else None
            tl, tr = _txt(vl), _txt(vr)
            lc, rc = f"L:{col}", f"R:{col}"
            rec[lc], rec[rc] = tl, tr
            if tl != tr:
                if tl and tr:
                    bl = br = MODIFIED_BG
                elif tl and not tr:
                    bl, br = DELETED_BG, GREY_BG
                else:
                    bl, br = GREY_BG, ADDED_BG
            else:
                bl = br = row_bg
            if bl != WHITE:
                styles[(i, lc)] = {"bg": bl}
            if br != WHITE:
                styles[(i, rc)] = {"bg": br}
        rows.append(rec)
    return pd.DataFrame(rows, columns=out_cols), styles, header


def _visible(change_type, toggles):
    return toggles.get(change_type, True)


def compute_two_side(L, R, toggles):
    """L, R already prep()'d (indexed by key). Returns
    (left_df, right_df, left_styles, right_styles, header_styles, changed_cols)."""
    keys, cols = _keys(L, R), _cols(L, R)
    added = set(R.index) - set(L.index)
    deleted = set(L.index) - set(R.index)
    inter = set(L.index) & set(R.index)

    diff_cells = {}
    for k in inter:
        for col in cols:
            vl = L.at[k, col] if col in L.columns else None
            vr = R.at[k, col] if col in R.columns else None
            el, er = _is_empty(vl), _is_empty(vr)
            if el and not er:
                diff_cells[(k, col)] = "na_added"
            elif not el and er:
                diff_cells[(k, col)] = "na_deleted"
            elif not el and not er and _txt(vl) != _txt(vr):
                diff_cells[(k, col)] = "changed"

    identical = not added and not deleted and not diff_cells
    changed_cols = {col for (k, col), ct in diff_cells.items() if _visible(ct, toggles)}

    left_styles, right_styles, left_rows, right_rows = {}, {}, [], []
    for i, k in enumerate(keys):
        has_changed = any((k, col) in diff_cells for col in cols)
        lrec, rrec = {KEY_COL: k}, {KEY_COL: k}

        if identical:
            left_styles[(i, KEY_COL)] = right_styles[(i, KEY_COL)] = M3["identical"]
        elif k in deleted:
            left_styles[(i, KEY_COL)] = M3["deleted"] if toggles.get("del_row", True) else M3["default"]
            right_styles[(i, KEY_COL)] = M3["grey"]
        elif k in added:
            left_styles[(i, KEY_COL)] = M3["grey"]
            right_styles[(i, KEY_COL)] = M3["added"] if toggles.get("add_row", True) else M3["default"]
        else:
            left_styles[(i, KEY_COL)] = M3["left_changed"] if has_changed else M3["default"]
            right_styles[(i, KEY_COL)] = M3["changed"] if has_changed else M3["default"]

        for col in cols:
            vl = L.at[k, col] if (k in L.index and col in L.columns) else None
            vr = R.at[k, col] if (k in R.index and col in R.columns) else None
            lrec[col], rrec[col] = _txt(vl), _txt(vr)

            if identical:
                left_styles[(i, col)] = right_styles[(i, col)] = M3["identical"]
                continue

            # left table
            if k in deleted:
                left_styles[(i, col)] = M3["deleted"] if toggles.get("del_row", True) else M3["default"]
            elif k in added:
                left_styles[(i, col)] = M3["grey"]
            elif (k, col) in diff_cells:
                left_styles[(i, col)] = M3["left_changed"]
            else:
                left_styles[(i, col)] = M3["default"]

            # right table (respects change-type visibility)
            if k in added:
                right_styles[(i, col)] = M3["added"] if toggles.get("add_row", True) else M3["default"]
            elif k in deleted:
                right_styles[(i, col)] = M3["grey"]
            elif (k, col) in diff_cells:
                ct = diff_cells[(k, col)]
                right_styles[(i, col)] = M3[ct] if _visible(ct, toggles) else M3["default"]
            else:
                right_styles[(i, col)] = M3["default"]

        left_rows.append(lrec)
        right_rows.append(rrec)

    header = {c: {"bg": CHANGED_HEADER} for c in changed_cols}
    left_df = pd.DataFrame(left_rows, columns=[KEY_COL] + cols)
    right_df = pd.DataFrame(right_rows, columns=[KEY_COL] + cols)
    return left_df, right_df, left_styles, right_styles, header, changed_cols
