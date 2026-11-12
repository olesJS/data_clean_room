"""Anonymisation and publication endpoints (SCRUM-55/57, UC-07)."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import get_current_user
from app.database import get_db
from app.models import Dataset, DatasetVersion, User
from app.schemas.publication import AnonymizeRequest, PublishRequest
from app.services.anonymizer import (
    AnonymizerError,
    apply_anonymization,
    preview_anonymization,
)
from app.services.publication_gate import apply_publication, evaluate

router = APIRouter(tags=["publication"])


def _get_owned_dataset(
    dataset_id: int,
    current_user: User,
    db: Session,
    action: Optional[str] = None,
    audit: bool = True,
) -> Dataset:
    """Only the owning DataProvider may publish or anonymise a dataset.

    Preview calls this with ``audit=False`` because it must be fully
    read-only, including rejected requests.
    """
    if current_user.role != "DataProvider":
        if audit and action:
            log_event(
                actor=current_user.email,
                action=action,
                object=f"dataset:{dataset_id}",
                result="FORBIDDEN",
                db=db,
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owning DataProvider can perform this action",
        )

    dataset = db.get(Dataset, dataset_id)
    if dataset is None or dataset.uploaded_by != current_user.email:
        if audit and action:
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


@router.post("/datasets/{dataset_id}/anonymize/preview")
@router.post(
    "/api/datasets/{dataset_id}/anonymize/preview",
    include_in_schema=False,
)
def preview_dataset_anonymization(
    dataset_id: int,
    payload: Optional[AnonymizeRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_owned_dataset(dataset_id, current_user, db, audit=False)
    try:
        preview = preview_anonymization(
            dataset, payload.methods if payload else None
        )
    except AnonymizerError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    return preview


@router.post("/datasets/{dataset_id}/anonymize")
@router.post(
    "/api/datasets/{dataset_id}/anonymize",
    include_in_schema=False,
)
def anonymize_dataset(
    dataset_id: int,
    payload: Optional[AnonymizeRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_owned_dataset(
        dataset_id, current_user, db, action="ANONYMIZE"
    )
    try:
        version = apply_anonymization(
            db,
            dataset,
            payload.methods if payload else None,
            actor=current_user.email,
        )
    except AnonymizerError as exc:
        log_event(
            actor=current_user.email,
            action="ANONYMIZE",
            object=f"dataset:{dataset.id}",
            result="INVALID",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    log_event(
        actor=current_user.email,
        action="ANONYMIZE",
        object=(
            f"dataset:{dataset.id}:version:{version.id}:"
            f"sha256:{version.sha256[:12]}"
        ),
        result="SUCCESS",
        db=db,
    )
    return {
        "dataset_id": dataset.id,
        "version_id": version.id,
        "version_number": version.version_number,
        "kind": version.kind,
        "file_name": version.file_name,
        "row_count": version.row_count,
        "sha256": version.sha256,
        "data_class": version.data_class,
        "created_at": version.created_at,
    }


@router.get("/datasets/{dataset_id}/publish/check")
@router.get(
    "/api/datasets/{dataset_id}/publish/check",
    include_in_schema=False,
)
def check_publication(
    dataset_id: int,
    retention_until: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_owned_dataset(
        dataset_id, current_user, db, action="PUBLISH_CHECK"
    )
    result = evaluate(db, dataset, retention_until=retention_until)
    log_event(
        actor=current_user.email,
        action="PUBLISH_CHECK",
        object=f"dataset:{dataset.id}:allowed:{result.allowed}",
        result="SUCCESS",
        db=db,
    )
    return result.as_dict()


@router.post("/datasets/{dataset_id}/publish")
@router.post(
    "/api/datasets/{dataset_id}/publish",
    include_in_schema=False,
)
def publish_dataset(
    dataset_id: int,
    payload: PublishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_owned_dataset(
        dataset_id, current_user, db, action="PUBLISH"
    )
    if dataset.status == "published":
        log_event(
            actor=current_user.email,
            action="PUBLISH",
            object=f"dataset:{dataset.id}",
            result="CONFLICT",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset is already published",
        )

    result = evaluate(
        db, dataset, retention_until=payload.retention_until
    )
    if not result.allowed:
        log_event(
            actor=current_user.email,
            action="DENY",
            object=(
                f"dataset:{dataset.id}:publish:reasons:"
                + ",".join(result.reason_codes())
            ),
            result="DENY",
            db=db,
        )
        return JSONResponse(status_code=422, content=result.as_dict())

    apply_publication(
        db,
        dataset,
        retention_until=payload.retention_until,
        new_class=result.new_class,
        actor=current_user.email,
    )
    log_event(
        actor=current_user.email,
        action="PUBLISH",
        object=(
            f"dataset:{dataset.id}:class:{result.new_class}:"
            f"retention:{payload.retention_until.isoformat()}"
        ),
        result="SUCCESS",
        db=db,
    )
    return {
        "dataset_id": dataset.id,
        "status": dataset.status,
        "data_class": dataset.data_class,
        "published_at": dataset.published_at,
        "published_by": dataset.published_by,
        "retention_until": dataset.retention_until,
        "gate": result.as_dict(),
    }


@router.get("/datasets/{dataset_id}/versions")
@router.get(
    "/api/datasets/{dataset_id}/versions",
    include_in_schema=False,
)
def list_dataset_versions(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_owned_dataset(
        dataset_id, current_user, db, action="LIST_DATASET_VERSIONS"
    )
    versions = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id)
        .order_by(DatasetVersion.version_number.desc())
        .all()
    )
    return [
        {
            "id": version.id,
            "kind": version.kind,
            "version_number": version.version_number,
            "file_name": version.file_name,
            "file_type": version.file_type,
            "file_size": version.file_size,
            "row_count": version.row_count,
            "sha256": version.sha256,
            "data_class": version.data_class,
            "created_by": version.created_by,
            "created_at": version.created_at,
        }
        for version in versions
    ]


__all__ = ["router"]
