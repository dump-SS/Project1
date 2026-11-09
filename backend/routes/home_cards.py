"""首页推荐卡路由（D21/D28，契约 v1.21.0）。

- `GET /me/home-cards`：产三组卡（组顺序固定 Go on → 推荐 → 洞察，空组不返回）
- `POST /me/card-impressions`：上报 shown/clicked/dismissed（D28 冷却数据源）

产卡逻辑与冷却消费在 `home_cards.py`（规则模板为主、不调 LLM——产卡链路无
用户内容出域；口径卡 §三）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from home_cards import build_home_cards, record_impression
from schemas.card import CardImpressionCreate, CardImpressionOut, HomeCardGroupResult
from schemas.user import User
from .deps import current_user

router = APIRouter(prefix="/me", tags=["个性化建议"])


@router.get(
    "/home-cards",
    response_model=list[HomeCardGroupResult],
    summary="首页三组推荐卡（D21，Go on → 推荐 → 洞察）",
)
def get_home_cards(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[dict]:
    """用户私有三组卡；无内容的组不返回（宁缺毋滥）。"""
    return build_home_cards(db, user.user_id)


@router.post(
    "/card-impressions",
    response_model=CardImpressionOut,
    status_code=status.HTTP_201_CREATED,
    summary="上报卡片展示 / 点击 / 划掉事件（D28 冷却数据源）",
)
def create_card_impression(
    payload: CardImpressionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CardImpressionOut:
    """落一行事件：id / createdAt 服务端生成；shownAt 可选（缺省记请求时刻）。"""
    row = record_impression(db, user.user_id, payload)
    return CardImpressionOut.model_validate({
        "id": row.id,
        "group": row.group,
        "cardType": row.card_type,
        "fingerprint": row.fingerprint,
        "action": row.action,
        "shownAt": row.shown_at,
        "createdAt": row.created_at,
    })
