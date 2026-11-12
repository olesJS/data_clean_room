"""Published dataset catalogue (UC-08)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import require_roles
from app.database import get_db
from app.models import Dataset, User
from app.services.anonymizer import latest_clean_version

router = APIRouter(tags=["catalog"])


@router.get("/catalog")
@router.get("/api/catalog", include_in_schema=False)
def list_catalog(
    current_user: User = Depends(
        require_roles(("DataConsumer", "DataSteward"))
    ),
    db: Session = Depends(get_db),
):
    datasets = (
        db.query(Dataset)
        .filter(Dataset.status == "published")
        .order_by(Dataset.published_at.desc())
        .all()
    )

    items = []
    for dataset in datasets:
        clean_version = latest_clean_version(db, dataset.id)
        items.append(
            {
                "dataset_id": dataset.id,
                "name": dataset.name,
                "data_class": dataset.data_class,
                "quality_score": dataset.quality_score,
                "row_count": dataset.row_count,
                "column_count": len(dataset.columns or {}),
                "published_at": dataset.published_at,
                "retention_until": dataset.retention_until,
                "clean_version_id": clean_version.id if clean_version else None,
                "provider": dataset.published_by or dataset.uploaded_by,
            }
        )

    log_event(
        actor=current_user.email,
        action="LIST_CATALOG",
        object=f"/catalog:published:{len(items)}",
        result="SUCCESS",
        db=db,
    )
    return items


__all__ = ["router"]
