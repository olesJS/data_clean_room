"""Quality rules and violation reports for the UC-04 UI (SCRUM-49/SCRUM-3)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.models import Dataset
from app.services.dataset_io import load_dataframe_for_dataset
from app.services.quality_engine import parse_yaml_rules, validate_dataframe

_ENV_RULES_DIR = "RULES_DIR"


def _candidate_directories() -> list[Path]:
    directories = []
    configured = os.getenv(_ENV_RULES_DIR)
    if configured:
        directories.append(Path(configured))
    directories.extend(
        [
            Path(__file__).resolve().parents[2] / "data",
            Path("/app/data"),
            Path("data").resolve(),
            Path("../data").resolve(),
        ]
    )
    return directories


def _candidate_rule_names(dataset: Dataset) -> list[str]:
    names: list[str] = []
    for raw_name in (dataset.name, dataset.original_filename):
        if not raw_name:
            continue
        stem = Path(str(raw_name)).stem
        lowered = stem.lower()
        if "payroll" in lowered:
            names.append("payroll_rules.yaml")
        if "customer" in lowered:
            names.append("customers_rules.yaml")
        names.append(f"{stem}_rules.yaml")
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(names))


def resolve_rules_path(dataset: Dataset) -> Path | None:
    """Find the YAML rules file associated with a dataset, if any."""
    names = _candidate_rule_names(dataset)
    for directory in _candidate_directories():
        for name in names:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def _action_counts(violations: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"reject": 0, "flag": 0, "block": 0}
    for violation in violations:
        action = str(violation.get("action", ""))
        if action in counts:
            counts[action] += int(violation.get("violation_count", 0))
    return counts


def quality_rules(dataset: Dataset) -> list[dict[str, Any]]:
    """Return the parsed rules for a dataset (empty list when none exist)."""
    path = resolve_rules_path(dataset)
    if path is None:
        return []
    return parse_yaml_rules(path)


def quality_report(
    dataset: Dataset,
    include_indices: bool = False,
) -> dict[str, Any]:
    """Evaluate the dataset file against its YAML rules.

    The response keeps the shape expected by the React screen: a score, row
    counters, per-action totals and a list of violations. Row indices are
    omitted by default because the UI never renders them.
    """
    path = resolve_rules_path(dataset)
    if path is None:
        report: dict[str, Any] = {
            "dataset_id": dataset.id,
            "score": float(dataset.quality_score or 0.0),
            "total_rows": int(dataset.row_count or 0),
            "unique_violating_rows": 0,
            "violation_count": 0,
            "can_publish": True,
            "has_blocking_violations": False,
            "duplicated_rows_count": 0,
            "action_counts": {"reject": 0, "flag": 0, "block": 0},
            "violations": [],
            "rules_configured": False,
        }
        report["summary"] = {
            "duplicate_rows_count": 0,
            "rules_configured": False,
        }
        return report

    dataframe = load_dataframe_for_dataset(dataset)
    raw_report = validate_dataframe(dataframe, path)
    violations = list(raw_report.get("violations", []))
    if not include_indices:
        violations = [
            {key: value for key, value in item.items() if key != "violating_indices"}
            for item in violations
        ]

    report = {
        "dataset_id": dataset.id,
        "score": float(raw_report.get("Score", 0.0)),
        "total_rows": int(raw_report.get("total_rows", 0)),
        "unique_violating_rows": int(
            raw_report.get("unique_violating_rows", 0)
        ),
        "violation_count": int(raw_report.get("violation_count", 0)),
        "can_publish": bool(raw_report.get("can_publish", True)),
        "has_blocking_violations": bool(
            raw_report.get("has_blocking_violations", False)
        ),
        "duplicated_rows_count": int(
            raw_report.get("duplicated_rows_count", 0)
        ),
        "action_counts": _action_counts(violations),
        "violations": violations,
        "rules_configured": True,
    }
    report["summary"] = {
        "duplicate_rows_count": report["duplicated_rows_count"],
        "rules_configured": True,
    }
    return report


__all__ = [
    "quality_report",
    "quality_rules",
    "resolve_rules_path",
]
