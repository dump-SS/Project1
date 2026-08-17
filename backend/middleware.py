"""
中间件：请求 ID / 访问日志
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("epochx.request")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 / 透传 X-Request-ID，并记录访问日志。"""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("[%s] %s %s → 500 (exception)", request_id, request.method, request.url.path)
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "[%s] %s %s → %d (%.1fms)",
            request_id, request.method, request.url.path,
            response.status_code, duration_ms,
        )
        return response
