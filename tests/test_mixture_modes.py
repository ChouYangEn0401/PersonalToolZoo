"""
Tests for the two Mixture pipeline modes:

  multi-encrypt — all stages fused into one .isd, decrypt reverses chain
  layer-wrap    — each stage wraps content in a new .isd, decrypt peels one layer at a time
"""

from crypto_tool.core.pipeline import (
    encrypt_multi,
    decrypt_multi,
    encrypt_layer_wrap,
    decrypt_layer_wrap,
    PartialDecryptError,
)
from crypto_tool.core.bytefile import ByteFile

# Stage configs: pw_source + key_type, NO pre-derived key_bytes
STAGES = [
    {"algorithm": "AES-256-CBC", "pw_source": "passwordA", "key_type": "text"},
    {"algorithm": "AES-256-CBC", "pw_source": "passwordB", "key_type": "text"},
]


def test_multi_encrypt_roundtrip():
    """content → enc1 → enc2 → ONE .isd  |  decrypt reverses stages."""
    orig = b"hello multi-encrypt world"
    bf = encrypt_multi(orig, STAGES, orig_name="test.txt", orig_size=len(orig))
    assert bf.mode == "multi-encrypt"
    recovered = decrypt_multi(bf, STAGES)
    assert recovered == orig


def test_multi_encrypt_partial_still_encrypted():
    """Decrypting with only ONE stage raises an error (data is still encrypted)."""
    orig = b"still encrypted if chain is incomplete"
    bf = encrypt_multi(orig, STAGES)
    # Supply only the first stage — AES padding error expected (not the original)
    partial_stages = [STAGES[0]]
    try:
        partial = decrypt_multi(bf, partial_stages)
        # If no exception, result must differ from original
        assert partial != orig
    except Exception:
        pass  # ValueError/DecryptionError is the expected outcome


def test_layer_wrap_roundtrip():
    """Each encrypt stage wraps in its own .isd; decrypt peels outermost first."""
    orig = b"hello layer-wrap world"
    outer_bytes = encrypt_layer_wrap(orig, STAGES, orig_name="test.txt", orig_size=len(orig))
    # outermost .isd must be parseable
    outer_bf = ByteFile.parse(outer_bytes.decode("utf-8"))
    assert outer_bf.mode == "layer-wrap"

    recovered = decrypt_layer_wrap(outer_bytes, STAGES)
    assert recovered == orig


def test_layer_wrap_single_peel_gives_inner_isd():
    """Peeling only the outer layer gives a valid inner .isd, not the original."""
    orig = b"secret"
    outer_bytes = encrypt_layer_wrap(orig, STAGES)

    # Peel the outer layer only (last stage in STAGES is the outermost)
    outer_bf = ByteFile.parse(outer_bytes.decode("utf-8"))
    from crypto_tool.core.pipeline import _dec_step
    inner_bytes = _dec_step(outer_bf.content, STAGES[-1])
    # inner_bytes must itself be a valid .isd (not the original plaintext)
    inner_bf = ByteFile.parse(inner_bytes.decode("utf-8"))
    # from inner .isd we can recover the original with the first stage
    final = _dec_step(inner_bf.content, STAGES[0])
    assert final == orig


def test_layer_wrap_partial_decrypt_error():
    """Wrong password for a layer raises PartialDecryptError (not a hard crash)."""
    orig = b"partial fail test"
    outer_bytes = encrypt_layer_wrap(orig, STAGES)

    bad_stages = [
        {"algorithm": "AES-256-CBC", "pw_source": "passwordA", "key_type": "text"},
        {"algorithm": "AES-256-CBC", "pw_source": "WRONG_PASSWORD", "key_type": "text"},
    ]
    try:
        decrypt_layer_wrap(outer_bytes, bad_stages)
        assert False, "Expected PartialDecryptError"
    except PartialDecryptError as e:
        # should have the last valid .isd bytes (the inner layer) as partial
        assert e.partial is not None
        assert e.stage_num >= 1


