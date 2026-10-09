"""治理服务层（违规分级处置 / 奖章 / 埋点）——G 板块。

给其他板块的进程内调用入口（跨板块只走协议，不直连 G 的表）：
- B：输入侧破甲/滥用检测命中 → record_violation（#43 分级处置）；
     Chat 请求入口 → get_active_sanction 判禁（临时封禁期内拒绝 AI 功能）。
- B：上下文栈/画像提取事件 → track_event（D39 chat_interaction / profile_trace）。
- C/E：里程碑事件（首次记录、连续 7 天、首个复盘、首个目标达成）→ award_milestone（#49）。

写失败一律吞掉（治理是辅助能力，绝不阻断业务主流程，PRD 8.2）。
所有写入与 models/governance.py 的口径一致；事件 payload 入库前经 privacy_filter 脱敏。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

__all__ = [
    "TEMP_BAN_HOURS",
    "MEDAL_MILESTONES",
    "VIOLATION_ACTIONS",
    "ANALYTICS_CATEGORIES",
    "record_violation",
    "get_active_sanction",
    "award_milestone",
    "track_event",
]

# #43：1 次警告 → 3 次临时封禁 → 永久。临时封禁时长拍板口径未给，
# pilot 内部定为 24h（如运营要改，这里一处改）。
TEMP_BAN_HOURS = 24

MEDAL_MILESTONES = {
    "first_record",
    "streak_7_days",
    "first_summary",
    "first_goal_achieved",
    "first_topic_book",
}

VIOLATION_ACTIONS = {"warn", "temp_ban", "perm_ban"}

ANALYTICS_CATEGORIES = {"chat_interaction", "ai_quality", "profile_trace"}


def _new_db():
    from database import SessionLocal

    return SessionLocal()


def _ladder_action(count: int) -> str:
    """累计违规次数 → 处置动作。1=警告；2–3=临时封禁；≥4=永久。"""
    if count <= 1:
        return "warn"
    if count <= 3:
        return "temp_ban"
    return "perm_ban"


def record_violation(user_id: str, reason: str, db=None) -> dict | None:
    """记录一次违规并按阶梯升级处置（#43：必须留痕）。

    reason 只放命中类型（如「破甲诱导」「滥用滥用输出」），**不含用户原文**。
    返回 {"level", "action", "created_at"}；失败返回 None（不阻断业务）。
    """
    own = db is None
    if own:
        db = _new_db()
    try:
        from models.governance import ViolationLog

        count = (
            db.query(ViolationLog)
            .filter(ViolationLog.user_id == user_id)
            .count()
        )
        level = count + 1
        action = _ladder_action(level)
        row = ViolationLog(
            id=f"vl_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            level=level,
            action=action,
            reason=(reason or "unknown")[:256],
        )
        db.add(row)
        db.commit()
        logger.info("[governance] 违规处置留痕 user=%s level=%d action=%s", user_id, level, action)
        return {"level": level, "action": action, "created_at": row.created_at}
    except Exception as e:  # noqa: BLE001 — 留痕失败绝不阻断业务
        logger.debug("[governance] 违规留痕写入失败（已忽略）: %s", e)
        if own:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        return None
    finally:
        if own:
            db.close()


def get_active_sanction(user_id: str, db=None) -> dict | None:
    """查当前生效的封禁状态。

    返回 None = 无生效处置；否则 {"action": "temp_ban"|"perm_ban", "until": datetime|None}。
    temp_ban 自最近一次该级处置起 TEMP_BAN_HOURS 内生效；perm_ban 永久。
    B 板块在 AI 功能入口调用：生效中 → 403（GUARDIAN/封禁语义按契约错误码）。
    """
    own = db is None
    if own:
        db = _new_db()
    try:
        from models.governance import ViolationLog

        row = (
            db.query(ViolationLog)
            .filter(
                ViolationLog.user_id == user_id,
                ViolationLog.action.in_(["temp_ban", "perm_ban"]),
            )
            # 同秒内多次违规 created_at 相同（SQLite 秒级精度），用 level 定序：
            # 阶梯单调递增，最高 level 即最新处置状态
            .order_by(ViolationLog.created_at.desc(), ViolationLog.level.desc())
            .first()
        )
        if row is None:
            return None
        if row.action == "perm_ban":
            return {"action": "perm_ban", "until": None}
        until = row.created_at + timedelta(hours=TEMP_BAN_HOURS)
        if datetime.utcnow() < until:
            return {"action": "temp_ban", "until": until}
        return None
    except Exception as e:  # noqa: BLE001 — 查询失败按无处置放行（业务优先）
        logger.debug("[governance] 封禁查询失败（按无处置）: %s", e)
        return None
    finally:
        if own:
            db.close()


def award_milestone(user_id: str, milestone: str, db=None) -> dict | None:
    """授予里程碑奖章（#49 最小版）。同里程碑幂等（唯一约束），重复授予返回 None。"""
    if milestone not in MEDAL_MILESTONES:
        logger.warning("[governance] 非法里程碑 %r，拒绝授予", milestone)
        return None
    own = db is None
    if own:
        db = _new_db()
    try:
        from models.governance import Medal
        from sqlalchemy.exc import IntegrityError

        exists = (
            db.query(Medal)
            .filter(Medal.user_id == user_id, Medal.milestone == milestone)
            .first()
        )
        if exists is not None:
            return None
        row = Medal(
            id=f"md_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            milestone=milestone,
        )
        db.add(row)
        db.commit()
        logger.info("[governance] 奖章授予 user=%s milestone=%s", user_id, milestone)
        # 注意 ORM 列名是 awarded_at（不是 created_at）
        return {"medal_id": row.id, "milestone": milestone, "awarded_at": row.awarded_at}
    except Exception as e:  # noqa: BLE001 — 奖章失败绝不阻断业务
        logger.debug("[governance] 奖章写入失败（已忽略）: %s", e)
        if own:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        return None
    finally:
        if own:
            db.close()


def _sanitize_payload(payload: dict | None) -> str | None:
    """payload 结构化脱敏：字符串值过 privacy_filter，非法 JSON 数据丢弃。

    D39 口径：payload 不含对话原文流水；身份只走 user_id 列，不进 payload。
    """
    if not isinstance(payload, dict):
        return None
    try:
        from privacy_filter import sanitize_text

        cleaned: dict = {}
        for k, v in payload.items():
            if isinstance(v, str):
                cleaned[str(k)[:64]] = sanitize_text(v)
            elif isinstance(v, (int, float, bool)) or v is None:
                cleaned[str(k)[:64]] = v
            else:
                # 复杂结构（list/dict）：只保留 JSON 可序列化且整体脱敏后长度可控的
                cleaned[str(k)[:64]] = sanitize_text(json.dumps(v, ensure_ascii=False))[:512]
        return json.dumps(cleaned, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 — 埋点失败绝不阻断业务
        logger.debug("[governance] 埋点 payload 脱敏失败（丢弃 payload）: %s", e)
        return None


def track_event(
    user_id: str,
    category: str,
    event_type: str,
    session_id: str | None = None,
    payload: dict | None = None,
    occurred_at: datetime | None = None,
    db=None,
) -> str | None:
    """写一条结构化埋点事件（D39）。返回事件 id，失败返回 None。

    category 必须是三块之一；event_type ≤64 字符。
    payload 入库前脱敏（_sanitize_payload），不含对话原文流水。
    """
    if category not in ANALYTICS_CATEGORIES:
        logger.warning("[governance] 非法埋点类别 %r，丢弃", category)
        return None
    own = db is None
    if own:
        db = _new_db()
    try:
        from models.analytics import AnalyticsEvent

        eid = f"ae_{uuid.uuid4().hex[:12]}"
        row = AnalyticsEvent(
            id=eid,
            user_id=user_id,
            category=category,
            event_type=(event_type or "unknown")[:64],
            session_id=session_id,
            payload_json=_sanitize_payload(payload),
            occurred_at=occurred_at or datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        return eid
    except Exception as e:  # noqa: BLE001 — 埋点失败绝不阻断业务
        logger.debug("[governance] 埋点写入失败（已忽略）: %s", e)
        if own:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        return None
    finally:
        if own:
            db.close()
