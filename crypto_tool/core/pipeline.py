"""
High-level mixture pipeline — two independent modes.

Multi-Encrypt  (mode="multi-encrypt", formerly "layered"):
    Encrypt:  content → enc₁ → enc₂ → … → encₙ → ONE .isd
    Decrypt:  parse .isd → decₙ → … → dec₁ → original bytes
    If any stage fails during decrypt, the whole operation fails (no valid .isd
    intermediate exists — only the single outer .isd is created).

Layer-Wrap  (mode="layer-wrap", formerly "nested"):
    Encrypt:  content → enc₁ → isd₁  →  isd₁_bytes → enc₂ → isd₂  →  …  →  isdₙ
    Decrypt:  parse isdₙ → dec (key_n) → isdₙ₋₁_bytes → parse → dec (key_n-1) → …
    On decrypt failure at any stage the last valid .isd bytes are preserved so the
    user can retry that stage or take the partial result to the File tab.
"""

from __future__ import annotations

from pathlib import Path

from .engine import EncryptionEngine
from .bytefile import ByteFile, default_note
from .utils import derive_key_bytes

# ── Stage key resolution ──────────────────────────────────────────────────

def _key_bytes(stage: dict) -> bytes:
    """Derive key bytes from a stage config.  PGP stages return b'' (not used)."""
    if stage.get("key_type") == "pgp":
        return b""
    return derive_key_bytes(stage["pw_source"], stage["key_type"])


def _enc_step(data: bytes, stage: dict) -> bytes:
    """Apply one encrypt step to *data*."""
    algo = stage["algorithm"]
    if algo == "PGP":
        pub_pem = Path(stage["pub_pem_path"]).read_bytes()
        return EncryptionEngine.encrypt(data, pub_pem, "PGP")
    return EncryptionEngine.encrypt(data, _key_bytes(stage), algo)


def _dec_step(data: bytes, stage: dict) -> bytes:
    """Apply one decrypt step to *data*."""
    algo = stage["algorithm"]
    if algo == "PGP":
        priv_pem = Path(stage["priv_pem_path"]).read_bytes()
        return EncryptionEngine.decrypt(data, priv_pem, "PGP")
    return EncryptionEngine.decrypt(data, _key_bytes(stage), algo)


# ── Multi-Encrypt ─────────────────────────────────────────────────────────

def encrypt_multi(
    data: bytes,
    stages: list[dict],
    *,
    orig_name: str | None = None,
    orig_size: int | None = None,
) -> ByteFile:
    """
    Apply every stage in forward order on the raw bytes, wrap result in ONE .isd.
    Decrypt must supply the same stages (code reverses internally).
    """
    result = data
    for stage in stages:
        result = _enc_step(result, stage)
    chain_meta = [
        {"algorithm": s["algorithm"], "key_type": s.get("key_type", "text")}
        for s in stages
    ]
    note = default_note(
        algorithm=stages[0]["algorithm"],
        key_type=stages[0].get("key_type", "text"),
        mode="multi-encrypt",
        iterations=len(stages),
        original_filename=orig_name,
        original_size=orig_size,
        mixture_chain=chain_meta,
    )
    return ByteFile(result, note)


def decrypt_multi(bf: ByteFile, stages: list[dict]) -> bytes:
    """
    Reverse the encrypt_multi chain.  Raises immediately on any cipher error.
    """
    result = bf.content
    for stage in reversed(stages):
        result = _dec_step(result, stage)
    return result


# ── Layer-Wrap ────────────────────────────────────────────────────────────

def encrypt_layer_wrap(
    data: bytes,
    stages: list[dict],
    *,
    orig_name: str | None = None,
    orig_size: int | None = None,
) -> bytes:
    """
    Each stage encrypts the current payload then wraps it in a fresh .isd.
    Returns the outermost .isd as raw UTF-8 bytes (ready to write to disk).
    """
    payload = data
    n = len(stages)
    for i, stage in enumerate(stages):
        encrypted = _enc_step(payload, stage)
        note = default_note(
            algorithm=stage["algorithm"],
            key_type=stage.get("key_type", "text"),
            mode="layer-wrap",
            iterations=n,
            original_filename=orig_name if i == 0 else None,
            original_size=orig_size if i == 0 else None,
        )
        note["layer"] = i + 1
        note["total_layers"] = n
        payload = ByteFile(encrypted, note).pack().encode("utf-8")
    return payload  # bytes of the outermost .isd text


class PartialDecryptError(Exception):
    """
    Raised by decrypt_layer_wrap when a stage fails mid-way.

    Attributes:
        partial   : bytes — the last successfully peeled .isd bytes (still valid
                    as a .isd; can be opened in the File tab or retried).
        completed : int   — number of stages successfully peeled before failure.
        stage_num : int   — 1-based stage number (from outer) that failed.
    """

    def __init__(self, msg: str, *, partial: bytes, completed: int, stage_num: int):
        super().__init__(msg)
        self.partial = partial
        self.completed = completed
        self.stage_num = stage_num


def decrypt_layer_wrap(data: bytes, stages: list[dict]) -> bytes:
    """
    Peel layers in reverse stage order (outermost first).

    On parse failure or cipher failure raises PartialDecryptError so the caller
    can save the last valid .isd and inform the user.
    """
    current = data
    n = len(stages)
    for i, stage in enumerate(reversed(stages)):
        stage_num = i + 1  # 1 = outermost
        try:
            bf = ByteFile.parse(current.decode("utf-8"))
        except Exception as exc:
            raise PartialDecryptError(
                f"Layer {stage_num}/{n}: cannot parse as .isd — {exc}",
                partial=current,
                completed=i,
                stage_num=stage_num,
            ) from exc
        try:
            current = _dec_step(bf.content, stage)
        except Exception as exc:
            raise PartialDecryptError(
                f"Layer {stage_num}/{n}: decryption failed — {exc}",
                partial=current,  # still the valid .isd bytes before this step
                completed=i,
                stage_num=stage_num,
            ) from exc
    return current
