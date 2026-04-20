"""Utility helpers for key derivation, file hashing, and validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

# Maximum file sizes for each password-key type (bytes)
KEY_FILE_LIMITS: dict[str, int] = {
    "file": 100 * 1024 * 1024,      # 100 MB
    "image": 50 * 1024 * 1024,      # 50 MB
    "video": 200 * 1024 * 1024,     # 200 MB
    "bytefile": 50 * 1024 * 1024,   # 50 MB
    "txtfile": 50 * 1024 * 1024,    # 50 MB (text file used as key)
}

MAX_TEXT_PASSWORD_LEN = 1024


def hash_file(path: str | Path, max_bytes: int | None = None) -> bytes:
    """Return SHA-256 digest of (the first *max_bytes* of) a file."""
    h = hashlib.sha256()
    total = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            if max_bytes is not None:
                remaining = max_bytes - total
                if remaining <= 0:
                    break
                chunk = chunk[:remaining]
            h.update(chunk)
            total += len(chunk)
    return h.digest()


def derive_key_bytes(
    source: str,
    key_type: str = "text",
) -> bytes:
    """
    Convert a password *source* (text or file path) into raw key bytes.

    For text   → UTF-8 encoded bytes
    For file types → SHA-256 hash of the file content (size-limited)
    """
    if key_type == "text":
        if len(source) > MAX_TEXT_PASSWORD_LEN:
            raise ValueError(
                f"Text password exceeds {MAX_TEXT_PASSWORD_LEN} characters"
            )
        return source.encode("utf-8")

    # Text-file keys: read as text, strip a trailing newline (common EOF newline)
    # and hash the resulting text. This avoids accidental extra '\n' at EOF
    # changing the derived key.
    if key_type == "txtfile":
        p = Path(source)
        if not p.is_file():
            raise FileNotFoundError(f"Key file not found: {source}")
        file_size = p.stat().st_size
        limit = KEY_FILE_LIMITS.get(key_type)
        if limit and file_size > limit:
            raise ValueError(
                f"Key file too large ({file_size / 1024 / 1024:.1f} MB). "
                f"Limit for '{key_type}' is {limit / 1024 / 1024:.0f} MB."
            )
        try:
            txt = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            txt = p.read_text(encoding="latin-1")
        # remove only trailing CR/LF characters at EOF
        txt = txt.rstrip("\r\n")
        return hashlib.sha256(txt.encode("utf-8")).digest()

    # File-based key types
    limit = KEY_FILE_LIMITS.get(key_type)
    p = Path(source)
    if not p.is_file():
        raise FileNotFoundError(f"Key file not found: {source}")

    file_size = p.stat().st_size
    if limit and file_size > limit:
        raise ValueError(
            f"Key file too large ({file_size / 1024 / 1024:.1f} MB). "
            f"Limit for '{key_type}' is {limit / 1024 / 1024:.0f} MB."
        )

    return hash_file(p, limit)


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"
