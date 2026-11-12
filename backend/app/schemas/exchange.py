"""Pydantic schemas for the data exchange flow (SCRUM-56)."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import LegalBasisPurpose


class ExchangeRequestCreate(BaseModel):
    dataset_id: int = Field(..., gt=0)
    purpose: LegalBasisPurpose = Field(
        ...,
        description="Processing purpose; must match an active legal basis",
        examples=["analytics"],
    )


class ExchangeDecision(BaseModel):
    access_until: Optional[dt.date] = Field(
        default=None,
        description="Last day on which the clean version may be downloaded",
    )
    review_comment: Optional[str] = Field(default=None, max_length=500)

    @field_validator("access_until")
    @classmethod
    def access_until_not_in_past(cls, value: dt.date | None) -> dt.date | None:
        if value is not None and value < dt.date.today():
            raise ValueError("access_until must be today or in the future")
        return value


class ExchangeReject(BaseModel):
    review_comment: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Why the request was rejected",
    )


class ExchangeRequestResponse(BaseModel):
    id: int
    dataset_id: int
    dataset_name: str
    dataset_version_id: Optional[int] = None
    requester_id: int
    requester_email: str
    reviewer_id: Optional[int] = None
    reviewer_email: Optional[str] = None
    status: str
    purpose: str
    requested_at: dt.datetime
    decided_at: Optional[dt.datetime] = None
    review_comment: Optional[str] = None
    access_until: Optional[dt.date] = None
    downloaded_at: Optional[dt.datetime] = None
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "ExchangeDecision",
    "ExchangeReject",
    "ExchangeRequestCreate",
    "ExchangeRequestResponse",
]
