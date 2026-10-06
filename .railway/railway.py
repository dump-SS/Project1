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
#
# ⚠️ 必须是 `python3` 而不是 `python`：Railway 的 Railpack 构建镜像
# （railpack-builder:mise-2026.9.15）**只有 python3、没有 python**。
# 实测踩过：`python scripts/railway_build.py` → `sh: 1: python: not found` → exit 127。
# 这条在本地 Windows 上测不出来（那边恰好有 python.exe）。
BUILD_COMMAND = "python3 scripts/railway_build.py"

# `exec` 让 uvicorn 成为 1 号进程，正确接收 Railway 发来的 SIGTERM；
# 前面先跑一次索引校验 —— 缺索引就让容器**启动即失败**，
# 而不是变成 unhealthy 后被反复重启（重启修不好缺失的索引）。
#
# 两处与本地不同的写法，都是实测逼出来的：
# - `python3` 而不是 `python`：Railpack 镜像没有 python（同build 命令那条）
# - `python3 -m uvicorn` 而不是裸 `uvicorn`：不依赖 uvicorn 的console script
#   是否在 PATH 上，解释器路径是确定的
# - 用 $PORT（Railway 注入）而不是写死端口
START_COMMAND = (
    "cd backend && "
    "python3 ../scripts/check_vector_index.py && "
    "exec python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT"
)

# ⚠️ 会写生产库。**已获 Skyer 认可（2026-10-05，原话「可以」）**——
# 失败会中止部署是有意的：宁可不部署，也不要带着旧 schema 上线。
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
            # 私有桶的 S3 签名凭据。**桶不开公开读**，索引下载必须签名。
            # 为什么不能开公开读：桶 epoch-x 不只放索引——docs/deployment-stack-evaluation.md
            # 记着二期多模态拍题要在**同一个桶**存用户上传的题目图片（用户数据）。
            # 一旦公开读，索引公开会连带把用户图片一起暴露。
            # 为什么是**两个**变量而不是一个令牌：实测 R2 的 S3 兼容端点只认 AWS SigV4，
            # `Authorization: Bearer <R2 API 令牌>` 会被拒（HTTP 400 Missing
            # x-amz-content-sha256）。SigV4 需要 key id + secret 两个值。
            # 为什么不用预签名 URL：S3 预签名最长 7 天，而 Railway 变量是静态的，
            # 过期后每次构建都失败，变成必须定期轮换的运维债。签名每次现算，不过期。
            "KB_VECTOR_ACCESS_KEY_ID": preserve(),
            "KB_VECTOR_SECRET_ACCESS_KEY": preserve(),
            # off = 检索走向量（读本地 FAISS 索引）。
            # 绝不能设 api：那样 add() 会把向量追加进线上索引，污染检索。
            "KB_EMBED_MODE": "off",
            # —— 索引下载源（已定：Cloudflare R2，私有读 + 预置 URL）——
            # **不设则构建直接失败**——这是有意的：
            # 宁可部署失败，也不要「部署成功但检索降级成 name_fuzzy」。
            "KB_VECTOR_URL": preserve(),
            # —— 前端（已定：前后端**分离**，前端 epochx.net / 后端 api.epochx.net）——
            # 0 = 不在本服务构建前端，前端由 Vercel 等单独部署。
            # 此时 main.py 对 / 与 SPA 路由返回 FRONTEND_NOT_DEPLOYED —— **这是预期行为**，
            # 因为 API 服务本来就不负责托管 UI。
            "BUILD_FRONTEND": "0",
            # —— 安全 / CORS ——
            # 前后端分域名 → 必须显式白名单。**不能用 `*`**：
            # main.py 用的是 allow_credentials=True，而浏览器规范禁止
            # `allow_origins=["*"] + allow_credentials=True`（带凭据的跨域请求会被直接拒）。
            # 该组合的坑已经被踩过一次——Vite dev server 把 /api 代理成同源，
            # CORS 从未真正触发，一旦分域名部署第一个请求就挂。见 main.py:80-82。
            "CORS_ALLOW_ORIGINS": "https://epochx.net",
            # epochx.net 与 api.epochx.net 是**同站不同源**（SameSite 比的是 eTLD+1，不是 origin），
            # 所以 Lax 的 cookie 在跨源 fetch 里**照样会带上** → 保持 lax 即可。
            # 改成 none 会无谓放宽 SameSite 覆盖面，不是这里需要的。
            # 跨源真正要靠的是上面那行 CORS 白名单 + allow_credentials=True。
            "COOKIE_SAMESITE": "lax",
            "COOKIE_SECURE": "true",
            # 生产必须 false（true 会允许 X-User-ID 头任意冒充用户，只留给本地调试）。
            "ALLOW_INSECURE_USER_HEADER": "false",
            # —— 外部服务 ——
            # ⚠️ 这三个是**必需的**，不是可选增强。独立核实过：
            #   backend/config.py:56 默认 llm_provider="mock"、llm_base_url=""、llm_model=""
            #   backend/llm_provider.py:182 → if llm_provider=="mock" or not llm_api_key: MockProvider()
            # 也就是说**只配 LLM_API_KEY 是不够的**：llm_provider 仍是 "mock"，
            # 线上后端会一直走规则模板、根本不调 AIping，且不报错、不降级提示——
            # 是一种「看起来在跑 AI、其实没有」的静默失效。
            "LLM_PROVIDER": "openai_compatible",
            "LLM_BASE_URL": "https://aiping.cn/api/v1",
            # 模型 ID 由 Skyer 指定，**不要自行替换**。若 AIping 上查不到这个模型，
            # 正确做法是报「未验/不存在」，而不是换一个能用的——换模型是用户决策。
            "LLM_MODEL": "GLM-5.3-Flash",
            # 只有它是真密钥，不落文件。
            "LLM_API_KEY": preserve(),
            # ⚠️ EMBED_* 当前留空，但**不要**把它们写成「永久占位 / 永久不启用」——
            # 那是替用户做了「永远不启用」的决定，而这个决定从没经过 Skyer 同意。
            #
            # 真实语义（b7e3b5d 契约字段 userContentEmbeddingApiEnabled）：
            # 用户自行选择「错题原文/作答/学习记录能否走第三方 API」，**默认关闭**。
            # 闸门从「禁止配置」挪到了「用户同意」——`KB_EMBED_MODE` 是**部署默认值**，
            # `userContentEmbeddingApiEnabled` 是**用户级开关**，两者是独立的两道闸。
            #
            # 所以现状是：默认不出域（保守，且历史上出过配置泄漏导致用户内容出域的事故），
            # 但**用户一旦自己打开开关，系统就需要 EMBED_API_KEY / BASE_URL / MODEL**。
            # 那属于后续另一次配置变更，不在本轮范围；此处只保证「默认不出域」。
            "EMBED_API_KEY": preserve(),
            "EMBED_BASE_URL": preserve(),
            "EMBED_MODEL": preserve(),
            "SMTP_HOST": preserve(),
            "SMTP_USER": preserve(),
            "SMTP_PASS": preserve(),
            "SMTP_PROVIDER": "real",
        },
    )

    # 项目名用 EpochX（首字母大写），与 workspace 的人类可读名一致
    # （workspace 实际叫「 EpochX」，那个前导空格是建workspace 时误输入的，
    #  属另一个对象、不影响这里；新项目不再继承那个空格）。
    # 依据：workspace 名、全部提交信息、团队口语都用 EpochX。
    return project("EpochX", resources=[backend])
