"""Legal basis validity checks for publication and exchange flows (SCRUM-58).

A legal basis authorises processing only while it is active: it must not be
revoked and its ``valid_until`` date (when set) must not be in the past. When a
processing purpose is supplied, at least one active record must match it
exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dataset, LegalBasis, LegalBasisPurpose

NO_LEGAL_BASIS = "no_legal_basis"
REVOKED = "revoked"
EXPIRED = "expired"
PURPOSE_MISMATCH = "purpose_mismatch"


@dataclass(frozen=True)
class LegalBasisCheckResult:
    """Result of a legal basis validity check."""

    ok: bool
    reason: Optional[str] = None

    @property
    def allowed(self) -> bool:
        """Alias used by gate services."""
        return self.ok


def _dataset_id(dataset: Union[Dataset, int]) -> int:
    return dataset.id if isinstance(dataset, Dataset) else dataset


def _purpose_value(value: object) -> str:
    if isinstance(value, LegalBasisPurpose):
        return value.value
    return str(value).lower()


def _matches_purpose(entry: LegalBasis, purpose: str) -> bool:
    return _purpose_value(entry.purpose) == purpose.lower()


def check_legal_basis(
    db: Session,
    dataset: Union[Dataset, int],
    purpose: Optional[Union[str, LegalBasisPurpose]] = None,
) -> LegalBasisCheckResult:
    """Check whether a dataset has an active legal basis.

    Args:
        db: SQLAlchemy session.
        dataset: Dataset ORM object or dataset id.
        purpose: Optional processing purpose. When supplied, an active record
            must have exactly this purpose.

    Returns:
        ``LegalBasisCheckResult(ok=True)`` when at least one active record
        matches; otherwise ``ok=False`` with one of ``no_legal_basis``,
        ``revoked``, ``expired`` or ``purpose_mismatch``.
    """
    dataset_id = _dataset_id(dataset)
    entries = db.scalars(
        select(LegalBasis).where(LegalBasis.dataset_id == dataset_id)
    ).all()

    if not entries:
        return LegalBasisCheckResult(False, NO_LEGAL_BASIS)

    today = date.today()
    active = [
        entry
        for entry in entries
        if entry.revoked_at is None
        and (entry.valid_until is None or entry.valid_until >= today)
    ]

    if active:
        if purpose is None:
            return LegalBasisCheckResult(True)
        purpose_value = _purpose_value(purpose)
        if any(_matches_purpose(entry, purpose_value) for entry in active):
            return LegalBasisCheckResult(True)
        return LegalBasisCheckResult(False, PURPOSE_MISMATCH)

    if all(entry.revoked_at is not None for entry in entries):
        return LegalBasisCheckResult(False, REVOKED)

    # There is at least one non-revoked record, but none is active, so it is
    # expired. This also covers a mix of revoked and expired records.
    if any(
        entry.revoked_at is None
        and entry.valid_until is not None
        and entry.valid_until < today
        for entry in entries
    ):
        return LegalBasisCheckResult(False, EXPIRED)

    # Defensive fallback: no active record and no explicit expired record.
    return LegalBasisCheckResult(False, REVOKED)


__all__ = [
    "EXPIRED",
    "LegalBasisCheckResult",
    "NO_LEGAL_BASIS",
    "PURPOSE_MISMATCH",
    "REVOKED",
    "check_legal_basis",
]
