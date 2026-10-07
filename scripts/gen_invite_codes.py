"""生成 pilot 邀请码（#50，一码一用）。

背景：注册改为**邀请码制**（契约 v1.8.0）：`POST /auth/register` 必填 `inviteCode`，
注册成功后回写 `invite_codes.used_by`（稳定 userId）/ `used_at` 供溯源。
按契约 `InviteCode` 的口径，**不做用户产品侧的邀请码管理接口**——生成只走本脚本。

码形：`EPX-XXXX-XXXX`（大写 Base32 字母表去掉易混字符 I/O/0/1），人可抄写、可转发。
规范化对齐后端 `routes/auth.py::_normalize_invite_code`（去空白 + 大写）。

幂等/安全性：随机生成，碰撞时重试；已存在的码不会覆盖（`--count` 表示"新增 N 个"）。

用法（在仓库根或 backend 下均可执行）：
    cd backend
    .venv\\Scripts\\python.exe ..\\scripts\\gen_invite_codes.py --count 20 --note "pilot 第一批"

参数：
    --count N     生成数量（默认 10）
    --note TEXT   备注（发给谁 / 哪批），写入 `invite_codes.note`
    --list        只列出邀请码状态表，不生成
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from database import Base, SessionLocal, engine
import models  # noqa: F401  触发所有 ORM 注册
from models.invite import InviteCode

# Base32 风格字母表：去掉 I / O / 0 / 1（手抄歧义）
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_GROUPS = 2
_GROUP_LEN = 4


def _random_code() -> str:
    parts = ["".join(secrets.choice(_ALPHABET) for _ in range(_GROUP_LEN)) for _ in range(_GROUPS)]
    return "EPX-" + "-".join(parts)


def generate(db, count: int, note: str | None) -> list[str]:
    created: list[str] = []
    while len(created) < count:
        code = _random_code()
        if db.get(InviteCode, code) is not None:
            continue  # 撞码概率极低，重试即可
        db.add(InviteCode(code=code, note=note))
        created.append(code)
    db.commit()
    return created


def list_codes(db) -> None:
    rows = db.execute(select(InviteCode).order_by(InviteCode.created_at.desc())).scalars().all()
    if not rows:
        print("（邀请码表为空——注册前先用本脚本生成）")
        return
    used = sum(1 for r in rows if r.used_by)
    print(f"共 {len(rows)} 个邀请码，已使用 {used} 个，未使用 {len(rows) - used} 个：")
    for r in rows:
        state = f"已用 by {r.used_by} @ {r.used_at}" if r.used_by else "未使用"
        note = f"  [{r.note}]" if r.note else ""
        print(f"  {r.code}  {state}{note}")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 pilot 邀请码（#50 一码一用）")
    parser.add_argument("--count", type=int, default=10, help="生成数量（默认 10）")
    parser.add_argument("--note", default=None, help="备注：发给谁 / 哪批")
    parser.add_argument("--list", action="store_true", help="只列出邀请码状态，不生成")
    args = parser.parse_args()

    # 与其它 seed 脚本一致：确保表结构存在（开发库可能尚未跑迁移）
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if args.list:
            list_codes(db)
            return
        if args.count < 1:
            print("--count 至少为 1")
            return
        created = generate(db, args.count, args.note)
        print(f"已生成 {len(created)} 个邀请码" + (f"（备注：{args.note}）" if args.note else "") + "：")
        for code in created:
            print(f"  {code}")
        print("\n把这些码发给对应同学；注册时必填，一码一用，用掉后 used_by 会记下使用者稳定 userId。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
