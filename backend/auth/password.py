"""密码哈希（scrypt + 随机盐）+ 复杂度校验。

对应 mock-server/server.js 的 hashPassword / verifyPassword / isStrongPassword。
用 hashlib.scrypt（标准库），不依赖第三方。
"""
from __future__ import annotations

import hashlib
import os
import secrets

# scrypt 参数（与 Node crypto.scryptSync 默认一致：N=16384, r=8, p=1, keylen=64）
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEYLEN = 64


def hash_password(password: str) -> str:
    """scrypt + 随机盐，返回 'salt:hash'（两者均为 hex）。"""
    salt = os.urandom(16).hex()
    hash_val = hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt),
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_KEYLEN,
    ).hex()
    return f"{salt}:{hash_val}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码。stored 格式 'salt:hash'。用 secrets.compare_digest 防时序攻击。"""
    if not stored or ":" not in stored:
        return False
    salt_hex, hash_hex = stored.split(":", 1)
    try:
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
            dklen=_KEYLEN,
        )
    except ValueError:
        return False
    expected = bytes.fromhex(hash_hex)
    return secrets.compare_digest(actual, expected)


def is_strong_password(password: str) -> bool:
    """密码复杂度：大写/小写/数字/符号 四类中至少满足两类。

    对应 mock-server isStrongPassword。
    """
    import re

    kinds = sum(bool(re.search(p, password)) for p in [r"[A-Z]", r"[a-z]", r"\d", r"[^A-Za-z0-9]"])
    return kinds >= 2
