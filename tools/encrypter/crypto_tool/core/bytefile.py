"""
.isd custom format — pack / parse encrypted data with metadata.

Format:
    CONTENT=\"\"\"<base64 encoded encrypted payload>\"\"\"
    NOTE=\"\"\"<JSON metadata>\"\"\"

This module historically used the ".bytefile" extension. The project
now uses the ".isd" extension for exported encrypted files. The
`ByteFile` class and helpers remain the canonical in-memory/on-disk
representation for this format.
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

BYTEFILE_EXT = ".isd"


def default_note(
    algorithm: str = "AES-256-CBC",
    key_type: str = "text",
    mode: str = "layered",
    iterations: int = 1,
    author: str = "@anonymous",
    password_hint: str | None = None,
    original_filename: str | None = None,
    original_size: int | None = None,
    mixture_chain: list[dict] | None = None,
    chunk_info: dict | None = None,
    pgp_mode: str | None = None,
    pgp_escrow: bool = False,
    pgp_recipient_count: int = 0,
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
        # PGP metadata — None means not PGP-wrapped
        "pgp_mode": pgp_mode,
        "pgp_escrow": pgp_escrow if pgp_escrow else None,
        "pgp_recipient_count": pgp_recipient_count if pgp_recipient_count else None,
    }


class ByteFile:
    """Represent a `.isd` package on disk or in memory.

    Note: the class historically referred to the filetype as "bytefile"; the
    on-disk extension is now `.isd` and the class handles packing/parsing that
    format.
    """

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
            raise ValueError("Invalid .isd format")
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
        m = self.note.get("mode", "all-in-one")
        # backward compat: map older names to new canonical names
        # old 'simple' / 'multi-encrypt' => 'all-in-one'
        if m in ("simple", "multi-encrypt"):
            return "all-in-one"
        # old 'node' / 'nested' / 'layer-wrap' => 'layered'
        if m in ("node", "nested", "layer-wrap"):
            return "layered"
        return m  # 'all-in-one' | 'layered' (canonical)

    @property
    def original_filename(self) -> str | None:
        return self.note.get("original_filename")

    @property
    def mixture_chain(self) -> list[dict] | None:
        return self.note.get("mixture_chain")
