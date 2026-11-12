"""Publication gate for UC-07 (SCRUM-57).

The gate is read-only: ``evaluate`` never changes the dataset. The publish
endpoint applies the decision after the gate allows it. Reasons are stable
codes so the UI and tests do not depend on human-readable wording.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Dataset, utc_now
from app.services.anonymizer import latest_clean_version, method_map
from app.services.legal_basis_service import check_legal_basis
from app.services.pii_utils import active_pii_findings

NO_CLEAN_VERSION = "no_clean_version"
PII_NOT_PROCESSED = "pii_not_processed"
HMAC_WITHOUT_LEGAL_BASIS = "hmac_without_legal_basis"
RETENTION_REQUIRED = "retention_required"

_REASON_META = {
    NO_CLEAN_VERSION: "no_clean",
    PII_NOT_PROCESSED: "pii_not_processed",
    HMAC_WITHOUT_LEGAL_BASIS: "hmac_no_basis",
    RETENTION_REQUIRED: "retention_req",
}


@dataclass
class GateResult:
    allowed: bool
    reasons: list[dict[str, Any]] = field(default_factory=list)
    new_class: str = "Internal"
    hmac_columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    clean_version_id: Optional[int] = None

    def reason_codes(self) -> list[str]:
        return [str(reason["code"]) for reason in self.reasons]

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": self.reasons,
            "new_class": self.new_class,
            "hmac_columns": self.hmac_columns,
            "missing_columns": self.missing_columns,
            "clean_version_id": self.clean_version_id,
        }


def _reason(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "code": code,
        "short_code": _REASON_META[code],
        "message": message,
        **extra,
    }


def _resolve_retention(
    dataset: Dataset,
    retention_until: Optional[date],
) -> Optional[date]:
    return retention_until if retention_until is not None else dataset.retention_until


def evaluate(
    db: Session,
    dataset: Dataset,
    retention_until: Optional[date] = None,
) -> GateResult:
    """Evaluate every publication condition without changing any state."""
    reasons: list[dict[str, Any]] = []
    clean_version = latest_clean_version(db, dataset.id)
    pii_findings = active_pii_findings(dataset)
    methods = method_map(db, dataset.id)

    if clean_version is None:
        reasons.append(
            _reason(
                NO_CLEAN_VERSION,
                "No clean dataset version exists; run anonymisation first.",
            )
        )

    missing = sorted(
        finding["column_name"]
        for finding in pii_findings
        if finding["column_name"] not in methods
    )
    if missing:
        reasons.append(
            _reason(
                PII_NOT_PROCESSED,
                "Some PII columns have no anonymisation method.",
                columns=missing,
            )
        )

    hmac_columns = sorted(
        column for column, method in methods.items() if method == "hmac"
    )
    if hmac_columns:
        legal_check = check_legal_basis(db, dataset)
        if not legal_check.ok:
            reasons.append(
                _reason(
                    HMAC_WITHOUT_LEGAL_BASIS,
                    "HMAC pseudonymisation requires an active legal basis.",
                    columns=hmac_columns,
                    legal_basis_reason=legal_check.reason,
                )
            )

    proposed_retention = _resolve_retention(dataset, retention_until)
    if proposed_retention is None or proposed_retention < date.today():
        reasons.append(
            _reason(
                RETENTION_REQUIRED,
                "A retention_until date today or later is required.",
            )
        )

    if not pii_findings:
        new_class = "Internal"
    elif hmac_columns:
        # HMAC is pseudonymisation, not anonymisation: the class stays Personal.
        new_class = "Personal"
    else:
        new_class = "Confidential"

    return GateResult(
        allowed=not reasons,
        reasons=reasons,
        new_class=new_class,
        hmac_columns=hmac_columns,
        missing_columns=missing,
        clean_version_id=clean_version.id if clean_version else None,
    )


def apply_publication(
    db: Session,
    dataset: Dataset,
    retention_until: date,
    new_class: str,
    actor: str,
) -> Dataset:
    """Persist an allowed publication and recalculate the dataset class."""
    dataset.status = "published"
    dataset.published_at = utc_now()
    dataset.published_by = actor
    dataset.retention_until = retention_until
    dataset.data_class = new_class
    db.commit()
    db.refresh(dataset)
    return dataset


__all__ = [
    "GateResult",
    "HMAC_WITHOUT_LEGAL_BASIS",
    "NO_CLEAN_VERSION",
    "PII_NOT_PROCESSED",
    "RETENTION_REQUIRED",
    "apply_publication",
    "evaluate",
]
