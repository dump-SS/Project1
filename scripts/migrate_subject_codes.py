"""学科代码迁移脚本（2026-08-26：英文小写 → 拼音大写，与知识点库标准对齐）。

映射（唯一真源，与 backend/schemas/enums.py 一致）：
    chinese→YW  math→SX  english→YY  physics→WL  chemistry→HX
    biology→SW  history→LS  geography→DL  politics→ZZ  other 保留

做两件事：
1. 幂等种入 9 个学科到 kb_subjects（id=ks_+新码, code=新码, 中文名）
2. 把所有业务表里的旧码 subject 字段映射为新码（打印受影响行数）

用法：
    cd backend
    .venv\\Scripts\\python.exe ../scripts/migrate_subject_codes.py --dry-run   # 只预览
    .venv\\Scripts\\python.exe ../scripts/migrate_subject_codes.py             # 执行

执行前建议备份 data.db。
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: F401  触发 ORM 注册
from database import SessionLocal
from models.knowledge import KnowledgeSubject

# (新码, 中文名, 教材版本)
SUBJECTS = [
    ("YW", "语文", "统编版2019"),
    ("SX", "数学", "人教A版2019"),
    ("YY", "英语", "人教版2019"),
    ("WL", "物理", "人教版2019"),
    ("HX", "化学", "人教版2019"),
    ("SW", "生物", "人教版2019"),
    ("ZZ", "思想政治", "统编版2019"),
    ("LS", "历史", "统编版2019"),
    ("DL", "地理", "人教版2019"),
]

OLD_TO_NEW = {
    "chinese": "YW", "math": "SX", "english": "YY", "physics": "WL",
    "chemistry": "HX", "biology": "SW", "history": "LS",
    "geography": "DL", "politics": "ZZ",
}

# (表名, 列名) —— 含 subject 字段的业务表
SUBJECT_COLUMNS = [
    ("learning_records", "subject"),
    ("goals", "subject"),
    ("plan_tasks", "subject"),
    ("assessment_snapshots", "subject"),
    ("kb_errors", "subject"),
    ("kb_points", "subject_code"),
    ("kb_subjects", "code"),
]


def _seed_subjects(db, dry_run: bool) -> None:
    for code, name, version in SUBJECTS:
        row = db.get(KnowledgeSubject, f"ks_{code}")
        if row is None:
            if not dry_run:
                db.add(KnowledgeSubject(
                    id=f"ks_{code}", code=code, name=name,
                    grade_band="senior", version=version,
                ))
            print(f"  + 学科 {code} {name}（{version}）")
        else:
            # 更新为新码（幂等；若已是新码则无变化）
            if row.code != code:
                if not dry_run:
                    row.code = code
                    row.name = name
                print(f"  ~ 学科 {code} 已存在，code 更新为 {code}")
    if not dry_run:
        db.commit()


def _migrate_columns(db, dry_run: bool) -> int:
    from sqlalchemy import text

    total = 0
    for table, column in SUBJECT_COLUMNS:
        # 表可能不存在（迁移前旧库），跳过
        try:
            exists = db.execute(text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"
            ), {"t": table}).scalar()
            if not exists:
                continue
        except Exception:  # noqa: BLE001
            continue
        for old, new in OLD_TO_NEW.items():
            n = db.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE {column} = :old"
            ), {"old": old}).scalar_one()
            if n and not dry_run:
                db.execute(text(
                    f"UPDATE {table} SET {column} = :new WHERE {column} = :old"
                ), {"new": new, "old": old})
            if n:
                total += n
                print(f"  {table}.{column}: {old} → {new} × {n}")
    if not dry_run:
        db.commit()
    return total


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    print("学科代码迁移：英文小写 → 拼音大写" + ("（DRY-RUN 预览）" if dry_run else "（执行）"))
    db = SessionLocal()
    try:
        print("[1/2] kb_subjects 学科种子")
        _seed_subjects(db, dry_run)
        print("[2/2] 业务表 subject 映射")
        n = _migrate_columns(db, dry_run)
        print(f"合计受影响行数：{n}")
        if dry_run:
            print("dry-run 完成，加 --dry-run 参数已预览；去掉参数执行真实迁移。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
