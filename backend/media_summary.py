"""#47 · 上传照片要点摘要（LLM 视觉，F 板块，契约 v1.18.0）。

design 第 974 行 D55 欠账：「生成的要点摘要可进收藏（走 privacy_filter）」。

职责边界：
- 本模块只做「图片字节 → 已脱敏摘要」这一步；**摘要不落库**；
- 收藏落库由调用方经 `POST /me/collection/items` 完成（sourceRef.type=upload_summary）；
- **脱敏在本模块内、返回前完成**（privacy_filter.sanitize_text）——这就是
  M5 验收门「摘要入库前脱敏」的落点：调用方拿到的文本已是可入库版本，
  后续无论谁把它存到哪里都不会漏脱敏（防御位置选在源头而不是各消费方）。

出域口径：照片属用户内容，随本轮送第三方模型——与带图 Chat 同一口径妥协
（data_class=state_plan），见 docs/openapi.yaml v1.12.0 段（待 Skyer 复核）。

⚠️ context 必须是**字面量 dict** 且含 data_class 常量（egress AST 扫描约定，
见 worksheet_extract.py 同款注释）。
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re

from llm_provider import get_provider
from privacy_filter import sanitize_text
from schemas.enums import Subject

logger = logging.getLogger(__name__)

_MAX_SUMMARY_LEN = 2000
_FALLBACK_SUBJECT = Subject.other
_FALLBACK_SUMMARY = "照片内容无法辨认"


class MediaSummaryError(Exception):
    """LLM 不可用 / 返回内容不可用。message 面向用户可读（映射 502 SUMMARY_FAILED）。"""


def _load_prompt() -> tuple[str, str]:
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "prompts", "media_summary.txt"), encoding="utf-8") as f:
        text = f.read()
    sys_match = re.search(r"(?m)^SYSTEM:\s*$", text)
    user_match = re.search(r"(?m)^USER:\s*$", text)
    if not sys_match or not user_match or user_match.start() <= sys_match.end():
        raise ValueError("media_summary.txt 缺少合法的 SYSTEM/USER 分段标记")
    return text[sys_match.end():user_match.start()].strip(), text[user_match.end():].strip()


def _parse_summary(text: str) -> tuple[Subject, str]:
    """从 LLM 输出抠出 {"subject", "summary"}。解析不出 → MediaSummaryError。"""
    raw = (text or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    parsed = None
    for candidate in ([raw] if start == -1 else [raw[start:end + 1], raw]):
        try:
            parsed = json.loads(candidate)
            break
        except (ValueError, TypeError):
            continue
    if not isinstance(parsed, dict):
        raise MediaSummaryError("模型没有返回可解析的摘要")
    raw_subject = str(parsed.get("subject", "")).strip().upper()
    try:
        subject = Subject(raw_subject)
    except ValueError:
        subject = _FALLBACK_SUBJECT
    summary = str(parsed.get("summary", "")).strip() or _FALLBACK_SUMMARY
    return subject, summary


def summarize_media(image_bytes: bytes, mime: str, user_id: str) -> tuple[str, Subject]:
    """图片字节 → (已脱敏摘要, 学科)。失败抛 MediaSummaryError（→502）。"""
    system, user_text = _load_prompt()
    provider = get_provider()

    image_ctx = {
        "image": {
            "mime": mime,
            "data_b64": base64.b64encode(image_bytes).decode("ascii"),
            "bytes": len(image_bytes),
        }
    }
    llm_text = provider.generate(
        user_text,
        context={
            "system": system,
            "scene": "media_summary",
            # ⚠️ data_class 必须是字面量（AST 扫描约定）；与带图 Chat 同一口径妥协。
            "data_class": "state_plan",
            "user_id": user_id,
            "feature_tier": "multimodal",
            **image_ctx,
        },
    )
    if llm_text is None or not llm_text.strip():
        logger.warning("[MEDIA_SUMMARY] LLM 无正文 user=%s mime=%s bytes=%d", user_id, mime, len(image_bytes))
        raise MediaSummaryError("这次没能总结这张照片，请重试一次")

    subject, summary = _parse_summary(llm_text)

    # 🔴 入库前脱敏（M5 验收门「摘要入库前脱敏（测试）」的落点）：
    # 在源头脱敏，而不是指望每个把摘要写进收藏的调用方记得脱。
    # prompt 已要求模型不输出个人信息，这里是**兜底防线**（模型不可信）。
    sanitized = sanitize_text(summary)
    if sanitized is None or not sanitized.strip():
        logger.warning("[MEDIA_SUMMARY] 摘要脱敏后为空 user=%s", user_id)
        raise MediaSummaryError("这次没能总结这张照片，请重试一次")
    if sanitized != summary:
        logger.info("[MEDIA_SUMMARY] 摘要触发脱敏 user=%s", user_id)

    summary = sanitized[:_MAX_SUMMARY_LEN]
    logger.info("[MEDIA_SUMMARY] 摘要成功 user=%s subject=%s len=%d", user_id, subject.value, len(summary))
    return summary, subject


def media_summary_prompt_ok() -> bool:
    try:
        _load_prompt()
        return True
    except (OSError, ValueError):
        return False
