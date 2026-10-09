"""跨层契约核对：后端真实响应字段 vs 前端手写 TS 类型。

**为什么需要这个脚本**：`frontend/tsconfig.json` 有意只检查 `.ts/.tsx`
（"队友的 .jsx/.js 不纳入类型检查"），所以前端页面里的手写类型一旦和后端漂移，
**tsc 与 vite build 都抓不到**。这个脚本用**临时空库**起真实 ASGI 应用，
把新接口的响应字段与 TS 里声明的字段逐项比对：
后端多字段没关系（可选字段），**少字段就是漂移**。

用法（在仓库根目录）：
    python scripts/verify_frontend_contract.py

安全性：`DATABASE_URL` 指向临时目录，**不碰开发库 backend/data.db**；
`ALLOW_INSECURE_USER_HEADER=true` 只为用 `X-User-ID` 头免登录（生产默认关闭）。

退出码：0 = 无漂移；1 = 有漂移（会列出缺哪些字段）。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# 必须在 import config 之前设置环境变量（pydantic-settings 优先级：环境变量 > .env）
_tmpdir = Path(tempfile.mkdtemp(prefix="epochx_contract_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmpdir / 'tmp.db').as_posix()}"
os.environ["ALLOW_INSECURE_USER_HEADER"] = "true"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

import models  # noqa: E402,F401  触发 ORM 注册
from database import Base, engine  # noqa: E402
from main import app  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)
HDR = {"X-User-ID": "u_contract_probe"}

failures: list[str] = []


def expect(label: str, actual: set[str], declared: set[str]) -> None:
    """后端响应 actual 必须覆盖前端声明的 declared。"""
    missing = declared - actual
    if missing:
        failures.append(f"{label} 缺少字段：{sorted(missing)}")
    print(f"  {'ok  ' if not missing else 'FAIL'} {label}  (后端 {len(actual)} / 前端声明 {len(declared)})")


def main() -> int:
    # ------------------------------------------------------------ 计时会话（D30/D31/#14）
    print("== /timer-sessions ==")
    r = client.post("/api/v1/timer-sessions",
                    json={"mode": "countdown", "targetMinutes": 30, "subject": "SX"}, headers=HDR)
    assert r.status_code == 201, r.text
    sid = r.json()["sessionId"]

    expect("TimerSession", set(r.json()), {
        "sessionId", "mode", "startedAt", "targetMinutes", "planId", "taskId",
        "subject", "status", "endedAt", "effectiveSeconds", "lastHeartbeatAt",
        "segments", "createdAt",
    })

    cur = client.get("/api/v1/timer-sessions/current", headers=HDR).json()
    expect("TimerCurrent", set(cur), {"active", "session", "restore"})
    expect("TimerRestore", set(cur["restore"]), {
        "sessionId", "mode", "remainingSeconds", "elapsedSeconds",
        "needsVerdict", "suggestedMinutes",
    })

    hb = client.post(f"/api/v1/timer-sessions/{sid}/heartbeat", headers=HDR)
    expect("TimerSession(heartbeat)", set(hb.json()), {"sessionId", "status", "lastHeartbeatAt"})

    seg = client.post(f"/api/v1/timer-sessions/{sid}/segments", json={"taskId": None}, headers=HDR)
    expect("TimerSegment", set(seg.json()), {"segmentId", "taskId", "startedAt", "endedAt", "seconds"})

    # ------------------------------------------------------------ 收尾（D20 三层：只传完成度）
    print("\n== finish（收尾三层：只传完成度 + 情绪）==")
    r = client.post(f"/api/v1/timer-sessions/{sid}/finish",
                    json={"completion": "completed", "selfReport": {"emotion": "neutral"}}, headers=HDR)
    assert r.status_code == 201, r.text
    created = r.json()
    expect("LearningRecordCreated", set(created), {
        "recordId", "subject", "startedAt", "durationMinutes", "planTaskId", "behavior",
        "selfReport", "note", "source", "sourceExamId", "assessment", "recommendation", "createdAt",
    })
    expect("assessment", set(created["assessment"]), {
        "assessmentId", "subject", "windowScore", "trend", "stateLabel",
        "dataSufficient", "recordCount",
    })
    expect("behavior", set(created["behavior"]), {
        "completion", "accuracy", "interruptions", "blurCount",
    })
    expect("selfReport", set(created["selfReport"]), {
        "focus", "fatigue", "emotion", "difficultyFeel",
    })

    # ------------------------------------------------------------ 记录回写（D15）
    print("\n== PATCH /learning-records/{id} ==")
    rid = created["recordId"]
    r = client.patch(f"/api/v1/learning-records/{rid}",
                     json={"accuracy": 0.8, "note": "补个备注"}, headers=HDR)
    assert r.status_code == 200, r.text
    expect("LearningRecordUpdated", set(r.json()), {"record", "recalculatedAssessment"})
    expect("record", set(r.json()["record"]), {
        "recordId", "behavior", "selfReport", "source", "sourceExamId",
    })

    # ------------------------------------------------------------ 考试（D49）
    print("\n== /exams ==")
    r = client.post("/api/v1/exams",
                    json={"subject": "SX", "name": "期中考试", "examDate": "2026-11-05",
                          "fullScore": 150, "durationMinutes": 120}, headers=HDR)
    assert r.status_code == 201, r.text
    exam_id = r.json()["examId"]
    expect("Exam", set(r.json()), {
        "examId", "subject", "name", "examDate", "score", "fullScore",
        "durationMinutes", "createdAt", "updatedAt",
    })

    client.patch(f"/api/v1/exams/{exam_id}", json={"score": 120}, headers=HDR)
    items = client.get("/api/v1/learning-records?source=exam", headers=HDR).json()["items"]
    assert len(items) == 1, f"成绩回填应生成 1 条 source=exam 记录，实际 {len(items)}"
    assert items[0]["source"] == "exam" and items[0]["sourceExamId"] == exam_id
    assert all(v is None for v in items[0]["selfReport"].values()), "考试记录不得编造自评"
    print("  ok   成绩回填 → source=exam 记录（自评整段为空，未造数）")

    # ------------------------------------------------------------ 结果
    print()
    if failures:
        print("契约漂移：")
        for f in failures:
            print("  -", f)
        return 1
    print("跨层契约核对通过：前端手写类型与后端实际响应一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
