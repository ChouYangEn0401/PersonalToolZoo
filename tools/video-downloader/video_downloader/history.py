"""下載紀錄（%APPDATA%\\PersonalToolZoo\\video-downloader\\history.json），最多留 500 筆。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

LIMIT = 500


class History:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        try:
            self._items: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._items = []

    def add(self, entry: dict) -> None:
        with self._lock:
            self._items.insert(0, entry)
            del self._items[LIMIT:]
            self._save()

    def items(self) -> list[dict]:
        with self._lock:
            return list(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items = []
            self._save()

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._items, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)
