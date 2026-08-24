"""板块二种子数据：物理/英语学科示例知识点（v2.2）。

内容运营正式交付 100/200 点清单前，先提供与数学同构的示例导入，
保证三学科端到端链路可跑通。幂等：按 (code) upsert，重复执行不产生重复行。

用法：
    cd backend
    .venv\\Scripts\\python.exe scripts/seed_kb_physics_english.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from database import SessionLocal, engine
import models  # noqa: F401
from models.knowledge import KnowledgePoint, KnowledgeSubject

SUBJECTS = {
    "physics": {"id": "ks_physics", "name": "物理", "grade_band": "senior", "version": "1.0"},
    "english": {"id": "ks_english", "name": "英语", "grade_band": "senior", "version": "1.0"},
}

POINTS: dict[str, list[tuple]] = {
    "physics": [
        ("physics.mech", "力学", "研究物体运动与受力规律的分支。", "先画受力分析图再列方程。", None, 2, 0.06),
        ("physics.mech.newton", "牛顿运动定律", "F=ma，力是改变物体运动状态的原因。", "注意受力分析的完整性与方向。", "physics.mech", 3, 0.04),
        ("physics.mech.energy", "机械能守恒", "只有重力或弹力做功时机械能守恒。", "先判断是否满足守恒条件。", "physics.mech", 3, 0.04),
        ("physics.mech.momentum", "动量守恒", "系统不受外力或合外力为零时动量守恒。", "注意矢量性，规定正方向。", "physics.mech", 4, 0.04),
        ("physics.em", "电磁学", "电场、磁场与电磁感应。", "左右手定则别用反。", None, 3, 0.06),
        ("physics.em.coulomb", "库仑定律", "F=k·q1q2/r²。", "适用条件：真空静止点电荷。", "physics.em", 2, 0.03),
        ("physics.em.ohm", "欧姆定律", "I=U/R。", "区分纯电阻电路与非纯电阻电路。", "physics.em", 2, 0.03),
        ("physics.em.faraday", "法拉第电磁感应", "E=n·ΔΦ/Δt。", "磁通量变化率的正负与方向判断。", "physics.em", 4, 0.05),
        ("physics.thermal", "热学", "分子动理论、理想气体与热力学定律。", "区分温度、热量与内能。", None, 2, 0.03),
        ("physics.thermal.gas", "理想气体状态方程", "pV/T=C。", "注意状态参量单位与温度用开尔文。", "physics.thermal", 3, 0.03),
    ],
    "english": [
        ("english.grammar", "语法", "英语句子结构与词法规则。", "先分析句子主干（主谓宾）。", None, 2, 0.06),
        ("english.grammar.tense", "时态", "动词时态表达动作发生时间与状态。", "区分一般过去时与现在完成时。", "english.grammar", 2, 0.03),
        ("english.grammar.clause", "从句", "定语从句、名词性从句与状语从句。", "关系词在从句中作何成分决定用哪个。", "english.grammar", 3, 0.04),
        ("english.grammar.nonfinite", "非谓语动词", "不定式、动名词与分词。", "作状语时注意与逻辑主语的关系。", "english.grammar", 4, 0.04),
        ("english.reading", "阅读理解", "主旨大意、细节理解与推理判断。", "选项偷换概念是高频干扰项。", None, 2, 0.05),
        ("english.reading.inference", "推理判断", "根据上下文推断隐含意义。", "只在原文依据上推断，不过度解读。", "english.reading", 3, 0.03),
        ("english.reading.mainidea", "主旨大意", "概括段落与全文中心。", "首尾段与首尾句常含主旨。", "english.reading", 2, 0.03),
        ("english.writing", "书面表达", "应用文写作与句式丰富性。", "注意人称、时态与格式要求。", None, 3, 0.05),
        ("english.writing.cohesion", "衔接连贯", "连接词与指代使文章连贯。", "连接词别堆砌，逻辑要自然。", "english.writing", 3, 0.03),
        ("english.vocab", "词汇", "核心词汇的词义、搭配与派生。", "一词多义按语境判断。", None, 2, 0.05),
    ],
}


def main() -> None:
    db = SessionLocal()
    try:
        for code, meta in SUBJECTS.items():
            subj = db.get(KnowledgeSubject, meta["id"])
            if subj is None:
                db.add(KnowledgeSubject(id=meta["id"], code=code, **{k: v for k, v in meta.items() if k != "id"}))
                db.flush()

        for code, ps in POINTS.items():
            for pcode, name, definition, tip, parent, difficulty, weight in ps:
                existing = db.query(KnowledgePoint).filter_by(subject_code=code, code=pcode).first()
                if existing is None:
                    db.add(KnowledgePoint(
                        id=f"kp_{pcode.replace('.', '_')}",
                        subject_code=code,
                        code=pcode,
                        name=name,
                        definition=definition,
                        error_tip=tip,
                        parent_id=f"kp_{parent.replace('.', '_')}" if parent else None,
                        difficulty=difficulty,
                        exam_weight=weight,
                        enabled=True,
                    ))
                else:
                    existing.name = name
                    existing.definition = definition
                    existing.error_tip = tip
                    existing.difficulty = difficulty
                    existing.exam_weight = weight
        db.commit()
        for code in ("physics", "english"):
            n = db.query(KnowledgePoint).filter_by(subject_code=code).count()
            print(f"seeded: {code} points={n}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
