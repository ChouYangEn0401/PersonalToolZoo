"""筆記庫：輸出資料夾裡有哪些影片與合併（collection），各自有哪些分析與輸出。

GUI 的「筆記庫」分頁與 CLI 的 `list --json` 共用這裡。只讀檔案、不連網、不呼叫 AI。
"""

from __future__ import annotations

import json
from pathlib import Path

from video_notes.naming import COLLECTIONS_DIR, Artifacts


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _analysis_summaries(art: Artifacts) -> list[dict]:
    """每份 analysis.<slug>.json 的摘要（slug、一句話結論、模式、品質旗標）；讀不懂的只回 slug。"""
    out = []
    for path in art.all_analyses():
        slug = path.name[len("analysis."):-len(".json")]
        data = _read_json(path)
        out.append({
            "slug": slug,
            "file": path.name,
            "summary": str(data.get("summary", ""))[:200],
            "profile": (data.get("mode") or {}).get("profile", ""),
            "template": (data.get("layout_hint") or {}).get("template", ""),
            "quality_flags": data.get("quality_flags") or [],
            "schema_version": data.get("schema_version"),
        })
    return out


def _entry(folder: Path, kind: str, title: str, url: str, updated_from: Path) -> dict:
    art = Artifacts(folder)
    status = art.status()
    return {
        "type": kind,                       # "video" 或 "collection"
        "folder": str(folder),
        "name": folder.name,
        "title": title or folder.name,
        "url": url,
        "notes": status["notes"],           # 舊版也有的：notes.<slug>.md 的 slug
        "analyses": _analysis_summaries(art),
        "outputs": status["outputs"],       # outputs/ 底下的檔名
        "transcript": bool(status["transcript"]),
        "updated": updated_from.stat().st_mtime if updated_from.exists() else folder.stat().st_mtime,
    }


def list_videos(root: Path) -> list[dict]:
    items = []
    if not root.is_dir():
        return items
    for folder in root.iterdir():
        if not folder.is_dir() or folder.name == COLLECTIONS_DIR:
            continue
        art = Artifacts(folder)
        if not art.info.is_file():
            continue
        record = _read_json(art.info)
        entry = _entry(folder, "video", (record.get("video") or {}).get("title", ""), record.get("url", ""), art.info)
        entry["kind"] = record.get("kind", "")       # short / video（舊欄位，GUI 有用）
        entry["profile"] = record.get("auto_profile", "")
        items.append(entry)
    return sorted(items, key=lambda x: x["updated"], reverse=True)


def list_collections(root: Path) -> list[dict]:
    items = []
    base = root / COLLECTIONS_DIR
    if not base.is_dir():
        return items
    for folder in base.iterdir():
        art = Artifacts(folder)
        if not folder.is_dir() or not art.collection.is_file():
            continue
        record = _read_json(art.collection)
        entry = _entry(folder, "collection", record.get("title", ""), "", art.collection)
        entry["members"] = record.get("members") or []
        items.append(entry)
    return sorted(items, key=lambda x: x["updated"], reverse=True)


def list_library(root: Path) -> dict:
    """{"videos": [...], "collections": [...]}，各自依更新時間新到舊。"""
    return {"videos": list_videos(root), "collections": list_collections(root)}
