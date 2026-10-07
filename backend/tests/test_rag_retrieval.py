"""T8 RAG 检索链路测试（error-parse 向量召回路径）。

覆盖 `_retrieve_error_points` 的两条路径：
- 路径 1：错题已绑定知识点（kb_error_points）
- 路径 2（T8 新增）：错题原文向量召回——mock embed_text/vector_search，
  覆盖 point 类型 ref、error 类型 ref、embedding off、向量失败降级 四态。

⚠️ 合规（PRD 12.6 / AGENTS.md 铁律 6）：本链路处理的是**错题原文**，属用户内容，
**只能走本地模型、永不出域**。所以这里的成功路径 mock 的是 `local` 而**不是** `api`——
2026-09-27 之前这些用例 mock 的是 `api`，等于把「错题出域」固化成了预期行为，已翻转。

⚠️ 2026-10-06 起：`_retrieve_error_points` 会**查两次**（KB + USER 两个命名空间），
所以这里的 `vector_store.search` 桩必须接受 `store` kwarg（否则桩签名不匹配 → TypeError
被调用侧 try/except 吞成静默降级 → 表现为「召回悄悄失效」，而不是报错）。
"""
from __future__ import annotations

import pytest

from database import SessionLocal
from models.knowledge import ErrorPoint, ErrorRecord, KnowledgePoint
from routes.knowledge import _retrieve_error_points


def _stub_search(monkeypatch, kb_hits=(), user_hits=()) -> list[str]:
    """装 `vector_store.search` 桩：按 store 返回不同结果，并记录查询过的 store。

    返回被查询过的 store 列表（顺序即调用顺序），供断言「两库都查了」。
    """
    seen: list[str] = []

    def _fake(vec, top_k=5, subject=None, *, store="kb", **kw):
        seen.append(store)
        return list(user_hits) if store == "user" else list(kb_hits)

    monkeypatch.setattr("vector_store.search", _fake)
    return seen


def _local_mode(monkeypatch, result: list[float] | None = [0.1, 0.2]) -> None:
    """把错题召回 mock 成「本地模型可用，产出 result」。

    同时把 KB_EMBED_MODE 拨成 api——**正是这个组合曾经导致错题出域**，
    用来证明本链路现在也不会走 api。
    """
    monkeypatch.setattr("config.settings.kb_embed_mode", "api")
    monkeypatch.setattr("embedding_service.embed_mode", lambda: "api")
    monkeypatch.setattr("embedding_service.embed_mode_for", lambda source, **kw: "local")
    monkeypatch.setattr("embedding_service.embed_text", lambda text, source=None, **kw: result)


def _seed(monkeypatch, subject: str = "SX") -> str:
    """造错题 + 2 个知识点（其中 1 个绑定到错题），返回 error_id。"""
    db = SessionLocal()
    try:
        db.add(ErrorRecord(
            id="err_t8", user_id="u_t8", subject=subject,
            raw_text="函数在区间上单调递增怎么判断",
        ))
        db.add(KnowledgePoint(
            id="kp_bound", subject_code=subject, code="math.func.mono",
            name="函数单调性", definition="随自变量增减的性质", error_tip="注意定义域",
        ))
        db.add(KnowledgePoint(
            id="kp_unbound", subject_code=subject, code="math.deriv",
            name="导数与极值", definition="一阶导数求极值", error_tip="注意二阶导",
        ))
        db.add(ErrorPoint(id="erp_1", error_id="err_t8", point_id="kp_bound", confidence=1.0))
        db.commit()
    finally:
        db.close()
    return "err_t8"


def test_linked_points_path_without_embedding(monkeypatch):
    """embedding off：只走路径 1（已绑定知识点）。"""
    _seed(monkeypatch)
    monkeypatch.setattr("embedding_service.embed_mode_for", lambda source, **kw: "off")
    out = _retrieve_error_points("err_t8")
    names = {p["name"] for p in out}
    assert "函数单调性" in names
    assert "导数与极值" not in names  # 未绑定且无向量 → 不召回


def test_vector_recall_point_ref(monkeypatch):
    """向量库命中 point 类型 ref → 直接取知识点，与绑定并集。"""
    _seed(monkeypatch)
    _local_mode(monkeypatch)
    seen = _stub_search(monkeypatch, kb_hits=[("kp_unbound", 0.9)])
    out = _retrieve_error_points("err_t8")
    names = {p["name"] for p in out}
    assert "函数单调性" in names  # 路径 1
    assert "导数与极值" in names  # 路径 2（point ref）
    assert out[0]["definition"]  # 元信息非空
    assert seen == ["kb", "user"]  # 🔴 两库都查了（合并检索）


def test_vector_recall_error_ref(monkeypatch):
    """🔴 核心回归：USER 命名空间的 error 类型 ref 必须被召回（方案 B 后仍可达）。

    2026-10-06 方案 B 把错题向量隔离到 USER store 后，曾出现「只查 KB → 永远收不到
    error ref → 下面这段分支成不可达代码」的缺口。本用例锁死它必须重新可达。
    """
    err2 = _seed(monkeypatch)
    db = SessionLocal()
    try:
        db.add(ErrorRecord(
            id="err_similar", user_id="u_t8", subject="SX",
            raw_text="判断复合函数的单调性",
        ))
        db.add(ErrorPoint(id="erp_2", error_id="err_similar", point_id="kp_unbound", confidence=1.0))
        db.commit()
    finally:
        db.close()

    _local_mode(monkeypatch)
    # 相似错题的向量落在 **USER** store（这才是方案 B 后的真实布局）
    seen = _stub_search(monkeypatch, user_hits=[("err_similar", 0.85)])
    out = _retrieve_error_points(err2)
    names = {p["name"] for p in out}
    assert "导数与极值" in names  # 经相似错题召回 ← 这条断言就是「分支重新可达」的证明
    assert "函数单调性" in names  # 原绑定仍在
    assert seen == ["kb", "user"]


def test_vector_recall_failure_falls_back(monkeypatch):
    """向量召回失败（embed_text None）→ 静默降级，仅返回路径 1 结果，不报错。"""
    _seed(monkeypatch)
    _local_mode(monkeypatch, result=None)
    out = _retrieve_error_points("err_t8")
    names = {p["name"] for p in out}
    assert names == {"函数单调性"}


def test_vector_recall_cross_subject_filtered(monkeypatch):
    """跨学科召回被过滤：英语知识点不进入数学错题的检索结果。"""
    _seed(monkeypatch, subject="SX")
    db = SessionLocal()
    try:
        db.add(KnowledgePoint(
            id="kp_en", subject_code="YY", code="eng.tense",
            name="时态辨析", definition="动词时态", error_tip="注意主谓一致",
        ))
        db.commit()
    finally:
        db.close()

    _local_mode(monkeypatch)
    _stub_search(monkeypatch, kb_hits=[("kp_en", 0.99), ("kp_bound", 0.8)])
    out = _retrieve_error_points("err_t8")
    names = {p["name"] for p in out}
    assert "时态辨析" not in names  # 跨学科被过滤
    assert "函数单调性" in names


def test_error_text_never_leaves_domain(monkeypatch):
    """🔴 出域红线：`KB_EMBED_MODE=api` 时，错题召回仍**不得**调用外部 API。

    直接把 `embedding_service._embed_api` 换成炸弹——被调用即测试失败。
    """
    _seed(monkeypatch)
    monkeypatch.setattr("config.settings.kb_embed_mode", "api")
    monkeypatch.setattr("config.settings.embed_base_url", "https://example.invalid/v1")
    monkeypatch.setattr("config.settings.embed_api_key", "leak-me")
    monkeypatch.setattr("config.settings.embed_model", "embedding-3")
    monkeypatch.setattr(
        "embedding_service._embed_api",
        lambda text: pytest.fail("错题原文被发往外部 embedding API"),
    )
    # 本地模型也没装 → 应宁缺毋滥返回 None，只走路径 1
    out = _retrieve_error_points("err_t8")
    assert {p["name"] for p in out} == {"函数单调性"}


def test_error_text_declares_user_scope(monkeypatch):
    """错题召回必须显式声明 `source=EMBED_SRC_USER`（缺省会按知识库处理并可能出域）。"""
    _seed(monkeypatch)
    seen: list[str] = []

    def _capture(text, source=None, **kw):
        # **kw：embed_text 现在还有 user_api_opt_in（PRD 12.6 / D41）。
        # ⚠️ 桩签名不跟上会抛 TypeError，而调用侧的 try/except 会把它吞成静默降级 ——
        # 表现为「召回悄悄失效」而不是报错（本次实测踩到）。
        seen.append(source)
        return None

    monkeypatch.setattr("config.settings.kb_embed_mode", "api")
    monkeypatch.setattr("embedding_service.embed_mode_for", lambda source, **kw: "local")
    monkeypatch.setattr("embedding_service.embed_text", _capture)
    _retrieve_error_points("err_t8")
    assert seen == ["user"]


# --- 以下：两次检索合并的语义（2026-10-06 · 方案 B 后续）---------------------


def test_merge_hits_dedups_and_orders_by_similarity():
    """合并：按 refId 去重、按相似度降序、截断到 limit。"""
    from routes.knowledge import _merge_hits

    out = _merge_hits(
        [("kp_a", 0.7), ("kp_b", 0.95)],
        [("err_x", 0.9), ("kp_a", 0.5)],  # kp_a 两库都出现 → 保高分 0.7
        limit=5,
    )
    assert out == [("kp_b", 0.95), ("err_x", 0.9), ("kp_a", 0.7)]


def test_merge_hits_no_id_collision_between_kb_and_user():
    """🔴 确认两库 refId 空间不撞：KB=point id（kp_*）、USER=error id（err_*）。

    若将来真出现同 id，合并会按高分保一条（去重生效），不会重复产出。
    """
    from routes.knowledge import _merge_hits

    out = _merge_hits([("kp_a", 0.6)], [("err_a", 0.8)], limit=5)
    assert {r for r, _ in out} == {"kp_a", "err_a"}
    assert len(out) == 2


def test_merge_hits_one_sided_not_penalized():
    """只有一边有命中时，不被「按比例分配」白削——单调不劣。"""
    from routes.knowledge import _merge_hits

    only_kb = _merge_hits([(f"kp_{i}", 0.9 - i * 0.01) for i in range(5)], [], limit=5)
    only_user = _merge_hits([], [(f"err_{i}", 0.9 - i * 0.01) for i in range(5)], limit=5)
    assert len(only_kb) == 5
    assert len(only_user) == 5


def test_user_recall_survives_kb_empty(monkeypatch):
    """端到端：KB 索引空、USER 有命中 —— error ref 仍要能召回（方案 B 的关键场景）。"""
    _seed(monkeypatch)
    db = SessionLocal()
    try:
        db.add(ErrorRecord(id="err_sim2", user_id="u_t8", subject="SX", raw_text="单调性判断"))
        db.add(ErrorPoint(id="erp_3", error_id="err_sim2", point_id="kp_unbound", confidence=1.0))
        db.commit()
    finally:
        db.close()

    _local_mode(monkeypatch)
    _stub_search(monkeypatch, kb_hits=[], user_hits=[("err_sim2", 0.88)])
    out = _retrieve_error_points("err_t8")
    assert "导数与极值" in {p["name"] for p in out}
