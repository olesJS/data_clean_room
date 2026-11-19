
from sqlalchemy.orm import Session

from app.models import Dataset
from app.services.legal_basis_service import check_legal_basis as verify_legal_basis


def check_legal_basis(
    dataset: Dataset,
    purpose: str,
    db: Session,
) -> bool:
    """Checks whether dataset has a valid legal basis for data exchange/processing."""
    result = verify_legal_basis(db, dataset, purpose=None)
    return result.ok
