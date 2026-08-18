"""Auth 子包：从 mock-server 迁移的认证逻辑。

模块划分（对应 mock-server/server.js 的各部分）：
- models.py: AuthUser / AuthCode / AuthSession ORM
- password.py: scrypt 密码哈希 + 校验 + 复杂度检查
- code.py: 验证码生成/存储/校验/消费
- session.py: Session 创建/查询/销毁
- email.py: SMTP 发验证码邮件
- rate_limit.py: IP/邮箱级限流 + 连续失败锁定
"""
from __future__ import annotations

from .models import AuthUser, AuthCode, AuthSession

__all__ = ["AuthUser", "AuthCode", "AuthSession"]
