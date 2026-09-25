"""/learning-records 系列。

阶段 3（已接入）：POST 落库后用 state_engine 同步重算状态快照，
并自动创建建议任务（pending）触发 ai_suggestion 同步生成。
GET 列表读库，DELETE 删除后即时重算。计算公式在 state_engine 内。

重构 M2（C 板块）：
- 落库编排抽到 `record_service.py`（计时收尾要与本模块算出同一个状态分，不能两套）；
- 新增 **PATCH 事后回写**（D15：学习记录是"可事后回写的活实体"，不是提交即封存的快照）。
  回写重算状态快照，但**不重复触发建议生成**——否则用户每补一次正确率就收到一条新建议。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models.learning_record import LearningRecord as LearningRecordORM
from record_service import (
    as_utc_iso,
    get_user_weights,
    persist_record,
    recompute_snapshot,
    record_orm_to_payload,
    window_rows,
)
from schemas.learning_record import (
    LearningRecord,
    LearningRecordCreated,
    LearningRecordDeleted,
    LearningRecordList,
    LearningRecordUpdated,
    RecordInput,
    RecordUpdate,
)
from schemas.user import User
from .deps import current_user

# 兼容既有引用：routes/assessment.py 仍按旧名导入 _get_user_weights，
# 直接删除会连带打断它（也打断"权重只从用户级权重表读"这一条的唯一入口）。
_as_utc_iso = as_utc_iso
_window_rows = window_rows
_get_user_weights = get_user_weights
_recompute_snapshot = recompute_snapshot

router = APIRouter(prefix="/learning-records", tags=["学习记录"])


@router.post(
    "",
    response_model=LearningRecordCreated,
    status_code=status.HTTP_201_CREATED,
    summary="提交学习记录（核心接口）③④",
)
def create_learning_record(
    body: RecordInput,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> LearningRecordCreated:
    """保存记录，同步用 state_engine 重算状态；建议生成挂后台（PRD 6.4），立即返回 pending 句柄。"""
    return LearningRecordCreated.model_validate(
        persist_record(db, _user.user_id, body, background_tasks)
    )


@router.get("", response_model=LearningRecordList, summary="学习记录列表")
def list_learning_records(
    subject: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> LearningRecordList:
    query = select(LearningRecordORM).where(LearningRecordORM.user_id == _user.user_id)
    if subject:
        query = query.where(LearningRecordORM.subject == subject)
    if date_from:
        query = query.where(LearningRecordORM.started_at >= date_from)
    if date_to:
        query = query.where(LearningRecordORM.started_at <= date_to)

    # total 必须用和查询相同的过滤条件——之前只按 user 统计，
    # 带 subject/date 筛选时 total > len(items)，分页器会误以为还有更多页
    total_query = query.with_only_columns(func.count()).order_by(None)
    total = db.execute(total_query).scalar_one()

    query = query.order_by(LearningRecordORM.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(query).scalars().all()

    return LearningRecordList(
        items=[LearningRecord.model_validate(record_orm_to_payload(r)) for r in rows],
        pagination={"page": page, "pageSize": page_size, "total": total},
    )


@router.patch(
    "/{record_id}",
    response_model=LearningRecordUpdated,
    summary="事后回写学习记录（正确率 / 完成度 / 自评 / 备注）",
)
def update_learning_record(
    record_id: str,
    body: RecordUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> LearningRecordUpdated:
    """回写一条已存在的记录（D15 三态可填：结束即填 / 延后补 / 永不填）。

    语义要点：
    - **只在字段被显式传入时才改**（`model_fields_set`）——传 `accuracy: null` 是"清空"，
      不传是"别动"，两者必须区分，否则前端只想改备注会把正确率抹掉；
    - 回写后**重算该学科状态快照**（accuracy/selfReport 都参与算分，不重算会与列表不一致）；
    - **不创建新建议**（D15 验收："回写不重复触发评估"）——建议是"一次学习结束后"的产物，
      补个正确率不该再推一条建议给用户。
    """
    row = db.get(LearningRecordORM, record_id)
    if row is None or row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "记录不存在"},
        )

    provided = body.model_fields_set

    if "completion" in provided and body.completion is not None:
        row.behavior_completion = body.completion.value
    if "accuracy" in provided:
        row.behavior_accuracy = body.accuracy
    if "note" in provided:
        row.note = body.note
    # ⚠️ `model_fields_set` 装的是**字段名**（self_report），不是别名（selfReport）——
    # 按别名判断会静默不生效，表现为"自评改不动"。
    if "self_report" in provided and body.self_report is not None:
        row.self_report_focus = body.self_report.focus
        row.self_report_fatigue = body.self_report.fatigue
        row.self_report_emotion = body.self_report.emotion.value
        row.self_report_difficulty_feel = body.self_report.difficulty_feel.value

    db.commit()
    db.refresh(row)

    assessment = recompute_snapshot(db, _user.user_id, row.subject, record_id)

    return LearningRecordUpdated.model_validate(
        {
            "record": record_orm_to_payload(row),
            "recalculatedAssessment": assessment,
        }
    )


@router.delete(
    "/{record_id}",
    response_model=LearningRecordDeleted,
    summary="删除学习记录并重算当前窗口",
)
def delete_learning_record(
    record_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
) -> LearningRecordDeleted:
    row = db.get(LearningRecordORM, record_id)
    if row is None or row.user_id != _user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "记录不存在"},
        )

    subject = row.subject
    db.delete(row)
    db.commit()

    assessment = recompute_snapshot(db, _user.user_id, subject, record_id)

    return LearningRecordDeleted.model_validate(
        {
            "deleted": True,
            "recordId": record_id,
            "recalculatedAssessment": assessment,
        }
    )
