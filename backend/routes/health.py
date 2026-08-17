"""
健康检查：同时探活数据库。
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from config import settings
from database import engine

router = APIRouter(tags=["meta"])


@router.get("/health", summary="健康检查（应用 + 数据库）")
def health() -> dict:
    db_ok = True
    db_error: str | None = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_ok = False
        db_error = str(e)

    return {
        "status": "ok" if db_ok else "degraded",
        "service": settings.app_name,
        "checks": {
            "app": "ok",
            "database": {"status": "ok" if db_ok else "fail", "error": db_error},
        },
    }
