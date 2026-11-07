"""API Router for Legal Basis registry endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import get_current_user
from app.database import get_db
from app.models import Dataset, LegalBasis, User
from app.schemas.legal_basis import LegalBasisCreate, LegalBasisResponse

router = APIRouter(tags=["legal-basis"])


@router.post(
    "/datasets/{dataset_id}/legal-basis",
    response_model=LegalBasisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a legal basis for a dataset",
)
def create_legal_basis(
    dataset_id: int,
    payload: LegalBasisCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    actor = current_user.email
    target_object = f"dataset:{dataset_id}"

    # Check the role before accessing the dataset to avoid leaking its existence.
    if current_user.role not in ("DataProvider", "DataSteward"):
        log_event(
            actor=actor,
            action="CREATE_LEGAL_BASIS",
            object=target_object,
            result="FORBIDDEN",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Access forbidden: only DataSteward or an owning "
                "DataProvider can register legal bases"
            ),
        )

    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id))
    if not dataset:
        log_event(
            actor=actor,
            action="CREATE_LEGAL_BASIS",
            object=target_object,
            result="NOT_FOUND",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with id {dataset_id} not found",
        )

    if (
        current_user.role == "DataProvider"
        and dataset.uploaded_by != current_user.email
    ):
        log_event(
            actor=actor,
            action="CREATE_LEGAL_BASIS",
            object=target_object,
            result="FORBIDDEN",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Access forbidden: only the dataset owner or "
                "DataSteward can add a legal basis"
            ),
        )

    legal_basis_entry = LegalBasis(
        dataset_id=dataset_id,
        type=payload.type,
        document_ref=payload.document_ref,
        date=payload.date,
        entered_by=current_user.id,
    )

    db.add(legal_basis_entry)
    db.commit()
    db.refresh(legal_basis_entry)

    log_event(
        actor=actor,
        action="CREATE_LEGAL_BASIS",
        object=f"dataset:{dataset_id}:legal_basis:{legal_basis_entry.id}",
        result="SUCCESS",
        db=db,
    )

    return legal_basis_entry


@router.get(
    "/datasets/{dataset_id}/legal-basis",
    response_model=List[LegalBasisResponse],
    summary="List all legal basis records for a dataset",
)
def get_legal_basis_list(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    actor = current_user.email
    target_object = f"dataset:{dataset_id}"

    # 1. Verify dataset exists
    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id))

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with id {dataset_id} not found",
        )

    if current_user.role == "DataSteward":
        pass
    elif (
        current_user.role == "DataProvider"
        and dataset.uploaded_by == current_user.email
    ):
        pass
    else:
        log_event(
            actor=actor,
            action="GET_LEGAL_BASIS",
            object=target_object,
            result="FORBIDDEN",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Access forbidden: only the dataset owner or "
                "DataSteward can view legal bases"
            ),
        )

    query = (
        select(LegalBasis)
        .where(LegalBasis.dataset_id == dataset_id)
        .order_by(LegalBasis.created_at.desc())
    )
    return db.scalars(query).all()
