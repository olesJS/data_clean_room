import hashlib
import logging
import os
from datetime import date
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import get_current_user
from app.database import get_db
from app.models import (
    AnonymizationMethod,
    AnonymizationMethodType,
    Dataset,
    DatasetVersion,
    DatasetVersionKind,
    User,
)
from app.schemas.publication import PublishRequest
from app.services.anonymizer import apply_anonymization, is_column_generalizable
from app.services.publication_gate import apply_publication, evaluate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["publication"])


class AnonymizeRequest(BaseModel):
    columns: Dict[str, str]  # e.g. {"ipn": "mask", "age": "generalize"}


def _get_dataset_for_owner(
    dataset_id: int,
    current_user: User,
    request: Request,
    db: Session,
    *,
    forbidden_detail: Optional[str] = None,
) -> Dataset:
    """Access restricted strictly to dataset owner (DataProvider).

    - Non-owner DataProvider -> 404 (PO Decision 8)
    - Consumer/Steward -> 403
    - Missing -> 404
    """
    actor = current_user.email
    path = request.url.path

    if current_user.role != "DataProvider":
        log_event(
            actor=actor,
            action="ACCESS_DENIED",
            object=path,
            result="FORBIDDEN",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=forbidden_detail
            or "Access forbidden: only DataProvider can anonymize datasets",
        )

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset or dataset.uploaded_by != current_user.email:
        log_event(
            actor=actor,
            action="ACCESS_DENIED",
            object=path,
            result="FAILURE",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found",
        )

    return dataset


def _load_raw_dataframe(dataset: Dataset) -> pd.DataFrame:
    raw_version = dataset.file_path
    if not os.path.exists(raw_version):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Raw dataset file not found on server",
        )

    try:
        if dataset.file_type == "csv":
            return pd.read_csv(
                dataset.file_path,
                dtype={"ipn": str, "tax_id": str, "edrpou": str},
            )
        elif dataset.file_type == "json":
            return pd.read_json(dataset.file_path)
        else:
            return pd.read_csv(dataset.file_path)
    except Exception as exc:
        logger.exception("Failed to load raw dataframe: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не вдалося завантажити файл",
        )


@router.post("/api/datasets/{dataset_id}/anonymize/preview")
def preview_anonymization(
    dataset_id: int,
    payload: AnonymizeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    dataset = _get_dataset_for_owner(dataset_id, current_user, request, db)
    df = _load_raw_dataframe(dataset)

    # Validate requested columns
    for col, method in payload.columns.items():
        if col not in df.columns:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Column '{col}' not found in dataset",
            )
        m_lower = method.lower()
        if m_lower not in ("mask", "generalize", "hmac", "hmac_sha256"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown anonymization method '{method}'",
            )
        if m_lower == "generalize" and not is_column_generalizable(col, df[col]):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Generalization is not supported for column '{col}'",
            )

    # Preview first 10 rows
    preview_df = df.head(10).copy()
    anonymized_df = apply_anonymization(preview_df, payload.columns)

    preview_result = {}
    for col in payload.columns:
        preview_result[col] = {
            "before": preview_df[col].tolist(),
            "after": anonymized_df[col].tolist(),
        }

    return {
        "dataset_id": dataset.id,
        "preview_rows_count": len(preview_df),
        "columns": preview_result,
    }


@router.post("/api/datasets/{dataset_id}/anonymize")
def apply_dataset_anonymization(
    dataset_id: int,
    payload: AnonymizeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    dataset = _get_dataset_for_owner(dataset_id, current_user, request, db)
    df = _load_raw_dataframe(dataset)

    # Validate requested columns
    for col, method in payload.columns.items():
        if col not in df.columns:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Column '{col}' not found in dataset",
            )
        m_lower = method.lower()
        if m_lower not in ("mask", "generalize", "hmac", "hmac_sha256"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown anonymization method '{method}'",
            )
        if m_lower == "generalize" and not is_column_generalizable(col, df[col]):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Generalization is not supported for column '{col}'",
            )

    # Apply anonymization to full dataframe
    clean_df = apply_anonymization(df, payload.columns)

    # Save clean file to storage
    storage_dir = os.path.dirname(dataset.file_path)
    clean_filename = f"clean_{os.path.basename(dataset.file_path)}"
    clean_path = os.path.join(storage_dir, clean_filename)

    if dataset.file_type == "json":
        clean_df.to_json(clean_path, orient="records", force_ascii=False, indent=2)
    else:
        clean_df.to_csv(clean_path, index=False)

    with open(clean_path, "rb") as f:
        clean_bytes = f.read()
    clean_sha256 = hashlib.sha256(clean_bytes).hexdigest()

    # Create or update DatasetVersion(kind='clean')
    clean_version = (
        db.query(DatasetVersion)
        .filter(
            DatasetVersion.dataset_id == dataset.id,
            DatasetVersion.kind == DatasetVersionKind.CLEAN,
        )
        .first()
    )
    if not clean_version:
        clean_version = DatasetVersion(
            dataset_id=dataset.id,
            kind=DatasetVersionKind.CLEAN,
            file_path=clean_path,
            sha256=clean_sha256,
            row_count=len(clean_df),
            created_by=current_user.id,
        )
        db.add(clean_version)
    else:
        clean_version.file_path = clean_path
        clean_version.sha256 = clean_sha256
        clean_version.row_count = len(clean_df)

    # Store applied methods in anonymization_methods table
    db.query(AnonymizationMethod).filter(
        AnonymizationMethod.dataset_id == dataset.id
    ).delete()

    for col, method in payload.columns.items():
        m_type = (
            AnonymizationMethodType.HMAC
            if "hmac" in method.lower()
            else AnonymizationMethodType(method.lower())
        )
        db.add(
            AnonymizationMethod(
                dataset_id=dataset.id,
                column_name=col,
                method=m_type,
                applied_by=current_user.id,
            )
        )

    db.commit()

    # Audit: log ANONYMIZE event (no PII, no HMAC key!)
    log_event(
        actor=current_user.email,
        action="ANONYMIZE",
        object=f"dataset:{dataset.id}",
        result="SUCCESS",
        db=db,
    )

    return {
        "dataset_id": dataset.id,
        "clean_sha256": clean_sha256,
        "row_count": len(clean_df),
        "status": "anonymized",
        "applied_columns": list(payload.columns.keys()),
    }


@router.get("/api/datasets/{dataset_id}/publish/check")
def check_publication(
    dataset_id: int,
    request: Request,
    retention_until: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Evaluate the publication gate without changing any state."""
    dataset = _get_dataset_for_owner(
        dataset_id,
        current_user,
        request,
        db,
        forbidden_detail=(
            "Access forbidden: only DataProvider can publish datasets"
        ),
    )
    result = evaluate(db, dataset, retention_until=retention_until)

    return result.as_dict()


@router.post("/api/datasets/{dataset_id}/publish")
def publish_dataset(
    dataset_id: int,
    payload: PublishRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Publish a dataset when every gate condition is satisfied."""
    dataset = _get_dataset_for_owner(
        dataset_id,
        current_user,
        request,
        db,
        forbidden_detail=(
            "Access forbidden: only DataProvider can publish datasets"
        ),
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

    result = evaluate(db, dataset, retention_until=payload.retention_until)
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

    response = {
        "dataset_id": dataset.id,
        "status": dataset.status,
        "data_class": dataset.data_class,
        "published_at": dataset.published_at,
        "published_by": dataset.published_by,
        "retention_until": dataset.retention_until,
        "gate": result.as_dict(),
    }

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

    return response
