"""API Router for Legal Basis registry endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_event
from app.auth import get_current_user
from app.database import get_async_db
from app.models import Dataset, LegalBasis, User
from app.schemas.legal_basis import LegalBasisCreate, LegalBasisResponse

router = APIRouter(tags=["legal-basis"])


@router.post(
    "/datasets/{dataset_id}/legal-basis",
    response_model=LegalBasisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a legal basis for a dataset",
)
async def create_legal_basis(
    dataset_id: int,
    payload: LegalBasisCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    actor = current_user.email
    target_object = f"dataset:{dataset_id}"

    # 1. Verify dataset exists
    stmt = select(Dataset).where(Dataset.id == dataset_id)
    result = await db.execute(stmt)
    dataset = result.scalar_one_or_none()

    if not dataset:
        log_event(
            actor=actor,
            action="CREATE_LEGAL_BASIS",
            object=target_object,
            result="NOT_FOUND",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with id {dataset_id} not found",
        )

    # 2. RBAC Access Control:
    # DataConsumer is forbidden from managing legal bases
    if current_user.role == "DataConsumer":
        log_event(
            actor=actor,
            action="CREATE_LEGAL_BASIS",
            object=target_object,
            result="FORBIDDEN",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: DataConsumer cannot register legal bases",
        )

    # DataProvider must be the owner of the dataset
    if (
        current_user.role == "DataProvider"
        and dataset.uploaded_by != current_user.email
    ):
        log_event(
            actor=actor,
            action="CREATE_LEGAL_BASIS",
            object=target_object,
            result="FORBIDDEN",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Access forbidden: only the dataset owner "
                "or DataSteward can add a legal basis"
            ),
        )

    # 3. Instantiate and persist LegalBasis
    legal_basis_entry = LegalBasis(
        dataset_id=dataset_id,
        type=payload.type,
        document_ref=payload.document_ref,
        date=payload.date,
        entered_by=current_user.id,
    )

    db.add(legal_basis_entry)
    await db.commit()
    await db.refresh(legal_basis_entry)

    # 4. Audit Log record
    log_event(
        actor=actor,
        action="CREATE_LEGAL_BASIS",
        object=f"dataset:{dataset_id}:legal_basis:{legal_basis_entry.id}",
        result="SUCCESS",
    )

    return legal_basis_entry


@router.get(
    "/datasets/{dataset_id}/legal-basis",
    response_model=List[LegalBasisResponse],
    summary="List all legal basis records for a dataset",
)
async def get_legal_basis_list(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    actor = current_user.email
    target_object = f"dataset:{dataset_id}"

    # 1. Verify dataset exists
    stmt = select(Dataset).where(Dataset.id == dataset_id)
    result = await db.execute(stmt)
    dataset = result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with id {dataset_id} not found",
        )

    # 2. RBAC Access Control:
    # Raw dataset metadata/legal basis is accessible to
    # DataProvider (owner) and DataSteward
    if (
        current_user.role == "DataProvider"
        and dataset.uploaded_by != current_user.email
    ):
        log_event(
            actor=actor,
            action="GET_LEGAL_BASIS",
            object=target_object,
            result="FORBIDDEN",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: you do not own this dataset",
        )

    # 3. Fetch entries
    query = (
        select(LegalBasis)
        .where(LegalBasis.dataset_id == dataset_id)
        .order_by(LegalBasis.created_at.desc())
    )
    res = await db.execute(query)
    entries = res.scalars().all()

    return entries
