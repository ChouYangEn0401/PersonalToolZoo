import subprocess
import shlex
import os
from typing import Dict, Tuple, List
from datetime import datetime, timezone


def _git(cmd: List[str], cwd: str = None) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, cwd=cwd).decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git command failed: {' '.join(cmd)}")


def parse_numstat(init: str, latest: str, repo_path: str = None) -> List[Dict]:
    """Return list of records: {path, added, deleted, binary}
    Uses `git diff --numstat init..latest`.
    """
    out = _git(["git", "diff", "--numstat", f"{init}..{latest}"], cwd=repo_path)
    records = []
    for line in out.splitlines():
        parts = line.split('\t')
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[2]
        binary = False
        try:
            added = int(a)
            deleted = int(d)
        except ValueError:
            # binary file shows -    -
            binary = True
            added = 0
            deleted = 0
        records.append({"path": path, "added": added, "deleted": deleted, "binary": binary})
    return records


def ls_tree_sizes(commit: str, repo_path: str = None) -> Dict[str, int]:
    """Return dict path -> size (bytes) for a tree of a commit using `git ls-tree -r -l`.
    Size will be an int; if file missing, it won't appear.
    """
    out = _git(["git", "ls-tree", "-r", "-l", commit], cwd=repo_path)
    sizes = {}
    for line in out.splitlines():
        if '\t' not in line:
            continue
        left, path = line.split('\t', 1)
        left_parts = left.split()
        if len(left_parts) < 4:
            continue
        size_token = left_parts[-1]
        try:
            size = int(size_token)
        except ValueError:
            size = 0
        sizes[path] = size
    return sizes


def aggregate_by_extension(init: str, latest: str, repo_path: str = None) -> Dict:
    """Compute per-file and per-extension aggregates between two commits.
    Returns a dict with 'files' list and 'by_ext' mapping.
    """
    records = parse_numstat(init, latest, repo_path=repo_path)
    sizes_init = ls_tree_sizes(init, repo_path=repo_path)
    sizes_latest = ls_tree_sizes(latest, repo_path=repo_path)

    files = []
    by_ext = {}
    total_files = 0
    for r in records:
        path = r["path"]
        added = r["added"]
        deleted = r["deleted"]
        binary = r["binary"]
        size_i = sizes_init.get(path)
        size_l = sizes_latest.get(path)
        bytes_change = None
        # try fallback to git cat-file for missing sizes (useful for binary files)
        def _try_cat_size(commit, pth):
            try:
                out = _git(["git", "cat-file", "-s", f"{commit}:{pth}"], cwd=repo_path)
                return int(out.strip())
            except Exception:
                return None

        if size_i is None and (binary or True):
            # attempt to fetch size at init commit
            try:
                size_i = _try_cat_size(init, path)
            except Exception:
                size_i = None
        if size_l is None and (binary or True):
            try:
                size_l = _try_cat_size(latest, path)
            except Exception:
                size_l = None
        if size_i is not None or size_l is not None:
            bytes_change = (size_l or 0) - (size_i or 0)

        ext = os.path.splitext(path)[1].lower() or os.path.basename(path)
        rec = {"path": path, "ext": ext, "added": added, "deleted": deleted, "binary": binary, "bytes_change": bytes_change}
        files.append(rec)

        ag = by_ext.setdefault(ext, {"files": 0, "added": 0, "deleted": 0, "bytes_change": 0, "binary": 0, "sample": []})
        ag["files"] += 1
        ag["added"] += added
        ag["deleted"] += deleted
        if binary:
            ag["binary"] += 1
        if bytes_change is not None:
            ag["bytes_change"] += bytes_change
        if len(ag["sample"]) < 3:
            ag["sample"].append(path)
        total_files += 1

    # commit times
    def _get_iso(commit: str) -> str:
        """Return ISO 8601 committer date for a commit/ref, or empty string."""
        try:
            out = _git(["git", "show", "-s", "--format=%cI", commit], cwd=repo_path).strip()
            if out:
                return out
        except Exception:
            pass
        try:
            out = _git(["git", "show", "-s", "--format=%ci", commit], cwd=repo_path).strip()
            return out
        except Exception:
            return ""

    init_iso = _get_iso(init)
    latest_iso = _get_iso(latest)
    duration_seconds = None
    duration_human = None
    if init_iso and latest_iso:
        try:
            dt_init = datetime.fromisoformat(init_iso)
            dt_latest = datetime.fromisoformat(latest_iso)
            delta = dt_latest - dt_init
            duration_seconds = int(delta.total_seconds())
            secs = duration_seconds
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
            duration_human = " ".join(parts) if parts else "0s"
        except Exception:
            duration_seconds = None
            duration_human = None

    return {"total_files": total_files, "files": files, "by_ext": by_ext,
            "init_time": init_iso, "latest_time": latest_iso,
            "duration_seconds": duration_seconds, "duration_human": duration_human}
