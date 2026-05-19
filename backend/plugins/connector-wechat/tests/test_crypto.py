"""Unit tests for AES-128-ECB crypto module."""

from __future__ import annotations

import base64

import pytest

from connector_wechat.crypto import (
    decrypt_media,
    encrypt_media,
    generate_key,
    key_to_base64,
    parse_key,
)


def test_round_trip() -> None:
    plaintext = b"Hello, WeChat media!"
    ciphertext, key = encrypt_media(plaintext)
    assert ciphertext != plaintext
    result = decrypt_media(ciphertext, key)
    assert result == plaintext


def test_round_trip_large() -> None:
    plaintext = b"x" * 10000
    ciphertext, key = encrypt_media(plaintext)
    result = decrypt_media(ciphertext, key)
    assert result == plaintext


def test_round_trip_block_aligned() -> None:
    # 16 bytes = exactly one AES block
    plaintext = b"0123456789abcdef"
    ciphertext, key = encrypt_media(plaintext)
    result = decrypt_media(ciphertext, key)
    assert result == plaintext


def test_encrypt_with_provided_key() -> None:
    key = generate_key()
    plaintext = b"test data"
    ciphertext, returned_key = encrypt_media(plaintext, key)
    assert returned_key == key
    assert decrypt_media(ciphertext, key) == plaintext


def test_generate_key_length() -> None:
    key = generate_key()
    assert len(key) == 16


def test_parse_key_raw_bytes() -> None:
    key = b"\x00" * 16
    assert parse_key(key) == key


def test_parse_key_base64() -> None:
    raw = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10"
    encoded = base64.b64encode(raw).decode()
    assert parse_key(encoded) == raw


def test_parse_key_hex() -> None:
    raw = b"\xab\xcd\xef\x01\x23\x45\x67\x89\xab\xcd\xef\x01\x23\x45\x67\x89"
    hex_str = raw.hex()
    assert len(hex_str) == 32
    assert parse_key(hex_str) == raw


def test_parse_key_invalid() -> None:
    with pytest.raises(ValueError, match="Cannot parse AES key"):
        parse_key("too_short")


def test_parse_key_bytes_as_string() -> None:
    raw = b"\x01" * 16
    encoded = base64.b64encode(raw)  # bytes, not str
    assert parse_key(encoded) == raw


def test_key_to_base64() -> None:
    key = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10"
    result = key_to_base64(key)
    assert base64.b64decode(result) == key


def test_decrypt_wrong_key() -> None:
    plaintext = b"secret data"
    ciphertext, key = encrypt_media(plaintext)
    wrong_key = b"\xff" * 16
    # Wrong key either produces garbage or raises due to invalid padding
    try:
        result = decrypt_media(ciphertext, wrong_key)
        assert result != plaintext
    except ValueError:
        pass  # Invalid padding is expected with wrong key


def test_encrypt_invalid_key_length() -> None:
    with pytest.raises(ValueError, match="AES key must be 16 bytes"):
        encrypt_media(b"data", b"short")


def test_decrypt_invalid_key_length() -> None:
    with pytest.raises(ValueError, match="AES key must be 16 bytes"):
        decrypt_media(b"x" * 16, b"short")
