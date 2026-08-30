"""板块三群体参照 schema（M1-M3，对齐 openapi.yaml 板块三 schemas）。"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CommunityConsent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool
    auto_participate: bool = Field(default=True, alias="autoParticipate")
    updated_at: datetime = Field(..., alias="updatedAt")


class CommunityConsentUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool
    auto_participate: bool | None = Field(None, alias="autoParticipate")


class CommunityHistogramBucket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lo: float
    hi: float | None = None
    count: int


class CommunityAggregateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stage: str
    metric: str
    period: str
    pool_size: int = Field(..., alias="poolSize")
    percentiles: dict
    histogram: List[CommunityHistogramBucket]
    computed_at: datetime = Field(..., alias="computedAt")
