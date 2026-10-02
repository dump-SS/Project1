"""HTTP 5xx 计数 + 请求数分母 —— G 板块 · pilot 一期前置（`pilot-metrics-and-admission.md` §2.2 / §5 第 1 项）。

为什么需要它
------------
pilot→beta 准入标准第 2 条要求「正式放号之日起连续 4 周后端 5xx 率 ≤ 1%」，
但项目此前**没有任何 5xx 监控设施**——只有 `routes/health.py` 一个探活端点，
无 Prometheus / Sentry / 日志聚合，这条验收门完全无法验证。

分子 + 分母都在本文件
---------------------
- **分子**：`/api/v1/**` 的 5xx，逐条实时落 `analytics_events`
  （`category="ai_quality"` / `eventType="http_5xx"`）。
- **分母**：同一中间件在**进程内累计**计入分母的请求数，到点/到量后 **flush 一条汇总**
  （`eventType="http_request_total"`，payload 带 `count`）。
  两条埋点同表同口径，5xx 率可以直接用一条 SQL 读出。

⚠️ **为什么分母不逐请求落库**（X0 2026-10-02 裁定，勿改成每请求一行）
--------------------------------------------------------------------
`analytics_events` 是给**结构化事件**设计的表（`category` 只有三个枚举），
每请求写一行会把它污染成请求流水表。读访问日志也不行：`epochx.request` 的 INFO 行
只在 uvicorn 启动时才有 handler（项目无 `basicConfig`）、**不落库**、会轮转、重启即断档，
撑不起「连续 4 周」的验收门。所以走「进程内计数 + 定期汇总落库」。

⚠️ **部署前提：单进程单端口 uvicorn**（`README.md`：生产形态只起一个 uvicorn 进程）。
计数器在进程内，**不跨进程**——与 `backend/README.md` 的限流计数同一前提
（那里也注明「多实例部署需换共享存储」）。**若将来上多 worker / 多实例，本分母会低估**，
届时需换共享存储（Redis 或计数表）。

口径（基线 v1.0 已锁定）
------------------------
- 统计范围：仅 `/api/v1/**` 的 API 请求
- 排除：`/health` 探活（被刷会稀释分母）、静态资源请求
- 分子只记 5xx；**4xx 不计入分子**
- 分母（`http_request_total` 的 `count`）：**本实现按 X0 裁定把 4xx 也计入**
  ——⚠️ 这与 §2.2 基线「排除 4xx」**互相矛盾**，见下「待 X0 确认」

落点方案 A（Skyer 2026-10-02 拍板）
-----------------------------------
`analytics_events.user_id` 是 NOT NULL，但**登录接口的 5xx 恰恰没有登录态**——而那是最该盯的。
方案 A：无登录态一律填固定值 `"system"`，payload 标 `userScoped=false`，
并约定 `user_id == "system"` 的事件**不参与任何用户维度指标**。
这样不必新建表、不必写 Alembic 迁移、不必改契约。

⚠️ 三处与裁定原文的偏离（都已在交付说明里点出，请 X0 复核）
----------------------------------------------------------
1. **分母汇总行一律 `user_id="system"`、`userScoped=false`**，不按「当前请求的登录态」填真实 id。
   理由：一条汇总跨多个用户，归属到任何单个用户都是错的；且「到点 flush」可能发生在任意请求上，
   没有唯一用户可归属。这也与 §2.2「system 事件不参与用户维度指标」一致。
2. **定时 flush 实现为「每次计入分母的请求时检查是否到点」**（opportunistic），
   而非后台定时任务。理由：`main.py` 只允许加一行 `add_middleware`，挂不上 lifespan；
   且 TestClient 下每个请求一个事件循环，后台任务会被销毁。
   行为等价于「阈值 / 到点取先到者」，**差异只在静默期**（见下方「已知取舍」）。
3. **payload 多存一个 `count4xx`**。裁定说「4xx 也计入分母」，而 §2.2 说「排除 4xx」——
   两个口径互斥。多存一个整数就能**两种口径都算得出来**（严格口径 = `count - count4xx`），
   不必再跑一轮。裁定的 SQL 只读 `$.count`，不受影响。

已知取舍
--------
- **进程退出时未 flush 的余数会丢**（`main.py` 挂不上 shutdown 钩子）。方向上保守：
  分母偏小 → 率偏高 → 门槛更严，不会漏放。
- 静默期结束后，计数要等下一次请求才 flush（窗口被拉长）。对「率」无影响，只影响时间切片粒度。

硬约束
------
- payload 只放计数与窗口信息。⚠️ **绝不落 query string、request body、任何 header**。
- 埋点写失败一律吞掉：治理是辅助能力，绝不阻断业务主流程（与 `governance_service` 同口径）。
- **不吞掉、不改写业务异常**：未处理异常记一条 500 后原样 `raise`。
- category 只能用 `ai_quality`：契约 `AnalyticsCategory` 枚举只有
  `chat_interaction` / `ai_quality` / `profile_trace`，写别的值会被 `track_event`
  **静默丢弃**（返回 None 且只打 warning），所以不要新增枚举值、不要改契约。
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from governance_service import track_event

logger = logging.getLogger("epochx.http_error")

# 只统计契约资源：/api/v1/**（/health、/docs、静态资源、SPA 回退都在此范围之外）
TRACKED_PREFIX = "/api/v1"

# 显式排除表。探活被刷会稀释分母，必须排除；静态资源由前缀规则天然排除，
# 这里仍列出来是为了让口径可读、可被断言（见 tests/test_http_error_tracking.py）。
EXCLUDED_PATHS = frozenset({"/health"})

# 无登录态时的固定 user_id（方案 A）。约定：该值不参与任何用户维度指标。
SYSTEM_USER_ID = "system"

# 契约 AnalyticsCategory 的合法值之一。写 "quality" 之类会被 track_event 静默丢弃。
CATEGORY_AI_QUALITY = "ai_quality"
EVENT_TYPE_HTTP_5XX = "http_5xx"
EVENT_TYPE_HTTP_REQUEST_TOTAL = "http_request_total"

# 分母 flush 触发条件（取先到者）。pilot 量级下 100 次 ≈ 数小时，够细也不至于写太频。
FLUSH_THRESHOLD = 100
FLUSH_INTERVAL_SECONDS = 300


def should_track_path(path: str) -> bool:
    """路径是否在统计范围内（仅 `/api/v1/**`）。

    纯函数，便于直接断言口径。状态码判定（分子 >=500 / 分母计入 4xx）不在这里。
    """
    if path in EXCLUDED_PATHS:
        return False
    return path == TRACKED_PREFIX or path.startswith(TRACKED_PREFIX + "/")


class _RequestCounter:
    """进程内请求计数（分母）。**不跨进程**——部署前提见模块 docstring。

    只在内存里累加（纯 Python、无 I/O），所以可以在事件循环里直接调用；
    只有真正要落库时才把取走的那一批交给线程池。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total = 0
        self.count_4xx = 0
        self.window_started_at: float | None = None
        self.baseline_emitted = False

    def reset(self) -> None:
        """清空计数（测试用；语义等价于一次进程重启后的初始态）。"""
        with self._lock:
            self.total = 0
            self.count_4xx = 0
            self.window_started_at = None
            self.baseline_emitted = False

    def account(self, status_code: int) -> tuple[bool, tuple[int, int, float] | None]:
        """记一次请求。返回 `(是否需落进程启动基线, 需 flush 的批次或 None)`。

        批次是 `(count, count4xx, windowMinutes)`，且**已从计数器里取走并归零**——
        这样 flush 期间（含 await 写库）进来的新请求会自然落到下一个窗口，不丢不重。
        """
        now = time.time()
        with self._lock:
            need_baseline = not self.baseline_emitted
            self.baseline_emitted = True

            if self.window_started_at is None:
                self.window_started_at = now

            self.total += 1
            if 400 <= status_code < 500:
                self.count_4xx += 1

            due = (
                self.total >= FLUSH_THRESHOLD
                or (now - self.window_started_at) >= FLUSH_INTERVAL_SECONDS
            )
            if not due:
                return need_baseline, None

            batch = (
                self.total,
                self.count_4xx,
                (now - self.window_started_at) / 60.0,
            )
            self.total = 0
            self.count_4xx = 0
            self.window_started_at = now
            return need_baseline, batch


_COUNTER = _RequestCounter()


def _resolve_actor(request: Request) -> str | None:
    """解析请求身份 → user_id；无登录态返回 None。

    刻意复用 `routes.deps.resolve_user_id`（身份的**唯一实现**）：若这里另写一份，
    鉴权逻辑一变、埋点归属就会静默漂移。这里不做 401——埋点是旁路，没有身份就是 system。
    """
    from auth.session import COOKIE_NAME
    from routes.deps import resolve_user_id

    return resolve_user_id(
        sid=request.cookies.get(COOKIE_NAME),
        authorization=request.headers.get("authorization"),
        x_user_id=request.headers.get("X-User-ID"),
    )


async def _record(request: Request, status_code: int, duration_ms: float) -> None:
    """落一条 5xx 埋点（分子）。**任何失败都吞掉**——绝不阻断业务响应。"""
    try:
        actor = await run_in_threadpool(_resolve_actor, request)
        payload = {
            # ⚠️ 只有 path：request.url.path 不含 query string，也不含 body / header
            "path": request.url.path,
            "method": request.method,
            "statusCode": status_code,
            "durationMs": round(duration_ms, 1),
            "userScoped": actor is not None,
        }
        await run_in_threadpool(
            track_event,
            actor or SYSTEM_USER_ID,
            CATEGORY_AI_QUALITY,
            EVENT_TYPE_HTTP_5XX,
            None,  # session_id：5xx 是请求级事件，不挂 Chat 会话
            payload,
        )
    except Exception as e:  # noqa: BLE001 — 埋点失败绝不阻断业务
        logger.debug("[http_5xx] 埋点写入失败（已忽略）: %s", e)


def _flush_total(count: int, count_4xx: int, window_minutes: float) -> None:
    """落一条分母汇总（同步，供线程池调用）。**任何失败都吞掉**。

    ⚠️ 汇总行一律记在 `system` 名下：一批计数跨多个用户，归属到任何单个用户都是错的。
    """
    try:
        payload = {
            "count": count,
            "count4xx": count_4xx,  # 让 §2.2「排除 4xx」的严格口径也能算（= count - count4xx）
            "windowMinutes": round(window_minutes, 2),
            "userScoped": False,
        }
        track_event(
            SYSTEM_USER_ID,
            CATEGORY_AI_QUALITY,
            EVENT_TYPE_HTTP_REQUEST_TOTAL,
            None,
            payload,
        )
    except Exception as e:  # noqa: BLE001 — 分母是辅助指标，绝不阻断业务
        logger.debug("[http_total] 分母 flush 失败（已忽略）: %s", e)


class HttpErrorTrackingMiddleware(BaseHTTPMiddleware):
    """把 `/api/v1/**` 的 5xx 落进 `analytics_events`（分子），并累计请求数（分母）。"""

    async def dispatch(self, request: Request, call_next):
        track = should_track_path(request.url.path)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 未处理异常：外层 ServerErrorMiddleware 会把它变成 500。
            # 先记一条，再**原样抛出**——中间件不得吞掉或改写业务异常。
            if track:
                await _record(request, 500, (time.perf_counter() - start) * 1000)
                await self._account_request(500)
            raise

        if track:
            if response.status_code >= 500:
                await _record(
                    request, response.status_code, (time.perf_counter() - start) * 1000
                )
            await self._account_request(response.status_code)
        return response

    @staticmethod
    async def _account_request(status_code: int) -> None:
        """分母记账：纯内存累加；只有需要落库时才进线程池。失败一律吞掉。"""
        try:
            need_baseline, batch = _COUNTER.account(status_code)
            if need_baseline:
                # 进程启动基线：count=0。让「第一个周期」也有起点可算。
                await run_in_threadpool(_flush_total, 0, 0, 0.0)
            if batch is not None:
                await run_in_threadpool(_flush_total, *batch)
        except Exception as e:  # noqa: BLE001 — 计数失败绝不阻断业务
            logger.debug("[http_total] 分母计数失败（已忽略）: %s", e)


# --- 读出用 SQL（pilot 运营直接复制）---

FIVE_XX_COUNT_SQL = """
-- 分子：/api/v1/** 的 5xx 事件，按天。err_5xx_anonymous = 无登录态（登录接口等）。
-- SQLite（本地开发库 backend/data.db 用这条）
SELECT date(occurred_at)                                        AS day,
       COUNT(*)                                                 AS err_5xx,
       SUM(CASE WHEN user_id = 'system' THEN 1 ELSE 0 END)      AS err_5xx_anonymous
FROM   analytics_events
WHERE  category = 'ai_quality'
  AND  event_type = 'http_5xx'
GROUP  BY day
ORDER  BY day;
"""

FIVE_XX_COUNT_SQL_PG = """
-- 分子：/api/v1/** 的 5xx 事件，按天（Postgres / Neon 用这条）
SELECT (occurred_at AT TIME ZONE 'UTC')::date                   AS day,
       COUNT(*)                                                 AS err_5xx,
       COUNT(*) FILTER (WHERE user_id = 'system')                AS err_5xx_anonymous
FROM   analytics_events
WHERE  category = 'ai_quality'
  AND  event_type = 'http_5xx'
GROUP  BY day
ORDER  BY day;
"""

FIVE_XX_RATE_SQL = """
-- 5xx 率（近 28 天）：分子分母同表同口径。分母 = http_request_total 的 count 之和。
-- SQLite（本地开发库 backend/data.db）
SELECT
  ROUND(100.0 * SUM(CASE WHEN event_type = 'http_5xx' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN event_type = 'http_request_total'
                         THEN CAST(json_extract(payload_json, '$.count') AS INTEGER)
                         ELSE 0 END), 0), 3) AS rate_pct
FROM analytics_events
WHERE category = 'ai_quality'
  AND event_type IN ('http_5xx', 'http_request_total')
  AND created_at >= datetime('now', '-28 days');
"""

FIVE_XX_RATE_SQL_PG = """
-- 5xx 率（近 28 天）—— Postgres / Neon（目标环境）
SELECT
  ROUND(100.0 * COUNT(*) FILTER (WHERE event_type = 'http_5xx')
        / NULLIF(SUM(CASE WHEN event_type = 'http_request_total'
                          THEN (payload_json::jsonb ->> 'count')::int ELSE 0 END), 0), 3)
        AS rate_pct
FROM analytics_events
WHERE category = 'ai_quality'
  AND event_type IN ('http_5xx', 'http_request_total')
  AND created_at >= now() - interval '28 days';
"""

FIVE_XX_RATE_SQL_STRICT = """
-- §2.2 严格口径（分母排除 4xx）：与上面唯一差别是分母减掉 count4xx。
-- ⚠️ 仅在 X0 裁定「分母排除 4xx」时使用；裁定若维持「4xx 也计」，用 FIVE_XX_RATE_SQL。
SELECT
  ROUND(100.0 * SUM(CASE WHEN event_type = 'http_5xx' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN event_type = 'http_request_total'
                         THEN CAST(json_extract(payload_json, '$.count') AS INTEGER)
                              - CAST(json_extract(payload_json, '$.count4xx') AS INTEGER)
                         ELSE 0 END), 0), 3) AS rate_pct
FROM analytics_events
WHERE category = 'ai_quality'
  AND event_type IN ('http_5xx', 'http_request_total')
  AND created_at >= datetime('now', '-28 days');
"""

FIVE_XX_RATE_SQL_STRICT_PG = """
-- §2.2 严格口径（分母排除 4xx）—— Postgres / Neon
SELECT
  ROUND(100.0 * COUNT(*) FILTER (WHERE event_type = 'http_5xx')
        / NULLIF(SUM(CASE WHEN event_type = 'http_request_total'
                          THEN (payload_json::jsonb ->> 'count')::int
                               - (payload_json::jsonb ->> 'count4xx')::int
                          ELSE 0 END), 0), 3) AS rate_pct
FROM analytics_events
WHERE category = 'ai_quality'
  AND event_type IN ('http_5xx', 'http_request_total')
  AND created_at >= now() - interval '28 days';
"""
