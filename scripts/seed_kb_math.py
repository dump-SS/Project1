"""板块二种子数据：数学单科知识点（示例 50 点，PRD 12.3.1）。

幂等导入：按 (subject_code, code) upsert，重复执行不产生重复行。
内容为高中数学常用知识点清单，供 v2.1 演示与联调；
正式 50 点内容由内容团队按 kb_ 字段模板交付后替换。

用法：
    cd backend
    .venv\\Scripts\\python.exe scripts/seed_kb_math.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from database import Base, SessionLocal, engine
import models  # noqa: F401  触发所有 ORM 注册
from models.knowledge import (
    KnowledgePoint,
    KnowledgePointRelation,
    KnowledgeSubject,
)


MATH_SUBJECT_ID = "ks_math"
MATH_SUBJECT = {
    "id": MATH_SUBJECT_ID,
    "code": "math",
    "name": "数学",
    "grade_band": "senior",
    "version": "1.0",
    "enabled": True,
}

# (code, name, definition, error_tip, parent_code, difficulty, exam_weight)
# parent_code=None 表示根节点（章节）
MATH_POINTS: list[tuple] = [
    # 函数
    ("math.func", "函数", "函数是把一个集合的元素映射到另一个集合的对应关系。", "注意定义域与值域的对应该关系。", None, 2, 0.05),
    ("math.func.domain", "函数定义域", "使函数解析式有意义的所有自变量取值。", "分母不为零、偶次根号内非负、对数真数大于零。", "math.func", 2, 0.03),
    ("math.func.range", "函数值域", "函数所有可能的因变量取值。", "求值域先看定义域。", "math.func", 3, 0.02),
    ("math.func.monotonicity", "函数单调性", "函数在区间上随自变量增大而增大或减小的性质。", "用定义证明时注意设 x1<x2 并判断差的正负。", "math.func", 3, 0.04),
    ("math.func.parity", "函数奇偶性", "偶函数满足 f(-x)=f(x)，奇函数满足 f(-x)=-f(x)。", "先检查定义域是否关于原点对称。", "math.func", 2, 0.03),
    ("math.func.period", "函数周期性", "存在非零 T 使 f(x+T)=f(x)。", "周期函数注意最小正周期的求法。", "math.func", 3, 0.02),
    ("math.func.quadratic", "二次函数", "形如 f(x)=ax²+bx+c（a≠0）。", "a>0 开口向上，a<0 开口向下；顶点横坐标 -b/2a。", "math.func", 2, 0.04),
    ("math.func.exponential", "指数函数", "形如 y=a^x（a>0 且 a≠1）。", "a>1 递增，0<a<1 递减；过定点 (0,1)。", "math.func", 3, 0.03),
    ("math.func.log", "对数函数", "形如 y=log_a(x)（a>0 且 a≠1）。", "真数必须大于零；与指数函数互为反函数。", "math.func", 3, 0.03),
    ("math.func.power", "幂函数", "形如 y=x^α。", "不同 α 的图象与定义域不同，先画图再判断。", "math.func", 2, 0.02),
    # 三角函数
    ("math.trig", "三角函数", "研究正弦、余弦、正切等周期函数的定义与性质。", "牢记同角公式与诱导公式的符号口诀。", None, 3, 0.05),
    ("math.trig.sine", "正弦函数", "y=sin x，周期 2π，值域 [-1,1]。", "五点作图法画图象；注意相位变换。", "math.trig", 2, 0.03),
    ("math.trig.cosine", "余弦函数", "y=cos x，周期 2π，值域 [-1,1]。", "cos(-x)=cos x，是偶函数。", "math.trig", 2, 0.02),
    ("math.trig.tangent", "正切函数", "y=tan x，周期 π。", "定义域 x≠π/2+kπ；注意渐近线。", "math.trig", 3, 0.02),
    ("math.trig.identities", "三角恒等变换", "和差角、倍角、辅助角等公式的变形与运用。", "注意符号与降幂公式（cos²x=(1+cos2x)/2）。", "math.trig", 4, 0.04),
    # 解三角形
    ("math.triangle", "解三角形", "用正弦定理与余弦定理求解三角形的边角。", "已知两边及一边对角时可能有两解。", None, 3, 0.04),
    ("math.triangle.sine_rule", "正弦定理", "a/sinA = b/sinB = c/sinC = 2R。", "用于已知两角一边或两边一边对角。", "math.triangle", 2, 0.02),
    ("math.triangle.cosine_rule", "余弦定理", "c² = a² + b² - 2ab·cosC。", "求角用余弦定理的角形式。", "math.triangle", 2, 0.02),
    ("math.triangle.area", "三角形面积", "S = ½·ab·sinC。", "已知两边夹角求面积。", "math.triangle", 1, 0.01),
    # 数列
    ("math.sequence", "数列", "按一定顺序排列的一列数及通项与前 n 项和。", "区分 an 与 Sn 的关系：a1=S1，an=Sn-S(n-1)。", None, 3, 0.05),
    ("math.sequence.arithmetic", "等差数列", "从第二项起每一项与前一项的差为常数 d。", "通项 an=a1+(n-1)d；求和公式两种形式。", "math.sequence", 2, 0.03),
    ("math.sequence.geometric", "等比数列", "从第二项起每一项与前一项的比为常数 q（q≠0）。", "q=1 时求和为 n·a1；注意公比是否等于 1。", "math.sequence", 3, 0.03),
    ("math.sequence.sum", "数列求和", "裂项相消、错位相减、分组求和等。", "错位相减注意对齐项与末项符号。", "math.sequence", 4, 0.04),
    # 立体几何
    ("math.solid", "立体几何", "研究空间几何体的结构、表面积与体积。", "先证明后计算；看清是用正视图还是三视图。", None, 3, 0.05),
    ("math.solid.volume", "体积与表面积", "柱锥台球的表面积与体积公式。", "锥体体积是柱体的 1/3。", "math.solid", 2, 0.03),
    ("math.solid.spatial_line", "空间直线与平面", "线面平行、垂直的判定与性质。", "判定定理条件要写全（如线线垂直需相交）。", "math.solid", 4, 0.04),
    ("math.solid.space_vector", "空间向量", "用向量方法解决立体几何角度与距离问题。", "建系找坐标要准确，法向量小心方向。", "math.solid", 4, 0.03),
    # 解析几何
    ("math.analytic", "解析几何", "用坐标与方程研究曲线（直线、圆、圆锥曲线）。", "先定型再定量，联立方程别忘了判别式。", None, 3, 0.06),
    ("math.analytic.line", "直线", "直线的斜率、点斜式、斜截式与一般式。", "斜率不存在时直线垂直于 x 轴。", "math.analytic", 2, 0.03),
    ("math.analytic.circle", "圆", "圆心与半径确定圆的标准方程 x²+y²=r² 等的变形。", "一般式配方求圆心半径时注意 D²+E²-4F>0。", "math.analytic", 2, 0.03),
    ("math.analytic.ellipse", "椭圆", "到两定点距离之和为定值的点的轨迹。", "分清 a、b、c 关系（a²=b²+c²）与焦点位置。", "math.analytic", 4, 0.04),
    ("math.analytic.hyperbola", "双曲线", "到两定点距离之差的绝对值为定值的点的轨迹。", "关系 c²=a²+b²；渐近线 y=±(b/a)x。", "math.analytic", 4, 0.03),
    ("math.analytic.parabola", "抛物线", "到定点与定直线距离相等的点的轨迹。", "焦点、准线、p 的含义别混。", "math.analytic", 3, 0.03),
    # 概率统计
    ("math.prob", "概率统计", "随机事件概率、分布与统计量的计算。", "古典概型注意样本空间是否等可能。", None, 2, 0.04),
    ("math.prob.classical", "古典概型", "等可能基本事件下的 P(A)=m/n。", "分子分母计数要同标准。", "math.prob", 2, 0.02),
    ("math.prob.conditional", "条件概率", "P(B|A)=P(AB)/P(A)。", "与相互独立事件 P(AB)=P(A)P(B) 区分。", "math.prob", 3, 0.03),
    ("math.prob.distribution", "随机变量分布", "二项分布、超几何分布及其期望方差。", "二项分布 X~B(n,p)：E=np，D=np(1-p)。", "math.prob", 3, 0.03),
    ("math.prob.normal", "正态分布", "钟形曲线，μ 中心、σ 宽度。", "3σ 原则的区间概率。", "math.prob", 4, 0.02),
    # 导数
    ("math.derivative", "导数", "函数在某点的瞬时变化率及其几何意义。", "先求定义域与导数，再列表讨论单调性。", None, 4, 0.06),
    ("math.derivative.rules", "求导法则", "和差积商与复合函数求导法则。", "内层导数必须乘上（链式法则）。", "math.derivative", 3, 0.03),
    ("math.derivative.monotone", "导数与单调性", "f'(x)>0 增、f'(x)<0 减。", "端点与驻点都要列入讨论。", "math.derivative", 4, 0.04),
    ("math.derivative.extreme", "极值与最值", "驻点、极值点与闭区间最值的求法。", "极值点处导数可能为 0 但不一定可导；最值可与端点比较。", "math.derivative", 4, 0.04),
    # 集合与逻辑
    ("math.set", "集合", "集合的表示、运算与关系。", "空集是任何集合的子集，注意不要漏。", None, 1, 0.03),
    ("math.set.ops", "集合运算", "交集、并集、补集。", "用 Venn 图或数轴辅助，端点取等要标清。", "math.set", 1, 0.02),
    ("math.set.proposition", "命题与逻辑", "充分条件、必要条件与充要条件。", "判断谁推出谁：p⇒q 则 p 是 q 的充分条件。", "math.set", 2, 0.02),
    # 复数
    ("math.complex", "复数", "形如 a+bi 的数及四则运算。", "i²=-1；复数相等的充要条件是实部虚部分别相等。", None, 1, 0.02),
    ("math.complex.modulus", "复数模与几何意义", "|z|=√(a²+b²)，对应复平面距离。", "|z-z0| 的几何意义是距离。", "math.complex", 2, 0.01),
    # 不等式
    ("math.inequality", "不等式", "基本不等式与解不等式。", "乘除负数要变号；基本不等式注意一正二定三相等。", None, 2, 0.03),
    ("math.inequality.mean", "基本不等式", "a+b≥2√(ab)（a,b>0）。", "验证取等条件 a=b 是否满足。", "math.inequality", 2, 0.02),
    ("math.inequality.abs", "含绝对值不等式", "|x|<a 与 |x|>a 的解集。", "含绝对值需分类讨论或平方去绝对值。", "math.inequality", 3, 0.02),
]

# (src_code, dst_code, type, weight)
MATH_RELATIONS: list[tuple] = [
    ("math.func", "math.func.monotonicity", "prerequisite", 0.9),
    ("math.func", "math.func.parity", "prerequisite", 0.7),
    ("math.func", "math.derivative", "prerequisite", 0.8),
    ("math.func.exponential", "math.func.log", "contrast", 0.9),
    ("math.derivative", "math.derivative.monotone", "derived", 0.9),
    ("math.derivative.monotone", "math.derivative.extreme", "prerequisite", 0.9),
    ("math.trig", "math.analytic", "applied_in", 0.5),
    ("math.sequence", "math.prob.distribution", "applied_in", 0.4),
]


def _by_code(db) -> dict:
    return {
        row.code: row
        for row in db.query(KnowledgePoint).filter(KnowledgePoint.subject_code == "math").all()
    }


def _finalize(db, row: KnowledgePoint) -> None:
    db.add(row)
    db.flush()  # 拿到 row.id


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 1. 学科 upsert
        subj = db.get(KnowledgeSubject, MATH_SUBJECT_ID)
        if subj is None:
            subj = KnowledgeSubject(**MATH_SUBJECT)
            db.add(subj)
            db.flush()
        else:
            for k, v in MATH_SUBJECT.items():
                if k != "id":
                    setattr(subj, k, v)

        # 2. 知识点 upsert（先建根节点拿 id，再建子节点）
        code_row: dict[str, KnowledgePoint] = {}
        # 两轮：第一轮根，第二轮子（parent 已存在）
        for parent_code in (None, "not_none"):
            for code, name, definition, error_tip, pc, difficulty, weight in MATH_POINTS:
                is_root = pc is None
                if parent_code is None and not is_root:
                    continue
                if parent_code is not None and is_root:
                    continue
                existing = code_row.get(code) or db.query(KnowledgePoint).filter_by(
                    subject_code="math", code=code
                ).first()
                if existing is None:
                    obj = KnowledgePoint(
                        id=f"kp_{code.replace('.', '_')}",
                        subject_code="math",
                        code=code,
                        name=name,
                        definition=definition,
                        error_tip=error_tip,
                        parent_id=code_row[pc].id if pc else None,
                        difficulty=difficulty,
                        exam_weight=weight,
                        enabled=True,
                    )
                    db.add(obj)
                    db.flush()
                    code_row[code] = obj
                else:
                    for k, v in dict(
                        name=name, definition=definition, error_tip=error_tip,
                        difficulty=difficulty, exam_weight=weight,
                    ).items():
                        setattr(existing, k, v)
                    existing.parent_id = code_row[pc].id if pc else None
                    code_row[code] = existing

        # 3. 关系 upsert（按 src+dst 去重）
        for src, dst, rtype, w in MATH_RELATIONS:
            from sqlalchemy import select
            dup = db.execute(
                select(KnowledgePointRelation).where(
                    KnowledgePointRelation.src_id == code_row[src].id,
                    KnowledgePointRelation.dst_id == code_row[dst].id,
                )
            ).scalars().first()
            if dup is None:
                db.add(KnowledgePointRelation(
                    id=f"kpr_{src.replace('.', '_')}_{dst.replace('.', '_')}",
                    src_id=code_row[src].id,
                    dst_id=code_row[dst].id,
                    type=rtype,
                    weight=w,
                ))

        db.commit()
        n_pts = db.query(KnowledgePoint).filter_by(subject_code="math").count()
        n_rel = db.query(KnowledgePointRelation).count()
        print(f"seeded: math points={n_pts}, relations={n_rel}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
