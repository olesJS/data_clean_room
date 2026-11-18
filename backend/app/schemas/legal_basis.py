"""Pydantic v2 schemas for Legal Basis."""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import LegalBasisPurpose, LegalBasisType


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
    purpose: LegalBasisPurpose = Field(
        ...,
        description=(
            "Processing purpose: analytics, research, reporting, or publication"
        ),
        examples=["analytics"],
    )
    valid_until: dt.date | None = Field(
        default=None,
        description=(
            "Optional expiry date (YYYY-MM-DD). Must be today or later when set."
        ),
        examples=["2027-12-31"],
    )

    @field_validator("valid_until")
    @classmethod
    def valid_until_not_in_past(cls, value: dt.date | None) -> dt.date | None:
        """Reject an expiry date that is already in the past."""
        if value is not None and value < dt.date.today():
            raise ValueError("valid_until must be today or in the future")
        return value


class LegalBasisRevoke(BaseModel):
    """Schema for revoking a legal basis."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Human-readable reason for revocation",
        examples=["Data subject withdrew consent"],
    )


class LegalBasisResponse(BaseModel):
    """Schema for returning legal basis information."""

    id: str = Field(..., description="Unique UUID identifier of the record")
    dataset_id: int = Field(..., description="Associated dataset ID")
    type: LegalBasisType = Field(..., description="Legal basis type")
    document_ref: str = Field(..., description="Document reference")
    date: dt.date = Field(..., description="Effective date")
    purpose: LegalBasisPurpose = Field(..., description="Processing purpose")
    valid_until: dt.date | None = Field(
        ..., description="Expiry date, or null when the basis does not expire"
    )
    entered_by: int = Field(..., description="User ID who created the record")
    created_at: dt.datetime = Field(
        ..., description="Timestamp of record creation (UTC)"
    )
    revoked_at: dt.datetime | None = Field(
        ..., description="Timestamp of revocation (UTC), or null"
    )
    revoked_by: int | None = Field(
        ..., description="User ID who revoked the record, or null"
    )
    revoked_reason: str | None = Field(
        ..., description="Reason for revocation, or null"
    )
    is_active: bool = Field(
        ...,
        description=(
            "True when the basis is neither revoked nor expired; used by the "
            "publication gate and legal basis checks"
        ),
    )

    model_config = ConfigDict(from_attributes=True)
