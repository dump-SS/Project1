"""D55 · 作业单照片 → 结构化作业项（LLM 视觉抽取，F 板块）。

design 第 974 行「作业单直接生成计划」的抽取一步。职责边界：
- 本模块只做「图片字节 → WorksheetExtraction」这一步，不落库、不建计划；
- 计划落库走 routes/plan.py 的 tasks 覆写路径（schemas/plan.PlanTaskInput）；
- 调用方（routes/worksheet.py）负责归属校验与 R2 取回，本模块拿到的必是已通过
  校验的图片字节。

出域口径：作业单照片属用户内容，随本轮送第三方模型——与带图 Chat 同一口径
妥协（data_class=state_plan），见 docs/openapi.yaml info.description v1.12.0 段
（lead-1 判断、待 Skyer 复核的已知不一致）。

⚠️ context 必须是**字面量 dict** 且含 data_class 常量：test_egress_ci 用 AST 扫
每个 .generate( 调用点（见 chat_engine.py 同款注释），提成变量会被判 <dynamic>。
"""
from __future__ import annotations

import base64
import json
import logging
import re

from llm_provider import get_provider
from schemas.enums import Subject
from schemas.worksheet import WorksheetExtraction, WorksheetItem

logger = logging.getLogger(__name__)

_MAX_ITEMS = 20
_MIN_MINUTES = 5
_MAX_MINUTES = 240
_FALLBACK_TOPIC = "未识别到作业项"

#: LLM 给出的 subject 不在枚举内时的兜底（契约 Subject.other 的语义就是"无法归类"）
_FALLBACK_SUBJECT = Subject.other


class WorksheetExtractError(Exception):
    """LLM 不可用 / 返回内容解析不出结构。message 面向用户可读（映射 502 EXTRACT_FAILED）。"""


def _load_prompt() -> tuple[str, str]:
    """读 prompts/worksheet_extract.txt 的 SYSTEM / USER 两段（同 chat_engine._load_file）。"""
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "prompts", "worksheet_extract.txt"), encoding="utf-8") as f:
        text = f.read()
    sys_match = re.search(r"(?m)^SYSTEM:\s*$", text)
    user_match = re.search(r"(?m)^USER:\s*$", text)
    if not sys_match or not user_match or user_match.start() <= sys_match.end():
        raise ValueError("worksheet_extract.txt 缺少合法的 SYSTEM/USER 分段标记")
    return text[sys_match.end():user_match.start()].strip(), text[user_match.end():].strip()


def _parse_items(text: str) -> list[dict]:
    """从 LLM 输出里抠出 JSON 数组并归一化。解析不出 → WorksheetExtractError。

    解析策略（对推理模型输出的容错，逐层放宽）：
    1. 直接 json.loads 全文；
    2. 截取首个 `[` 到最后一个 `]` 再 loads（容忍模型带前后缀说明文字）；
    3. 都失败 → 报错（上游映射 502，可重试）。
    """
    raw = (text or "").strip()
    candidates = [raw]
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end > start:
        candidates.insert(0, raw[start:end + 1])
    parsed = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            break
        except (ValueError, TypeError):
            continue
    if not isinstance(parsed, list) or not parsed:
        raise WorksheetExtractError("模型没有返回可解析的作业项")

    items: list[dict] = []
    for entry in parsed[:_MAX_ITEMS]:
        if not isinstance(entry, dict):
            continue
        # subject：大小写不敏感地归一到枚举；不认识的一律 other（契约兜底语义）
        raw_subject = str(entry.get("subject", "")).strip().upper()
        try:
            subject = Subject(raw_subject)
        except ValueError:
            subject = _FALLBACK_SUBJECT
        topic = str(entry.get("topic", "")).strip() or _FALLBACK_TOPIC
        try:
            minutes = int(entry.get("estimatedMinutes", 0))
        except (TypeError, ValueError):
            minutes = 0
        # 契约口径：越界值截断到 [5, 240]，而不是整项拒绝（一张作业单不该因为
        # 模型把 300 分钟写成 3000 就整体失败——确认卡里用户还能改）
        minutes = max(_MIN_MINUTES, min(_MAX_MINUTES, minutes))
        items.append({
            "subject": subject,
            "topic": topic[:100],
            "estimated_minutes": minutes,
        })
    if not items:
        raise WorksheetExtractError("模型返回的作业项全部无法解析")
    return items


def extract_worksheet_items(image_bytes: bytes, mime: str, user_id: str) -> WorksheetExtraction:
    """取回后的图片字节 → 结构化作业项。失败抛 WorksheetExtractError（→502）。"""
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
            "scene": "worksheet",
            # ⚠️ data_class 必须是本 dict 里的**字面量**（AST 扫描约定，见模块 docstring）。
            #    与带图 Chat 同一口径妥协：真正类目是 user_error_content，改它要动出域口径。
            "data_class": "state_plan",
            "user_id": user_id,
            "feature_tier": "multimodal",
            **image_ctx,
        },
    )
    if llm_text is None or not llm_text.strip():
        logger.warning("[WORKSHEET] LLM 无正文 user=%s mime=%s bytes=%d", user_id, mime, len(image_bytes))
        raise WorksheetExtractError("这次没能从照片里认出作业项，请重试一次")

    items = _parse_items(llm_text)
    logger.info(
        "[WORKSHEET] 抽取成功 user=%s items=%d mime=%s bytes=%d",
        user_id, len(items), mime, len(image_bytes),
    )
    if any(item["topic"] == _FALLBACK_TOPIC for item in items):
        logger.info("[WORKSHEET] 照片中未识别到作业项（模型兜底项）user=%s", user_id)
    return WorksheetExtraction(items=items)


def worksheet_prompt_paths_ok() -> bool:
    """冒烟自检：prompt 文件存在且分段合法（main 启动/测试可选用）。"""
    try:
        _load_prompt()
        return True
    except (OSError, ValueError):
        return False
