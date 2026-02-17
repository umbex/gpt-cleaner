from __future__ import annotations

import base64
import hashlib
import random


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    out = bytearray()
    key_len = len(key)
    for idx, byte in enumerate(data):
        out.append(byte ^ key[idx % key_len])
    return bytes(out)


def encrypt_value(plain_text: str, secret: str) -> str:
    raw = plain_text.encode("utf-8")
    key = hashlib.sha256(secret.encode("utf-8")).digest()
    encrypted = _xor_bytes(raw, key)
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_value(cipher_text: str, secret: str) -> str:
    raw = base64.urlsafe_b64decode(cipher_text.encode("ascii"))
    key = hashlib.sha256(secret.encode("utf-8")).digest()
    decrypted = _xor_bytes(raw, key)
    return decrypted.decode("utf-8")


def simple_encrypt(value: str, secret: str) -> str:
    encrypted = encrypt_value(value, secret)
    return f"ENC[{encrypted}]"


def deterministic_anagram(value: str, seed: str) -> str:
    chars = list(value)
    randomizer = random.Random(hash_text(value + seed))
    randomizer.shuffle(chars)
    return "".join(chars)
