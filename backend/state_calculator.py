"""状态计算服务：路由层与 state_engine 的接入点。

main.py 阶段 3 注释预留的模块——把数据库里的学习记录交给引擎计算，
返回 openapi 契约形状的 dict（供 Pydantic model_validate）。

职责边界：
- 本模块负责 ORM → 引擎输入 → 窗口评估 → 契约 dict 的编排；
- 所有公式与判定规则在 state_engine 内，本模块不写任何计算逻辑。
- 权重来自用户级权重表（UserWeightConfig，PRD 5.2 硬约束）；
  未调权用户使用默认等权（与 PRD 初始值一致）。
"""

from __future__ import annotations

import uuid

from state_engine.adapter import (
    compute_window_for_records,
    record_payload_to_engine,
    window_to_snapshot_payload,
    window_to_state_result_payload,
)
from state_engine.types import WeightConfig
from state_engine.types import RecordInput as EngineRecordInput

__all__ = [
    "gen_id",
    "orm_record_to_engine_input",
    "compute_window",
    "compute_state_result",
]


def gen_id(prefix: str) -> str:
    """应用层生成的资源 ID（参考 mock-server 的 r_/a_/rec_ 风格）。"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def orm_record_to_engine_input(row) -> EngineRecordInput:
    """ORM LearningRecord 行 → 引擎输入。

    ORM 把 behavior/selfReport 平铺成列（behavior_completion 等），
    这里重新组装成引擎需要的嵌套结构。
    """
    payload = {
        "behavior": {
            "completion": row.behavior_completion,
            "accuracy": row.behavior_accuracy,
            "interruptions": row.behavior_interruptions,
            "blurCount": row.behavior_blur_count,
        },
        "selfReport": {
            "focus": row.self_report_focus,
            "fatigue": row.self_report_fatigue,
            "emotion": row.self_report_emotion,
            "difficultyFeel": row.self_report_difficulty_feel,
        },
        "durationMinutes": row.duration_minutes,
    }
    return record_payload_to_engine(payload)


def compute_window(engine_inputs: list[EngineRecordInput], weights: WeightConfig | None = None):
    """一批（时间正序）引擎输入 → 窗口评估。

    weights 不传时用默认等权（PRD 初始值）；生产环境应从 UserWeightConfig 读后传入。
    """
    return compute_window_for_records(engine_inputs, weights=weights)


def compute_snapshot_dict(
    engine_inputs: list[EngineRecordInput],
    subject: str,
    assessment_id: str | None,
    weights: WeightConfig | None = None,
) -> dict:
    """窗口评估 → AssessmentSnapshot 形状（camelCase dict）。"""
    window = compute_window_for_records(engine_inputs, weights=weights)
    return window_to_snapshot_payload(window, subject, assessment_id)


def compute_state_result_dict(
    engine_inputs: list[EngineRecordInput],
    subject: str,
    assessment_id: str | None,
    record_ids: list[str],
    weights: WeightConfig | None = None,
) -> dict:
    """窗口评估 → StateResult 形状（camelCase dict，含 displayText/basedOn）。"""
    window = compute_window_for_records(engine_inputs, weights=weights)
    return window_to_state_result_payload(window, subject, assessment_id, record_ids)
