"""Quality rules and violations API (UC-04, SCRUM-49)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import get_current_user
from app.database import get_db
from app.models import Dataset, User
from app.services.quality_service import quality_report, quality_rules

router = APIRouter(tags=["quality"])


def _get_quality_dataset(
    dataset_id: int,
    current_user: User,
    db: Session,
    action: str,
) -> Dataset:
    """Provider owner or DataSteward can read quality data; others get 403."""
    if current_user.role == "DataConsumer":
        log_event(
            actor=current_user.email,
            action=action,
            object=f"dataset:{dataset_id}",
            result="FORBIDDEN",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Consumers cannot inspect quality rules or violations.",
        )

    dataset = db.get(Dataset, dataset_id)
    is_foreign_provider = (
        dataset is not None
        and current_user.role == "DataProvider"
        and dataset.uploaded_by != current_user.email
    )
    if dataset is None or is_foreign_provider:
        log_event(
            actor=current_user.email,
            action=action,
            object=f"dataset:{dataset_id}",
            result="NOT_FOUND",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )
    return dataset


@router.get("/datasets/{dataset_id}/quality-rules")
@router.get(
    "/api/datasets/{dataset_id}/quality-rules",
    include_in_schema=False,
)
def get_quality_rules(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_quality_dataset(
        dataset_id, current_user, db, action="GET_QUALITY_RULES"
    )
    rules = quality_rules(dataset)
    log_event(
        actor=current_user.email,
        action="GET_QUALITY_RULES",
        object=f"dataset:{dataset.id}:{dataset.name}",
        result="SUCCESS",
        db=db,
    )
    return rules


@router.get("/datasets/{dataset_id}/quality-violations")
@router.get(
    "/api/datasets/{dataset_id}/quality-violations",
    include_in_schema=False,
)
def get_quality_violations(
    dataset_id: int,
    include_indices: bool = Query(
        default=False,
        description="Include row indices in each violation (up to 100 per rule)",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_quality_dataset(
        dataset_id, current_user, db, action="GET_QUALITY_VIOLATIONS"
    )
    report = quality_report(dataset, include_indices=include_indices)
    log_event(
        actor=current_user.email,
        action="GET_QUALITY_VIOLATIONS",
        object=f"dataset:{dataset.id}:{dataset.name}",
        result="SUCCESS",
        db=db,
    )
    return report


__all__ = ["router"]
