"""Per-column cleaning transforms (GUI-free), ported from the old
GUI_ExcelDiffVisualizationTool. Used by the diff tab's column cleaning.
"""
from __future__ import annotations

import pandas as pd

TRANSFORMS = ["default", "to str", "Upper", "Lower", "Capitalize",
              "Round", "Round_1", "Round_2", "轉%", "NA to 0", "ABS", "to int"]


def apply_transform(value, transform, round_digits=None):
    if pd.isna(value):
        return 0 if transform == "NA to 0" else value
    if transform in ("default", "NA to 0"):
        return value
    if transform == "to str":
        return str(value)
    s = str(value)
    if transform == "Upper":
        return s.upper()
    if transform == "Lower":
        return s.lower()
    if transform == "Capitalize":
        return s.capitalize()
    if transform == "Round_1":
        return round(float(value), 1)
    if transform == "Round_2":
        return round(float(value), 2)
    if transform == "Round":
        if round_digits is None:
            raise ValueError("Round digits not specified")
        return round(float(value), round_digits)
    if transform == "轉%":
        return float(value) * 100
    if transform == "ABS":
        return abs(float(value))
    if transform == "to int":
        return int(float(value))
    return value
