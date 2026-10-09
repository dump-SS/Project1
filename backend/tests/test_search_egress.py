"""搜题（D24）+ 讲解（D52）+ 出域合规（2026-09-30 拍板）测试。

本文守三条硬口径，任何一条挂了都不许合：

1. **错题/学习记录的 embedding 永不出域**（PRD 12.6）——`knowledge_raw` 仍然被拒，
   知识点库原始素材一个字都出不去；新开的 `user_error_content` 只允许
   「用户主动发起 + 用户自己的内容」，且有自己的白名单。
2. **开关关着就一个字都不出去**——`settings.knowledge_ai_egress_enabled=false`
   时，发给模型的 prompt 里**不得出现题面**（这是降级到方案 A 的可验证证据）。
3. **出域只绑定用户即时动作**——`routes/search.py` 里不允许出现任何
   `BackgroundTasks` / `add_task` / 定时入口（直接扫源码断言）。

外加 D24/D52 的产品口径：三态被记忆、讲解两态并存、精品样例与动态生成可区分、
中学解法约束进了 prompt。
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from database import SessionLocal
from egress_guard import (
    KNOWLEDGE_RAW,
    USER_ERROR_CONTENT,
    EgressViolation,
    Guard,
)
from main import app
from models.explanation import Explanation as ExplanationORM
from models.knowledge import KnowledgePoint as KnowledgePointORM
from models.user import Settings as SettingsORM

client = TestClient(app)

HDR = {"X-User-ID": "u_test_search_egress"}
POINT_ID = "kp_search_egress_001"
QUESTION = "已知函数 f(x)=x^2-2x，求它的单调区间，用到的知识点是函数单调性"

_SEARCH_ROUTE_SRC = (
    Path(__file__).resolve().parents[1] / "routes" / "search.py"
).read_text(encoding="utf-8")


class _CaptureProvider:
    """替身 provider：记录每次出域的 prompt 与 context，并**照常跑 egress 校验**。

    跑校验是关键——否则测试只会证明「代码没调 Guard」，而不是「调了也过得去」。
    """

    def __init__(self, reply: str = "### 💡 解答\n测试解答正文") -> None:
        self.prompts: list[str] = []
        self.contexts: list[dict] = []
        self.reply = reply

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        from llm_provider import _enforce_egress

        _enforce_egress(prompt, context)  # 与真实 provider 同一道闸
        self.prompts.append(prompt)
        self.contexts.append(context or {})
        return self.reply


@pytest.fixture
def _point():
    db = SessionLocal()
    try:
        db.add(KnowledgePointORM(
            id=POINT_ID, subject_code="SX", code="sx.monotonic",
            name="函数单调性", definition="描述函数增减方向的性质",
            difficulty=3, exam_weight=0.6,
        ))
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def _capture(monkeypatch):
    import llm_provider

    prov = _CaptureProvider()
    monkeypatch.setattr(llm_provider, "get_provider", lambda: prov)
    monkeypatch.setattr(llm_provider, "_provider", None)
    return prov


def _set_egress(user_id: str, enabled: bool) -> None:
    db = SessionLocal()
    try:
        row = db.get(SettingsORM, user_id)
        if row is None:
            db.add(SettingsORM(
                user_id=user_id,
                ai_weight_tuning_enabled=True,
                send_text_to_ai=False,
                knowledge_ai_egress_enabled=enabled,
                community_consent_enabled=False,
                community_auto_participate=True,
            ))
        else:
            row.knowledge_ai_egress_enabled = enabled
        db.commit()
    finally:
        db.close()


def _search(**kw) -> dict:
    body: dict = {"subject": "SX", "rawText": QUESTION}
    body.update(kw)
    r = client.post("/api/v1/search-archives", json=body, headers=HDR)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# 一、出域红线
# ---------------------------------------------------------------------------

def test_knowledge_raw_still_denied():
    """知识点库原始素材永不出域——放宽 user_error_content 没有顺带放开它。"""
    with pytest.raises(EgressViolation):
        Guard.check({"rawText": "题库爬来的题面", "definition": "教材原文"}, KNOWLEDGE_RAW)


def test_user_error_content_allows_own_question():
    """用户当场输入的题面：允许（白名单内的题面字段）。"""
    payload = {
        "subject": "SX",
        "rawText": QUESTION,
        "studentAnswer": "x>1",
        "correctAnswer": "x<1",
        "errorNote": "符号弄反了",
    }
    assert Guard.check(dict(payload), USER_ERROR_CONTENT) == payload


def test_user_error_content_still_has_whitelist():
    """放宽不等于全放：白名单外的字段照样拒（误传知识点库素材字段会被挡下）。"""
    with pytest.raises(EgressViolation):
        Guard.check({"rawText": QUESTION, "definition": "教材定义"}, USER_ERROR_CONTENT)
    with pytest.raises(EgressViolation):
        Guard.check({"rawText": QUESTION, "vector": [0.1, 0.2]}, USER_ERROR_CONTENT)


def test_embedding_of_user_content_never_offdomain():
    """错题/学习记录的 embedding 必须本地——这条红线与本次放宽无关，回归守住。"""
    from egress_guard import EMBED_SRC_USER, assert_embed_source_offdomain_allowed

    with pytest.raises(EgressViolation):
        assert_embed_source_offdomain_allowed(EMBED_SRC_USER)


# ---------------------------------------------------------------------------
# 二、开关：关着就一个字都不出去
# ---------------------------------------------------------------------------

def test_egress_off_sends_no_raw_text(_point, _capture):
    """开关关闭（默认）→ 题面不出现在发给模型的 prompt 里。"""
    _set_egress(HDR["X-User-ID"], enabled=False)
    item = _search()

    assert _capture.prompts, "应当调用过一次模型"
    prompt = _capture.prompts[0]
    assert "x^2-2x" not in prompt, f"题面泄漏到 prompt：{prompt}"
    assert _capture.contexts[0]["data_class"] == "knowledge_aggregated"
    # 归档照常落库，功能不因合规降级而不可用
    assert item["rawText"] == QUESTION
    assert item["solution"]


def test_egress_on_sends_raw_text_and_logs(_point, _capture):
    """开关打开 → 题面可出域，且**留痕**（用户 / 内容类型 / 时间）。"""
    _set_egress(HDR["X-User-ID"], enabled=True)

    # 本套件的 logging 插件未启用（caplog 不可用），手动挂一个采集器
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collect()
    egress_logger = logging.getLogger("egress")
    egress_logger.addHandler(handler)
    prev = egress_logger.level
    egress_logger.setLevel(logging.INFO)
    try:
        _search()
    finally:
        egress_logger.removeHandler(handler)
        egress_logger.setLevel(prev)

    assert _capture.prompts[0].count("x^2-2x") >= 1
    ctx = _capture.contexts[0]
    assert ctx["data_class"] == USER_ERROR_CONTENT

    allowed = [r for r in records if "[EGRESS][ALLOW]" in r.getMessage()]
    assert allowed, "出域未留痕"
    msg = allowed[0].getMessage()
    assert HDR["X-User-ID"] in msg, "留痕缺少用户"
    assert USER_ERROR_CONTENT in msg, "留痕缺少内容类型"
    assert allowed[0].created is not None, "留痕缺少时间"


def test_only_direct_mode_needs_raw_text(_point, _capture):
    """「能走聚合就走聚合」：解析式/引导式不依赖题面数值，不开开关也不发题面。"""
    _set_egress(HDR["X-User-ID"], enabled=True)
    _search(mode="analytic")
    assert _capture.contexts[-1]["data_class"] == "knowledge_aggregated"
    assert "x^2-2x" not in _capture.prompts[-1]

    _search(mode="guided")
    assert _capture.contexts[-1]["data_class"] == "knowledge_aggregated"


def test_no_settings_row_means_off(_point, _capture):
    """查不到设置行 = 关闭（默认保守，绝不因为读不到就放行）。"""
    _search()
    assert _capture.contexts[0]["data_class"] == "knowledge_aggregated"


# ---------------------------------------------------------------------------
# 三、加固 ①：只绑定用户即时动作
# ---------------------------------------------------------------------------

def test_search_route_has_no_background_path():
    """按 AST 扫源码：搜题链路不得出现后台任务 / 预生成 / 定时入口。

    用 AST 而不是字符串包含：文件头注释里**必须**解释这条规则（会提到
    BackgroundTasks 字样），字符串扫描会把注释本身判成违规——那就成了
    「越认真写注释越不过」，规则反而没人敢写清楚。
    """
    import ast

    tree = ast.parse(_SEARCH_ROUTE_SRC)

    imported_or_used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_or_used.update(a.asname or a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported_or_used.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.Name):
            imported_or_used.add(node.id)
        elif isinstance(node, ast.Attribute):
            imported_or_used.add(node.attr)

    forbidden = {"BackgroundTasks", "BackgroundTask", "add_task", "apply_async", "cron", "apscheduler"}
    hits = sorted(forbidden & imported_or_used)
    assert not hits, f"搜题路由出现后台/定时入口，违反「每次点击即一次授权」：{hits}"


# ---------------------------------------------------------------------------
# 四、D24 三态
# ---------------------------------------------------------------------------

def test_mode_is_remembered(_point, _capture):
    """三态可切换且**被记忆**：第二次不传 mode 应沿用上次。"""
    _set_egress(HDR["X-User-ID"], enabled=False)
    first = _search(mode="analytic")
    assert first["mode"] == "analytic"

    second = _search()  # 不传 mode
    assert second["mode"] == "analytic", "未沿用上次选择"

    _search(mode="guided")
    assert _search()["mode"] == "guided"


def test_invalid_mode_rejected(_point):
    r = client.post(
        "/api/v1/search-archives",
        json={"subject": "SX", "rawText": QUESTION, "mode": "whatever"},
        headers=HDR,
    )
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "mode"


def test_empty_raw_text_rejected(_point):
    r = client.post(
        "/api/v1/search-archives",
        json={"subject": "SX", "rawText": "   "},
        headers=HDR,
    )
    assert r.status_code == 400


def test_knowledge_card_uses_frozen_protocol(_point, _capture):
    """结尾统一输出的知识点卡 = 冻结的 KnowledgeRef 四字段，且 mastery 是 null 不是 0。"""
    _set_egress(HDR["X-User-ID"], enabled=False)
    item = _search()
    assert item["pointIds"], "应当匹配到知识点"
    card = item["pointIds"][0]
    assert set(card) == {"pointId", "subjectCode", "name", "mastery"}, card
    assert card["mastery"] is None, "样本不足必须是 null，不能写成 0"


def test_archive_list_and_detail(_point, _capture):
    _set_egress(HDR["X-User-ID"], enabled=False)
    item = _search(mode="direct")
    lst = client.get("/api/v1/search-archives", headers=HDR).json()
    assert [i["archiveId"] for i in lst["items"]] == [item["archiveId"]]
    assert lst["pagination"]["total"] == 1

    one = client.get(f"/api/v1/search-archives/{item['archiveId']}", headers=HDR)
    assert one.status_code == 200
    assert one.json()["rawText"] == QUESTION

    filtered = client.get(
        "/api/v1/search-archives", params={"mode": "guided"}, headers=HDR
    ).json()
    assert filtered["items"] == []

    assert client.get("/api/v1/search-archives/sa_not_exist", headers=HDR).status_code == 404


def test_other_users_archive_invisible(_point, _capture):
    """归档按用户隔离，不能 A 搜到 B 的题面。"""
    _set_egress(HDR["X-User-ID"], enabled=False)
    item = _search()
    assert client.get(
        f"/api/v1/search-archives/{item['archiveId']}",
        headers={"X-User-ID": "u_someone_else"},
    ).status_code == 404


# ---------------------------------------------------------------------------
# 五、D52 讲解
# ---------------------------------------------------------------------------

def test_middle_school_constraint_in_prompts():
    """中学解法约束必须写进 prompt——超纲解法对中学考试无效且会误导。"""
    from routes.search import EXPLANATION_SYSTEM, SOLUTION_SYSTEM

    for p in (SOLUTION_SYSTEM, EXPLANATION_SYSTEM):
        assert "中学" in p
        assert "超纲" in p


def test_word_card_only_for_language_subjects():
    """查词卡模板只给语言类学科（语文/英语），理科题不硬塞。"""
    from routes.search import _build_solution_prompt

    assert "📇 查词卡" in _build_solution_prompt("direct", "题目", "YY")
    assert "📇 查词卡" in _build_solution_prompt("direct", "题目", "YW")
    assert "📇 查词卡" not in _build_solution_prompt("direct", "题目", "SX")


def test_explanation_two_modes_coexist(_point, _capture):
    """「回顾取原文」与「重新讲」并存：重生成不顶掉旧的。"""
    _capture.reply = "讲解正文 A"
    a = client.post(
        "/api/v1/explanations",
        json={"pointId": POINT_ID, "subject": "SX", "mode": "regenerated"},
        headers=HDR,
    )
    assert a.status_code == 201, a.text

    _capture.reply = "讲解正文 B"
    b = client.post(
        "/api/v1/explanations",
        json={"pointId": POINT_ID, "subject": "SX", "mode": "regenerated"},
        headers=HDR,
    )
    assert b.json()["explanationId"] != a.json()["explanationId"]

    # original 取回最近一条（B），不新生成
    before = len(_capture.prompts)
    orig = client.post(
        "/api/v1/explanations",
        json={"pointId": POINT_ID, "subject": "SX", "mode": "original"},
        headers=HDR,
    )
    assert orig.status_code == 200
    assert orig.json()["content"] == "讲解正文 B"
    assert orig.json()["mode"] == "regenerated"
    assert len(_capture.prompts) == before, "original 不该调模型"

    lst = client.get("/api/v1/explanations", headers=HDR).json()
    assert lst["pagination"]["total"] == 2, "两条都还在，没被顶掉"


def test_explanation_original_without_archive_is_404(_point):
    r = client.post(
        "/api/v1/explanations",
        json={"pointId": POINT_ID, "subject": "SX", "mode": "original"},
        headers=HDR,
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_curated_samples_distinguishable(_point):
    """精品样例（isCurated=true）与动态生成严格区分，可按标记过滤出来。"""
    db = SessionLocal()
    try:
        db.add(ExplanationORM(
            id="exp_cur_1", user_id=HDR["X-User-ID"], point_id=POINT_ID,
            subject="SX", mode="original", content="精品样例正文", is_curated=True,
        ))
        db.add(ExplanationORM(
            id="exp_dyn_1", user_id=HDR["X-User-ID"], point_id=POINT_ID,
            subject="SX", mode="regenerated", content="动态生成正文", is_curated=False,
        ))
        db.commit()
    finally:
        db.close()

    curated = client.get(
        "/api/v1/explanations", params={"isCurated": True}, headers=HDR
    ).json()
    dynamic = client.get(
        "/api/v1/explanations", params={"isCurated": False}, headers=HDR
    ).json()

    assert [i["explanationId"] for i in curated["items"]] == ["exp_cur_1"]
    assert curated["items"][0]["isCurated"] is True
    assert [i["explanationId"] for i in dynamic["items"]] == ["exp_dyn_1"]
    assert dynamic["items"][0]["isCurated"] is False


def test_curated_seed_script_has_3_to_5_samples():
    """pilot 要求 3–5 条精品样例，别写成一大坨。"""
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / "seed_curated_explanations.py"
    spec = importlib.util.spec_from_file_location("seed_curated_explanations", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert 3 <= len(mod.CURATED) <= 5, f"精品样例数量 {len(mod.CURATED)} 不在 3–5 之间"
    for subject, name, definition, content in mod.CURATED:
        assert subject and name and definition and content
        assert len(content) > 50, f"{name} 的讲解正文过短，撑不起「精品」"


def test_explanation_detail_and_isolation(_point):
    db = SessionLocal()
    try:
        db.add(ExplanationORM(
            id="exp_detail_1", user_id=HDR["X-User-ID"], point_id=POINT_ID,
            subject="SX", mode="original", content="内容", is_curated=True,
        ))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/explanations/exp_detail_1", headers=HDR)
    assert r.status_code == 200
    assert r.json()["content"] == "内容"

    assert client.get(
        "/api/v1/explanations/exp_detail_1",
        headers={"X-User-ID": "u_someone_else"},
    ).status_code == 404
