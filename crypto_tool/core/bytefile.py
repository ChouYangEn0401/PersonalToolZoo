"""
.bytefile custom format — pack / parse encrypted data with metadata.

Format:
    CONTENT=\"\"\"<base64 encoded encrypted payload>\"\"\"
    NOTE=\"\"\"<JSON metadata>\"\"\"
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CONTENT_RE = re.compile(r'CONTENT="""(.*?)"""', re.DOTALL)
_NOTE_RE = re.compile(r'NOTE="""(.*?)"""', re.DOTALL)

BYTEFILE_EXT = ".bytefile"


def default_note(
    algorithm: str = "AES-256-CBC",
    key_type: str = "text",
    mode: str = "simple",
    iterations: int = 1,
    author: str = "@anonymous",
    password_hint: str | None = None,
    original_filename: str | None = None,
    original_size: int | None = None,
    mixture_chain: list[dict] | None = None,
    chunk_info: dict | None = None,
) -> dict[str, Any]:
    return {
        "encryption_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": author,
        "password_hint": password_hint,
        "algorithm": algorithm,
        "key_type": key_type,
        "mode": mode,
        "iterations": iterations,
        "mixture_chain": mixture_chain,
        "original_filename": original_filename,
        "original_size": original_size,
        "chunk_info": chunk_info,
    }


class ByteFile:
    """Represent a .bytefile on disk or in memory."""

    def __init__(self, content: bytes, note: dict[str, Any]):
        self.content = content  # raw encrypted bytes
        self.note = note

    # ── Pack to string / file ──────────────────────────────────────────

    def pack(self) -> str:
        b64 = base64.b64encode(self.content).decode("ascii")
        note_json = json.dumps(self.note, ensure_ascii=False, indent=2)
        return f'CONTENT="""{b64}"""\nNOTE="""{note_json}"""'

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.write_text(self.pack(), encoding="utf-8")
        return p

    # ── Parse from string / file ───────────────────────────────────────

    @classmethod
    def parse(cls, text: str) -> "ByteFile":
        cm = _CONTENT_RE.search(text)
        nm = _NOTE_RE.search(text)
        if not cm or not nm:
            raise ValueError("Invalid .bytefile format")
        content = base64.b64decode(cm.group(1))
        note = json.loads(nm.group(1))
        return cls(content, note)

    @classmethod
    def load(cls, path: str | Path) -> "ByteFile":
        text = Path(path).read_text(encoding="utf-8")
        return cls.parse(text)

    # ── Convenience helpers ────────────────────────────────────────────

    @property
    def algorithm(self) -> str:
        return self.note.get("algorithm", "AES-256-CBC")

    @property
    def mode(self) -> str:
        return self.note.get("mode", "simple")

    @property
    def original_filename(self) -> str | None:
        return self.note.get("original_filename")

    @property
    def mixture_chain(self) -> list[dict] | None:
        return self.note.get("mixture_chain")
