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
    yield
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

# CORS：MVP 阶段允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

from routes import assessment, goal, learning_record, plan, recommendation, summary, user

api_v1 = _APIRouter(prefix="/api/v1")
api_v1.include_router(user.router)
api_v1.include_router(goal.router)
api_v1.include_router(plan.router)
api_v1.include_router(learning_record.router)
api_v1.include_router(assessment.router)
api_v1.include_router(recommendation.router)
api_v1.include_router(summary.router)

app.include_router(health.router)
app.include_router(api_v1)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
