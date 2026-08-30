"""
应用配置：所有运行时参数从环境变量（.env）读取。

使用 pydantic-settings 做类型校验，访问 settings.xxx 即可拿到值。
严禁在业务代码里直接读 os.environ，统一走这里。
"""
from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
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

    # --- 板块二：embedding 开关（ADR：local/cloud/off，默认 off 走 name_fuzzy 降级）---
    # api = 第三方 OpenAI 兼容 /v1/embeddings（2026-08-25 决策：允许适当出域，预留自有服务器接入位）
    kb_embed_mode: str = "off"
    embed_api_key: str = ""
    embed_base_url: str = ""
    embed_model: str = ""
    # 单次 API 调用超时（秒）与重试次数（共 attempts = retries + 1）
    embed_request_timeout: int = 60
    embed_max_retries: int = 1

    # --- SMTP（验证码邮件，auth 迁移后从 mock-server 接管）---
    smtp_host: str = "smtp.163.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_pass: str = ""
    # 发送路由：real=真实 SMTP，mock=写到 logger（团队测试用，scripts/test-accounts/ 默认为 mock）
    smtp_provider: str = "real"

    # --- 速率限制（PRD 6.4）---
    rate_limit_recommendation_per_day: int = 5
    rate_limit_summary_per_day: int = 1

    # --- 板块三：群体匿名参照（参数配置化，决策方案 v1.7 §4.2/§4.3/§4.5，不写代码常量）---
    # 最小群体规模 k：聚合写入与查询双重校验
    community_min_pool: int = 20
    # 直方图桶计数下限 n：count < n 的桶并入相邻桶（防单桶小样本反推）
    community_bucket_min: int = 3
    # 匿名参与 ID 的 HMAC 盐（环境变量，不落库；轮换时保留最近 community_salt_keep 个版本）
    community_salt: str = ""
    community_salt_keep: int = 2
    # 聚合查询限频：每用户每分钟次数（§4.8）
    community_agg_rate_per_minute: int = 5
    # 「数据积累中」水印撤除门槛：连续达标周期数（§4.9，配置化）
    community_demo_min_periods: int = 4

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def _normalize_sqlite_path(self) -> "Settings":
        """把 sqlite 相对路径（如 ./data.db）锚定到 backend 目录。

        SQLite 相对路径依赖进程工作目录，uvicorn / 测试 / 脚本的 cwd 不一致时
        会连到不同文件、或报「unable to open database file」。这里统一转成
        基于 BACKEND_DIR 的绝对路径，消除 cwd 依赖。
        """
        url = self.database_url
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            raw = url[len("sqlite:///"):]
            if raw and not Path(raw).is_absolute():
                abs_path = (BACKEND_DIR / raw).resolve()
                self.database_url = f"sqlite:///{abs_path.as_posix()}"
        return self


settings = Settings()
