"""Pydantic schemas for anonymisation and publication endpoints."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field


class AnonymizeRequest(BaseModel):
    methods: Optional[dict[str, str]] = Field(
        default=None,
        description=(
            "Optional per-column overrides: mask, generalize, hmac or redact"
        ),
        examples=[{"ipn": "hmac", "person_name": "mask"}],
    )


class PublishRequest(BaseModel):
    retention_until: dt.date = Field(
        ...,
        description="Date until which the published dataset may be retained",
        examples=["2027-12-31"],
    )


__all__ = ["AnonymizeRequest", "PublishRequest"]
