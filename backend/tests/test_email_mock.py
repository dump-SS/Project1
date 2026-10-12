"""SMTP mock 路由测试。

- 切 SMTP_PROVIDER=mock 时，发送不抛异常、不连真实 SMTP
- 验证码通过 logger "auth.email.mock" 输出，含 type/to/code 关键信息
- real 路径仍可加载（不真正连）

注意：conftest 会比本模块更早触发 `from config import settings`，
那时 pydantic-settings 读的是当时的 .env。我们测试时用 monkeypatch
直接覆盖 settings.smtp_provider 即可（属性赋值，不重新读 .env）。
"""

from __future__ import annotations

import logging

import pytest

from auth.email import send_code_email
from config import settings


@pytest.fixture(autouse=True)
def _ensure_mock_provider():
    """每个测试前强制 mock，测试结束恢复。"""
    original = getattr(settings, "smtp_provider", "real")
    settings.smtp_provider = "mock"
    yield
    settings.smtp_provider = original


def test_mock_provider_writes_to_logger(caplog):
    """mock 模式：验证码通过 logger 输出，不抛异常、不连真实 SMTP。"""
    caplog.set_level(logging.WARNING, logger="auth.email")

    send_code_email("register", "test1@epochx.dev", "123456")

    # mock 写到模块 logger auth.email，含 code + email
    mock_records = [r for r in caplog.records
                    if r.name == "auth.email" and "MOCK-EMAIL" in r.getMessage()]
    assert mock_records, "应至少有一条 auth.email 含 MOCK-EMAIL 标记的日志"
    last = mock_records[-1]
    msg = last.getMessage()
    assert "test1@epochx.dev" in msg
    assert "123456" in msg
    assert "register" in msg


def test_mock_provider_three_scenarios(caplog):
    """三种验证码类型（register/login/reset）都能走 mock。"""
    caplog.set_level(logging.WARNING, logger="auth.email")

    for code_type, code in [("register", "111111"), ("login", "222222"), ("reset", "333333")]:
        send_code_email(code_type, f"user_{code_type}@epochx.dev", code)

    types_seen = {r.getMessage().split("type=")[1].split(" ")[0]
                  for r in caplog.records
                  if r.name == "auth.email" and "MOCK-EMAIL" in r.getMessage()}
    assert types_seen == {"register", "login", "reset"}


def test_real_provider_does_not_call_mock(caplog, monkeypatch):
    """SMTP_PROVIDER=real 时，不会写 mock logger（路径分流正确）。

    必须显式清空 SMTP_USER/SMTP_PASS：_send_real 只有在这两项为空时才走
    「未配置」分支直接返回。若开发机 .env 配了真实邮箱凭据（本项目 .env 就配了
    163），用例会真的去连 SMTP——凭据有效则发真邮件、失效则抛
    SMTPAuthenticationError，两种情况都让用例结果取决于机器环境而随机失败。
    """
    settings.smtp_provider = "real"
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_pass", "")

    caplog.set_level(logging.WARNING, logger="auth.email")
    send_code_email("register", "test_real@epochx.dev", "999999")

    mock_records = [r for r in caplog.records
                    if r.name == "auth.email" and "MOCK-EMAIL" in r.getMessage()]
    assert not mock_records, "real 模式不应写 MOCK-EMAIL 日志"
    # 走「未配置」分支时应留下告警，而不是静默当作发送成功
    assert any("未配置 SMTP_USER/SMTP_PASS" in r.getMessage() for r in caplog.records), (
        "凭据为空时应有「未配置」告警"
    )


def test_smtp_defaults_point_to_resend():
    """迁移后**代码默认值**必须是 Resend（防有人改回 163）。

    注意：读 `Settings` 类的字段默认值，而不是 `settings` 实例——
    实例会被本机 `.env`（可能仍是 163）覆盖，那样测的是环境不是代码。
    """
    from config import Settings

    fields = Settings.model_fields
    assert fields["smtp_host"].default == "smtp.resend.com"
    # 2026-10-11 生产事故后由 465(SMTPS) 改为 587(STARTTLS)：465 在这条网络上不稳定。
    # 该端口必须与 auth/email.py 的 `SMTP` + `starttls()` 配套，不能只改端口号。
    assert fields["smtp_port"].default == 587
    assert fields["smtp_from"].default == "no-reply@send.epochx.net"
    # 缺 timeout 会让一次连不通的发信挂到系统级放弃（实测曾挂死约 17 分钟）
    # 2026-10-12 由 15 放宽到 30：network-flow 实证容器到 587 能建连且服务端有应答，
    # 真卡在 starttls 多 IP 重试，单次发码累计 30-40s。
    # ⚠️ 放宽必须与 routes/auth.py 的后台化配套，否则失败时仍会长时间占住请求线程。
    assert fields["smtp_timeout"].default == 30


def test_send_real_uses_smtp_from_not_smtp_user(monkeypatch):
    """🔴 From 头必须用 smtp_from，**不得**用 smtp_user。

    原因：Resend 的 SMTP 用户名是字面量 "resend"，若沿用旧写法
    `formataddr(("EpochX", smtp_user))` 会拼出无效地址 `EpochX <resend>` 被拒信。
    本用例不发真邮件——把 `smtplib.SMTP` 换成假的，只检查构造出的消息头。

    2026-10-11 起走 587 STARTTLS，故假对象需实现 ehlo/starttls/sendmail 全链路；
    若实现缺失，测试会因 AttributeError 而红——这正是我们要的：
    **协议一旦回退到 SMTP_SSL，这个用例会立刻失败**。
    """
    sent: dict = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port
            sent["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def ehlo(self):
            sent["ehlo"] = sent.get("ehlo", 0) + 1

        def starttls(self, context=None):
            sent["starttls"] = True

        def login(self, user, pwd):
            sent["login"] = (user, pwd)

        def sendmail(self, frm, to, msg):
            sent["envelope_from"] = frm
            sent["msg"] = msg

    monkeypatch.setattr("auth.email.smtplib.SMTP", _FakeSMTP)
    monkeypatch.setattr(settings, "smtp_user", "resend")
    monkeypatch.setattr(settings, "smtp_pass", "re_dummy")
    monkeypatch.setattr(settings, "smtp_host", "smtp.resend.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_from", "no-reply@send.epochx.net")

    from auth.email import _send_real

    _send_real("register", "to@epochx.dev", "654321")

    assert sent["host"] == "smtp.resend.com" and sent["port"] == 587
    # STARTTLS 两步式：必须真的调了 starttls，且 ehlo 在其前后各一次
    assert sent["starttls"] is True
    assert sent["ehlo"] == 2
    # timeout 必须显式传下去，否则又回到「挂到系统级放弃」的老问题
    assert sent["timeout"] is not None and sent["timeout"] <= 30
    assert sent["login"] == ("resend", "re_dummy")
    assert "no-reply@send.epochx.net" in sent["msg"]
    assert "EpochX <resend>" not in sent["msg"]  # 旧写法的产物绝不能出现
    # envelope sender 也应是发件地址，不是 smtp_user
    assert sent["envelope_from"] == "no-reply@send.epochx.net"

def test_code_send_is_backgrounded_not_synchronous():
    """🔴 发验证码必须走 BackgroundTasks，**不得**在请求线程里同步发信。

    2026-10-11 生产事故的治本修复。同步发信时，一次连不通的 SMTP 会占住请求线程
    数十秒（实测 41s；加 timeout 之前更是一次挂死约 17 分钟），而该请求全程持有
    DB session——期间 Neon 连接被掐断、回池成为失效连接，配合「连接池缺 pre_ping」
    把服务打成「/health 绿但接口大面积不可用」。

    本用例用 AST 静态检查（不依赖运行行为），锁死三点：
      1) send-code 三个端点都注入了 BackgroundTasks
      2) 都把 background_tasks 传给了 _send_code
      3) _send_code 里发信动作确实走 background_tasks.add_task
    **一旦有人改回同步调用，这个用例会立刻红。**
    """
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "routes" / "auth.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    endpoints = ("send_register_code", "send_reset_code", "send_login_code")
    for name in endpoints:
        fn = funcs.get(name)
        assert fn is not None, f"找不到 {name}"
        args = [a.arg for a in fn.args.args]
        assert "background_tasks" in args, (
            f"{name} 没有注入 background_tasks —— 发信会退回同步，正是事故根因"
        )
        kw_names = {kw.arg for kw in ast.walk(fn) if isinstance(kw, ast.Call)
                    for kw in kw.keywords if kw.arg}
        assert "background_tasks" in kw_names or any(
            isinstance(c, ast.Name) and c.id == "background_tasks"
            for c in ast.walk(fn)
        ), f"{name} 没有把 background_tasks 传给 _send_code"

    inner = funcs.get("_send_code")
    assert inner is not None, "找不到 _send_code"
    assert any(
        isinstance(n, ast.Attribute) and n.attr == "add_task"
        for n in ast.walk(inner)
    ), "_send_code 里没有 background_tasks.add_task —— 发信仍是同步调用"
