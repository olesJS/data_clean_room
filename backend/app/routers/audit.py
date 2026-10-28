from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import require_role
from app.database import get_db
from app.models import AuditLog, User
from app.schemas import AuditLogResponse

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=List[AuditLogResponse])
@router.get("/api/audit", response_model=List[AuditLogResponse])
def get_audit_logs(
    current_user: User = Depends(require_role("DataSteward")),
    db: Session = Depends(get_db),
):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()

    log_event(
        actor=current_user.email,
        action="GET_AUDIT",
        object="/audit",
        result="SUCCESS",
        db=db,
    )

    return logs
