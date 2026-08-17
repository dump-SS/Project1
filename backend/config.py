"""
应用配置：所有运行时参数从环境变量（.env）读取。

使用 pydantic-settings 做类型校验，访问 settings.xxx 即可拿到值。
严禁在业务代码里直接读 os.environ，统一走这里。
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根目录（与 docs/ 平级）
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    # --- 服务 ---
    app_name: str = "EpochX API"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    # --- 数据库 ---
    database_url: str = "sqlite:///./data.db"

    # --- 鉴权 ---
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 天，与 mock-server 会话有效期一致

    # --- AI 接入（占位，下个 PR 接入真实 LLM）---
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # --- SMTP（验证码邮件，auth 迁移后从 mock-server 接管）---
    smtp_host: str = "smtp.163.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_pass: str = ""

    # --- 速率限制（PRD 6.4）---
    rate_limit_recommendation_per_day: int = 5
    rate_limit_summary_per_day: int = 1

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
