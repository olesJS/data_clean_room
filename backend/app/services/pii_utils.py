"""Shared helpers for active PII findings (profiling, gate, anonymizer)."""

from __future__ import annotations

from typing import Any

from app.models import Dataset


def active_pii_findings(dataset: Dataset) -> list[dict[str, Any]]:
    """Return PII findings that are still considered active.

    A finding is active when it has a PII type (original or manually corrected)
    and was not explicitly rejected by the owning DataProvider. Manually
    corrected types take precedence over the detector output.
    """
    findings = dataset.pii_json or []
    active: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        pii_type = finding.get("corrected_pii_type") or finding.get("pii_type")
        if not pii_type:
            continue
        if finding.get("user_confirmed") is False:
            continue
        column_name = finding.get("column_name")
        if not column_name:
            continue
        active.append(
            {
                "column_name": str(column_name),
                "pii_type": str(pii_type),
                "confirmed": finding.get("user_confirmed"),
            }
        )
    return active


def active_pii_columns(dataset: Dataset) -> list[str]:
    """Return names of columns with active PII findings."""
    return [finding["column_name"] for finding in active_pii_findings(dataset)]


__all__ = ["active_pii_columns", "active_pii_findings"]
