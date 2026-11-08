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

_ALLOWED_ROLES = ("DataProvider", "DataSteward")


def _get_visible_dataset(
    dataset_id: int,
    current_user: User,
    action: str,
    db: Session,
) -> Dataset:
    """Return a dataset the current user may access, or raise 404.

    A missing dataset and a dataset owned by another DataProvider are
    intentionally indistinguishable (PO decision 8): returning 404 prevents
    dataset enumeration.
    """
    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id))
    is_foreign_provider_dataset = (
        dataset is not None
        and current_user.role == "DataProvider"
        and dataset.uploaded_by != current_user.email
    )

    if dataset is None or is_foreign_provider_dataset:
        log_event(
            actor=current_user.email,
            action=action,
            object=f"dataset:{dataset_id}",
            result="NOT_FOUND",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with id {dataset_id} not found",
        )

    return dataset


def _ensure_allowed_role(
    current_user: User,
    action: str,
    dataset_id: int,
    db: Session,
) -> None:
    """Reject unsupported roles before any dataset lookup."""
    if current_user.role in _ALLOWED_ROLES:
        return

    log_event(
        actor=current_user.email,
        action=action,
        object=f"dataset:{dataset_id}",
        result="FORBIDDEN",
        db=db,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Access forbidden: only DataSteward or an owning "
            "DataProvider can access legal bases"
        ),
    )


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
    _ensure_allowed_role(
        current_user,
        action="CREATE_LEGAL_BASIS",
        dataset_id=dataset_id,
        db=db,
    )
    _get_visible_dataset(
        dataset_id,
        current_user,
        action="CREATE_LEGAL_BASIS",
        db=db,
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
        actor=current_user.email,
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
    _ensure_allowed_role(
        current_user,
        action="GET_LEGAL_BASIS",
        dataset_id=dataset_id,
        db=db,
    )
    _get_visible_dataset(
        dataset_id,
        current_user,
        action="GET_LEGAL_BASIS",
        db=db,
    )

    query = (
        select(LegalBasis)
        .where(LegalBasis.dataset_id == dataset_id)
        .order_by(LegalBasis.created_at.desc())
    )
    return db.scalars(query).all()
