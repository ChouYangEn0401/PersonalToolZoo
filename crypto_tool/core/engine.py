"""
Encryption engine — provides all supported cipher implementations.

Supported algorithms:
  AES-256-CBC, AES-256-GCM, ChaCha20-Poly1305,
  Blowfish-CBC, 3DES-CBC, XOR, Base64
"""

from __future__ import annotations

import base64
import os
from abc import ABC, abstractmethod

from Crypto.Cipher import AES, Blowfish, DES3, ChaCha20_Poly1305
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
from . import pgp as _pgp


PBKDF2_ITERATIONS = 100_000

ALGORITHMS: list[str] = [
    "AES-256-CBC",
    "AES-256-GCM",
    "ChaCha20-Poly1305",
    "Blowfish-CBC",
    "3DES-CBC",
    "XOR",
    "XOR-FOLD",
    "Base64",
    "PGP",
    "PGP-Multi",
    "PGP-Escrow",
]

# Algorithms that use RSA asymmetric keys instead of a symmetric password
PGP_ALGORITHMS: frozenset[str] = frozenset({"PGP", "PGP-Multi", "PGP-Escrow"})

# Algorithms safe for per-stage pipelines (single-key ops only)
STAGE_ALGORITHMS: list[str] = [a for a in ALGORITHMS if a not in ("PGP-Multi", "PGP-Escrow")]

# Algorithms valid as the inner cipher inside a PGP envelope
NON_PGP_ALGORITHMS: list[str] = [a for a in ALGORITHMS if a not in PGP_ALGORITHMS]


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class CipherBase(ABC):
    name: str = ""

    @abstractmethod
    def encrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        ...

    @abstractmethod
    def decrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        ...

    @staticmethod
    def _derive(key_bytes: bytes, salt: bytes, dk_len: int = 32) -> bytes:
        return PBKDF2(key_bytes, salt, dkLen=dk_len, count=PBKDF2_ITERATIONS,
                       hmac_hash_module=SHA256)


# ---------------------------------------------------------------------------
# AES-256-CBC
# ---------------------------------------------------------------------------

class AES_CBC(CipherBase):
    name = "AES-256-CBC"

    def encrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt = get_random_bytes(16)
        key = self._derive(key_bytes, salt, 32)
        iv = get_random_bytes(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ct = cipher.encrypt(pad(data, AES.block_size))
        return salt + iv + ct

    def decrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt, iv, ct = data[:16], data[16:32], data[32:]
        key = self._derive(key_bytes, salt, 32)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), AES.block_size)


# ---------------------------------------------------------------------------
# AES-256-GCM
# ---------------------------------------------------------------------------

class AES_GCM(CipherBase):
    name = "AES-256-GCM"

    def encrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt = get_random_bytes(16)
        key = self._derive(key_bytes, salt, 32)
        cipher = AES.new(key, AES.MODE_GCM)
        ct, tag = cipher.encrypt_and_digest(data)
        # salt(16) + nonce(16) + tag(16) + ct
        return salt + cipher.nonce + tag + ct

    def decrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt = data[:16]
        nonce = data[16:32]
        tag = data[32:48]
        ct = data[48:]
        key = self._derive(key_bytes, salt, 32)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ct, tag)


# ---------------------------------------------------------------------------
# ChaCha20-Poly1305
# ---------------------------------------------------------------------------

class ChaCha20Poly1305(CipherBase):
    name = "ChaCha20-Poly1305"

    def encrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt = get_random_bytes(16)
        key = self._derive(key_bytes, salt, 32)
        cipher = ChaCha20_Poly1305.new(key=key)
        ct, tag = cipher.encrypt_and_digest(data)
        # salt(16) + nonce(12) + tag(16) + ct
        return salt + cipher.nonce + tag + ct

    def decrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt = data[:16]
        nonce = data[16:28]
        tag = data[28:44]
        ct = data[44:]
        key = self._derive(key_bytes, salt, 32)
        cipher = ChaCha20_Poly1305.new(key=key, nonce=nonce)
        return cipher.decrypt_and_verify(ct, tag)


# ---------------------------------------------------------------------------
# Blowfish-CBC
# ---------------------------------------------------------------------------

class BlowfishCBC(CipherBase):
    name = "Blowfish-CBC"

    def encrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt = get_random_bytes(16)
        key = self._derive(key_bytes, salt, 32)
        iv = get_random_bytes(8)
        cipher = Blowfish.new(key, Blowfish.MODE_CBC, iv)
        ct = cipher.encrypt(pad(data, Blowfish.block_size))
        return salt + iv + ct

    def decrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt, iv, ct = data[:16], data[16:24], data[24:]
        key = self._derive(key_bytes, salt, 32)
        cipher = Blowfish.new(key, Blowfish.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), Blowfish.block_size)


# ---------------------------------------------------------------------------
# 3DES-CBC
# ---------------------------------------------------------------------------

class TripleDES_CBC(CipherBase):
    name = "3DES-CBC"

    def encrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt = get_random_bytes(16)
        key_raw = self._derive(key_bytes, salt, 24)
        key = DES3.adjust_key_parity(key_raw)
        iv = get_random_bytes(8)
        cipher = DES3.new(key, DES3.MODE_CBC, iv)
        ct = cipher.encrypt(pad(data, DES3.block_size))
        return salt + iv + ct

    def decrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt, iv, ct = data[:16], data[16:24], data[24:]
        key_raw = self._derive(key_bytes, salt, 24)
        key = DES3.adjust_key_parity(key_raw)
        cipher = DES3.new(key, DES3.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), DES3.block_size)


# ---------------------------------------------------------------------------
# XOR (with PBKDF2 derived key)
# ---------------------------------------------------------------------------

class XORCipher(CipherBase):
    name = "XOR"

    def encrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt = get_random_bytes(16)
        key = self._derive(key_bytes, salt, 32)
        xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return salt + xored

    def decrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        salt, ct = data[:16], data[16:]
        key = self._derive(key_bytes, salt, 32)
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(ct))


# ---------------------------------------------------------------------------
# XOR-FOLD (fold full key over the data buffer so every key byte is used)
# ---------------------------------------------------------------------------

class XORFoldCipher(CipherBase):
    name = "XOR-FOLD"

    def encrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        """XOR-FOLD: derive a key from the password and XOR each key byte
        sequentially into the data buffer, wrapping the data index as needed.
        This ensures every derived key byte is applied at least once even when
        the key is longer than the data.
        """
        salt = get_random_bytes(16)
        key = self._derive(key_bytes, salt, 32)
        # operate on mutable buffer so we can fold the full key over it
        buf = bytearray(data)
        if len(buf) == 0:
            return salt + bytes(buf)
        for i, kb in enumerate(key):
            buf[i % len(buf)] ^= kb
        return salt + bytes(buf)

    def decrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        # symmetric: same operation reverses itself
        salt, ct = data[:16], data[16:]
        key = self._derive(key_bytes, salt, 32)
        buf = bytearray(ct)
        if len(buf) == 0:
            return bytes(buf)
        for i, kb in enumerate(key):
            buf[i % len(buf)] ^= kb
        return bytes(buf)


# ---------------------------------------------------------------------------
# PGP — RSA+AES-GCM hybrid (single-recipient)
# key_bytes must be PEM bytes of public key (encrypt) or private key (decrypt)
# ---------------------------------------------------------------------------

class PGPCipher(CipherBase):
    name = "PGP"

    def encrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        """Encrypt using recipient's RSA public key PEM."""
        return _pgp.encrypt(key_bytes, data)

    def decrypt(self, data: bytes, key_bytes: bytes) -> bytes:
        """Decrypt using holder's RSA private key PEM."""
        return _pgp.decrypt(key_bytes, data)


# ---------------------------------------------------------------------------
# Base64 (encoding only — no password)
# ---------------------------------------------------------------------------

class Base64Cipher(CipherBase):
    name = "Base64"

    def encrypt(self, data: bytes, _key_bytes: bytes) -> bytes:
        return base64.b64encode(data)

    def decrypt(self, data: bytes, _key_bytes: bytes) -> bytes:
        return base64.b64decode(data)


# ---------------------------------------------------------------------------
# Registry & engine
# ---------------------------------------------------------------------------

_CIPHER_MAP: dict[str, CipherBase] = {
    "AES-256-CBC": AES_CBC(),
    "AES-256-GCM": AES_GCM(),
    "ChaCha20-Poly1305": ChaCha20Poly1305(),
    "Blowfish-CBC": BlowfishCBC(),
    "3DES-CBC": TripleDES_CBC(),
    "XOR": XORCipher(),
    "XOR-FOLD": XORFoldCipher(),
    "Base64": Base64Cipher(),
    # All three PGP variants share PGPCipher; multi-key encrypt uses pgp_encrypt_multi() helpers.
    "PGP": PGPCipher(),
    "PGP-Multi": PGPCipher(),
    "PGP-Escrow": PGPCipher(),
}


class EncryptionEngine:
    """High-level API used by the GUI."""

    algorithms = ALGORITHMS

    @staticmethod
    def get_cipher(name: str) -> CipherBase:
        if name not in _CIPHER_MAP:
            raise ValueError(f"Unknown algorithm: {name}")
        return _CIPHER_MAP[name]

    @classmethod
    def encrypt(cls, data: bytes, key_bytes: bytes,
                algorithm: str = "AES-256-CBC") -> bytes:
        return cls.get_cipher(algorithm).encrypt(data, key_bytes)

    @classmethod
    def decrypt(cls, data: bytes, key_bytes: bytes,
                algorithm: str = "AES-256-CBC") -> bytes:
        return cls.get_cipher(algorithm).decrypt(data, key_bytes)

    @classmethod
    def encrypt_chain(cls, data: bytes, chain: list[dict]) -> bytes:
        """Apply a list of {algorithm, key_bytes} in order."""
        result = data
        for step in chain:
            result = cls.encrypt(result, step["key_bytes"], step["algorithm"])
        return result

    @classmethod
    def decrypt_chain(cls, data: bytes, chain: list[dict]) -> bytes:
        """Decrypt in reverse order of the chain."""
        result = data
        for step in reversed(chain):
            result = cls.decrypt(result, step["key_bytes"], step["algorithm"])
        return result

    # ── PGP helpers ───────────────────────────────────────────────────

    @staticmethod
    def pgp_encrypt(data: bytes, pub_pem: bytes) -> bytes:
        """Encrypt to a single RSA recipient (public key PEM)."""
        return _pgp.encrypt(pub_pem, data)

    @staticmethod
    def pgp_encrypt_multi(data: bytes, pub_pems: list[bytes]) -> bytes:
        """Encrypt to multiple RSA recipients (list of public key PEMs)."""
        return _pgp.encrypt_multi(pub_pems, data)

    @staticmethod
    def pgp_decrypt(data: bytes, priv_pem: bytes) -> bytes:
        """Decrypt an RSA+AES-GCM envelope using a private key PEM."""
        return _pgp.decrypt(priv_pem, data)

    @staticmethod
    def pgp_generate_keypair(bits: int = 4096) -> tuple[bytes, bytes]:
        """Generate an RSA keypair. Returns (private_pem, public_pem)."""
        return _pgp.generate_rsa_keypair(bits)
