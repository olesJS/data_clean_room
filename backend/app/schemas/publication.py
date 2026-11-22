"""Pydantic schemas for the publication gate (SCRUM-57, UC-07)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class PublishRequest(BaseModel):
    retention_until: dt.date = Field(
        ...,
        description="Date until which the published dataset may be retained",
        examples=["2027-12-31"],
    )


__all__ = ["PublishRequest"]
