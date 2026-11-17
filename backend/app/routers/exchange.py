import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Dataset,
    DatasetVersion,
    DatasetVersionKind,
    ExchangeRequest,
    ExchangeRequestStatus,
    User,
)
from app.services.exchange_service import check_legal_basis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["exchange"])


class CreateExchangeRequest(BaseModel):
    dataset_id: int
    purpose: str = Field(..., min_length=10, max_length=500)


class ReviewExchangeRequest(BaseModel):
    comment: Optional[str] = Field(None, max_length=500)


@router.get("/api/catalog")
def get_catalog(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Returns published datasets for Consumer catalog, excluding raw PII."""
    datasets = (
        db.query(Dataset)
        .filter(Dataset.status == "published")
        .order_by(Dataset.created_at.desc())
        .all()
    )

    catalog_cards = []
    for d in datasets:
        # Load applied anonymization methods
        methods = [
            {"column": m.column_name, "method": m.method.value}
            for m in d.anonymization_methods
        ]
        card = {
            "id": d.id,
            "name": d.name,
            "data_class": d.data_class,
            "row_count": d.row_count,
            "quality_score": d.quality_score,
            "anonymization_methods": methods,
            "uploaded_by": d.uploaded_by,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        catalog_cards.append(card)

    return catalog_cards


@router.post("/api/requests", status_code=status.HTTP_201_CREATED)
def create_exchange_request(
    payload: CreateExchangeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Consumer requests access to a dataset."""
    actor = current_user.email
    path = request.url.path

    if current_user.role != "DataConsumer":
        log_event(
            actor=actor,
            action="ACCESS_DENIED",
            object=path,
            result="FORBIDDEN",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: only DataConsumer can create exchange requests",
        )

    # Check dataset existence and published status
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == payload.dataset_id, Dataset.status == "published")
        .first()
    )
    if not dataset:
        log_event(
            actor=actor,
            action="REQUEST_DATASET",
            object=f"dataset:{payload.dataset_id}",
            result="NOT_FOUND",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Published dataset {payload.dataset_id} not found",
        )

    # Check duplicate pending request
    duplicate = (
        db.query(ExchangeRequest)
        .filter(
            ExchangeRequest.dataset_id == payload.dataset_id,
            ExchangeRequest.consumer_id == current_user.id,
            ExchangeRequest.status == ExchangeRequestStatus.PENDING,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending request already exists for this dataset",
        )

    req = ExchangeRequest(
        dataset_id=payload.dataset_id,
        consumer_id=current_user.id,
        purpose=payload.purpose,
        status=ExchangeRequestStatus.PENDING,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    log_event(
        actor=actor,
        action="REQUEST",
        object=f"dataset:{dataset.id}",
        result="SUCCESS",
        db=db,
    )

    return {
        "id": req.id,
        "dataset_id": req.dataset_id,
        "purpose": req.purpose,
        "status": req.status.value,
        "created_at": req.created_at.isoformat(),
    }


@router.get("/api/requests")
def list_exchange_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List exchange requests based on role:

    - Consumer: own requests
    - Steward: all requests
    - Provider: requests on datasets owned by this provider
    """
    if current_user.role == "DataConsumer":
        query = db.query(ExchangeRequest).filter(
            ExchangeRequest.consumer_id == current_user.id
        )
    elif current_user.role == "DataSteward":
        query = db.query(ExchangeRequest)
    elif current_user.role == "DataProvider":
        query = (
            db.query(ExchangeRequest)
            .join(Dataset)
            .filter(Dataset.uploaded_by == current_user.email)
        )
    else:
        query = db.query(ExchangeRequest).filter(ExchangeRequest.id == -1)

    requests = query.order_by(ExchangeRequest.created_at.desc()).all()
    results = []
    for r in requests:
        results.append(
            {
                "id": r.id,
                "dataset_id": r.dataset_id,
                "dataset_name": r.dataset.name if r.dataset else None,
                "consumer_id": r.consumer_id,
                "consumer_email": r.consumer.email if r.consumer else None,
                "purpose": r.purpose,
                "status": r.status.value,
                "review_comment": r.review_comment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            }
        )
    return results


@router.post("/api/requests/{request_id}/approve")
def approve_exchange_request(
    request_id: int,
    payload: ReviewExchangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """DataSteward approves request after checking legal basis."""
    if current_user.role != "DataSteward":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: only DataSteward can approve exchange requests",
        )

    req = (
        db.query(ExchangeRequest).filter(ExchangeRequest.id == request_id).first()
    )
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request {request_id} not found",
        )

    if req.status != ExchangeRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request is already resolved with status {req.status.value}",
        )

    # Check legal basis
    if not check_legal_basis(req.dataset, req.purpose, db):
        log_event(
            actor=current_user.email,
            action="DENY",
            object=f"request:{req.id}",
            result="LEGAL_BASIS_INVALID",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot approve request: no valid legal basis found for dataset",
        )

    req.status = ExchangeRequestStatus.APPROVED
    req.reviewed_by = current_user.id
    req.review_comment = payload.comment
    req.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    log_event(
        actor=current_user.email,
        action="APPROVE",
        object=f"request:{req.id}",
        result="SUCCESS",
        db=db,
    )

    return {
        "id": req.id,
        "status": req.status.value,
        "reviewed_at": req.reviewed_at.isoformat(),
    }


@router.post("/api/requests/{request_id}/reject")
def reject_exchange_request(
    request_id: int,
    payload: ReviewExchangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """DataSteward rejects request."""
    if current_user.role != "DataSteward":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: only DataSteward can reject exchange requests",
        )

    req = (
        db.query(ExchangeRequest).filter(ExchangeRequest.id == request_id).first()
    )
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request {request_id} not found",
        )

    if req.status != ExchangeRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request is already resolved with status {req.status.value}",
        )

    req.status = ExchangeRequestStatus.REJECTED
    req.reviewed_by = current_user.id
    req.review_comment = payload.comment
    req.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    log_event(
        actor=current_user.email,
        action="DENY",
        object=f"request:{req.id}",
        result="REJECTED_BY_STEWARD",
        db=db,
    )

    return {
        "id": req.id,
        "status": req.status.value,
        "reviewed_at": req.reviewed_at.isoformat(),
    }


@router.get("/api/requests/{request_id}/download")
def download_clean_dataset(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Consumer downloads clean anonymized dataset for approved request."""
    path = request.url.path
    req = (
        db.query(ExchangeRequest).filter(ExchangeRequest.id == request_id).first()
    )
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request {request_id} not found",
        )

    # Only request creator (consumer) can download
    if req.consumer_id != current_user.id:
        log_event(
            actor=current_user.email,
            action="ACCESS_DENIED",
            object=path,
            result="FORBIDDEN",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: you can only download your own approved requests",
        )

    if req.status != ExchangeRequestStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot download: request is in status {req.status.value}",
        )

    # Re-check legal basis before download
    if not check_legal_basis(req.dataset, req.purpose, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legal basis is no longer valid for this dataset",
        )

    # Locate clean DatasetVersion (RAW is NEVER served!)
    clean_version = (
        db.query(DatasetVersion)
        .filter(
            DatasetVersion.dataset_id == req.dataset_id,
            DatasetVersion.kind == DatasetVersionKind.CLEAN,
        )
        .first()
    )
    if not clean_version or not os.path.exists(clean_version.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clean version of dataset is not available yet",
        )

    log_event(
        actor=current_user.email,
        action="DOWNLOAD",
        object=f"dataset:{req.dataset_id}:clean",
        result="SUCCESS",
        db=db,
    )

    clean_filename = f"{req.dataset.name}_clean.csv"
    return FileResponse(
        clean_version.file_path,
        filename=clean_filename,
        media_type="text/csv",
    )
