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

    # 危险开关：启用「非安全身份回落链」——X-User-ID 头 / Bearer u_ 前缀 token /
    # 无会话时兜底共享账号 u_10237（见 routes/deps.py:current_user 的第 2–4 层）。
    # 默认 false：生产环境身份唯一来源是 sid cookie，无有效会话一律 401。
    # 打开它等于允许请求方自报身份冒充任意用户（垂直越权），只允许在测试/联调环境置 true。
    allow_insecure_user_header: bool = False

    # --- 部署形态：CORS 与 Cookie 策略（部署评估 §2-5 / §2-6）---
    # 首选同域部署（前端 域/app + 后端 域/api）：同源，不需要 CORS 中间件，
    # cookie 用 SameSite=Lax 即可。只有分域部署才需要配置下面三项。
    #
    # 允许的跨域来源，逗号分隔（如 "https://example.com,https://app.example.com"）。
    # 留空 = 不挂 CORS 中间件（同域部署的默认形态）。
    # ⚠️ 不能写 "*"：浏览器规范禁止 allow_origins=["*"] 与 allow_credentials=True 并用。
    cors_allow_origins: str = ""
    # sid cookie 的 SameSite 策略：lax（同域，默认）/ strict / none（分域必需）。
    # 置 none 时自动补 Secure——浏览器对 SameSite=None 强制要求 Secure，否则直接丢弃 cookie。
    cookie_samesite: str = "lax"
    # 给 sid cookie 加 Secure（只在 HTTPS 上回传）。生产 HTTPS 应置 true；
    # 本地 http 开发必须保持 false，否则浏览器不回传 cookie、登录态直接失效。
    cookie_secure: bool = False

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
