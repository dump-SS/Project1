"""讲解精品样例种子：pilot 3–5 条（D52 / #22）。

精品样例（``is_curated=true``）与动态生成（``is_curated=false``）**严格区分**：
- 精品样例是**预制入库、人工过稿、长期保存**的，用来验证 schema 与生成管线，
  也用来给「讲解到底长什么样」定调；
- 动态生成是用户点「重新讲一遍」现产的，随时可能被下一条取代。

所以本脚本**幂等按 (subject, name) upsert 精品行**，绝不覆盖用户自己生成的讲解
（只认 is_curated=true 的行，且 userId 固定为系统账号 ``u_curated``）。

知识点挂靠：按 ``name`` 在 ``kb_points`` 里找同名点；找不到就按给定内容建一条
（pilot 阶段知识库可能还没铺满，建点比挂空更安全——挂空的精品样例查不出来）。

用法（在仓库根目录执行，与其它 seed 脚本一致）：
    cd backend && .venv\\Scripts\\python.exe ..\\scripts\\seed_curated_explanations.py
"""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from database import Base, SessionLocal, engine  # noqa: E402
import models  # noqa: F401  触发所有 ORM 注册
from models.explanation import Explanation  # noqa: E402
from models.knowledge import KnowledgePoint  # noqa: E402

# 精品样例归属的系统账号（不占用任何真实用户）
CURATED_USER_ID = "u_curated"


def _stable_suffix(*parts: str) -> str:
    """稳定 ID 后缀。

    ⚠️ 不用内置 ``hash()``：Python 对 str 的哈希默认**按进程随机化**
    （PYTHONHASHSEED），同一条样例每次运行会算出不同 ID——upsert 就失效了，
    跑几次库里就堆几份重复精品行。这里用 md5 取前 8 位，跨进程跨机器都稳定。
    """
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:8]

# (subject_code, point_name, point_definition, content)
# 5 条覆盖 4 个学科，其中英语那条带「查词卡」——用来验证 D52 的语言类学科形态。
CURATED: list[tuple[str, str, str, str]] = [
    (
        "SX",
        "函数单调性",
        "设函数 f(x) 的定义域为 I，区间 D⊆I。若对任意 x1<x2∈D 都有 f(x1)<f(x2)，"
        "则称 f(x) 在 D 上单调递增；若 f(x1)>f(x2) 则单调递减。",
        "### 📖 函数单调性\n\n"
        "① **一句话**：单调性描述的是「x 变大时 y 往哪边走」，只看方向，不看快慢。\n\n"
        "② **一个例子**：f(x)=x² 在 (−∞,0] 上递减、在 [0,+∞) 上递增——"
        "同一个函数在不同区间可以有相反的单调性，所以**说单调性必须带上区间**。\n\n"
        "③ **易错点**：把「在整个定义域上单调」当成默认。正确做法是求导后看符号，"
        "再按导数零点**分段**下结论。\n\n"
        "④ **自检小问**：f(x)=x³−3x 在 [−2,2] 上单调吗？先求 f′(x)=3x²−3，看它在哪段为正。",
    ),
    (
        "SX",
        "等差数列前 n 项和",
        "S_n = n(a₁+a_n)/2 = n·a₁ + n(n−1)d/2。",
        "### 📖 等差数列前 n 项和\n\n"
        "① **一句话**：首尾配对，每对的和都是 a₁+a_n，一共 n/2 对。\n\n"
        "② **一个例子**：1+2+…+100 = 100×(1+100)/2 = 5050。这就是高斯小时候那道题。\n\n"
        "③ **易错点**：n 是项数，**不是末项的值**。求「前多少项」时先用 "
        "a_n = a₁+(n−1)d 把 n 解出来，再代 S_n。\n\n"
        "④ **自检小问**：a₁=2、d=3，S_n=155，求 n。（提示：会得到二次方程，取正整数解）",
    ),
    (
        "WL",
        "牛顿第二定律",
        "物体加速度的大小跟合外力成正比、跟质量成反比，方向与合外力相同：F=ma。",
        "### 📖 牛顿第二定律\n\n"
        "① **一句话**：力不是维持运动的原因，**力是改变运动（产生加速度）的原因**。\n\n"
        "② **一个例子**：推空的购物车比推装满的更容易加速——同样 F，m 越大 a 越小。\n\n"
        "③ **易错点**：把 F 当成某一个力。公式里的 F 是**合外力**，"
        "解题第一步永远是受力分析、求合力。\n\n"
        "④ **自检小问**：10 kg 物体受 30 N 水平拉力、摩擦力 10 N，加速度多大？"
        "（先求合力 20 N，再除以质量）",
    ),
    (
        "HX",
        "氧化还原反应",
        "有化合价升降（本质是电子转移）的化学反应。升价被氧化、降价被还原。",
        "### 📖 氧化还原反应\n\n"
        "① **一句话**：记口诀「**升失氧、降得还**」——化合价升高、失电子、被氧化；"
        "降低、得电子、被还原。\n\n"
        "② **一个例子**：Zn + CuSO₄ → ZnSO₄ + Cu，Zn 从 0 升到 +2（被氧化），"
        "Cu 从 +2 降到 0（被还原）。\n\n"
        "③ **易错点**：把「被氧化」当成「和氧反应」。早期定义已淘汰，"
        "现在一律按**化合价**判。\n\n"
        "④ **自检小问**：2H₂+O₂→2H₂O 里，谁是还原剂？（提示：找化合价升高的那个）",
    ),
    (
        "YY",
        "现在完成时的用法",
        "have/has + 过去分词，表示过去发生的动作对现在造成的影响或持续到现在。",
        "### 📖 现在完成时\n\n"
        "① **一句话**：它连的是「过去发生的动作」和「现在的结果」，"
        "所以**不和具体过去时间点连用**。\n\n"
        "② **一个例子**：I **have lost** my key.（钥匙现在还没找到）"
        "对比 I **lost** my key yesterday.（只陈述昨天丢了这个事实）\n\n"
        "③ **易错点**：和 yesterday / in 2020 这类明确过去时间状语连用。"
        "见到它们，改用一般过去时。\n\n"
        "④ **自检小问**：「我已经写完作业了」怎么说？"
        "（I have finished my homework.）\n\n"
        "### 📇 查词卡\n\n"
        "| 词语 / 表达 | 释义 | 例句 | 出处 |\n"
        "|---|---|---|---|\n"
        "| present perfect | 现在完成时 | I have lived here for 3 years. | 人教版必修一 Unit 3 |\n"
        "| for / since | 持续时段 / 自某时起 | since 2020 | 人教版必修一 Unit 3 |\n\n"
        "> 出处回溯：人教版高中英语必修一 Unit 3，语法附录。",
    ),
]


def _ensure_point(db, subject_code: str, name: str, definition: str) -> str:
    """按 (subject_code, name) 找知识点；没有就建一条，返回 point_id。"""
    row = db.execute(
        select(KnowledgePoint).where(
            KnowledgePoint.subject_code == subject_code,
            KnowledgePoint.name == name,
        )
    ).scalars().first()
    if row is not None:
        return row.id

    suffix = _stable_suffix(subject_code, name)
    point_id = f"kp_curated_{subject_code.lower()}_{suffix}"
    db.add(KnowledgePoint(
        id=point_id,
        subject_code=subject_code,
        code=f"curated.{subject_code.lower()}.{suffix}",
        name=name,
        definition=definition,
        error_tip=None,
        parent_id=None,
        difficulty=3,
        exam_weight=0.5,
        enabled=True,
    ))
    db.flush()
    return point_id


def main() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        created, updated = 0, 0
        for subject, name, definition, content in CURATED:
            point_id = _ensure_point(db, subject, name, definition)
            row = db.execute(
                select(Explanation).where(
                    Explanation.user_id == CURATED_USER_ID,
                    Explanation.point_id == point_id,
                    Explanation.is_curated.is_(True),
                )
            ).scalars().first()
            if row is None:
                db.add(Explanation(
                    id=f"exp_curated_{_stable_suffix(subject, name)}",
                    user_id=CURATED_USER_ID,
                    point_id=point_id,
                    subject=subject,
                    mode="original",
                    content=content,
                    is_curated=True,
                    created_at=datetime.now(timezone.utc),
                ))
                created += 1
            else:
                row.content = content
                row.subject = subject
                updated += 1
        db.commit()

        total = db.execute(
            select(Explanation).where(Explanation.is_curated.is_(True))
        ).scalars().all()
        print(f"[seed_curated_explanations] 新增 {created} 条 / 更新 {updated} 条")
        print(f"[seed_curated_explanations] 精品样例共 {len(total)} 条：")
        for e in total:
            print(f"  - {e.subject}  pointId={e.point_id}  len={len(e.content)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
