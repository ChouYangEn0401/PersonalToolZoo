"""Simple PGP-like utilities: RSA keypair + hybrid encryption (RSA+AES-GCM)

This module provides a small, well-documented API for:
- generating RSA keypairs
- encrypting data with a recipient's public key (hybrid: AES-GCM payload + RSA-OAEP encrypted AES key)
- decrypting with the recipient private key
- signing and verifying using RSA PKCS#1 v1.5 with SHA-256

NOT a full PGP implementation — lightweight helper for app integration.
"""

from __future__ import annotations

import os
import struct
from typing import Tuple

from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
from Crypto.Hash import SHA256
from Crypto.Signature import pkcs1_15


def generate_rsa_keypair(bits: int = 2048) -> Tuple[bytes, bytes]:
    """Generate an RSA keypair.

    Returns (private_pem, public_pem) as bytes (PEM encoded).
    """
    key = RSA.generate(bits)
    priv = key.export_key(format="PEM")
    pub = key.publickey().export_key(format="PEM")
    return priv, pub


def encrypt(recipient_pub_pem: bytes, data: bytes) -> bytes:
    """Encrypt data to `recipient_pub_pem` using hybrid RSA+AES-GCM.

    Envelope format (binary):
      2 bytes: len(enc_key) (big-endian unsigned short)
      enc_key: RSA-OAEP encrypted AES key
      12 bytes: AES-GCM nonce
      16 bytes: AES-GCM tag
      rest: ciphertext

    Returns the envelope bytes.
    """
    pub = RSA.import_key(recipient_pub_pem)
    # AES-256 key
    aes_key = get_random_bytes(32)
    # encrypt symmetric key with RSA-OAEP
    rsa_cipher = PKCS1_OAEP.new(pub, hashAlgo=SHA256)
    enc_key = rsa_cipher.encrypt(aes_key)

    # AES-GCM encrypt payload
    nonce = get_random_bytes(12)
    aes = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
    ct, tag = aes.encrypt_and_digest(data)

    # pack: keylen(2) | enc_key | nonce | tag | ct
    return struct.pack(
        ">H", len(enc_key)
    ) + enc_key + nonce + tag + ct


def decrypt(recipient_priv_pem: bytes, envelope: bytes) -> bytes:
    """Decrypt envelope produced by `encrypt` using `recipient_priv_pem`.

    Raises ValueError on malformed data or decryption/authentication failure.
    """
    priv = RSA.import_key(recipient_priv_pem)
    if len(envelope) < 2:
        raise ValueError("Invalid envelope")
    keylen = struct.unpack(
        ">H", envelope[:2]
    )[0]
    offset = 2
    if len(envelope) < offset + keylen + 12 + 16:
        raise ValueError("Envelope too short")
    enc_key = envelope[offset : offset + keylen]
    offset += keylen
    nonce = envelope[offset : offset + 12]
    offset += 12
    tag = envelope[offset : offset + 16]
    offset += 16
    ct = envelope[offset:]

    rsa_cipher = PKCS1_OAEP.new(priv, hashAlgo=SHA256)
    aes_key = rsa_cipher.decrypt(enc_key)

    aes = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
    try:
        pt = aes.decrypt_and_verify(ct, tag)
    except Exception as exc:
        raise ValueError("AES-GCM authentication failed") from exc
    return pt


def sign(signer_priv_pem: bytes, data: bytes) -> bytes:
    """Return PKCS#1 v1.5 signature (SHA-256) of data using signer private key."""
    priv = RSA.import_key(signer_priv_pem)
    h = SHA256.new(data)
    sig = pkcs1_15.new(priv).sign(h)
    return sig


def verify(signer_pub_pem: bytes, data: bytes, signature: bytes) -> bool:
    """Verify PKCS#1 v1.5 signature. Returns True on success, False otherwise."""
    pub = RSA.import_key(signer_pub_pem)
    h = SHA256.new(data)
    try:
        pkcs1_15.new(pub).verify(h, signature)
        return True
    except (ValueError, TypeError):
        return False


def encrypt_and_sign(recipient_pub_pem: bytes, signer_priv_pem: bytes, data: bytes) -> bytes:
    """Sign `data` with `signer_priv_pem` then encrypt the payload for recipient.

    Returns the envelope bytes: rsa/aes envelope containing `signature || data`.
    """
    sig = sign(signer_priv_pem, data)
    payload = struct.pack(
        ">I", len(sig)
    ) + sig + data
    return encrypt(recipient_pub_pem, payload)


def decrypt_and_verify(recipient_priv_pem: bytes, signer_pub_pem: bytes, envelope: bytes) -> bytes:
    """Decrypt envelope and verify signature with `signer_pub_pem`.

    Returns the original data if signature verifies; raises ValueError otherwise.
    """
    payload = decrypt(recipient_priv_pem, envelope)
    if len(payload) < 4:
        raise ValueError("Malformed signed payload")
    siglen = struct.unpack(
        ">I", payload[:4]
    )[0]
    if len(payload) < 4 + siglen:
        raise ValueError("Malformed signed payload")
    sig = payload[4 : 4 + siglen]
    data = payload[4 + siglen :]
    if not verify(signer_pub_pem, data, sig):
        raise ValueError("Signature verification failed")
    return data
