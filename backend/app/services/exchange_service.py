
from sqlalchemy.orm import Session

from app.models import Dataset, LegalBasis


def check_legal_basis(
    dataset: Dataset,
    purpose: str,
    db: Session,
) -> bool:
    """Checks whether dataset has a valid legal basis for data exchange/processing.

    Must have at least one registered legal basis (Consent, Contract, Law).
    """
    legal_basis_entry = (
        db.query(LegalBasis)
        .filter(LegalBasis.dataset_id == dataset.id)
        .first()
    )
    if not legal_basis_entry:
        return False

    return True
