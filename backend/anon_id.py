"""板块三匿名参与 ID 生成器（决策 v1.7 §4.5）。

anon_participant_id = HMAC-SHA256(user_id, salt_version 对应盐) 的 64 hex（不可反查）。
- 盐走环境变量 `COMMUNITY_SALT`，不落库；支持多版本：用 `|` 分隔的历史盐链（最新在前），
  列表索引即 salt_version（0 = 最新）。
- 保留最近 `community_salt_keep` 个版本用于撤回删除（§4.5）；更早版本的特征行已随
  周期滚动物理删除，不影响撤回承诺。
- 缺省时用进程内固定兜底盐（仅开发可用，生产必须配置 COMMUNITY_SALT）。
"""
from __future__ import annotations

import hashlib
import hmac

from config import settings

__all__ = ["compute_anon_id", "CURRENT_SALT_VERSION", "SALT_VERSIONS"]

CURRENT_SALT_VERSION = 0


def _salt_chain() -> list[bytes]:
    """解析盐链：最新在前，索引即版本号。"""
    raw = settings.community_salt or ""
    if not raw:
        raw = "epochx-dev-salt"
    keep = max(1, settings.community_salt_keep)
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    if not parts:
        parts = ["epochx-dev-salt"]
    return [p.encode("utf-8") for p in parts[:keep]]


# 当前可用的全部盐版本（撤回删除时循环，§4.5「保留最近 N 版」）
def _available_versions() -> list[int]:
    return list(range(len(_salt_chain())))


def _salt_for(version: int) -> bytes:
    chain = _salt_chain()
    if version < 0 or version >= len(chain):
        version = len(chain) - 1  # 越界回退到最老可用版本
    return chain[version]


# 模块导入时固化（settings 在 import 后已加载）：
SALT_VERSIONS = _available_versions()


def compute_anon_id(user_id: str, salt_version: int = CURRENT_SALT_VERSION) -> str:
    """HMAC-SHA256(user_id, 对应版本盐) → 64 位 hex，不可反查。"""
    key = _salt_for(salt_version)
    digest = hmac.new(key, user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:64]
