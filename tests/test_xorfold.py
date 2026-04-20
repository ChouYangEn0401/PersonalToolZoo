import os
from crypto_tool.core.engine import EncryptionEngine


def test_xorfold_roundtrip():
    plain = b"hello"
    password = b"verysecretpassword"
    ct = EncryptionEngine.encrypt(plain, password, algorithm="XOR-FOLD")
    pt = EncryptionEngine.decrypt(ct, password, algorithm="XOR-FOLD")
    assert pt == plain


def test_xor_vs_xorfold_difference_when_key_longer_than_data():
    plain = b"a"
    password = b"this-password-is-longer-than-data"
    ct_xor = EncryptionEngine.encrypt(plain, password, algorithm="XOR")
    ct_fold = EncryptionEngine.encrypt(plain, password, algorithm="XOR-FOLD")
    # ciphertexts should differ when key is longer than data
    assert ct_xor != ct_fold
