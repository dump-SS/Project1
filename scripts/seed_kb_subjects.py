"""学科种子数据：kb_subjects 补 9 行（重构 M0 硬前置）。

背景：`kb_subjects` 表此前 **0 行**，而 `GET /knowledge/subjects` 读的是
`kb_subjects where enabled=true`（routes/knowledge_kb.py），所以该接口**必返空**——
知识链路（检索 / 图谱 / mastery 入口 / 预习复习）全部悬空。本脚本补齐 9 个学科。

学科代码与 `Subject` 枚举（openapi.yaml 0.4 节）一致，也与 `kb_points.subject_code`
的实测分布一一对应（9 科共 3391 条知识点，2026-09-19 实测）。

grade_band 留空：知识点库（kb_points）本身不带学段字段，9 科内容同时覆盖初高中，
填 junior / senior 任一都是臆断，填 other 又容易被前端当作「其他学科」误读。

幂等：按 `code` upsert，重复执行不产生重复行，也不覆盖已存在行的自定义内容。

用法（在 backend/ 目录下执行，与其它 seed 脚本一致）：
    cd backend
    .venv\\Scripts\\python.exe ..\\scripts\\seed_kb_subjects.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from database import Base, SessionLocal, engine
import models  # noqa: F401  触发所有 ORM 注册
from models.knowledge import KnowledgeSubject

# (code, name) —— 顺序按 Subject 枚举，便于人工比对
SUBJECTS: list[tuple[str, str]] = [
    ("YW", "语文"),
    ("SX", "数学"),
    ("YY", "英语"),
    ("WL", "物理"),
    ("HX", "化学"),
    ("SW", "生物"),
    ("ZZ", "思想政治"),
    ("LS", "历史"),
    ("DL", "地理"),
]

VERSION = "1.0"


def main() -> None:
    # 表结构由 alembic 管理；这里只确保已存在（幂等，不会 ALTER 已有表）
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        created, updated = 0, 0
        for code, name in SUBJECTS:
            row = db.execute(
                select(KnowledgeSubject).where(KnowledgeSubject.code == code)
            ).scalars().first()
            if row is None:
                db.add(KnowledgeSubject(
                    id=f"ks_{code}",
                    code=code,
                    name=name,
                    grade_band=None,  # 见文件头说明
                    version=VERSION,
                    enabled=True,
                ))
                created += 1
            else:
                # 已存在则只对齐「启用状态与版本」，不覆盖人工改过的显示名
                row.enabled = True
                if not row.version:
                    row.version = VERSION
                updated += 1
        db.commit()

        total = db.execute(select(KnowledgeSubject)).scalars().all()
        enabled = [s for s in total if s.enabled]
        print(f"[seed_kb_subjects] 新增 {created} 行 / 已存在 {updated} 行")
        print(f"[seed_kb_subjects] kb_subjects 共 {len(total)} 行，其中 enabled=true {len(enabled)} 行")
        for s in sorted(total, key=lambda x: x.code):
            print(f"  - {s.code:>3}  {s.name}  enabled={s.enabled}  version={s.version}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
