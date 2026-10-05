"""Railway 基础设施即代码（IaC）—— EpochX 后端。

为什么用 IaC 而不是 `railway.json`
---------------------------------
官方文档已把 Config as Code（`railway.json` / `railway.toml`）标为**废弃**：
「Existing files keep working for legacy services until **2026-12-01**」，
且**新服务无法再选用它**（"New services cannot opt into Config as Code"）。
所以新项目直接上 IaC，不写 `railway.json`。

注意两者的作用面不同，别混：
- `railway.json` 是**部署时**从仓库读的
- **`.railway/` 不参与部署**。IaC 由 CLI 的 `railway config plan` / `apply` 评估，
  把 build / start / healthcheck 等**推到服务设置上**，之后的部署才用这些设置。

作者 API 的 key 大小写是混的（已用 `railway-sdk` 实际源码核对，别凭直觉改）：
`build` / `start` / `healthcheck` 是小写，但 **`preDeploy` 与 `healthcheckTimeout`
是驼峰**；写错不报错、只是那一项被静默丢掉。

用法
----
    pip install railway-sdk
    railway login && railway link
    railway config plan      # 只读预览，安全
    railway config apply     # 确认后才写

密钥一律用 `preserve()`：**含义是「保留 Railway 上已有的值」**，
本文件因此不含任何真实凭据，也不因为值变而过期。
"""

from railway_sdk import define_railway, github, preserve, project, service

REPO = "dump-SS/Project1"

# 后端依赖不在根目录的 requirements.txt 里（在 backend/pyproject.toml），
# 且 `pip install ./backend` 实测会因setuptools 平铺布局发现失败，
# 所以依赖安装由 scripts/railway_build.py 用 tomllib 解析 pyproject 后执行。
BUILD_COMMAND = "python scripts/railway_build.py"

# `exec` 让 uvicorn 成为 1 号进程，正确接收 Railway 发来的 SIGTERM；
# 前面先跑一次索引校验 —— 缺索引就让容器**启动即失败**，
# 而不是变成 unhealthy 后被反复重启（重启修不好缺失的索引）。
# 用 $PORT（Railway 注入）而不是写死端口。
START_COMMAND = (
    "cd backend && "
    "python ../scripts/check_vector_index.py && "
    "exec uvicorn main:app --host 0.0.0.0 --port $PORT"
)

# ⚠️ 会写生产库。失败会中止部署——这是有意的（宁可不部署，也不要带着旧 schema 上线）。
# 待 lead-1 / Skyer 拍板：见 runbook「待确认事项」。
PRE_DEPLOY_COMMAND = "cd backend && python -m alembic upgrade head"


@define_railway
def main(ctx=None):
    backend = service(
        "backend",
        source=github(REPO, branch="main"),
        build=BUILD_COMMAND,
        start=START_COMMAND,
        preDeploy=PRE_DEPLOY_COMMAND,
        # 用 /health（应用 + 数据库），**不用** /health/vector-index：
        # 后者在索引 degraded 时仍返回 HTTP 200（degraded 是响应体字段，不是状态码），
        # 填进 healthcheckPath 会永远被判健康、等于没设。
        # 索引的闸门在 start 里——启动即失败，比变成 unhealthy 后反复重启更合适。
        healthcheck="/health",
        # 冷启动要加载 26.5MB FAISS 索引，给足超时，别让 Railway 误杀健康容器。
        healthcheckTimeout=300,
        # 显式写 1，不靠默认值。两处进程内状态依赖单实例：
        #   1. auth/rate_limit.py 的限流计数（其 docstring 自述多实例需 Redis）
        #   2. FAISS 索引的 _index / _refs 全局状态
        # 多副本会同时打破两处；pilot 期限流不准可接受，但索引不能没有。
        replicas=1,
        env={
            # —— 必填 ——
            # DATABASE_URL / JWT_SECRET 用 preserve()：值只在 Railway 上，本文件不承载。
            # DATABASE_URL 必须指向 Neon，且要带 psycopg2 可用的形式。
            "DATABASE_URL": preserve(),
            "JWT_SECRET": preserve(),
            # —— 向量索引（本项目 pilot 的关键路径）——
            # KB_VECTOR_DIR 指向 railway_build.py 下载解压后的目录。
            # 必须显式设：生产 DATABASE_URL 是 Neon（非 SQLite），
            # 不设时 _index_root() 会回落到进程 cwd，容器重启后路径可能变 → 读不到索引 → 静默降级。
            "KB_VECTOR_DIR": "/app/kb_vectors",
            "KB_VECTOR_EXPECTED_COUNT": "3391",
            # off = 检索走向量（读本地 FAISS 索引）。
            # 绝不能设 api：那样 add() 会把向量追加进线上索引，污染检索。
            "KB_EMBED_MODE": "off",
            # 索引下载源。**不设则构建直接失败**——这是有意的：
            # 宁可部署失败，也不要「部署成功但检索降级成 name_fuzzy」。
            "KB_VECTOR_URL": preserve(),
            # —— 前端 ——
            # 1 = 本服务构建并托管 SPA（同域，免 CORS）。0 = 前端由 Vercel 等单独部署，
            # 此时 main.py 对 / 与 SPA 路由返回 FRONTEND_NOT_DEPLOYED（预期行为）。
            "BUILD_FRONTEND": "1",
            # —— 安全 ——
            # 前后端同域（Railway 独占一个域名）时无需 CORS；
            # 若前端另部署到 Vercel，必须改成前端域名，否则浏览器拦跨域。
            "CORS_ALLOW_ORIGINS": preserve(),
            "COOKIE_SECURE": "true",
            "COOKIE_SAMESITE": "lax",
            # 生产必须 false（true 会允许 X-User-ID 头任意冒充用户，只留给本地调试）。
            "ALLOW_INSECURE_USER_HEADER": "false",
            # —— 外部服务 ——
            "LLM_API_KEY": preserve(),
            "EMBED_API_KEY": preserve(),
            "EMBED_BASE_URL": preserve(),
            "EMBED_MODEL": preserve(),
            "SMTP_HOST": preserve(),
            "SMTP_USER": preserve(),
            "SMTP_PASS": preserve(),
            "SMTP_PROVIDER": "real",
        },
    )

    return project("epochx", resources=[backend])
