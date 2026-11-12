"""Data exchange request lifecycle (SCRUM-56, E7).

Rules fixed by the Product Owner:
    * only DataConsumer can create a request;
    * only the owning DataProvider can approve or reject it;
    * a request moves Requested -> Approved | Rejected -> Downloaded, and
      Approved -> Expired when ``access_until`` has passed;
    * the purpose is validated against an active legal basis on exchange
      (not during publication);
    * only the clean dataset version can ever be downloaded; the raw file is
      never exposed.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.audit import log_event
from app.models import (
    Dataset,
    ExchangeRequest,
    ExchangeRequestStatus,
    User,
    utc_now,
)
from app.schemas.exchange import (
    ExchangeDecision,
    ExchangeReject,
    ExchangeRequestCreate,
)
from app.services.anonymizer import latest_clean_version
from app.services.legal_basis_service import check_legal_basis

DEFAULT_ACCESS_DAYS = 30
ACTIVE_STATUSES = (
    ExchangeRequestStatus.REQUESTED.value,
    ExchangeRequestStatus.APPROVED.value,
)


def _audit_deny(
    db: Session,
    actor: str,
    object_ref: str,
    reason: str,
) -> None:
    log_event(
        actor=actor,
        action="DENY",
        object=f"{object_ref}:reason:{reason}",
        result="DENY",
        db=db,
    )


def _request_ref(request: ExchangeRequest) -> str:
    return (
        f"request:{request.id}:dataset:{request.dataset_id}:"
        f"purpose:{request.purpose}"
    )


def _purpose_value(request: ExchangeRequest) -> str:
    return str(request.purpose)


def _base_query(db: Session, current_user: User):
    query = db.query(ExchangeRequest).options(
        joinedload(ExchangeRequest.dataset),
        joinedload(ExchangeRequest.requester),
        joinedload(ExchangeRequest.reviewer),
    )
    if current_user.role == "DataConsumer":
        query = query.filter(ExchangeRequest.requester_id == current_user.id)
    elif current_user.role == "DataProvider":
        query = query.join(ExchangeRequest.dataset).filter(
            Dataset.uploaded_by == current_user.email
        )
    elif current_user.role != "DataSteward":
        query = query.filter(ExchangeRequest.id == -1)
    return query


def _expire_overdue(
    db: Session, requests: Iterable[ExchangeRequest]
) -> None:
    today = date.today()
    changed = False
    for request in requests:
        if (
            request.status == ExchangeRequestStatus.APPROVED.value
            and request.access_until is not None
            and request.access_until < today
        ):
            request.status = ExchangeRequestStatus.EXPIRED.value
            request.updated_at = utc_now()
            changed = True
    if changed:
        db.commit()


def serialize_request(request: ExchangeRequest) -> dict[str, Any]:
    return {
        "id": request.id,
        "dataset_id": request.dataset_id,
        "dataset_name": request.dataset.name if request.dataset else "",
        "dataset_version_id": request.dataset_version_id,
        "requester_id": request.requester_id,
        "requester_email": (
            request.requester.email if request.requester else ""
        ),
        "reviewer_id": request.reviewer_id,
        "reviewer_email": (
            request.reviewer.email if request.reviewer else None
        ),
        "status": request.status,
        "purpose": _purpose_value(request),
        "requested_at": request.requested_at,
        "decided_at": request.decided_at,
        "review_comment": request.review_comment,
        "access_until": request.access_until,
        "downloaded_at": request.downloaded_at,
        "created_at": request.created_at,
        "updated_at": request.updated_at,
    }


def list_requests(db: Session, current_user: User) -> list[ExchangeRequest]:
    requests = (
        _base_query(db, current_user)
        .order_by(ExchangeRequest.requested_at.desc())
        .all()
    )
    _expire_overdue(db, requests)
    return requests


def get_visible_request(
    db: Session,
    request_id: int,
    current_user: User,
) -> ExchangeRequest:
    request = (
        _base_query(db, current_user)
        .filter(ExchangeRequest.id == request_id)
        .first()
    )
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exchange request not found",
        )
    _expire_overdue(db, [request])
    return request


def _require_owner(
    db: Session,
    request: ExchangeRequest,
    current_user: User,
) -> None:
    owned = (
        current_user.role == "DataProvider"
        and request.dataset is not None
        and request.dataset.uploaded_by == current_user.email
    )
    if owned:
        return
    _audit_deny(
        db,
        current_user.email,
        _request_ref(request),
        "not_dataset_owner",
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the owning DataProvider can decide on this request",
    )


def _clean_version_or_deny(
    db: Session,
    dataset_id: int,
    object_ref: str,
    actor: str,
) -> Any:
    clean_version = latest_clean_version(db, dataset_id)
    if clean_version is None:
        _audit_deny(db, actor, object_ref, "no_clean_version")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No clean dataset version is available",
        )
    return clean_version


def create_request(
    db: Session,
    current_user: User,
    payload: ExchangeRequestCreate,
) -> ExchangeRequest:
    dataset = db.get(Dataset, payload.dataset_id)
    if dataset is None or dataset.status != "published":
        _audit_deny(
            db,
            current_user.email,
            f"dataset:{payload.dataset_id}",
            "dataset_not_published",
        )
        # Consumers may only discover published datasets -> avoid enumeration.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published dataset not found",
        )

    duplicate = (
        db.query(ExchangeRequest)
        .filter(
            ExchangeRequest.dataset_id == dataset.id,
            ExchangeRequest.requester_id == current_user.id,
            ExchangeRequest.status.in_(ACTIVE_STATUSES),
        )
        .first()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active request for this dataset already exists",
        )

    purpose = payload.purpose.value
    legal_check = check_legal_basis(db, dataset, purpose)
    if not legal_check.ok:
        _audit_deny(
            db,
            current_user.email,
            f"dataset:{dataset.id}:purpose:{purpose}",
            f"legal_basis_invalid:{legal_check.reason}",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"legal_basis_invalid: {legal_check.reason}",
        )

    clean_version = _clean_version_or_deny(
        db,
        dataset.id,
        f"dataset:{dataset.id}:purpose:{purpose}",
        current_user.email,
    )
    request = ExchangeRequest(
        dataset_id=dataset.id,
        dataset_version_id=clean_version.id,
        requester_id=current_user.id,
        status=ExchangeRequestStatus.REQUESTED.value,
        purpose=purpose,
        requested_at=utc_now(),
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    log_event(
        actor=current_user.email,
        action="REQUEST",
        object=_request_ref(request),
        result="SUCCESS",
        db=db,
    )
    return request


def approve_request(
    db: Session,
    current_user: User,
    request_id: int,
    payload: Optional[ExchangeDecision] = None,
) -> ExchangeRequest:
    request = get_visible_request(db, request_id, current_user)
    _require_owner(db, request, current_user)

    if request.status != ExchangeRequestStatus.REQUESTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot approve a request in status {request.status}",
        )
    if request.dataset is None or request.dataset.status != "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset is no longer published",
        )

    legal_check = check_legal_basis(
        db, request.dataset, _purpose_value(request)
    )
    if not legal_check.ok:
        _audit_deny(
            db,
            current_user.email,
            _request_ref(request),
            f"legal_basis_invalid:{legal_check.reason}",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"legal_basis_invalid: {legal_check.reason}",
        )

    clean_version = _clean_version_or_deny(
        db, request.dataset_id, _request_ref(request), current_user.email
    )

    payload = payload or ExchangeDecision()
    access_until = payload.access_until or (
        date.today() + timedelta(days=DEFAULT_ACCESS_DAYS)
    )
    if access_until < date.today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="access_until must be today or in the future",
        )

    request.status = ExchangeRequestStatus.APPROVED.value
    request.reviewer_id = current_user.id
    request.decided_at = utc_now()
    request.review_comment = payload.review_comment
    request.access_until = access_until
    request.dataset_version_id = clean_version.id
    request.updated_at = utc_now()
    db.commit()
    db.refresh(request)

    log_event(
        actor=current_user.email,
        action="REQUEST_APPROVED",
        object=_request_ref(request),
        result="SUCCESS",
        db=db,
    )
    return request


def reject_request(
    db: Session,
    current_user: User,
    request_id: int,
    payload: ExchangeReject,
) -> ExchangeRequest:
    request = get_visible_request(db, request_id, current_user)
    _require_owner(db, request, current_user)

    if request.status != ExchangeRequestStatus.REQUESTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot reject a request in status {request.status}",
        )

    request.status = ExchangeRequestStatus.REJECTED.value
    request.reviewer_id = current_user.id
    request.decided_at = utc_now()
    request.review_comment = payload.review_comment
    request.updated_at = utc_now()
    db.commit()
    db.refresh(request)

    log_event(
        actor=current_user.email,
        action="REQUEST_REJECTED",
        object=_request_ref(request),
        result="SUCCESS",
        db=db,
    )
    return request


def prepare_download(
    db: Session,
    current_user: User,
    request_id: int,
) -> tuple[ExchangeRequest, str, str]:
    """Validate a download and return (request, file_path, file_name)."""
    request = get_visible_request(db, request_id, current_user)
    if request.requester_id != current_user.id:
        _audit_deny(
            db,
            current_user.email,
            _request_ref(request),
            "not_requester",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requester can download this dataset",
        )

    if request.status == ExchangeRequestStatus.EXPIRED.value or (
        request.access_until is not None
        and request.access_until < date.today()
    ):
        request.status = ExchangeRequestStatus.EXPIRED.value
        db.commit()
        _audit_deny(
            db, current_user.email, _request_ref(request), "access_expired"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access_expired",
        )

    if request.status not in (
        ExchangeRequestStatus.APPROVED.value,
        ExchangeRequestStatus.DOWNLOADED.value,
    ):
        _audit_deny(
            db,
            current_user.email,
            _request_ref(request),
            "request_not_approved",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="request_not_approved",
        )

    legal_check = check_legal_basis(
        db, request.dataset, _purpose_value(request)
    )
    if not legal_check.ok:
        _audit_deny(
            db,
            current_user.email,
            _request_ref(request),
            f"legal_basis_invalid:{legal_check.reason}",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"legal_basis_invalid: {legal_check.reason}",
        )

    clean_version = _clean_version_or_deny(
        db, request.dataset_id, _request_ref(request), current_user.email
    )
    if not clean_version.file_path or not os.path.isfile(
        clean_version.file_path
    ):
        _audit_deny(
            db, current_user.email, _request_ref(request), "clean_file_missing"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Clean dataset file is missing",
        )

    request.status = ExchangeRequestStatus.DOWNLOADED.value
    request.dataset_version_id = clean_version.id
    request.downloaded_at = utc_now()
    request.updated_at = utc_now()
    db.commit()
    db.refresh(request)

    log_event(
        actor=current_user.email,
        action="DOWNLOAD",
        object=_request_ref(request),
        result="SUCCESS",
        db=db,
    )
    return request, clean_version.file_path, clean_version.file_name


__all__ = [
    "ACTIVE_STATUSES",
    "DEFAULT_ACCESS_DAYS",
    "approve_request",
    "create_request",
    "get_visible_request",
    "list_requests",
    "prepare_download",
    "reject_request",
    "serialize_request",
]
