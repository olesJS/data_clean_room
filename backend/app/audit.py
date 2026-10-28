from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AuditLog


def log_event(
    actor: str,
    action: str,
    object: str,
    result: str,
    db: Optional[Session] = None,
) -> Optional[AuditLog]:
    """Log an audit event to the database.

    Args:
        actor: User email or identifier performing the action.
        action: The action taken (e.g. LOGIN, UPLOAD_DATASET, GET_AUDIT).
        object: The target object or entity (e.g. filename, auth endpoint).
        result: Result of the action (e.g. SUCCESS, FAILURE).
        db: Optional SQLAlchemy Session. If None, a dedicated session is created.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        log_entry = AuditLog(
            timestamp=datetime.now(timezone.utc),
            actor=str(actor),
            action=str(action),
            object=str(object),
            result=str(result),
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception as exc:
        db.rollback()
        print(f"[AUDIT LOG ERROR] Failed to record event: {exc}")
        return None
    finally:
        if close_db:
            db.close()
