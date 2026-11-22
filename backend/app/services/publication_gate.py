"""Publication gate for UC-07 (SCRUM-57).

The gate is read-only: ``evaluate`` never changes the dataset. The publish
endpoint applies the decision after the gate allows it. Reasons are stable
codes so the UI and tests do not depend on human-readable wording.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.models import (
    AnonymizationMethod,
    Dataset,
    DatasetVersion,
    DatasetVersionKind,
    utc_now,
)
from app.services.legal_basis_service import check_legal_basis
from app.services.pii_utils import active_pii_findings
from app.services.quality_engine import validate_dataframe
from app.services.quality_rules_resolver import get_rules_path_for_dataset

NO_CLEAN_VERSION = "no_clean_version"
PII_NOT_PROCESSED = "pii_not_processed"
HMAC_WITHOUT_LEGAL_BASIS = "hmac_without_legal_basis"
RETENTION_REQUIRED = "retention_required"
QUALITY_BLOCKED = "quality_blocked"

_HMAC_METHODS = {"hmac", "hmac_sha256"}

_REASON_META = {
    NO_CLEAN_VERSION: "no_clean",
    PII_NOT_PROCESSED: "pii_not_processed",
    HMAC_WITHOUT_LEGAL_BASIS: "hmac_no_basis",
    RETENTION_REQUIRED: "retention_req",
    QUALITY_BLOCKED: "quality_block",
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


def latest_clean_version(
    db: Session,
    dataset_id: int,
) -> Optional[DatasetVersion]:
    """Return the most recent clean version for a dataset, if any."""
    return (
        db.query(DatasetVersion)
        .filter(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.kind == DatasetVersionKind.CLEAN,
        )
        .order_by(DatasetVersion.created_at.desc(), DatasetVersion.id.desc())
        .first()
    )


def method_map(db: Session, dataset_id: int) -> dict[str, str]:
    """Return ``{column_name: method}`` for applied anonymisation methods."""
    methods: dict[str, str] = {}
    rows = (
        db.query(AnonymizationMethod)
        .filter(AnonymizationMethod.dataset_id == dataset_id)
        .order_by(AnonymizationMethod.id.asc())
        .all()
    )
    for row in rows:
        method = row.method
        methods[row.column_name] = (
            method.value if hasattr(method, "value") else str(method)
        )
    return methods


def _resolve_retention(
    dataset: Dataset,
    retention_until: Optional[date],
) -> Optional[date]:
    return retention_until if retention_until is not None else dataset.retention_until


def quality_blocks_publication(dataset: Dataset) -> bool:
    """Return whether resolved quality rules contain a blocking violation."""
    if not dataset.file_path or not os.path.exists(dataset.file_path):
        return False

    if dataset.file_type == "csv":
        frame = pd.read_csv(
            dataset.file_path,
            dtype={"ipn": str, "tax_id": str, "edrpou": str},
        )
    elif dataset.file_type == "json":
        frame = pd.read_json(dataset.file_path)
    else:
        frame = pd.read_csv(dataset.file_path)

    rules_path = get_rules_path_for_dataset(dataset)
    report = validate_dataframe(frame, rules_path or [])
    return bool(report.get("can_publish") is False)


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
        column
        for column, method in methods.items()
        if str(method).lower() in _HMAC_METHODS
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

    if quality_blocks_publication(dataset):
        reasons.append(
            _reason(
                QUALITY_BLOCKED,
                "Dataset quality rules contain blocking violations.",
                has_blocking_violations=True,
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
    "QUALITY_BLOCKED",
    "apply_publication",
    "evaluate",
    "latest_clean_version",
    "method_map",
    "quality_blocks_publication",
]
