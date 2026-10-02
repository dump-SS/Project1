"""HTTP 5xx 计数中间件 —— G 板块 · pilot 一期前置（`pilot-metrics-and-admission.md` §2.2 / §5 第 1 项）。

为什么需要它
------------
pilot→beta 准入标准第 2 条要求「正式放号之日起连续 4 周后端 5xx 率 ≤ 1%」，
但项目此前**没有任何 5xx 监控设施**——只有 `routes/health.py` 一个探活端点，
无 Prometheus / Sentry / 日志聚合，这条验收门完全无法验证。

口径（基线 v1.0 已锁定，勿自创）
--------------------------------
- 统计范围：仅 `/api/v1/**` 的 API 请求
- 只记 5xx：`response.status_code >= 500` 才记；**4xx 一律不记**（客户端行为，与服务稳定性无关）
- 排除：`/health` 探活（被刷会稀释分母）、静态资源请求
- 落点：`analytics_events`，`category="ai_quality"` / `eventType="http_5xx"`

落点方案 A（Skyer 2026-10-02 拍板）
-----------------------------------
`analytics_events.user_id` 是 NOT NULL，但**登录接口的 5xx 恰恰没有登录态**——而那是最该盯的。
方案 A：无登录态一律填固定值 `"system"`，payload 标 `userScoped=false`，
并约定 `user_id == "system"` 的事件**不参与任何用户维度指标**。
这样不必新建表、不必写 Alembic 迁移、不必改契约。

⚠️ 已知缺口：分母不在库里（留 Skyer 定夺，勿自行"补"）
-----------------------------------------------------
§2.2 的**分母是请求数**，而本中间件按口径只落 5xx 行 → **分母不在库内**。
所以单靠 SQL 只能读出分子，读不出"率"。分母目前只有两个来源：
  ① 访问日志：`middleware.RequestIDMiddleware` 每个请求打一行 `→ <status>`；
  ② 补一条总请求计数埋点——会显著增加 `analytics_events` 行数，或需要迁移（属 X0 决策）。
本文件只提供分子 SQL（见 `FIVE_XX_COUNT_SQL` / `FIVE_XX_COUNT_SQL_PG`）。

硬约束
------
- payload 只放 path / method / statusCode / durationMs / userScoped。
  ⚠️ **绝不落 query string、request body、任何 header**——token 与个人信息都在那里。
- 埋点写失败一律吞掉：治理是辅助能力，绝不阻断业务主流程（与 `governance_service` 同口径）。
- **不吞掉、不改写业务异常**：未处理异常记一条 500 后原样 `raise`。
- category 只能用 `ai_quality`：契约 `AnalyticsCategory` 枚举只有
  `chat_interaction` / `ai_quality` / `profile_trace`，写别的值会被 `track_event`
  **静默丢弃**（返回 None 且只打 warning），所以不要新增枚举值、不要改契约。
"""
from __future__ import annotations

import logging
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


def should_track_path(path: str) -> bool:
    """路径是否在统计范围内（仅 `/api/v1/**`）。

    纯函数，便于直接断言口径。状态码判定（>=500）不在这里，见 `_record` 的调用点。
    """
    if path in EXCLUDED_PATHS:
        return False
    return path == TRACKED_PREFIX or path.startswith(TRACKED_PREFIX + "/")


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
    """落一条 5xx 埋点。**任何失败都吞掉**——绝不阻断业务响应。"""
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


class HttpErrorTrackingMiddleware(BaseHTTPMiddleware):
    """把 `/api/v1/**` 的 5xx 落进 `analytics_events`（§2.2 的数据来源）。"""

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
            raise

        if track and response.status_code >= 500:
            await _record(
                request, response.status_code, (time.perf_counter() - start) * 1000
            )
        return response


# --- 读出用 SQL（pilot 运营直接复制；⚠️ 分母不在库内，见模块 docstring）---

FIVE_XX_COUNT_SQL = """
-- 分子：/api/v1/** 的 5xx 事件，按天。err_5xx_anonymous = 无登录态（登录接口等）。
-- SQLite（本地开发库 data.db 用这条）
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
