"""考试成绩回填 → 生成 `source=exam` 的学习记录（D49 喂状态评估）。

这条链路的难点不是"生成一条记录"，而是**在不造数的前提下**生成：
- 考试没有自评 → `selfReport` 整段留空，引擎走"自评不可用 → 只按行为子分计"的降级；
- 记录时长必填 → 只有 `Exam.durationMinutes`（客观事实）在场才生成，**没填就不生成**；
- 用户会改分数、会录错 → 必须**幂等**，不能每改一次就在状态窗口里多一条记录。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from database import SessionLocal
from main import app
from models.learning_record import LearningRecord as LearningRecordORM
from models.recommendation import Recommendation

client = TestClient(app)
HDR = {"X-User-ID": "u_test_examlink"}


def _create_exam(**over):
    body = {"subject": "SX", "name": "期中考试", "examDate": "2026-11-05", "fullScore": 150}
    body.update(over)
    return client.post("/api/v1/exams", json=body, headers=HDR)


def _records(**params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"/api/v1/learning-records?{q}", headers=HDR).json()["items"]


def _record_count() -> int:
    db = SessionLocal()
    try:
        return db.query(LearningRecordORM).filter(
            LearningRecordORM.user_id == "u_test_examlink"
        ).count()
    finally:
        db.close()


def test_backfill_with_duration_creates_exam_record():
    exam_id = _create_exam(durationMinutes=120).json()["examId"]
    r = client.patch(f"/api/v1/exams/{exam_id}", json={"score": 120}, headers=HDR)
    assert r.status_code == 200

    items = _records(source="exam")
    assert len(items) == 1
    rec = items[0]
    assert rec["source"] == "exam"
    assert rec["sourceExamId"] == exam_id
    assert rec["subject"] == "SX"
    assert rec["durationMinutes"] == 120
    # 得分率 = 120/150
    assert abs(rec["behavior"]["accuracy"] - 0.8) < 1e-9
    assert rec["behavior"]["completion"] == "completed"
    # 关键：考试没有自评，四字段全空——**没有编数据**
    assert rec["selfReport"] == {
        "focus": None, "fatigue": None, "emotion": None, "difficultyFeel": None,
    }
    # 记录起点取考试当天 00:00（不编一个"看起来像真的"时刻）
    assert rec["startedAt"].startswith("2026-11-05T00:00:00")


def test_backfill_without_duration_creates_nothing():
    """没填考试时长就不生成记录——绝不为了凑一条记录编一个时长。"""
    exam_id = _create_exam().json()["examId"]  # 无 durationMinutes
    client.patch(f"/api/v1/exams/{exam_id}", json={"score": 120}, headers=HDR)

    assert _records(source="exam") == []
    assert _record_count() == 0
    # 但分数本身要落库
    got = client.get(f"/api/v1/exams/{exam_id}", headers=HDR).json()
    assert got["score"] == 120


def test_create_exam_with_score_and_duration_also_links():
    """考后一次录入（创建时就带分数与时长）同样要喂状态评估。"""
    r = _create_exam(score=135, durationMinutes=90)
    assert r.status_code == 201
    items = _records(source="exam")
    assert len(items) == 1
    assert abs(items[0]["behavior"]["accuracy"] - 0.9) < 1e-9


def test_repeated_backfill_is_idempotent():
    """改分数不该在状态窗口里多出一条记录。"""
    exam_id = _create_exam(durationMinutes=120).json()["examId"]
    client.patch(f"/api/v1/exams/{exam_id}", json={"score": 120}, headers=HDR)
    client.patch(f"/api/v1/exams/{exam_id}", json={"score": 135}, headers=HDR)

    items = _records(source="exam")
    assert len(items) == 1, "重复回填必须只维护同一条记录"
    assert abs(items[0]["behavior"]["accuracy"] - 0.9) < 1e-9


def test_revoking_score_removes_the_record():
    """撤回回填（传 null）就是撤回：记录一并消失，不留半条。"""
    exam_id = _create_exam(durationMinutes=120).json()["examId"]
    client.patch(f"/api/v1/exams/{exam_id}", json={"score": 120}, headers=HDR)
    assert len(_records(source="exam")) == 1

    client.patch(f"/api/v1/exams/{exam_id}", json={"score": None}, headers=HDR)
    assert _records(source="exam") == []


def test_deleting_exam_removes_generated_record():
    """考试录错了删掉 → 它的记录也不该留下（否则是一条无源可查的孤立数据）。"""
    exam_id = _create_exam(durationMinutes=120).json()["examId"]
    client.patch(f"/api/v1/exams/{exam_id}", json={"score": 120}, headers=HDR)
    assert len(_records(source="exam")) == 1

    assert client.delete(f"/api/v1/exams/{exam_id}", headers=HDR).status_code == 200
    assert _records(source="exam") == []


def test_exam_record_does_not_trigger_recommendation():
    """补一个分数不该推一条"学习建议"给用户。"""
    exam_id = _create_exam(durationMinutes=120).json()["examId"]
    client.patch(f"/api/v1/exams/{exam_id}", json={"score": 120}, headers=HDR)

    db = SessionLocal()
    try:
        n = db.query(Recommendation).filter(
            Recommendation.user_id == "u_test_examlink"
        ).count()
    finally:
        db.close()
    assert n == 0


def test_exam_record_feeds_state_window():
    """成绩确实进了状态窗口：攒够 3 条考试记录后 /assessments/current 有读数。

    且因为考试没有自评，自评侧不可用——`windowScore` 只能由行为子分贡献，
    这正是"不硬凑"的体现（不会凭空补一个自评分）。
    """
    for i, score in enumerate([120, 130, 140]):
        exam_id = _create_exam(name=f"月考{i}", examDate=f"2026-10-0{i + 1}",
                               durationMinutes=100).json()["examId"]
        client.patch(f"/api/v1/exams/{exam_id}", json={"score": score}, headers=HDR)

    assert len(_records(source="exam")) == 3

    cur = client.get("/api/v1/assessments/current?subject=SX", headers=HDR).json()["items"][0]
    assert cur["dataSufficient"] is True
    assert cur["windowScore"] is not None

    # 行为子分完全可算（完成度 + 得分率 + 节奏），自评侧则明确不可用
    bd = client.get("/api/v1/me/state-breakdown?subject=SX", headers=HDR)
    if bd.status_code == 200:
        body = bd.json()
        assert body["behaviorSubAvg"] is not None
        assert body["selfReportSubAvg"] is None, "没有自评就不能拿 0.0 冒充"
