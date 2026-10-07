"""CI 出域断言（红线，PRD 12.6 + 计划书 §8）：
错题原文/作答/答案/自述错因/检索片段原文/embedding 向量 永不出现在出域 payload。

覆盖：
1. EgressGuard 黑名单字段（rawText/studentAnswer/correctAnswer/errorNote/...）
2. knowledge_raw data_class 整体拒绝
3. 错题全流程产生的出域 payload 不夹带原文字段（端到端抓 provider 入参）
4. **embedding 侧出域**：用户内容的 embed_text 调用点必须显式声明
   ``source=EMBED_SRC_USER``；漏声明就可能被当成知识库出域。
   本条用 AST 静态扫描源码，**新增调用点忘标会直接挂 CI**。
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from egress_guard import EGRESS_BLOCKED_FIELD_NAMES, EgressViolation, Guard, KNOWLEDGE_AGGREGATED, KNOWLEDGE_RAW

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
ROUTES_DIR = BACKEND_ROOT / "routes"


RAW_FIELDS = [
    "rawText", "raw_text", "studentAnswer", "student_answer",
    "correctAnswer", "correct_answer", "errorNote", "error_note",
    "questionText", "question_text", "errorSummary", "error_summary",
    "note", "description", "vector", "embedding",
]


def test_all_raw_fields_are_blocked():
    assert set(RAW_FIELDS) <= set(EGRESS_BLOCKED_FIELD_NAMES)


def test_knowledge_raw_whole_class_rejected():
    with pytest.raises(EgressViolation, match="knowledge_raw 禁止出域"):
        Guard.check({"studentAnswer": "x=1"}, KNOWLEDGE_RAW)


def test_errorbook_aggregated_payload_has_no_raw():
    """错题归因出域 payload（模拟）只含白名单字段，杜绝原文串入。"""
    agg = {
        "pointName": "函数单调性",
        "pointDefinition": "随自变量增减的性质",
        "errorCandidates": ["概念不清", "计算失误"],
    }
    # 白名单校验通过
    assert Guard.check(agg, KNOWLEDGE_AGGREGATED) == agg


def test_errorbook_aggregated_payload_with_raw_rejected():
    """试图把 rawText 塞进出域 payload → 直接拒绝。"""
    with pytest.raises(EgressViolation):
        Guard.check(
            {
                "pointName": "函数",
                "rawText": "求 f(x) 的极值（不该出域）",
            },
            KNOWLEDGE_AGGREGATED,
        )


def test_nested_vector_embedding_rejected():
    """向量字段（embedding）也不许出现在出域 payload。"""
    with pytest.raises(EgressViolation):
        Guard.check(
            {"errorCandidates": ["粗心"], "meta": {"embedding": [0.1, 0.2, 0.3]}},
            KNOWLEDGE_AGGREGATED,
        )


# ---------------------------------------------------------------------------
# embedding 侧：错题原文永不出域（M3 验收门）
# ---------------------------------------------------------------------------

# 允许省略 source 的白名单：只有知识库链路可以。
# 理由：知识库内容是编者提供的公开数据，出域是既定决策；且现网知识库索引由外部
# 模型（EMBED_MODEL=embedding-3，1024 维）建成，与本地 bge（512 维）**不在同一
# 向量空间**，强行改本地会让召回彻底失效。错题/学习记录则**必须**显式标注。
_KB_ONLY_OK = {"knowledge_kb.py"}


def _read(path: pathlib.Path) -> str:
    # utf-8-sig：部分 routes 文件带 BOM，ast.parse 不接受 U+FEFF，但 import 机制吃得下。
    return path.read_bytes().decode("utf-8-sig")


def _embed_text_calls() -> list[tuple[str, int, bool]]:
    """扫 routes/ 下所有 embed_text(...) 调用点 → (文件, 行号, 是否显式标 source)。"""
    found: list[tuple[str, int, bool]] = []
    for path in sorted(ROUTES_DIR.glob("*.py")):
        tree = ast.parse(_read(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "embed_text"):
                continue
            has_source = any(kw.arg == "source" for kw in node.keywords)
            found.append((path.name, node.lineno, has_source))
    return found


def test_embed_text_call_sites_exist():
    """防扫描器自身失效：调用点集合不该是空的。"""
    assert _embed_text_calls(), "routes/ 下没扫到 embed_text 调用——扫描逻辑坏了"


def test_user_content_embed_calls_declare_source():
    """🔴 除知识库链路外，所有 embed_text 调用点必须显式声明 source。"""
    offenders = [
        f"{name}:{line}"
        for name, line, has_source in _embed_text_calls()
        if not has_source and name not in _KB_ONLY_OK
    ]
    assert not offenders, (
        "这些 embed_text 调用点没声明 source，可能把用户内容按知识库出域："
        + "、".join(offenders)
    )


def test_error_book_call_site_is_user_scope():
    """错题本写入侧必须声明 EMBED_SRC_USER。"""
    tree = ast.parse(_read(ROUTES_DIR / "error_book.py"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "embed_text"):
            continue
        src = next((kw.value for kw in node.keywords if kw.arg == "source"), None)
        assert isinstance(src, ast.Name) and src.id == "EMBED_SRC_USER", (
            f"error_book.py:{node.lineno} 的 embed_text 未使用 EMBED_SRC_USER"
        )


# ---------------------------------------------------------------------------
# LLM 调用侧：每个出域调用点必须显式声明 data_class
# ---------------------------------------------------------------------------
#
# 为什么这条要单独守：llm_provider._enforce_egress 对 **data_class=None 直接放行**
# （向后兼容板块一历史调用）。于是「忘了声明」不会报错，只会静默出域——
# 且因为没声明 egress_fields，白名单校验也不跑。曾经就有过实例的：
# routes/knowledge.py 的 error-parse 是 P0 整改过的接口，却因 context 里
# 既没 data_class 也没 egress_fields，整改后的校验**从未真正执行**。
#
# 所以这里用 AST 静态扫全仓：**新增调用点漏声明会直接挂 CI**。

# data_class 的合法取值（knowledge_raw 声明了也会被拒，但好过不声明）
_DECLARED_CLASSES = {"state_plan", "knowledge_aggregated", "knowledge_raw", "user_error_content"}

# 默认按 state_plan 放行的历史调用：这些文件属于板块一，改动需 B 板块确认，
# 暂不强制（列出即留痕，别让豁免变成隐形）
_LEGACY_NO_DECLARE_OK: set[str] = set()

# data_class 走变量、静态无法直接读值的调用点。
# 必须**逐条写明理由**，且下面有断言校验「清单里的每一项都还真实存在」——
# 一旦代码改了、调用点消失，豁免项就会报错，逼人回来删掉，防止豁免越积越多。
_DYNAMIC_DECLARE_OK: dict[str, str] = {
    "routes/search.py": (
        "data_class 由 build_search_payload() 按出域开关返回，只能是 "
        "user_error_content 或 knowledge_aggregated 两者之一；取值集合本身由 "
        "test_search_egress.py 的开关用例覆盖（关→聚合、开→user_error_content）"
    ),
}


def _llm_generate_calls() -> list[tuple[str, int, str | None]]:
    """扫整个 backend 下所有 `*.generate(...)` 调用点 → (相对路径, 行号, data_class)。"""
    found: list[tuple[str, int, str | None]] = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        rel = path.relative_to(BACKEND_ROOT)
        if rel.parts[0] in {"tests", ".pytest_data", "alembic", "versions_archive"}:
            continue
        if path.name.startswith("_"):
            continue
        try:
            tree = ast.parse(_read(path))
        except (SyntaxError, UnicodeDecodeError):  # 非源码/编码异常文件跳过
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "generate"):
                continue
            # context 可能走关键字，也可能走第二个位置参数（ai_suggestion.py 就两种都有）
            ctx = next((kw.value for kw in node.keywords if kw.arg == "context"), None)
            if ctx is None and len(node.args) >= 2:
                ctx = node.args[1]
            if ctx is None:
                found.append((str(rel), node.lineno, None))
                continue
            if not isinstance(ctx, ast.Dict):
                # 动态拼装的 context 无法静态判定，留给人工评审
                found.append((str(rel), node.lineno, "<dynamic>"))
                continue
            dc = None
            for k, v in zip(ctx.keys, ctx.values):
                if isinstance(k, ast.Constant) and k.value == "data_class":
                    dc = v.value if isinstance(v, ast.Constant) else "<dynamic>"
            found.append((str(rel), node.lineno, dc))
    return found


def test_llm_generate_call_sites_exist():
    """防扫描器自身失效：调用点集合不该是空的。"""
    assert len(_llm_generate_calls()) >= 8, (
        f"只扫到 {len(_llm_generate_calls())} 个 generate 调用点——扫描逻辑坏了"
    )


def _normalize(path: str) -> str:
    """Windows 反斜杠 → 正斜杠，保证豁免表在两套路径分隔符下都能命中。"""
    return path.replace("\\", "/")


def test_every_llm_call_declares_data_class():
    """🔴 每个 LLM 出域调用点必须显式声明 data_class（漏声明 = provider 层静默放行）。"""
    offenders = [
        f"{path}:{line}"
        for path, line, dc in _llm_generate_calls()
        if dc is None and _normalize(path) not in _LEGACY_NO_DECLARE_OK
    ]
    dynamic_unregistered = [
        f"{path}:{line}"
        for path, line, dc in _llm_generate_calls()
        if dc == "<dynamic>" and _normalize(path) not in _DYNAMIC_DECLARE_OK
    ]
    assert not offenders, (
        "这些 generate 调用点没声明 data_class，provider 层会直接放行、白名单一律不校验："
        + "、".join(offenders)
    )
    assert not dynamic_unregistered, (
        "这些调用点的 data_class 是动态值、静态无法判定，"
        "必须在 _DYNAMIC_DECLARE_OK 里显式登记并写明理由：" + "、".join(dynamic_unregistered)
    )


def test_dynamic_exemptions_are_still_real():
    """豁免表不能变成永久死角：清单里的文件若已无动态调用点，说明该删了。"""
    dynamic_files = {
        _normalize(p) for p, _l, dc in _llm_generate_calls() if dc == "<dynamic>"
    }
    stale = set(_DYNAMIC_DECLARE_OK) - dynamic_files
    assert not stale, (
        "这些豁免项已对不上任何调用点（代码改过了？），请从 _DYNAMIC_DECLARE_OK 删除："
        + "、".join(sorted(stale))
    )


def test_declared_data_classes_are_known():
    """声明了但不认识的值同样要挂——拼错一个字母就等于没声明。"""
    bad = [
        f"{path}:{line}={dc}"
        for path, line, dc in _llm_generate_calls()
        if dc not in (None, "<dynamic>") and dc not in _DECLARED_CLASSES
    ]
    assert not bad, "data_class 取值非法：" + "、".join(bad)


# ---------------------------------------------------------------------------
# 后台任务侧：用户内容不得走定时/后台批量出域（2026-09-30 拍板加固 ①）
# ---------------------------------------------------------------------------

def test_scheduled_llm_jobs_send_only_aggregated():
    """定时任务的 LLM 调用只允许发聚合字段，不许带任何用户内容。

    定时任务没有「用户当场点击」这个前提，所以**永远**不该出现
    user_error_content——它一旦出现就是「无授权批量外发」。
    """
    jobs_dir = BACKEND_ROOT / "jobs"
    assert jobs_dir.is_dir()
    offenders: list[str] = []
    for path in sorted(jobs_dir.glob("*.py")):
        tree = ast.parse(_read(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "generate"):
                continue
            ctx = next((kw.value for kw in node.keywords if kw.arg == "context"), None)
            if not isinstance(ctx, ast.Dict):
                offenders.append(f"{path.name}:{node.lineno} context 无法静态判定")
                continue
            dc = None
            for k, v in zip(ctx.keys, ctx.values):
                if isinstance(k, ast.Constant) and k.value == "data_class":
                    dc = v.value if isinstance(v, ast.Constant) else None
            if dc != "knowledge_aggregated":
                offenders.append(f"{path.name}:{node.lineno} data_class={dc!r}")
    assert not offenders, "定时任务出域类别不合规（只允许 knowledge_aggregated）：" + "、".join(offenders)


def test_error_parse_really_goes_through_guard():
    """运行时验证：error-parse 的出域必须真的经过 EgressGuard，而不是只在注释里守。

    这条的由来值得记着：该接口是 P0 整改产物，注释写着「由 EgressGuard 白名单强校验」，
    但 context 里既没 data_class 也没 egress_fields——provider 层对未声明直接放行，
    **整改后的校验从未真正执行过**。静态扫描只能证明「写了字面量」，
    这条从运行时证明「真的传到了 provider」。
    """
    from fastapi.testclient import TestClient

    import llm_provider
    from main import app

    captured: list[dict] = []

    class _Spy:
        def generate(self, prompt: str, context: dict | None = None) -> str | None:
            llm_provider._enforce_egress(prompt, context)
            captured.append(context or {})
            return "### 📌 错误定位\n测试"

    client = TestClient(app)
    # 打桩必须落在 _provider 单例上：routes/knowledge.py 是**顶层**
    # `from llm_provider import get_provider`，替换模块属性对已绑定的引用无效。
    # 而 get_provider() 在 _provider 非 None 时直接返回它，改单例才拦得住。
    orig = llm_provider._provider
    llm_provider._provider = _Spy()
    try:
        r = client.post(
            "/api/v1/error-parse",
            json={"errorId": "err_ci_probe"},
            headers={"X-User-ID": "u_egress_ci"},
        )
    finally:
        llm_provider._provider = orig

    assert r.status_code == 200, r.text
    assert captured, "error-parse 没有产生出域调用，用例前提不成立"
    ctx = captured[0]
    assert ctx.get("data_class") == "knowledge_aggregated", f"声明缺失或不对：{ctx}"
    assert "egress_fields" in ctx, "没传 egress_fields，白名单校验等于没跑"
