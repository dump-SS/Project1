"""危机检测第 2 层（语义兜底）行为测试 —— mock provider，确定性可重复。

对应 safety_filter.crisis_check 的第 2 层：只处理第 1 层漏掉、且命中 _SOFT_MARKERS
的残余形态。本文件验证五件事：
1. 第 1 层命中 → **不调用** LLM（确定性层零成本、零延迟）；
2. 软标记命中 + 模型判危机 → 转介（layer=l2_semantic，理由/类别留痕）；
3. 软标记命中 + 模型判非危机 → 放行（变体措辞靠语义层放行，不是靠放宽关键词）；
4. 兜底调用故障 / 输出不可解析 → **fail-toward-refer**（按危机处理）；
5. **误报保护**：用例集全部负例**都不进入兜底**（软标记刻意收紧）——
   即使 LLM 故障，普通倾诉也不会因兜底而被误报。

留痕断言：每次兜底调用写 ai_call_log（scene=crisis_check_l3）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import ai_call_log
import llm_provider
from safety_filter import crisis_check, detect_crisis, is_crisis_signal

CASES_PATH = Path(__file__).parent / "data" / "crisis_cases.yaml"


class FakeProvider:
    """伪 LLM provider：记录调用，按脚本返回或抛错。"""

    def __init__(self, reply: str | None = None, exc: Exception | None = None):
        self.reply = reply
        self.exc = exc
        self.calls: list[tuple[str, dict | None]] = []

    def generate(self, prompt: str, context: dict | None = None) -> str | None:
        self.calls.append((prompt, context))
        if self.exc is not None:
            raise self.exc
        return self.reply


@pytest.fixture()
def provider(monkeypatch):
    """安装伪 provider 并捕获 ai_call_log 调用。返回 (fake, log_records)。"""
    fake = FakeProvider()
    logs: list[tuple] = []
    monkeypatch.setattr(llm_provider, "get_provider", lambda: fake)
    monkeypatch.setattr(ai_call_log, "log_call", lambda ctx, ms, ok, err=None: logs.append((ctx, ms, ok, err)))
    return fake, logs


CRISIS_JSON = '{"crisis": true, "class": "③告别/交代后事/送物", "reason": "告别式表达"}'
NOT_CRISIS_JSON = '{"crisis": false, "class": null, "reason": "普通倾诉"}'


def _load_negative_texts() -> list[str]:
    import yaml

    data = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    return [c["text"] for c in data["cases"] if not c["expect"]]


# ── 1. 第 1 层命中不调用 LLM ──

def test_l1_hit_skips_llm(provider):
    fake, logs = provider
    d = crisis_check("我真的不想活了")
    assert d.is_crisis is True
    assert d.layer == "l1_deterministic"
    assert fake.calls == [], "第 1 层命中不应调用 LLM"
    assert logs == []


# ── 2. 软标记 + 模型判危机 → 转介（变体措辞的真缺口） ──

def test_soft_marker_variant_escalates(provider):
    fake, logs = provider
    fake.reply = CRISIS_JSON
    text = "最近总有种撑不住的感觉"  # 无第 1 层模式命中（「撑不下去了」才命中），但带软标记
    assert detect_crisis(text) is None, "该变体应漏出第 1 层（否则本用例失去意义）"
    d = crisis_check(text)
    assert d.is_crisis is True
    assert d.layer == "l2_semantic"
    assert d.cls is not None
    assert len(fake.calls) == 1
    assert fake.calls[0][1]["scene"] == "crisis_check_l3"
    assert len(logs) == 1 and logs[0][2] is True, "兜底调用应写 ai_call_log（留痕）"


# ── 3. 软标记 + 模型判非危机 → 放行 ──

def test_soft_marker_model_says_no(provider):
    fake, _ = provider
    fake.reply = NOT_CRISIS_JSON
    d = crisis_check("和这学期告别了，有点舍不得")
    assert d.is_crisis is False
    assert d.layer == "l2_semantic"
    assert len(fake.calls) == 1


# ── 4. 故障/坏输出 → fail-toward-refer ──

def test_provider_error_refers(provider):
    fake, logs = provider
    fake.exc = RuntimeError("provider down")
    d = crisis_check("感觉快撑不住了")
    assert d.is_crisis is True, "兜底故障必须按危机处理（fail-toward-refer）"
    assert d.layer == "l2_semantic"
    assert "fail-toward-refer" in (d.reason or "")
    assert len(logs) == 1 and logs[0][2] is False, "故障也要留痕（success=False）"


def test_malformed_output_refers(provider):
    fake, _ = provider
    fake.reply = "抱歉，我无法判断。"  # 非 JSON
    d = crisis_check("感觉快撑不住了")
    assert d.is_crisis is True
    assert "不可解析" in (d.reason or "")


# ── 5. 无软标记 → 不调用、不转介（成本与误报的双重保护） ──

def test_no_soft_marker_never_calls_llm(provider):
    fake, _ = provider
    d = crisis_check("今天学得有点累，想早点睡")
    assert d.is_crisis is False
    assert d.layer == "none"
    assert fake.calls == [], "无尖锐措辞不应调用 LLM"


def _has_soft_marker(text: str) -> bool:
    from safety_filter import _SOFT_MARKERS

    return any(w in text for w in _SOFT_MARKERS)


def test_plain_negatives_never_call_llm(provider):
    """无软标记的负例：第 1 层放行后直接返回，不进兜底——即使 LLM 故障也不误报。"""
    fake, _ = provider
    plain = [t for t in _load_negative_texts() if not _has_soft_marker(t)]
    assert len(plain) >= 5, "无软标记负例应占多数（软标记刻意收紧的体现）"
    for text in plain:
        assert is_crisis_signal(text) is False, f"负例被第 1 层误判：{text}"
        assert crisis_check(text).is_crisis is False, f"负例被误转介：{text}"
    assert fake.calls == [], "无软标记负例不应触发语义兜底调用"


def test_ambiguous_negatives_freed_by_semantic_layer(provider):
    """含软标记的歧义负例（学习语境/正常告别）：设计上就该交给语义层——
    第 1 层排除后路由到兜底，由模型放行。这验证「歧义不靠放宽关键词、靠语义层判别」。"""
    fake, _ = provider
    ambiguous = [t for t in _load_negative_texts() if _has_soft_marker(t)]
    assert ambiguous, "应存在歧义负例（否则本用例失去意义）"
    fake.reply = NOT_CRISIS_JSON
    for text in ambiguous:
        d = crisis_check(text)
        assert d.is_crisis is False, f"歧义负例应被语义层放行：{text}"
        assert d.layer == "l2_semantic"
    assert len(fake.calls) == len(ambiguous)
