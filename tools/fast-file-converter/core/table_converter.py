"""Table format converter: Excel ↔ CSV ↔ Parquet."""

import os
import re
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

# Characters illegal in Windows/Linux filenames (also invalid in Excel sheet names)
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]')

# Matches {stem}.[{sheetname}].{csv|parquet}
_SHEET_PATTERN = re.compile(r"^(.+)\.\[(.+)\]\.(csv|parquet)$", re.IGNORECASE)


def _safe_filename_part(name: str) -> str:
    """Replace filesystem-illegal characters in a sheet name used as filename part."""
    return _ILLEGAL_CHARS.sub("_", name)


# ── Excel → CSV / Parquet ────────────────────────────────────────────────────


def excel_to_format(
    excel_path: str,
    output_dir: str,
    fmt: str,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> list[str]:
    """Expand every sheet in *excel_path* to individual files.

    Output naming rule::

        {stem}.[{sheet_name}].csv
        {stem}.[{sheet_name}].parquet

    Args:
        excel_path: Source ``.xlsx`` / ``.xls`` path.
        output_dir: Destination directory.
        fmt: ``"csv"`` or ``"parquet"``.
        progress_cb: Optional callback ``(fraction 0‑1, status_text) → None``.

    Returns:
        List of absolute paths for every file written.
    """
    xl = pd.ExcelFile(excel_path)
    sheets = xl.sheet_names
    stem = Path(excel_path).stem
    total = len(sheets)
    output_paths: list[str] = []

    for i, sheet in enumerate(sheets, 1):
        safe_sheet = _safe_filename_part(sheet)
        fname = f"{stem}.[{safe_sheet}].{fmt}"
        out_path = os.path.join(output_dir, fname)

        if progress_cb:
            progress_cb((i - 1) / total, f"讀取工作表：{sheet}")

        df = xl.parse(sheet)

        if fmt == "csv":
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
        elif fmt == "parquet":
            df.to_parquet(out_path, index=False, engine="pyarrow")
        else:
            raise ValueError(f"Unsupported format: {fmt!r}")

        output_paths.append(out_path)

        if progress_cb:
            progress_cb(i / total, f"已輸出：{fname}")

    return output_paths


# ── CSV / Parquet → Excel ────────────────────────────────────────────────────


def group_files_by_stem(file_paths: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Group file paths by their shared Excel stem.

    Files matching ``{stem}.[{sheetname}].{ext}`` are grouped together.
    Files that don't match are treated as a single sheet named ``工作表1``.

    Returns:
        ``{excel_stem: [(sheet_name, file_path), ...]}``
        Ordered by first occurrence of each stem, sheets in insertion order.
    """
    groups: dict[str, list[tuple[str, str]]] = {}

    for path in file_paths:
        fname = os.path.basename(path)
        m = _SHEET_PATTERN.match(fname)
        if m:
            stem, sheet = m.group(1), m.group(2)
        else:
            stem = os.path.splitext(fname)[0]
            sheet = "工作表1"

        if stem not in groups:
            groups[stem] = []
        groups[stem].append((sheet, path))

    return groups


def tables_to_excel(
    file_paths: list[str],
    output_dir: str,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> list[str]:
    """Merge CSV / Parquet files into Excel workbooks.

    Files sharing a ``{stem}`` (via the ``.[sheetname].`` pattern) are merged
    into a single ``.xlsx``; each file becomes one sheet.

    Args:
        file_paths: Source CSV / Parquet paths.
        output_dir: Destination directory.
        progress_cb: Optional callback ``(fraction 0‑1, status_text) → None``.

    Returns:
        List of absolute paths for every ``.xlsx`` written.
    """
    groups = group_files_by_stem(file_paths)
    total = len(groups)
    output_paths: list[str] = []

    for i, (stem, files) in enumerate(groups.items(), 1):
        out_path = os.path.join(output_dir, f"{stem}.xlsx")

        if progress_cb:
            progress_cb((i - 1) / total, f"產生：{stem}.xlsx …")

        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            for sheet, path in files:
                ext = os.path.splitext(path)[1].lower()
                if ext == ".csv":
                    df = pd.read_csv(path, encoding="utf-8-sig")
                elif ext == ".parquet":
                    df = pd.read_parquet(path, engine="pyarrow")
                else:
                    df = pd.read_csv(path)  # best-effort fallback

                # Excel sheet names are limited to 31 characters
                safe_name = sheet[:31]
                df.to_excel(writer, sheet_name=safe_name, index=False)

        output_paths.append(out_path)

        if progress_cb:
            progress_cb(i / total, f"已完成：{stem}.xlsx")

    return output_paths
