"""Exchange request API (SCRUM-56, E7)."""

from __future__ import annotations

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import User
from app.schemas.exchange import (
    ExchangeDecision,
    ExchangeReject,
    ExchangeRequestCreate,
    ExchangeRequestResponse,
)
from app.services import exchange_service

router = APIRouter(tags=["exchange"])


def _media_type(file_name: str) -> str:
    extension = os.path.splitext(file_name)[1].lower()
    if extension == ".json":
        return "application/json"
    return "text/csv"


@router.post(
    "/exchange-requests",
    response_model=ExchangeRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a data access request (DataConsumer)",
)
@router.post(
    "/api/exchange-requests",
    response_model=ExchangeRequestResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_exchange_request(
    payload: ExchangeRequestCreate,
    current_user: User = Depends(require_role("DataConsumer")),
    db: Session = Depends(get_db),
):
    request = exchange_service.create_request(db, current_user, payload)
    return exchange_service.serialize_request(request)


@router.get(
    "/exchange-requests",
    response_model=List[ExchangeRequestResponse],
    summary="List exchange requests visible to the current role",
)
@router.get(
    "/api/exchange-requests",
    response_model=List[ExchangeRequestResponse],
    include_in_schema=False,
)
def list_exchange_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    requests = exchange_service.list_requests(db, current_user)
    return [exchange_service.serialize_request(item) for item in requests]


@router.get(
    "/exchange-requests/{request_id}",
    response_model=ExchangeRequestResponse,
)
@router.get(
    "/api/exchange-requests/{request_id}",
    response_model=ExchangeRequestResponse,
    include_in_schema=False,
)
def get_exchange_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request = exchange_service.get_visible_request(
        db, request_id, current_user
    )
    return exchange_service.serialize_request(request)


@router.post(
    "/exchange-requests/{request_id}/approve",
    response_model=ExchangeRequestResponse,
    summary="Approve a request (owning DataProvider only)",
)
@router.post(
    "/api/exchange-requests/{request_id}/approve",
    response_model=ExchangeRequestResponse,
    include_in_schema=False,
)
def approve_exchange_request(
    request_id: int,
    payload: Optional[ExchangeDecision] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request = exchange_service.approve_request(
        db, current_user, request_id, payload
    )
    return exchange_service.serialize_request(request)


@router.post(
    "/exchange-requests/{request_id}/reject",
    response_model=ExchangeRequestResponse,
    summary="Reject a request (owning DataProvider only)",
)
@router.post(
    "/api/exchange-requests/{request_id}/reject",
    response_model=ExchangeRequestResponse,
    include_in_schema=False,
)
def reject_exchange_request(
    request_id: int,
    payload: ExchangeReject,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request = exchange_service.reject_request(
        db, current_user, request_id, payload
    )
    return exchange_service.serialize_request(request)


@router.get(
    "/exchange-requests/{request_id}/download",
    summary="Download the clean dataset version (requester only)",
)
@router.get(
    "/api/exchange-requests/{request_id}/download",
    include_in_schema=False,
)
def download_exchange_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, file_path, file_name = exchange_service.prepare_download(
        db, current_user, request_id
    )
    if not os.path.isfile(file_path):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Clean dataset file is missing",
        )
    return FileResponse(
        path=file_path,
        media_type=_media_type(file_name),
        filename=file_name,
    )


__all__ = ["router"]
