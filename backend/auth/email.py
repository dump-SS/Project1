"""SMTP 邮件发送（验证码邮件）。

对应 mock-server/server.js 的 buildEmailHtml + setCode 的发信部分。
用 smtplib（标准库）+ ssl，不依赖第三方。

SMTP 配置从环境变量读（SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS），
与 mock-server/.env 对齐。

发送路由（按 SMTP_PROVIDER 自动切换）：
- real：真实 smtplib.SMTP_SSL 连接，失败抛异常
- mock：写到 logger "auth.email.mock"，团队测试时直接看后端日志取验证码
  （scripts/test-accounts/ 默认会切到 mock）
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from config import settings

logger = logging.getLogger(__name__)

# 邮件文案模板（对应 mock-server buildEmailHtml 的 copy）
_EMAIL_COPY = {
    "register": ("欢迎加入 EpochX", "感谢你注册 EpochX，请输入下面的验证码完成邮箱验证："),
    "login": ("登录验证码", "你正在登录 EpochX，请输入下面的验证码完成登录："),
    "reset": ("重置密码验证码", "你正在重置登录密码，请输入下面的验证码继续："),
}

_SUBJECTS = {
    "register": "【EpochX】注册验证码",
    "reset": "【EpochX】重置密码验证码",
    "login": "【EpochX】登录验证码",
}


def _build_html(code_type: str, code: str) -> str:
    """生成验证码邮件 HTML（简化版，保持与 mock-server 风格一致）。"""
    title, greeting = _EMAIL_COPY.get(code_type, ("邮箱验证码", "请输入下面的验证码完成验证："))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<body style="margin:0;padding:0;background:#f2fafd;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f2fafd;padding:36px 16px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;">
        <tr><td style="background:#ffffff;border-radius:16px;padding:40px 36px 36px;border:1px solid #e8f6fc;">
          <p style="font-family:Georgia,serif;font-size:22px;font-weight:bold;color:#2c3e50;">{title}</p>
          <div style="width:44px;height:4px;background:#4AD1FF;border-radius:2px;margin:0 0 26px;"></div>
          <p style="font-family:sans-serif;font-size:14px;color:#5a6b7a;line-height:1.8;margin:0 0 26px;">{greeting}</p>
          <div style="background:#eaf7ff;border:1px solid #cdeeff;border-radius:12px;padding:22px 16px;text-align:center;margin:0 0 26px;">
            <div style="font-family:sans-serif;font-size:12px;color:#7a8a99;letter-spacing:3px;margin-bottom:10px;">验 证 码</div>
            <div style="font-family:'Courier New',monospace;font-size:36px;font-weight:bold;color:#4AD1FF;letter-spacing:6px;">{code}</div>
          </div>
          <p style="font-family:sans-serif;font-size:12px;color:#9aa8b5;line-height:1.7;">验证码 5 分钟内有效，请勿泄露给他人。<br>如非本人操作，请忽略本邮件。</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _send_real(code_type: str, email: str, code: str) -> None:
    """真实 SMTP 发送。失败抛异常，调用方 catch 后记日志。"""
    smtp_host = getattr(settings, "smtp_host", "smtp.163.com")
    smtp_port = getattr(settings, "smtp_port", 465)
    smtp_user = getattr(settings, "smtp_user", "")
    smtp_pass = getattr(settings, "smtp_pass", "")

    if not smtp_user or not smtp_pass:
        # 未配置 SMTP：记日志不发送（开发环境常见，验证码可通过日志/测试获取）
        logger.warning(
            "[SMTP] 未配置 SMTP_USER/SMTP_PASS，验证码 %s 未发送（邮箱: %s）", code, email
        )
        return

    subject = _SUBJECTS.get(code_type, "【EpochX】邮箱验证码")
    html = _build_html(code_type, code)
    text = f"您的验证码是 {code}，5 分钟内有效。如非本人操作，请忽略本邮件。"

    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr(("EpochX", smtp_user))
    msg["To"] = email
    msg["Subject"] = subject
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [email], msg.as_string())


def _send_mock(code_type: str, email: str, code: str) -> None:
    """Mock 发送：把验证码写到 logger + 直接 print 到 stdout。

    团队测试时直接看后端终端 grep 取码；用 print 兜底是防止 uvicorn 的
    logging 配置（非 dictConfig）下子 logger 事件丢失。
    """
    msg = (
        f"[MOCK-EMAIL] type={code_type} to={email} code={code} "
        f"(SMTP_PROVIDER=mock, 团队测试模式, 直接从日志取码即可)"
    )
    # 双通道：logger + print，最大限度保证可见
    logger.warning(msg)
    # print 走 stdout，uvicorn 启动时不重定向 file 时一定可见
    import sys
    print(msg, file=sys.stdout, flush=True)


def send_code_email(code_type: str, email: str, code: str) -> None:
    """发送验证码邮件。

    按 SMTP_PROVIDER 路由：
    - real：真实 SMTP，失败抛异常
    - mock：写到 auth.email.mock logger，团队测试用，不抛异常

    调用方约定：try/except 捕获后写自己的业务日志，不阻断流程。
    """
    provider = getattr(settings, "smtp_provider", "real")
    if provider == "mock":
        _send_mock(code_type, email, code)
    else:
        _send_real(code_type, email, code)
