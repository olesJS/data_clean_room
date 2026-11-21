
import re
from typing import Optional, Union

from sqlalchemy.orm import Session

from app.models import Dataset, LegalBasisPurpose
from app.services.legal_basis_service import (
    LegalBasisCheckResult,
)
from app.services.legal_basis_service import (
    check_legal_basis as verify_legal_basis,
)


def check_legal_basis(
    dataset: Dataset,
    purpose: Optional[Union[str, LegalBasisPurpose]],
    db: Session,
) -> LegalBasisCheckResult:
    """Checks whether dataset has an active legal basis matching purpose."""
    if not purpose:
        return verify_legal_basis(db, dataset, purpose=None)

    # Check if exact match or if any active legal basis matches one of categories
    p_lower = str(purpose).strip().lower()
    matched_categories = [
        cat.value
        for cat in LegalBasisPurpose
        if re.search(rf"\b{cat.value}\b", p_lower) or cat.value == p_lower
    ]

    if matched_categories:
        # If any matching category is authorized by an active legal basis, grant access
        for cat in matched_categories:
            res = verify_legal_basis(db, dataset, purpose=cat)
            if res.ok:
                return res
        # If none matched active, return result for the primary matched category
        return verify_legal_basis(db, dataset, purpose=matched_categories[0])

    return verify_legal_basis(db, dataset, purpose=p_lower)

