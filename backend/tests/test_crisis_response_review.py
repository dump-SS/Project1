"""危机响应评审机制（G 板块一期 · pilot-metrics §5 第 1 项）。

【只测不改】本文件只验证 backend/safety_filter.py 的现状召回，不修改其召回逻辑。
扩召回会引入误报，误报率需真实 Chat 数据校准，属 X0 决策；已知缺口以
xfail(strict=True) 显式挂牌——将来扩召回使缺口用例转绿时，strict xfail 会让
套件变红，强制摘牌并复评，缺口不允许静默消失。

产出（供评审记录 docs/pilot-crisis-review-template.md 使用）：
- 召回率 = 命中正例 / 全部正例（含已知缺口，按触发类别分组输出）
- 误报率 = 误报负例 / 全部负例（必须为 0：出现任何误报本测试直接判红）

依赖说明：用例集为 YAML；venv 里已有 PyYAML 6.0.3（传递依赖，本次未新增任何
声明依赖）。PyYAML 缺席的环境回退到内置迷你解析器（只支持用例集的固定子集，
子集之外的形状直接报错——宁可红不可错）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from safety_filter import CRISIS_RESPONSE, is_crisis_signal

CASES_PATH = Path(__file__).parent / "data" / "crisis_cases.yaml"
TXT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "crisis_response.txt"


# ---------------------------------------------------------------------------
# 用例集加载
# ---------------------------------------------------------------------------


def _scalar(value: str) -> str | bool:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    if value in ("true", "false"):
        return value == "true"
    return value


def _mini_yaml_cases(raw: str) -> list[dict]:
    """PyYAML 缺席时的兜底解析器：只认本用例集的固定子集
    （cases: 列表；`- key: value` 起头、`key: value` 续行；值不含 ASCII 冒号）。
    子集之外的任何结构直接抛错，不做猜测。"""
    cases: list[dict] = []
    current: dict | None = None
    in_cases = False
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "cases:":
            in_cases = True
            continue
        if not in_cases:
            continue
        first = re.match(r"^- (\w+): (.*)$", stripped)
        if first:
            current = {first.group(1): _scalar(first.group(2))}
            cases.append(current)
            continue
        rest = re.match(r"^(\w+): (.*)$", stripped)
        if rest and current is not None:
            current[rest.group(1)] = _scalar(rest.group(2))
            continue
        raise ValueError(f"用例集出现迷你解析器不支持的结构：{line!r}")
    if not cases:
        raise ValueError("用例集为空或结构不被识别")
    return cases


def _load_cases() -> list[dict]:
    raw = CASES_PATH.read_text(encoding="utf-8")
    try:
        import yaml  # venv 已有（传递依赖），不构成新增依赖
    except ImportError:
        return _mini_yaml_cases(raw)
    data = yaml.safe_load(raw)
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError("用例集缺少 cases 列表")
    return data["cases"]


CASES = _load_cases()
POSITIVE = [c for c in CASES if c["expect"]]
NEGATIVE = [c for c in CASES if not c["expect"]]


def _parametrize_args(cases: list[dict]) -> list:
    args: list = []
    for case in cases:
        if case["known_gap"]:
            args.append(
                pytest.param(
                    case,
                    id=case["id"],
                    marks=pytest.mark.xfail(
                        reason=f"召回缺口（待 X0 决策）：{case['note']}",
                        strict=True,
                    ),
                )
            )
        else:
            args.append(pytest.param(case, id=case["id"]))
    return args


# ---------------------------------------------------------------------------
# 逐条断言
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _parametrize_args(POSITIVE))
def test_l3_should_refer(case: dict):
    """正例：按基线应转介 L3（固定文案）。known_gap 用例当前必漏（strict xfail）。"""
    assert is_crisis_signal(case["text"]) is True


@pytest.mark.parametrize("case", _parametrize_args(NEGATIVE))
def test_l3_should_not_refer(case: dict):
    """负例：L1 / L2 未到 L3 / 学习类误伤，不得触发危机转介（任何误报都是红线）。"""
    assert is_crisis_signal(case["text"]) is False


# ---------------------------------------------------------------------------
# 汇总：召回率 / 误报率（数字同步进 docs/pilot-crisis-review-template.md 第 0 号记录）
# ---------------------------------------------------------------------------


def test_review_summary_recall_and_false_positive_rate():
    hits = [c["id"] for c in POSITIVE if is_crisis_signal(c["text"])]
    misses = [c["id"] for c in POSITIVE if not is_crisis_signal(c["text"])]
    false_positives = [c["id"] for c in NEGATIVE if is_crisis_signal(c["text"])]

    recall = len(hits) / len(POSITIVE)
    fp_rate = len(false_positives) / len(NEGATIVE)

    lines = [f"[危机响应评审] 召回率 {len(hits)}/{len(POSITIVE)} = {recall:.0%}"]
    for category in dict.fromkeys(c["category"] for c in POSITIVE):
        group = [c for c in POSITIVE if c["category"] == category]
        hit_n = sum(1 for c in group if is_crisis_signal(c["text"]))
        lines.append(
            f"[危机响应评审]   {category}: {hit_n}/{len(group)} "
            f"{'✅' if hit_n == len(group) else '❌ 召回缺口'}"
        )
    lines.append(f"[危机响应评审] 误报率 {len(false_positives)}/{len(NEGATIVE)} = {fp_rate:.0%}")
    if misses:
        lines.append(f"[危机响应评审] 漏报用例（xfail 挂牌，待 X0 决策）：{'、'.join(misses)}")
    print("\n" + "\n".join(lines))

    # 误报是红线：现版 0 误报，将来扩召回若引入误报，这里必须红——
    # 「误报率需真实 Chat 数据校准」正是要交回 X0 的决策点。
    assert fp_rate == 0, f"危机检测出现误报（直接判红，扩召回需 X0 校准）：{false_positives}"


# ---------------------------------------------------------------------------
# 一致性断言：两处各写一份的 L3 固定文案不得静默漂移
# ---------------------------------------------------------------------------


def _l3_copy_from_txt() -> str:
    """从 crisis_response.txt 解析「L3 固定转介文案」——文案本体不得硬编码进测试。"""
    collected: list[str] = []
    in_section = False
    for line in TXT_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_section = stripped.startswith("# L3 固定转介文案")
            continue
        if in_section and stripped:
            collected.append(stripped)
    assert collected, "crisis_response.txt 里找不到「L3 固定转介文案」一节"
    return "".join(collected)


def test_l3_fixed_copy_matches_safety_filter():
    """safety_filter.CRISIS_RESPONSE 必须与基线 txt 的 L3 固定文案逐字一致。

    两处各写一份、没有断言保护就会静默漂移（派发单指出的缺口②）。
    """
    assert CRISIS_RESPONSE == _l3_copy_from_txt(), (
        "safety_filter.CRISIS_RESPONSE 与 crisis_response.txt 的 L3 固定转介文案"
        "出现漂移：改文案必须两处同步（或经评审改基线后同步实现）"
    )
