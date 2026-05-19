"""AES-128-ECB encryption/decryption for WeChat CDN media.

WeChat's iLink Bot API transfers media through an encrypted CDN.
Each file has its own AES-128 key. Keys may arrive as base64 or
hex-encoded strings.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

_AES_KEY_SIZE = 16  # 128 bits
_AES_BLOCK_SIZE = 128  # bits (for PKCS7 padding)


def parse_key(raw: str | bytes) -> bytes:
    """Normalize an AES key from base64 or hex to 16 raw bytes.

    Accepts:
    - 16 raw bytes (passthrough)
    - base64-encoded string (24 chars for 16 bytes)
    - hex-encoded string (32 chars for 16 bytes)
    """
    if isinstance(raw, bytes):
        if len(raw) == _AES_KEY_SIZE:
            return raw
        # Try decoding as base64 or hex string
        raw = raw.decode("ascii")

    raw = raw.strip()
    if len(raw) == 32:
        # Hex-encoded: 32 hex chars → 16 bytes
        try:
            key = bytes.fromhex(raw)
            if len(key) == _AES_KEY_SIZE:
                return key
        except ValueError:
            pass

    # Try base64
    try:
        key = base64.b64decode(raw)
        if len(key) == _AES_KEY_SIZE:
            return key
    except Exception:
        pass

    raise ValueError(f"Cannot parse AES key: expected 16 bytes, got {len(raw)} chars")


def generate_key() -> bytes:
    """Generate a random 128-bit AES key."""
    return os.urandom(_AES_KEY_SIZE)


def encrypt_media(plaintext: bytes, key: bytes | None = None) -> tuple[bytes, bytes]:
    """Encrypt media with AES-128-ECB + PKCS#7 padding.

    Returns (ciphertext, key). If key is None, a random key is generated.
    """
    if key is None:
        key = generate_key()
    if len(key) != _AES_KEY_SIZE:
        raise ValueError(f"AES key must be {_AES_KEY_SIZE} bytes, got {len(key)}")

    padder = PKCS7(_AES_BLOCK_SIZE).padder()
    padded = padder.update(plaintext) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return ciphertext, key


def decrypt_media(ciphertext: bytes, key: bytes) -> bytes:
    """Decrypt media with AES-128-ECB + PKCS#7 unpadding."""
    if len(key) != _AES_KEY_SIZE:
        raise ValueError(f"AES key must be {_AES_KEY_SIZE} bytes, got {len(key)}")

    cipher = Cipher(algorithms.AES(key), modes.ECB())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = PKCS7(_AES_BLOCK_SIZE).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    return plaintext


def key_to_base64(key: bytes) -> str:
    """Encode a raw key as base64 for API payloads."""
    return base64.b64encode(key).decode("ascii")
