"""权重管理与 AI 调权校验 — PRD 5.2 第 4 点。

核心规则（PRD 硬限制，必须在代码层强制校验，不依赖提示词约束）：
- alpha, beta ∈ [0.3, 0.7]，且 alpha + beta = 1
- 各子项权重 ∈ [0.1, 0.5]，同组归一化为 1
- 单次调整幅度上限：任一权重单次变动不超过 0.1
- 越界/非法/缺失/API 失败 → 回退到**当前权重**（不是初始值）
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import WeightConfig

# PRD 硬限制常量
ALPHA_BETA_MIN = 0.3
ALPHA_BETA_MAX = 0.7
SUB_WEIGHT_MIN = 0.1
SUB_WEIGHT_MAX = 0.5
MAX_SINGLE_DELTA = 0.1


@dataclass(frozen=True, slots=True)
class WeightAdjustment:
    """AI 模型返回的调权建议。"""
    alpha: float
    beta: float
    w1: float
    w2: float
    w3: float
    w4: float
    w5: float
    w6: float
    reason: str  # PRD 6.5：理由必须返回


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """校验结果。"""
    valid: bool
    new_weights: WeightConfig | None
    rejection_reason: str | None = None


def _in_range(value: float, lo: float, hi: float) -> bool:
    return lo - 1e-9 <= value <= hi + 1e-9


def _normalize_triple(a: float, b: float, c: float) -> tuple[float, float, float]:
    total = a + b + c
    if total == 0:
        return 1 / 3, 1 / 3, 1 / 3
    return a / total, b / total, c / total


def _check_delta(old: float, new: float, name: str) -> str | None:
    if abs(new - old) > MAX_SINGLE_DELTA + 1e-9:
        return f"{name} 变动 {abs(new - old):.4f} 超过单次上限 {MAX_SINGLE_DELTA}"
    return None


def validate_adjustment(
    current: WeightConfig,
    proposed: WeightAdjustment,
) -> ValidationResult:
    """校验 AI 返回的调权建议是否符合 PRD 硬限制。

    通过 → 返回归一化后的新权重。
    任一规则违反 → 回退到 current（PRD：一律回退到当前权重，不是初始值）。
    """
    errors: list[str] = []

    # 1. alpha/beta 区间
    if not _in_range(proposed.alpha, ALPHA_BETA_MIN, ALPHA_BETA_MAX):
        errors.append(f"alpha={proposed.alpha:.4f} 不在 [{ALPHA_BETA_MIN}, {ALPHA_BETA_MAX}]")
    if not _in_range(proposed.beta, ALPHA_BETA_MIN, ALPHA_BETA_MAX):
        errors.append(f"beta={proposed.beta:.4f} 不在 [{ALPHA_BETA_MIN}, {ALPHA_BETA_MAX}]")

    # 2. 子项区间
    for name, val in [("w1", proposed.w1), ("w2", proposed.w2), ("w3", proposed.w3),
                      ("w4", proposed.w4), ("w5", proposed.w5), ("w6", proposed.w6)]:
        if not _in_range(val, SUB_WEIGHT_MIN, SUB_WEIGHT_MAX):
            errors.append(f"{name}={val:.4f} 不在 [{SUB_WEIGHT_MIN}, {SUB_WEIGHT_MAX}]")

    # 3. 单次变动幅度
    for name, old, new in [
        ("alpha", current.alpha, proposed.alpha),
        ("beta", current.beta, proposed.beta),
        ("w1", current.w1, proposed.w1),
        ("w2", current.w2, proposed.w2),
        ("w3", current.w3, proposed.w3),
        ("w4", current.w4, proposed.w4),
        ("w5", current.w5, proposed.w5),
        ("w6", current.w6, proposed.w6),
    ]:
        err = _check_delta(old, new, name)
        if err:
            errors.append(err)

    if errors:
        return ValidationResult(
            valid=False,
            new_weights=None,
            rejection_reason="; ".join(errors),
        )

    # 4. 归一化：alpha+beta=1，同组子项归一化为 1
    alpha = proposed.alpha
    beta = 1.0 - alpha  # 强制 alpha+beta=1
    w1, w2, w3 = _normalize_triple(proposed.w1, proposed.w2, proposed.w3)
    w4, w5, w6 = _normalize_triple(proposed.w4, proposed.w5, proposed.w6)

    return ValidationResult(
        valid=True,
        new_weights=WeightConfig(
            alpha=round(alpha, 6),
            beta=round(beta, 6),
            w1=round(w1, 6),
            w2=round(w2, 6),
            w3=round(w3, 6),
            w4=round(w4, 6),
            w5=round(w5, 6),
            w6=round(w6, 6),
        ),
    )
