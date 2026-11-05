"""v1.19.0 · 全站时间字段时区修复的回归测试（P0：裸 UTC 被前端按本地解析差 8 小时）。

修复方式：schemas/common.APIModel 全站响应基座——通配校验器把 naive datetime
补成 UTC-aware，ser_json_tz='utc' 归一输出 Z 后缀。本测试锁住三个行为：

1. **naive（历史数据 / utcnow() 存量）→ 带时区后缀**——这是缺陷本体；
2. **aware UTC → 归一 Z**（不因机器本地时区漂移）；
3. **date 字段（非 datetime）不受影响**（planDate 仍是裸日期）。

时间字段的下游消费（前端 new Date('...Z')）依赖 Z 后缀——这两个断言失效
就等于 P0 缺陷复发。
"""
from __future__ import annotations

from datetime import datetime, timezone

from schemas.common import APIModel
from schemas.plan import Plan


def _plan_response(createdAt: str) -> Plan:
    return Plan.model_validate({
        "planId": "p_tz",
        "planDate": "2026-11-03",
        "availableMinutes": 60,
        "tasks": [{
            "taskId": "t_1", "subject": "SX", "topic": "口算",
            "estimatedMinutes": 30, "priority": 1, "status": "pending",
        }],
        "createdAt": createdAt,
    })


def test_naive_datetime_serializes_with_z_suffix():
    """裸 UTC（存量数据形态）必须发 Z 后缀——这是 P0 缺陷本体的回归锁。"""
    plan = _plan_response("2026-11-03T04:00:00")  # naive，实际是 UTC
    j = plan.model_dump_json(by_alias=True)
    assert '"createdAt":"2026-11-03T04:00:00Z"' in j
    # 反向锁：不带后缀的形态不允许再出现
    assert '"createdAt":"2026-11-03T04:00:00"' not in j


def test_aware_utc_datetime_normalized_to_z():
    """aware UTC 归一输出 Z（pydantic ser_json_tz），不随机器本地时区漂移。"""
    plan = _plan_response("2026-11-03T04:00:00Z")
    assert '"createdAt":"2026-11-03T04:00:00Z"' in plan.model_dump_json(by_alias=True)


def test_aware_non_utc_datetime_converted_to_utc_z():
    """带非 UTC 时区的输入归一到 UTC（+08:00 的 12 点 = UTC 04 点）。"""
    plan = _plan_response("2026-11-03T12:00:00+08:00")
    assert '"createdAt":"2026-11-03T04:00:00Z"' in plan.model_dump_json(by_alias=True)


def test_date_fields_untouched():
    """planDate 是 date 不是 datetime——仍为裸日期，不带任何时区记号。"""
    plan = _plan_response("2026-11-03T04:00:00Z")
    j = plan.model_dump_json(by_alias=True)
    assert '"planDate":"2026-11-03"' in j
    assert '"planDate":"2026-11-03Z"' not in j


def test_base_model_is_wildcard_validator_ready():
    """APIModel 的通配校验器对非 datetime 字段零影响（穿透返回原值）。"""
    class M(APIModel):
        name: str
        count: int

    m = M(name="x", count=3)
    assert m.name == "x" and m.count == 3


def test_timezone_aware_internal_values_not_silently_shifted():
    """aware 值只做时区归一（换表示），不改变绝对时刻。

    UTC 04:00 与 +08:00 12:00 是同一时刻——上两例已分别锁定表示形式；
    这里再从 datetime 对象层面锁「绝对时刻不变」，防止有人把归一误改成
    replace(tzinfo=utc)（那会平移 8 小时，恰好复刻本次要修的 bug）。
    """
    plan = _plan_response("2026-11-03T12:00:00+08:00")
    assert plan.created_at.tzinfo is not None
    assert plan.created_at.astimezone(timezone.utc).hour == 4
