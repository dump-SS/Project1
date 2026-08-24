"""板块二错题 OCR 录入接口（PRD 12.3.2 / v2.2-6）。

选型结论（ADR 已记）：MVP 用手动录入保底，OCR 为实验功能。
本接口仅作形态预留：
- POST /error-book/ocr           上传图片 → 识别为文本 → 回填录入表单（不自动入库）
- 图片与识别原文只在本地处理，永不出域（云端 OCR 未接入，返回 501 提示需手动录入）

真实实现依赖本地 PaddleOCR（不阻塞上线）；不达标时降级为实验功能。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from schemas.user import User
from .deps import current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/error-book", tags=["错题本"])


class OcrRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # v1 只收 base64 数据或留空；不实现真实解码，仅作为接口形态与文档锚点
    image_base64: str | None = Field(None, alias="imageBase64")


class OcrResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    available: bool
    text: str | None = None
    message: str


@router.post(
    "/ocr",
    response_model=OcrResult,
    summary="错题拍照 OCR 录入（实验功能，手动录入保底）",
)
def ocr_error(
    payload: OcrRequest,
    _user: User = Depends(current_user),
) -> OcrResult:
    """OCR 未接入真实引擎时明确返回不可用，前端引导手动录入（计划书 v2.2-6 降级策略）。"""
    return OcrResult(
        available=False,
        text=None,
        message="OCR 暂未接入，请手动粘贴题干完成录入（图片不会离开本地）",
    )
