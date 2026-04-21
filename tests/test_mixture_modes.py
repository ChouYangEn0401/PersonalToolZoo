from crypto_tool.core.engine import EncryptionEngine
from crypto_tool.core.bytefile import ByteFile, default_note


def _enc_step(data: bytes, step: dict) -> bytes:
    return EncryptionEngine.encrypt(data, step["key_bytes"], step["algorithm"])


def _dec_step(data: bytes, step: dict) -> bytes:
    return EncryptionEngine.decrypt(data, step["key_bytes"], step["algorithm"])


CHAIN = [
    {"algorithm": "AES-256-CBC", "key_bytes": b"keyA", "key_type": "text"},
    {"algorithm": "AES-256-CBC", "key_bytes": b"keyB", "key_type": "text"},
]


def test_layered_encrypt_decrypt():
    """content → enc1 → enc2 → ONE .isd  |  decrypt reverses chain"""
    orig = b"hello layered world"

    # Encrypt: apply chain forward on raw bytes, wrap ONE .isd
    result = orig
    for step in CHAIN:
        result = _enc_step(result, step)
    chain_meta = [{"algorithm": s["algorithm"], "key_type": s["key_type"]} for s in CHAIN]
    bf = ByteFile(result, default_note(algorithm=CHAIN[0]["algorithm"], mode="layered",
                                       mixture_chain=chain_meta))
    isd_text = bf.pack()

    # Decrypt: parse .isd, reverse chain
    bf2 = ByteFile.parse(isd_text)
    recovered = bf2.content
    for step in reversed(CHAIN):
        recovered = _dec_step(recovered, step)
    assert recovered == orig


def test_layered_single_decrypt_still_encrypted():
    """Decrypting a layered .isd with only ONE stage leaves data still encrypted."""
    orig = b"still encrypted after one pass"
    result = orig
    for step in CHAIN:
        result = _enc_step(result, step)
    bf = ByteFile(result, default_note(algorithm=CHAIN[0]["algorithm"], mode="layered"))
    # Peel only the inner-most cipher (last stage) — result is NOT the original
    partial = _dec_step(bf.content, CHAIN[-1])
    assert partial != orig


def test_nested_encrypt_decrypt():
    """Each encrypt stage wraps in a new .isd; each decrypt stage peels one .isd."""
    orig = b"hello nested world"

    # Nested Encrypt
    payload = orig
    for i, step in enumerate(CHAIN):
        encrypted = _enc_step(payload, step)
        note = default_note(algorithm=step["algorithm"], key_type=step["key_type"], mode="nested")
        note["layer"] = i + 1
        note["total_layers"] = len(CHAIN)
        payload = ByteFile(encrypted, note).pack().encode("utf-8")
    # payload is now the outermost .isd bytes

    # Nested Decrypt: peel in reverse
    current = payload
    for step in reversed(CHAIN):
        bf = ByteFile.parse(current.decode("utf-8"))
        current = _dec_step(bf.content, step)
    assert current == orig


def test_nested_single_peel_gives_inner_isd():
    """Peeling only the outermost layer gives a valid inner .isd, not the original."""
    orig = b"secret"

    payload = orig
    for i, step in enumerate(CHAIN):
        encrypted = _enc_step(payload, step)
        note = default_note(algorithm=step["algorithm"], key_type=step["key_type"], mode="nested")
        note["layer"] = i + 1
        note["total_layers"] = len(CHAIN)
        payload = ByteFile(encrypted, note).pack().encode("utf-8")

    # Peel outer layer only
    outer_bf = ByteFile.parse(payload.decode("utf-8"))
    inner_bytes = _dec_step(outer_bf.content, CHAIN[-1])
    # inner_bytes must be another valid .isd
    inner_bf = ByteFile.parse(inner_bytes.decode("utf-8"))
    # and from there we can still get the original
    final = _dec_step(inner_bf.content, CHAIN[0])
    assert final == orig


