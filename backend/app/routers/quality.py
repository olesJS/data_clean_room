import logging
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import get_current_user
from app.database import get_db
from app.models import Dataset, User
from app.services.quality_engine import parse_yaml_rules, validate_dataframe
from app.services.quality_rules_resolver import get_rules_path_for_dataset

logger = logging.getLogger(__name__)

router = APIRouter(tags=["quality"])


def _check_dataset_access(
    dataset_id: int,
    current_user: User,
    request: Request,
    db: Session,
) -> Dataset:
    """RBAC check according to PO Decision 8 & Matrix:

    - DataProvider (owner) & DataSteward -> Allowed (return dataset)
    - DataConsumer -> 403 Forbidden
    - DataProvider (non-owner) -> 404 Not Found (do not disclose foreign dataset)
    - Non-existent dataset -> 404 Not Found
    """
    actor = current_user.email
    path = request.url.path

    # First check role: Consumer is never allowed to view quality details
    if current_user.role == "DataConsumer":
        log_event(
            actor=actor,
            action="ACCESS_DENIED",
            object=path,
            result="FORBIDDEN",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: DataConsumer is not authorized",
        )

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        log_event(
            actor=actor,
            action="ACCESS_DENIED",
            object=path,
            result="NOT_FOUND",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found",
        )

    if (
        current_user.role == "DataProvider"
        and dataset.uploaded_by != current_user.email
    ):
        # Non-owner provider gets 404 per PO Decision 8
        log_event(
            actor=actor,
            action="ACCESS_DENIED",
            object=path,
            result="NOT_FOUND",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found",
        )

    return dataset


@router.get("/api/datasets/{dataset_id}/quality-rules")
def get_dataset_quality_rules(
    dataset_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    dataset = _check_dataset_access(dataset_id, current_user, request, db)
    rules_path = get_rules_path_for_dataset(dataset)

    if not rules_path or not rules_path.exists():
        return []

    try:
        rules = parse_yaml_rules(rules_path)
        formatted_rules = []
        for r in rules:
            formatted_rules.append(
                {
                    "column": r.get("column", "*"),
                    "condition": str(r.get("condition", "")),
                    "action": r.get("action", "reject"),
                    "description": r.get("description", ""),
                }
            )
        return formatted_rules
    except Exception as exc:
        logger.warning(
            "Could not parse quality rules for dataset %d: %s",
            dataset_id,
            exc,
            exc_info=True,
        )
        return []


@router.get("/api/datasets/{dataset_id}/quality-violations")
def get_dataset_quality_violations(
    dataset_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    dataset = _check_dataset_access(dataset_id, current_user, request, db)
    rules_path = get_rules_path_for_dataset(dataset)

    # Load dataset file
    if not dataset.file_path or not os_path_exists(dataset.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset source file not found on server",
        )

    try:
        if dataset.file_type == "csv":
            # Read string columns carefully
            df = pd.read_csv(
                dataset.file_path,
                dtype={"ipn": str, "tax_id": str, "edrpou": str},
            )
        elif dataset.file_type == "json":
            df = pd.read_json(dataset.file_path)
        else:
            df = pd.read_csv(dataset.file_path)
    except Exception as exc:
        logger.exception("Failed to read dataset file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не вдалося обробити файл",
        )

    if rules_path and rules_path.exists():
        report = validate_dataframe(df, rules_path)
    else:
        # Fallback evaluation with empty rules (only duplicate check)
        report = validate_dataframe(df, [])

    # Format report matching frontend QualityReport contract
    score = report.get("Score", report.get("score", 100.0))
    violations = report.get("violations", [])

    action_counts = {"reject": 0, "flag": 0, "block": 0}
    for v in violations:
        act = v.get("action")
        if act in action_counts:
            action_counts[act] += v.get("violation_count", 0)

    duplicated_rows_count = report.get("duplicated_rows_count", 0)

    return {
        "dataset_id": dataset.id,
        "score": score,
        "total_rows": report.get("total_rows", len(df)),
        "unique_violating_rows": report.get("unique_violating_rows", 0),
        "can_publish": report.get("can_publish", True),
        "has_blocking_violations": report.get("has_blocking_violations", False),
        "action_counts": action_counts,
        "duplicated_rows_count": duplicated_rows_count,
        "summary": {
            "duplicate_rows_count": duplicated_rows_count,
        },
        "violations": violations,
    }


def os_path_exists(p: str) -> bool:
    import os

    return os.path.exists(p)
