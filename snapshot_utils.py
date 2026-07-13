"""Estimate cloc-style per-extension stats for a single folder snapshot.

For projects that aren't under version control there's no prior state to
diff against, so this reports the CURRENT composition instead of a delta:
total lines (text files) and total bytes per extension/category, as of the
moment you scan. The shape is deliberately different from
git_utils.aggregate_by_extension (lines/bytes instead of added/deleted/
bytes_change) since there is no "before" to compare with.
"""

import os
from datetime import datetime
from typing import Dict

_EXCLUDE_DIRS = {".git", ".svn", ".hg", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode"}
_BINARY_SNIFF_BYTES = 8000
_LINE_COUNT_SIZE_LIMIT = 20_000_000  # above this, report size only (skip line count)


def _walk_files(root_dir: str) -> Dict[str, str]:
    """Map relative_path (posix-style) -> absolute_path for every file under root_dir."""
    root_dir = os.path.abspath(root_dir)
    result: Dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS]
        for name in filenames:
            abs_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(abs_path, root_dir).replace(os.sep, "/")
            result[rel_path] = abs_path
    return result


def _count_lines(raw: bytes) -> int:
    if not raw:
        return 0
    lines = raw.count(b"\n")
    return lines + 1 if not raw.endswith(b"\n") else lines


def scan_by_extension(folder: str) -> Dict:
    """Census of a single folder right now: file count, total lines and total
    bytes per extension/category. No comparison to a prior state is made.
    """
    files_map = _walk_files(folder)

    files = []
    by_ext: Dict[str, Dict] = {}
    total_files = 0

    for rel_path, abs_path in sorted(files_map.items()):
        try:
            size = os.path.getsize(abs_path)
            with open(abs_path, "rb") as f:
                head = f.read(_BINARY_SNIFF_BYTES)
            binary = b"\0" in head

            lines = 0
            if not binary:
                if size <= _LINE_COUNT_SIZE_LIMIT:
                    with open(abs_path, "rb") as f:
                        raw = f.read()
                    lines = _count_lines(raw)
                else:
                    binary = True  # too large to usefully line-count; report size only
        except OSError:
            continue

        ext = os.path.splitext(rel_path)[1].lower() or os.path.basename(rel_path)
        files.append({"path": rel_path, "ext": ext, "lines": lines, "bytes": size, "binary": binary})

        ag = by_ext.setdefault(ext, {"files": 0, "lines": 0, "bytes": 0, "binary": 0, "sample": []})
        ag["files"] += 1
        ag["lines"] += lines
        ag["bytes"] += size
        if binary:
            ag["binary"] += 1
        if len(ag["sample"]) < 3:
            ag["sample"].append(rel_path)
        total_files += 1

    scan_time = datetime.now().astimezone().isoformat()
    return {"total_files": total_files, "files": files, "by_ext": by_ext, "scan_time": scan_time}
