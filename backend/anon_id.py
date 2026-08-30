"""板块三匿名参与 ID 生成器（决策 v1.7 §4.5）。

anon_participant_id = HMAC-SHA256(user_id, salt) 的前 16 字节 hex 前缀（不可反查）。
- salt 走环境变量（settings.community_salt），不落库；缺省时用进程内随机盐兜底
  （仅开发可用，生产必须配置 COMMUNITY_SALT）。
- salt_version 支持轮换：调用方按特征行的 salt_version 用对应版本盐计算 ID 做撤回删除；
  salt 保留最近 N 个版本（settings.community_salt_keep）。
"""
from __future__ import annotations

import hashlib
import hmac
import os

from config import settings

__all__ = ["compute_anon_id", "CURRENT_SALT_VERSION"]

CURRENT_SALT_VERSION = 0


def _salt_for(version: int) -> bytes:
    """取指定版本的盐（当前仅单版本实现；轮换时扩展为版本链）。"""
    salt = settings.community_salt or ""
    if not salt:
        # 开发兜底：从固定环境派生，保证进程内稳定
        salt = os.environ.get("COMMUNITY_SALT_DEV", "epochx-dev-salt")
    return salt.encode("utf-8")


def compute_anon_id(user_id: str, salt_version: int = CURRENT_SALT_VERSION) -> str:
    """HMAC-SHA256(user_id, salt) → 64 位 hex，不可反查。"""
    key = _salt_for(salt_version)
    digest = hmac.new(key, user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:64]
