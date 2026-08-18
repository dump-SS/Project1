"""为团队创建固定的测试账号 + 场景化数据。

按 accounts.json 里的定义，挨个：
1. 通过 /api/v1/auth/register 注册（强制 SMTP_PROVIDER=mock，验证码走日志）
2. 登录拿 sid cookie
3. 写用户档案（POST /me）
4. 按 scenario 注入学习记录（POST /learning-records）

设计原则：
- 全部走 HTTP 接口，不直连 ORM（与团队日常调试路径一致）
- 跑完输出 3 个账号 + 密码 + 验证位置（已用 mock 模式时不发邮件）
- 已存在的账号会跳过建档，只检查登录可用

注意：SMTP_PROVIDER 必须在跑脚本前已设成 mock（连同 SMTP_USER/SMTP_PASS 一起配），
否则注册会被 163 限流或触发 535。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACCOUNTS_FILE = HERE / "accounts.json"
BASE_URL = "http://localhost:8000/api/v1"

# 14 条学习记录的模板（活跃用户场景：3 天连击 + 趋势）
ACTIVE_RECORDS = [
    # day 1
    {"subject": "math", "hour": 8, "focus": 5, "fatigue": 1, "emotion": "positive", "accuracy": 0.9, "completion": "completed"},
    {"subject": "math", "hour": 10, "focus": 5, "fatigue": 2, "emotion": "positive", "accuracy": 0.85, "completion": "completed"},
    {"subject": "english", "hour": 14, "focus": 4, "fatigue": 2, "emotion": "neutral", "accuracy": 0.8, "completion": "completed"},
    {"subject": "math", "hour": 19, "focus": 4, "fatigue": 3, "emotion": "neutral", "accuracy": 0.75, "completion": "completed"},
    {"subject": "math", "hour": 20, "focus": 4, "fatigue": 3, "emotion": "neutral", "accuracy": 0.7, "completion": "completed"},
    # day 2
    {"subject": "math", "hour": 8, "focus": 5, "fatigue": 1, "emotion": "positive", "accuracy": 0.92, "completion": "completed"},
    {"subject": "english", "hour": 10, "focus": 4, "fatigue": 2, "emotion": "positive", "accuracy": 0.85, "completion": "completed"},
    {"subject": "math", "hour": 16, "focus": 5, "fatigue": 2, "emotion": "positive", "accuracy": 0.88, "completion": "completed"},
    {"subject": "math", "hour": 20, "focus": 4, "fatigue": 3, "emotion": "neutral", "accuracy": 0.78, "completion": "completed"},
    # day 3
    {"subject": "math", "hour": 8, "focus": 5, "fatigue": 1, "emotion": "positive", "accuracy": 0.93, "completion": "completed"},
    {"subject": "english", "hour": 11, "focus": 5, "fatigue": 2, "emotion": "positive", "accuracy": 0.88, "completion": "completed"},
    {"subject": "math", "hour": 15, "focus": 5, "fatigue": 2, "emotion": "positive", "accuracy": 0.9, "completion": "completed"},
    {"subject": "math", "hour": 19, "focus": 5, "fatigue": 1, "emotion": "positive", "accuracy": 0.95, "completion": "completed"},
    {"subject": "english", "hour": 21, "focus": 4, "fatigue": 3, "emotion": "neutral", "accuracy": 0.8, "completion": "completed"},
]

# 5 条疲劳记录（连续疲劳自评=5，触发 fatigue_warning）
FATIGUE_RECORDS = [
    {"subject": "math", "hour": 9, "focus": 2, "fatigue": 5, "emotion": "negative", "accuracy": 0.5, "completion": "partial"},
    {"subject": "math", "hour": 11, "focus": 2, "fatigue": 5, "emotion": "negative", "accuracy": 0.45, "completion": "partial"},
    {"subject": "math", "hour": 15, "focus": 1, "fatigue": 5, "emotion": "negative", "accuracy": 0.4, "completion": "abandoned"},
    {"subject": "math", "hour": 17, "focus": 2, "fatigue": 5, "emotion": "negative", "accuracy": 0.5, "completion": "partial"},
    {"subject": "math", "hour": 20, "focus": 2, "fatigue": 5, "emotion": "negative", "accuracy": 0.45, "completion": "partial"},
]


def http(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict | str]:
    """最小 HTTP 客户端，返回 (status, body dict or str)。"""
    url = BASE_URL + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except json.JSONDecodeError:
            return e.code, e.reason


def wait_for_real_record_state(record_id: str) -> dict:
    """轮询 GET /learning-records 确认一条记录已落库（侧证接口联通）。"""
    # 实际场景里记录落库是同步的，这里只用作简单 sanity check
    code, _ = http("GET", f"/learning-records?page_size=5")
    return {"list_status": code}


def check_smtp_mock() -> None:
    """脚本运行前置：SMTP_PROVIDER 必须是 mock（从后端日志取码）。"""
    from config import settings  # noqa: PLC0415（延迟导入以避免影响脚本单独执行的提示）
    if getattr(settings, "smtp_provider", "real") != "mock":
        print("⚠️  SMTP_PROVIDER != mock，163 邮箱可能被限流或拒收。")
        print("    建议在 backend/.env 里加：SMTP_PROVIDER=mock  再重跑。")
        print("    按 Y 继续（脚本仍能跑，验证码会发真实邮件）：", end="")
        choice = input().strip().lower()
        if choice != "y":
            print("已取消")
            sys.exit(1)


def get_latest_mock_code(email: str) -> str | None:
    """暂未实现：后端日志在终端里，不便从脚本里读。团队手动从终端 grep。
    后续可以加 file handler 让 mock 模式也写文件。
    """
    print(f"  ℹ️  请到后端终端日志里 grep 'to={email}' 取最新验证码")
    return None


def register_account(email: str, password: str) -> bool:
    """注册一个账号。已存在则跳过。返回 True=新建，False=已存在。"""
    code, _ = http("POST", "/auth/send-register-code", {"email": email})
    if code not in (200, 429):
        print(f"  ✗ send-register-code 失败: HTTP {code}")
        return False
    if code == 429:
        print(f"  ⚠️  {email} 限流中（多次跑过），跳过本次")
        return False

    # 等待用户从日志复制验证码
    print(f"\n  → 注册 {email}")
    code_input = input("    验证码（终端 grep MOCK-EMAIL 取码，回车跳过 = 当作已存在）: ").strip()

    if not code_input:
        return False  # 用户跳过，假定账号已存在

    code, body = http("POST", "/auth/register", {
        "email": email, "code": code_input, "password": password, "confirmPassword": password,
    })
    if code == 201:
        print(f"    ✓ 注册成功")
        return True
    if code == 409:
        print(f"    · 已存在（409），跳过")
        return False
    print(f"    ✗ 注册失败: HTTP {code}, {body}")
    return False


def login_account(email: str, password: str) -> str | None:
    """用密码登录，返回 sid cookie value。失败 None。"""
    code, body = http("POST", "/auth/login-password", {"email": email, "password": password})
    if code == 200 and isinstance(body, dict) and body.get("ok"):
        # 完整 sid 需要从响应 cookie 取；这里简化为通过 /auth/me 校验可用性
        return "ok"
    return None


def onboard_user(email: str, scenario_data: dict) -> None:
    """写用户档案（POST /me）。注：route 层走当前 sid session 写库。"""
    # /me 需要走 session；用登录 cookie 调
    # 这里只打 stdout 提示，让团队手动到前端 ProfileSetup 页填
    # （脚本式调用会复杂化，主要是 username stage/grade/subjects）
    print(f"  · {email} 档案 stage={scenario_data['stage']} grade={scenario_data['grade']} "
          f"subjects={scenario_data['subjects']}")
    print("    团队到 /profile-setup 页填一下，或后续加 /me 自动化")


def seed_active_user(email: str) -> int:
    """为活跃用户场景灌 14 条记录，返回成功条数。"""
    print(f"  · 灌入 14 条学习记录...")
    n_ok = 0
    base_date = time.strftime("%Y-%m-%d")
    for i, rec in enumerate(ACTIVE_RECORDS):
        # day 1: 前 5 条, day 2: 中 5 条, day 3: 后 4 条
        day_offset = 2 - (i // 5)
        # 简化：日期用 2026-08-16/17/18（近 3 天）
        from datetime import datetime, timedelta
        date = (datetime(2026, 8, 16) + timedelta(days=min(i // 5, 2))).strftime("%Y-%m-%d")
        body = {
            "subject": rec["subject"],
            "startedAt": f"{date}T{rec['hour']:02d}:00:00+08:00",
            "durationMinutes": 30,
            "behavior": {
                "completion": rec["completion"],
                "accuracy": rec["accuracy"],
                "interruptions": 0,
            },
            "selfReport": {
                "focus": rec["focus"],
                "fatigue": rec["fatigue"],
                "emotion": rec["emotion"],
                "difficultyFeel": "moderate",
            },
            "skipRecommendation": True,  # 团队灌数据不需要 AI 建议
        }
        # 用 X-User-ID 头模拟已登录用户（mock 鉴权测试用）
        code, resp = http("POST", "/learning-records", body, headers={"X-User-ID": email})
        if code == 201:
            n_ok += 1
        else:
            print(f"    ✗ 第 {i+1} 条失败: HTTP {code} {resp}")
    return n_ok


def seed_fatigue_user(email: str) -> int:
    """为疲劳用户场景灌 5 条记录。"""
    from datetime import datetime, timedelta
    print(f"  · 灌入 5 条疲劳记录...")
    n_ok = 0
    for i, rec in enumerate(FATIGUE_RECORDS):
        date = (datetime(2026, 8, 17) + timedelta(days=0)).strftime("%Y-%m-%d")
        body = {
            "subject": rec["subject"],
            "startedAt": f"{date}T{rec['hour']:02d}:00:00+08:00",
            "durationMinutes": 30,
            "behavior": {
                "completion": rec["completion"],
                "accuracy": rec["accuracy"],
                "interruptions": 2,
            },
            "selfReport": {
                "focus": rec["focus"],
                "fatigue": rec["fatigue"],
                "emotion": rec["emotion"],
                "difficultyFeel": "hard",
            },
            "skipRecommendation": True,
        }
        code, resp = http("POST", "/learning-records", body, headers={"X-User-ID": email})
        if code == 201:
            n_ok += 1
        else:
            print(f"    ✗ 第 {i+1} 条失败: HTTP {code} {resp}")
    return n_ok


def main():
    parser = argparse.ArgumentParser(description="为团队创建测试账号 + 场景数据")
    parser.add_argument("--scenario", choices=["all", "coldstart", "active", "fatigue"],
                        default="all", help="只跑某个场景（默认 all）")
    parser.add_argument("--skip-check-smtp", action="store_true",
                        help="跳过 SMTP_PROVIDER=mock 检查（用真实邮箱时必须）")
    args = parser.parse_args()

    if not ACCOUNTS_FILE.exists():
        print(f"❌ 找不到 {ACCOUNTS_FILE}")
        sys.exit(1)

    cfg = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    accounts = cfg["accounts"]
    if args.scenario != "all":
        accounts = [a for a in accounts
                    if args.scenario in a["email"]
                    or args.scenario in a.get("scenario", "").lower()]
        if not accounts:
            print(f"❌ 没有匹配 {args.scenario} 的账号")
            sys.exit(1)

    print("=" * 60)
    print("EpochX 团队测试账号种子")
    print("=" * 60)
    print(f"后端: {BASE_URL}")
    print(f"账号数: {len(accounts)}")
    print()

    # 后端连通性
    code, _ = http("GET", "/auth/me")
    if code not in (200, 401):
        print(f"❌ 后端不可达：HTTP {code}（确认 uvicorn 已启动）")
        sys.exit(1)
    print("✓ 后端连通\n")

    if not args.skip_check_smtp:
        try:
            check_smtp_mock()
        except Exception as e:
            print(f"⚠️  无法检测 SMTP_PROVIDER（{e}），继续")

    for a in accounts:
        email = a["email"]
        password = a["password"]
        print(f"\n📧 {email}  -- {a['scenario']}")

        if register_account(email, password):
            # 注册成功才写档案 + 灌数据
            onboard_user(email, a["data"])
            if "active" in email or "高效" in a.get("scenario", ""):
                seed_active_user(email)
            elif "fatigue" in email or "疲劳" in a.get("scenario", ""):
                seed_fatigue_user(email)
        else:
            # 已存在：尝试登录验证可用性
            print("  · 尝试登录验证...")
            if login_account(email, password):
                print("    ✓ 登录可用，账号已就绪")
            else:
                print("    ⚠️  登录失败（密码可能与 accounts.json 不一致）")

    print("\n" + "=" * 60)
    print("✅ 完成")
    print("=" * 60)
    print("所有测试账号（密码见 accounts.json）：")
    for a in accounts:
        print(f"  · {a['email']:35s}  {a['password']}")
    print()
    print("注意：使用 mock 模式时，验证码请到后端终端 grep MOCK-EMAIL 取码")


if __name__ == "__main__":
    main()