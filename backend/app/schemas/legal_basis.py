"""Pydantic v2 schemas for Legal Basis."""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.models import LegalBasisType


class LegalBasisCreate(BaseModel):
    """Schema for registering a new legal basis."""

    type: LegalBasisType = Field(
        ...,
        description="Type of legal ground: consent, contract, or law",
        examples=["consent"],
    )
    document_ref: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description=(
            "Reference or document number (e.g., contract #42, consent form ID)"
        ),
        examples=["DOC-2026-CONSENT-001"],
    )
    date: dt.date = Field(
        ...,
        description="Effective date of the legal basis (YYYY-MM-DD)",
        examples=["2026-10-24"],
    )


class LegalBasisResponse(BaseModel):
    """Schema for returning legal basis information."""

    id: str = Field(..., description="Unique UUID identifier of the record")
    dataset_id: int = Field(..., description="Associated dataset ID")
    type: LegalBasisType = Field(..., description="Legal basis type")
    document_ref: str = Field(..., description="Document reference")
    date: dt.date = Field(..., description="Effective date")
    entered_by: int = Field(..., description="User ID who created the record")
    created_at: dt.datetime = Field(
        ..., description="Timestamp of record creation (UTC)"
    )

    model_config = ConfigDict(from_attributes=True)
