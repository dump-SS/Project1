"""
健康检查：同时探活数据库。

⚠️ **本文件下的端点（含 `/health/vector-index`）是运维诊断端点，不在
`docs/openapi.yaml` 契约内、不保证向后兼容。**

依据（lead-1 2026-10-04 裁定）：`openapi.yaml` 文件头明写「本文件严格按设计文档
生成，未引入文档之外的字段」，它描述的是**业务资源**；`/health` 本身也不在契约里，
运维诊断端点放在契约外是既成先例。契约的对外承诺不含这些端点，
它们可随部署形态与排障需要调整——**前端/客户端不要依赖它们的响应结构**。
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from config import settings
from database import engine
from vector_store import vector_index_status

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


@router.get("/health/vector-index", summary="向量索引状态（运维诊断·不在契约内·不保证向后兼容）")
def health_vector_index() -> dict:
    """向量索引是否真的在用。**运维诊断端点，不在契约内、不保证向后兼容。**

    为什么需要这个接口：索引读不到时应用**照常启动**，检索静悄悄降级
    name_fuzzy（匹配质量下降但功能可用）。只打日志不够——容器里没人盯日志流，
    事先不会有人知道「搜不准」是因为索引没加载。暴露出来才能被部署检查与监控看见。

    ⚠️ 响应结构可随排障需要调整，不要让前端/客户端依赖它。

    ``count != expectedCount`` 时**先核对 refs.json 与库表是否同步**，
    不要直接重建索引（重建会把正确的向量覆盖成错的）。
    """
    return vector_index_status()
