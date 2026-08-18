"""适配层：契约 JSON ↔ state_engine 纯计算层的桥梁。

本模块只依赖 state_engine 本身与标准库，**不导入 Pydantic / SQLAlchemy**。
调用方（FastAPI 路由）负责把自己的对象转成 openapi 的 camelCase dict 传入，
再把返回的 dict 用 Pydantic `model_validate` 还原——无循环依赖，
state_engine 保持可独立测试。

字段名与枚举取值均以 docs/openapi.yaml 为准（与 schemas/enums.py 一致）。
"""

from __future__ import annotations

from .assessment import compute_window_assessment
from .scoring import compute_session_score
from .types import (
    BehaviorInput,
    Completion,
    Emotion,
    LabelThresholds,
    RecordInput,
    SelfReportInput,
    StateLabel,
    WindowAssessment,
    WeightConfig,
)

__all__ = [
    "record_payload_to_engine",
    "compute_window_for_records",
    "compute_subscore_breakdown",
    "window_to_snapshot_payload",
    "window_to_state_result_payload",
    "display_text_for",
]


# ---------- 输入转换：openapi RecordInput JSON → engine RecordInput ----------

def record_payload_to_engine(payload: dict) -> RecordInput:
    """把 openapi 的 RecordInput（camelCase，如 FastAPI 收到的 body）转成引擎输入。

    只取计算所需字段；subject/startedAt/note 等元字段不参与公式，直接忽略。
    """
    behavior = payload.get("behavior") or {}
    self_report = payload.get("selfReport") or {}

    return RecordInput(
        behavior=BehaviorInput(
            completion=Completion(behavior["completion"]),
            accuracy=behavior.get("accuracy"),
            interruptions=behavior.get("interruptions") or 0,
            blur_count=behavior.get("blurCount") or 0,
        ),
        self_report=SelfReportInput(
            focus=self_report["focus"],
            fatigue=self_report["fatigue"],
            emotion=Emotion(self_report["emotion"]),
            difficulty_feel=self_report.get("difficultyFeel", "moderate"),
        ),
        duration_minutes=int(payload.get("durationMinutes") or 0),
    )


# ---------- 计算：一批记录 → 窗口评估 ----------

def compute_window_for_records(
    records: list[RecordInput],
    weights: WeightConfig | None = None,
    thresholds: LabelThresholds | None = None,
) -> WindowAssessment:
    """对一批（已按时间正序的）引擎输入做单次打分 + 窗口评估。

    weights/thresholds 不传时用引擎默认值；生产环境应从用户级权重表读取后传入。
    """
    weights = weights or WeightConfig()
    scores = [compute_session_score(r, weights) for r in records]
    return compute_window_assessment(scores, records, thresholds)


def compute_subscore_breakdown(
    records: list[RecordInput],
    weights: WeightConfig | None = None,
) -> dict | None:
    """按指定权重计算窗口内各子分均值，让前端可视化"调权后行为/自评贡献"。

    与 compute_window_for_records 共享权重和记录输入，但额外返回：
    - behavior_sub_avg：行为子分均值（0-1）
    - self_report_sub_avg：自评子分均值（0-1）
    - 各自的"加权后贡献"：alpha * behavior_sub_avg 与 beta * self_report_sub_avg
    - 各自在总分中的占比（数据可视化用）

    记录为空或 < 1 条返回 None。
    """
    if not records:
        return None
    weights = weights or WeightConfig()
    scores = [compute_session_score(r, weights) for r in records]
    n = len(scores)
    behavior_avg = sum(s.behavior_sub for s in scores) / n
    self_report_avg = sum(s.self_report_sub for s in scores) / n
    behavior_contrib = weights.alpha * behavior_avg
    self_report_contrib = weights.beta * self_report_avg
    total = behavior_contrib + self_report_contrib
    if total > 0:
        behavior_share = behavior_contrib / total
        self_report_share = self_report_contrib / total
    else:
        behavior_share = self_report_share = 0.5
    return {
        "windowScore": round(behavior_contrib + self_report_contrib, 4),
        "behaviorSubAvg": round(behavior_avg, 4),
        "selfReportSubAvg": round(self_report_avg, 4),
        "behaviorContribution": round(behavior_contrib, 4),
        "selfReportContribution": round(self_report_contrib, 4),
        "behaviorShare": round(behavior_share, 4),
        "selfReportShare": round(self_report_share, 4),
        "recordCount": n,
    }


# ---------- 输出转换：WindowAssessment → openapi camelCase dict ----------

def window_to_snapshot_payload(
    window: WindowAssessment,
    subject: str,
    assessment_id: str | None,
) -> dict:
    """窗口评估 → AssessmentSnapshot 形状（camelCase）。

    数据不足时按契约给 assessmentId=null 且不含 windowScore/trend
    （与 docs/openapi.yaml v1.1 修订后的 AssessmentSnapshot 语义一致）。
    """
    if not window.data_sufficient:
        return {
            "assessmentId": assessment_id,
            "subject": subject,
            "stateLabel": "insufficient_data",
            "dataSufficient": False,
            "recordCount": window.record_count,
        }
    return {
        "assessmentId": assessment_id,
        "subject": subject,
        "windowScore": window.window_score,
        "trend": window.trend.value,
        "stateLabel": window.state_label.value,
        "dataSufficient": True,
        "recordCount": window.record_count,
    }


def window_to_state_result_payload(
    window: WindowAssessment,
    subject: str,
    assessment_id: str | None,
    record_ids: list[str],
) -> dict:
    """窗口评估 → StateResult 形状（含 displayText 与 basedOn，供 GET /assessments/current）。"""
    base = window_to_snapshot_payload(window, subject, assessment_id)
    base["displayText"] = display_text_for(window)
    base["windowSize"] = 7
    base["basedOn"] = {
        "recordIds": record_ids,
        "signals": window.signals,
    }
    return base


_DISPLAY_TEXTS: dict[StateLabel, str] = {
    StateLabel.EFFICIENT_STABLE: "最近状态高效且稳定，保持这个节奏",
    StateLabel.FATIGUE_WARNING: "最近状态有些疲劳，建议把节奏放慢一点",
    StateLabel.EMOTION_BLOCKED: "最近情绪有些受阻，放慢脚步也许会更好",
    StateLabel.FLUCTUATING_UP: "状态正在回升，波动中向好",
    StateLabel.INSUFFICIENT_DATA: "数据积累中，再记录几次就能给出判断",
}


def display_text_for(window: WindowAssessment) -> str:
    """状态标签的自然语言说明（公开文档说明 + 用户友好，不暴露权重与公式）。"""
    return _DISPLAY_TEXTS.get(window.state_label, "状态不明")