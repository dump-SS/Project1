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


def test_real_provider_does_not_call_mock(caplog):
    """SMTP_PROVIDER=real 时，不会写 mock logger（路径分流正确）。"""
    settings.smtp_provider = "real"
    # 真实路径需要 SMTP_USER/SMTP_PASS，conftest 走 mock 时这两个是空 → 走「未配置」分支 return
    # 关键是：不应触发 mock 输出
    caplog.set_level(logging.WARNING, logger="auth.email")
    send_code_email("register", "test_real@epochx.dev", "999999")
    mock_records = [r for r in caplog.records
                    if r.name == "auth.email" and "MOCK-EMAIL" in r.getMessage()]
    assert not mock_records, "real 模式不应写 MOCK-EMAIL 日志"