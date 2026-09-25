"""
EpochX API — FastAPI 入口

阶段：
  1. ORM 骨架 + 启动建表 ✅
  2. Pydantic schemas + 路由 + mock 数据（当前）✅
  3. 接入 state_calculator.py + ai_suggestion.py，替换 mock（待）
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import Base, engine
from middleware import RequestIDMiddleware

# 触发所有 ORM 类注册
import models  # noqa: F401
# 注册所有路由
import routes  # noqa: F401
from routes import health  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时建表；关闭时释放连接。"""
    Base.metadata.create_all(bind=engine)

    # 板块二自动周复盘定时任务（v2.2-4）：单机 asyncio 定时器，失败不阻断启动
    scheduler_task = None
    community_task = None
    try:
        from jobs.weekly_knowledge_summary import start_weekly_summary_scheduler
        scheduler_task = start_weekly_summary_scheduler()
    except Exception:  # noqa: BLE001 — 定时器可选能力，不影响核心启动
        pass

    # 板块三聚合/特征抽取定时任务（M2/M3）：失败不阻断启动
    try:
        from jobs.community_aggregate import start_community_scheduler
        community_task = start_community_scheduler()
    except Exception:  # noqa: BLE001
        pass

    yield

    if scheduler_task is not None:
        scheduler_task.cancel()
    if community_task is not None:
        community_task.cancel()
    engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description=(
        "严格按 docs/openapi.yaml 实施；阶段 2：所有路由接 mock 数据，"
        "等待接入 state_calculator.py / ai_suggestion.py。"
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    # 响应默认按 alias 输出（camelCase），与 openapi.yaml 对齐
    response_model_by_alias=True,
)

# CORS：默认按同域部署（前端 域/app + 后端 域/api），此时同源、不需要 CORS 中间件。
# 只有分域部署才通过 CORS_ALLOW_ORIGINS 显式给出白名单。
#
# 原来写的是 allow_origins=["*"] + allow_credentials=True —— 浏览器规范禁止该组合，
# 带凭据的跨域请求会被直接拒绝。之所以一直没暴露，是因为 Vite dev server 把 /api
# 代理成了同源请求，CORS 从未被真正触发；一旦前后端分域名部署，第一个请求就会挂。
_cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 请求 ID / 访问日志（放在 CORS 之后，让客户端先拿到 CORS 头）
app.add_middleware(RequestIDMiddleware)

# --- 统一错误响应：所有非 2xx 都返回 openapi.yaml 0.2 节的 { error: { code, message, field? } } ---


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    # HTTPException 的 status_code 优先；detail 可以是 Error 详情或字符串
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        error_body = {
            "code": str(detail["code"]),
            "message": str(detail["message"]),
        }
        if "field" in detail and detail["field"] is not None:
            error_body["field"] = str(detail["field"])
    else:
        # 默认错误码：按状态码映射
        code_map = {
            400: "VALIDATION_FAILED",
            401: "UNAUTHENTICATED",
            403: "GUARDIAN_AUTHORIZATION_EXPIRED",
            404: "RESOURCE_NOT_FOUND",
            409: "STATE_CONFLICT",
            429: "RATE_LIMITED",
        }
        error_body = {
            "code": code_map.get(exc.status_code, "INTERNAL_ERROR"),
            "message": str(detail) if detail is not None else "请求处理失败",
        }
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_body},
        headers={"X-Request-ID": getattr(_request.state, "request_id", "")},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Pydantic 校验失败：取第一个错误的字段路径作为 field
    first_err = exc.errors()[0] if exc.errors() else {}
    field_path = ".".join(str(x) for x in first_err.get("loc", [])[1:])  # 去掉 body
    error_body = {
        "code": "VALIDATION_FAILED",
        "message": first_err.get("msg", "请求参数校验失败"),
        "field": field_path or None,
    }
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": error_body},
        headers={"X-Request-ID": getattr(_request.state, "request_id", "")},
    )


# --- 注册业务路由（与 openapi.yaml tags 一一对应）---
# 契约 servers.url = /api/v1（openapi.yaml 第 20 行），路由必须挂在同一前缀下，
# 否则前端按契约请求 /api/v1/learning-records 会 404。
# /health 是基础设施探活、不属于契约资源，留在根路径。
from fastapi import APIRouter as _APIRouter

from routes import assessment, auth, community, daily_summary, error_book, exam, goal, governance, knowledge, knowledge_kb, learning_record, mastery, plan, recommendation, recommendation_content, summary, timer, user, weight

api_v1 = _APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(user.router)
api_v1.include_router(goal.router)
api_v1.include_router(exam.router)
api_v1.include_router(plan.router)
api_v1.include_router(timer.router)
api_v1.include_router(learning_record.router)
api_v1.include_router(assessment.router)
api_v1.include_router(recommendation.router)
api_v1.include_router(recommendation_content.router)
api_v1.include_router(summary.router)
api_v1.include_router(weight.router)
api_v1.include_router(daily_summary.router)
api_v1.include_router(knowledge.router)
api_v1.include_router(knowledge_kb.router)
api_v1.include_router(error_book.router)
api_v1.include_router(mastery.router)
# OCR 路线已彻底放弃（#32）：原 routes/ocr.py 的 501 占位已删除，统一走多模态。
# 契约里本就没有 /ocr 路径，删除后代码与契约一致。
api_v1.include_router(community.router)
api_v1.include_router(community.aggregate_router)
# G 板块（pilot 运营与治理）：用量查询 / 报错 / 违规留痕 / 奖章 / 埋点（openapi v1.7.0）
api_v1.include_router(governance.router)

app.include_router(health.router)
app.include_router(api_v1)


# --- 前端静态托管 + SPA 回退（生产环境，与 API 同端口，无跨域）---
# FRONTEND_DIR 默认取 backend/ 的上级目录下的 frontend/，
# 服务器布局为 /epochx/{backend,frontend}，本地仓库布局同样成立，无需额外配置。
import os
from pathlib import Path

from fastapi.responses import FileResponse

FRONTEND_DIR = Path(
    os.getenv("FRONTEND_DIR", str(Path(__file__).resolve().parent.parent / "frontend"))
).resolve()


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    """静态文件优先，找不到回退 index.html（SPA 路由），并防目录穿越。"""
    candidate = (FRONTEND_DIR / full_path).resolve()
    if full_path and candidate.is_file() and candidate.is_relative_to(FRONTEND_DIR):
        return FileResponse(candidate)
    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "FRONTEND_NOT_DEPLOYED", "message": "前端产物未部署"}},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
