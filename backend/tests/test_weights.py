"""权重校验测试。"""

from state_engine.types import WeightConfig
from state_engine.weights import ValidationResult, WeightAdjustment, validate_adjustment


def test_valid_adjustment():
    """合法调权应通过校验。"""
    current = WeightConfig()
    proposed = WeightAdjustment(
        alpha=0.55, beta=0.45,
        w1=0.35, w2=0.30, w3=0.35,
        w4=0.40, w5=0.30, w6=0.30,
        reason="fatigue 信号增强，提高自评权重"
    )
    result = validate_adjustment(current, proposed)
    assert result.valid
    assert result.new_weights is not None
    # alpha + beta = 1
    assert abs(result.new_weights.alpha + result.new_weights.beta - 1.0) < 1e-6


def test_alpha_out_of_range():
    """alpha 超出 [0.3, 0.7] 应被拒绝。"""
    current = WeightConfig()
    proposed = WeightAdjustment(
        alpha=0.8, beta=0.2,
        w1=0.33, w2=0.33, w3=0.34,
        w4=0.33, w5=0.33, w6=0.34,
        reason="test"
    )
    result = validate_adjustment(current, proposed)
    assert not result.valid
    assert "alpha" in (result.rejection_reason or "")


def test_delta_exceeded():
    """单次变动超过 0.1 应被拒绝。"""
    current = WeightConfig(alpha=0.5, beta=0.5)
    proposed = WeightAdjustment(
        alpha=0.65, beta=0.35,  # delta = 0.15 > 0.1
        w1=0.33, w2=0.33, w3=0.34,
        w4=0.33, w5=0.33, w6=0.34,
        reason="test"
    )
    result = validate_adjustment(current, proposed)
    assert not result.valid
    assert "变动" in (result.rejection_reason or "")


def test_sub_weight_out_of_range():
    """子项权重超出 [0.1, 0.5] 应被拒绝。"""
    current = WeightConfig()
    proposed = WeightAdjustment(
        alpha=0.5, beta=0.5,
        w1=0.05, w2=0.45, w3=0.50,  # w1 < 0.1
        w4=0.33, w5=0.33, w6=0.34,
        reason="test"
    )
    result = validate_adjustment(current, proposed)
    assert not result.valid
    assert "w1" in (result.rejection_reason or "")


def test_normalization():
    """通过校验后子项应归一化为 1。"""
    current = WeightConfig()
    proposed = WeightAdjustment(
        alpha=0.5, beta=0.5,
        w1=0.30, w2=0.35, w3=0.35,
        w4=0.30, w5=0.40, w6=0.30,
        reason="test"
    )
    result = validate_adjustment(current, proposed)
    assert result.valid
    w = result.new_weights
    assert abs(w.w1 + w.w2 + w.w3 - 1.0) < 1e-6
    assert abs(w.w4 + w.w5 + w.w6 - 1.0) < 1e-6
