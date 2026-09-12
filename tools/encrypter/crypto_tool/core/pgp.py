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
from Crypto.Signature import pkcs1_15, pss


def generate_rsa_keypair(bits: int = 4096) -> Tuple[bytes, bytes]:
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
    # single-recipient wrapper around encrypt_multi
    return encrypt_multi([recipient_pub_pem], data)


def encrypt_multi(recipient_pub_pems: list[bytes], data: bytes) -> bytes:
    """Encrypt to multiple recipients. Produces an envelope containing
    one RSA-OAEP-encrypted copy of the AES session key per recipient.

    Envelope format (binary):
      1 byte: version (0x01)
      2 bytes: recipient count (big-endian unsigned short)
      for each recipient:
        2 bytes: len(enc_key)
        enc_key bytes
      12 bytes: AES-GCM nonce
      16 bytes: AES-GCM tag
      rest: ciphertext
    """
    if not recipient_pub_pems:
        raise ValueError("No recipients")
    # generate AES-256 session key
    aes_key = get_random_bytes(32)
    enc_keys = []
    for pub_pem in recipient_pub_pems:
        pub = RSA.import_key(pub_pem)
        rsa_cipher = PKCS1_OAEP.new(pub, hashAlgo=SHA256)
        enc_keys.append(rsa_cipher.encrypt(aes_key))

    nonce = get_random_bytes(12)
    aes = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
    ct, tag = aes.encrypt_and_digest(data)

    out = bytearray()
    out.append(0x01)  # version
    out += struct.pack(
        ">H", len(enc_keys)
    )
    for ek in enc_keys:
        out += struct.pack(">H", len(ek)) + ek
    out += nonce + tag + ct
    return bytes(out)


def decrypt(recipient_priv_pem: bytes, envelope: bytes) -> bytes:
    """Decrypt envelope produced by `encrypt_multi` using `recipient_priv_pem`.

    Tries to decrypt each enclosed encrypted session key with the provided
    private key; when one succeeds it's used to decrypt the AES-GCM payload.
    """
    priv = RSA.import_key(recipient_priv_pem)
    if not envelope:
        raise ValueError("Empty envelope")
    ver = envelope[0]
    if ver != 0x01:
        raise ValueError("Unsupported envelope version")
    if len(envelope) < 3:
        raise ValueError("Envelope too short")
    offset = 1
    rcount = struct.unpack(">H", envelope[offset:offset+2])[0]
    offset += 2
    enc_keys = []
    for _ in range(rcount):
        if len(envelope) < offset + 2:
            raise ValueError("Malformed envelope")
        klen = struct.unpack(">H", envelope[offset:offset+2])[0]
        offset += 2
        if len(envelope) < offset + klen:
            raise ValueError("Malformed envelope")
        enc_keys.append(envelope[offset:offset+klen])
        offset += klen
    if len(envelope) < offset + 12 + 16:
        raise ValueError("Envelope missing payload")
    nonce = envelope[offset:offset+12]
    offset += 12
    tag = envelope[offset:offset+16]
    offset += 16
    ct = envelope[offset:]

    rsa_cipher = PKCS1_OAEP.new(priv, hashAlgo=SHA256)
    aes_key = None
    for ek in enc_keys:
        try:
            aes_key = rsa_cipher.decrypt(ek)
            break
        except Exception:
            continue
    if aes_key is None:
        raise ValueError("No matching encrypted session key for this private key")

    aes = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
    try:
        pt = aes.decrypt_and_verify(ct, tag)
    except Exception as exc:
        raise ValueError("AES-GCM authentication failed") from exc
    return pt


def sign(signer_priv_pem: bytes, data: bytes) -> bytes:
    """Return RSA-PSS signature (SHA-256) of data using signer private key."""
    priv = RSA.import_key(signer_priv_pem)
    h = SHA256.new(data)
    sig = pss.new(priv).sign(h)
    return sig


def verify(signer_pub_pem: bytes, data: bytes, signature: bytes) -> bool:
    """Verify RSA-PSS signature. Returns True on success, False otherwise."""
    pub = RSA.import_key(signer_pub_pem)
    h = SHA256.new(data)
    try:
        pss.new(pub).verify(h, signature)
        return True
    except (ValueError, TypeError):
        return False


def fingerprint(pub_pem: bytes) -> str:
    """Return a hex SHA-256 fingerprint of a public key PEM (lowercase hex)."""
    h = SHA256.new(pub_pem).digest()
    return h.hex()


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
