"""Estimate git_utils-style per-extension stats for two plain folder snapshots.

For projects that aren't under version control: instead of `git diff --numstat`
we walk two directory trees ourselves and diff matching files directly. Returns
the same shaped dict as git_utils.aggregate_by_extension so the GUI can render
either source with identical code.
"""

import difflib
import filecmp
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

_EXCLUDE_DIRS = {".git", ".svn", ".hg", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode"}
_BINARY_SNIFF_BYTES = 8000
_DIFF_SIZE_LIMIT = 5_000_000  # above this, report size only (skip line-level diff)


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


def _line_diff(old_raw: Optional[bytes], new_raw: Optional[bytes]) -> Tuple[int, int]:
    old_lines = old_raw.decode("utf-8", errors="replace").splitlines() if old_raw is not None else []
    new_lines = new_raw.decode("utf-8", errors="replace").splitlines() if new_raw is not None else []
    added = deleted = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        deleted += (i2 - i1)
        added += (j2 - j1)
    return added, deleted


def _folder_snapshot_time(paths: Dict[str, str]) -> Optional[str]:
    """Use the newest file mtime in the tree as a proxy for 'when this snapshot was taken'."""
    mtimes = []
    for abs_path in paths.values():
        try:
            mtimes.append(os.path.getmtime(abs_path))
        except OSError:
            pass
    if not mtimes:
        return None
    return datetime.fromtimestamp(max(mtimes)).astimezone().isoformat()


def aggregate_by_extension(init_dir: str, latest_dir: str) -> Dict:
    """Estimate the same per-extension stats as git_utils.aggregate_by_extension,
    but for two plain folder snapshots. Unchanged files are omitted, mirroring
    `git diff` semantics.
    """
    init_files = _walk_files(init_dir)
    latest_files = _walk_files(latest_dir)
    all_paths = sorted(set(init_files) | set(latest_files))

    files: List[Dict] = []
    by_ext: Dict[str, Dict] = {}
    total_files = 0

    for rel_path in all_paths:
        old_abs = init_files.get(rel_path)
        new_abs = latest_files.get(rel_path)

        try:
            old_size = os.path.getsize(old_abs) if old_abs else 0
            new_size = os.path.getsize(new_abs) if new_abs else 0

            if old_abs and new_abs and old_size == new_size and filecmp.cmp(old_abs, new_abs, shallow=False):
                continue  # unchanged; git diff would not list this file either

            bytes_change = new_size - old_size

            sniff_path = new_abs or old_abs
            with open(sniff_path, "rb") as f:
                head = f.read(_BINARY_SNIFF_BYTES)
            binary = b"\0" in head
            too_big = max(old_size, new_size) > _DIFF_SIZE_LIMIT

            added = deleted = 0
            if not binary and not too_big:
                old_raw = open(old_abs, "rb").read() if old_abs else None
                new_raw = open(new_abs, "rb").read() if new_abs else None
                added, deleted = _line_diff(old_raw, new_raw)
            elif too_big:
                binary = True  # too large to usefully line-diff; report size only
        except OSError:
            continue

        ext = os.path.splitext(rel_path)[1].lower() or os.path.basename(rel_path)
        files.append({"path": rel_path, "ext": ext, "added": added, "deleted": deleted,
                       "binary": binary, "bytes_change": bytes_change})

        ag = by_ext.setdefault(ext, {"files": 0, "added": 0, "deleted": 0,
                                      "bytes_change": 0, "binary": 0, "sample": []})
        ag["files"] += 1
        ag["added"] += added
        ag["deleted"] += deleted
        ag["bytes_change"] += bytes_change
        if binary:
            ag["binary"] += 1
        if len(ag["sample"]) < 3:
            ag["sample"].append(rel_path)
        total_files += 1

    init_iso = _folder_snapshot_time(init_files)
    latest_iso = _folder_snapshot_time(latest_files)
    duration_seconds = None
    duration_human = None
    if init_iso and latest_iso:
        delta_seconds = int((datetime.fromisoformat(latest_iso) - datetime.fromisoformat(init_iso)).total_seconds())
        duration_seconds = delta_seconds
        secs = abs(delta_seconds)
        days, secs = divmod(secs, 86400)
        hours, secs = divmod(secs, 3600)
        mins, secs = divmod(secs, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if mins:
            parts.append(f"{mins}m")
        if secs:
            parts.append(f"{secs}s")
        sign = "-" if delta_seconds < 0 else ""
        duration_human = sign + (" ".join(parts) if parts else "0s")

    return {"total_files": total_files, "files": files, "by_ext": by_ext,
            "init_time": init_iso, "latest_time": latest_iso,
            "duration_seconds": duration_seconds, "duration_human": duration_human,
            "time_is_estimated": True}
