"""知识点库导入脚本：JSON → kb_points + kb_point_relations + 向量索引。

数据源：D:\\Projects\\knowledge base\\docs\\knowledge-points\\*.json（内容团队产出，
见学科代码映射表）。每个文件结构：

    {
      "module_path": "数学（人教A版2019） 必修 第一册 第三章 ...",
      "l2_points": [
        {
          "id": "SX_A_G1_B1_HS_001",           # {SUBJECT_CODE}_{VERSION}_...
          "name": "函数的概念与三要素",
          "definition": "...",
          "explanation": "...",                # 讲解（80-200字，用"你"）
          "difficulty": 2,                     # 1-5
          "frequency": 5,                      # 1-5 考频
          "typical_errors": ["...", "..."],    # ≥3 条 JSON 数组
          "example": "[仿题]...",              # 例题
          "keywords": ["...", "..."],          # 3-8 个 JSON 数组
          "prerequisites": ["SX_A_G1_B1_HS_001"],  # 前置知识点 id（可空）
          "source_version": "人教A版2019",      # 教材版本全称
        }
      ]
    }

映射约定（与 docs/module2-next-iteration-tasks.md 一致）：
- subject_code = id 第一个 `_` 前的学科码（SX/YW/YY/...）；非法码跳过并告警
- code = id（点码直接用源 id，唯一可追溯）
- prerequisites → kb_point_relations（type=prerequisite，src=前置点，dst=当前点）
- typical_errors / keywords 存 JSON 数组文本（kb_points 列）
- parent_id 全部 NULL（扁平 L2 点；层级由 module_path 字符串表达，不建 L1 节点）
- exam_weight 未在源数据提供，走模型默认 0.1（考频 frequency 单独存，不混用）
- error_tip（单条易错点）源数据无，留空；多条见 typical_errors

向量化：KB_EMBED_MODE=api/local 时对 name+definition 向量化并写入本地 FAISS
（vector_store.add, ref_type="point"），供 RAG/points/match 检索；off 时跳过向量化。

幂等：按 id upsert（存在则更新字段），重复执行不产生重复行。

用法：
    cd backend
    .venv\\Scripts\\python.exe ../scripts/import_knowledge_points.py                 # 默认目录
    .venv\\Scripts\\python.exe ../scripts/import_knowledge_points.py <dir_or_file>   # 指定
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: F401  触发 ORM 注册
from database import SessionLocal
from models.knowledge import (
    KnowledgePoint,
    KnowledgePointRelation,
    KnowledgeSubject,
)

DEFAULT_DIR = Path(r"D:\Projects\knowledge base\docs\knowledge-points")

VALID_SUBJECTS = {"YW", "SX", "YY", "WL", "HX", "SW", "ZZ", "LS", "DL"}

# JSON 数组字段 → kb_points 的 JSON 文本列
_JSON_LIST_FIELDS = ("typical_errors", "keywords")


def _subject_code_from_id(point_id: str) -> str | None:
    code = point_id.split("_", 1)[0]
    return code if code in VALID_SUBJECTS else None


def _json_dumps(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def _list_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix == ".json" else []
    return sorted(target.glob("*.json"))


def _vectorize(point_id: str, text: str, model: str) -> bool:
    """对知识点文本向量化并写入本地 FAISS；失败/off 返回 False（不阻断导入）。"""
    try:
        from embedding_service import embed_mode, embed_text
        from vector_store import add as vector_add

        if embed_mode() not in ("local", "api"):
            return False
        vec = embed_text(text)
        if vec is None:
            return False
        return vector_add(vec, f"vp_{point_id}", "point", point_id, embed_mode(), len(vec))
    except Exception as e:  # noqa: BLE001
        print(f"    [向量化跳过] {point_id}: {type(e).__name__}")
        return False


def _import_point(db, pt: dict, module_path: str) -> tuple[str, bool]:
    """upsert 单知识点；返回 (id, 是否新建)。"""
    point_id = pt["id"]
    subject_code = _subject_code_from_id(point_id)
    if subject_code is None:
        print(f"  ! 非法学科码，跳过：{point_id}")
        return point_id, False

    fields = dict(
        subject_code=subject_code,
        code=point_id,
        name=pt["name"],
        definition=pt["definition"],
        explanation=pt.get("explanation"),
        difficulty=pt.get("difficulty", 3),
        frequency=pt.get("frequency"),
        example=pt.get("example"),
        module_path=module_path,
        source_version=pt.get("source_version"),
        enabled=True,
    )
    # JSON 数组字段
    for f in _JSON_LIST_FIELDS:
        val = pt.get(f) or []
        fields[f] = _json_dumps(val)

    existing = db.get(KnowledgePoint, point_id)
    is_new = existing is None
    if existing is None:
        db.add(KnowledgePoint(id=point_id, **fields))
    else:
        for k, v in fields.items():
            setattr(existing, k, v)
    db.flush()
    return point_id, is_new


def _import_relations(db, pt: dict) -> int:
    """prerequisites → kb_point_relations（幂等，按 src+dst 去重）。返回新增关系数。"""
    from sqlalchemy import select

    added = 0
    point_id = pt["id"]
    for pre_id in pt.get("prerequisites") or []:
        dup = db.execute(
            select(KnowledgePointRelation).where(
                KnowledgePointRelation.src_id == pre_id,
                KnowledgePointRelation.dst_id == point_id,
                KnowledgePointRelation.type == "prerequisite",
            )
        ).scalars().first()
        if dup is None:
            db.add(KnowledgePointRelation(
                id=f"kpr_{pre_id}__{point_id}",
                src_id=pre_id,
                dst_id=point_id,
                type="prerequisite",
                weight=0.5,
            ))
            added += 1
    return added


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    files = _list_files(target)
    if not files:
        print(f"未找到 JSON 文件：{target}")
        sys.exit(1)

    from embedding_service import embed_mode

    mode = embed_mode()
    print(f"导入 {len(files)} 个文件（embedding 模式：{mode}）")
    db = SessionLocal()
    total_new = total_upd = total_rel = total_vec = 0
    try:
        for fp in files:
            data = json.loads(fp.read_text(encoding="utf-8"))
            module_path = data.get("module_path", "")
            pts = data.get("l2_points", [])
            print(f"  {fp.name}: {len(pts)} 点 · module_path={module_path}")
            for pt in pts:
                pid, is_new = _import_point(db, pt, module_path)
                if is_new:
                    total_new += 1
                else:
                    total_upd += 1
                total_rel += _import_relations(db, pt)
                # 向量化（name+definition 作为检索文本）
                text = f"{pt['name']}。{pt.get('definition', '')}"
                if _vectorize(pid, text, mode):
                    total_vec += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(
        f"完成：新建 {total_new}，更新 {total_upd}，新增关系 {total_rel}，"
        f"向量化 {total_vec}（embedding 模式 {mode}）"
    )


if __name__ == "__main__":
    main()
