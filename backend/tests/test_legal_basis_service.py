"""Tests for SCRUM-58 legal basis validity checks."""

from datetime import date, timedelta

import pytest

from app.models import (
    Dataset,
    LegalBasis,
    LegalBasisPurpose,
    LegalBasisType,
    User,
    utc_now,
)
from app.services.legal_basis_service import (
    EXPIRED,
    NO_LEGAL_BASIS,
    PURPOSE_MISMATCH,
    REVOKED,
    check_legal_basis,
)


def _provider_id(db_session):
    return (
        db_session.query(User)
        .filter(User.email == "provider@example.com")
        .one()
        .id
    )


def _dataset(db_session):
    dataset = Dataset(
        name="Legal Basis Service Dataset",
        original_filename="legal-basis-service.csv",
        file_path="storage/legal-basis-service.csv",
        file_size=128,
        file_type="csv",
        columns={"id": "int"},
        row_count=1,
        uploaded_by="provider@example.com",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


def _basis(db_session, dataset_id, **overrides):
    values = {
        "dataset_id": dataset_id,
        "type": LegalBasisType.CONSENT,
        "document_ref": "CONSENT-SERVICE-001",
        "date": date.today(),
        "purpose": LegalBasisPurpose.ANALYTICS,
        "entered_by": _provider_id(db_session),
        "valid_until": None,
        "revoked_at": None,
        "revoked_by": None,
        "revoked_reason": None,
    }
    values.update(overrides)
    entry = LegalBasis(**values)
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


def test_no_legal_basis(db_session):
    dataset = _dataset(db_session)

    result = check_legal_basis(db_session, dataset)

    assert result.ok is False
    assert result.reason == NO_LEGAL_BASIS


def test_active_basis_allows_any_purpose(db_session):
    dataset = _dataset(db_session)
    _basis(db_session, dataset.id)

    result = check_legal_basis(db_session, dataset)

    assert result.ok is True
    assert result.reason is None
    assert result.allowed is True


def test_active_basis_with_matching_purpose(db_session):
    dataset = _dataset(db_session)
    _basis(db_session, dataset.id, purpose=LegalBasisPurpose.RESEARCH)

    result = check_legal_basis(db_session, dataset, purpose="research")

    assert result.ok is True


def test_active_basis_with_enum_purpose(db_session):
    dataset = _dataset(db_session)
    _basis(db_session, dataset.id, purpose=LegalBasisPurpose.REPORTING)

    result = check_legal_basis(
        db_session, dataset, purpose=LegalBasisPurpose.REPORTING
    )

    assert result.ok is True


def test_active_basis_with_wrong_purpose(db_session):
    dataset = _dataset(db_session)
    _basis(db_session, dataset.id, purpose=LegalBasisPurpose.ANALYTICS)

    result = check_legal_basis(db_session, dataset, purpose="publication")

    assert result.ok is False
    assert result.reason == PURPOSE_MISMATCH


def test_revoked_matching_purpose_wins_over_other_active_basis(db_session):
    """PO review on PR #30: report the revoked basis for the requested purpose."""
    dataset = _dataset(db_session)
    _basis(
        db_session,
        dataset.id,
        purpose=LegalBasisPurpose.ANALYTICS,
        revoked_at=utc_now(),
        revoked_by=_provider_id(db_session),
        revoked_reason="Withdrawn",
    )
    _basis(
        db_session,
        dataset.id,
        document_ref="CONTRACT-SERVICE-001",
        type=LegalBasisType.CONTRACT,
        purpose=LegalBasisPurpose.REPORTING,
    )

    result = check_legal_basis(db_session, dataset, purpose="analytics")

    assert result.ok is False
    assert result.reason == REVOKED


def test_expired_matching_purpose_wins_over_other_active_basis(db_session):
    dataset = _dataset(db_session)
    _basis(
        db_session,
        dataset.id,
        purpose=LegalBasisPurpose.ANALYTICS,
        valid_until=date.today() - timedelta(days=1),
    )
    _basis(
        db_session,
        dataset.id,
        document_ref="CONTRACT-SERVICE-001",
        type=LegalBasisType.CONTRACT,
        purpose=LegalBasisPurpose.REPORTING,
    )

    result = check_legal_basis(db_session, dataset, purpose="analytics")

    assert result.ok is False
    assert result.reason == EXPIRED


def test_no_matching_purpose_without_active_basis_returns_no_legal_basis(
    db_session,
):
    dataset = _dataset(db_session)
    _basis(
        db_session,
        dataset.id,
        purpose=LegalBasisPurpose.ANALYTICS,
        revoked_at=utc_now(),
    )

    result = check_legal_basis(db_session, dataset, purpose="research")

    assert result.ok is False
    assert result.reason == NO_LEGAL_BASIS


def test_revoked_basis_is_rejected(db_session):
    dataset = _dataset(db_session)
    _basis(
        db_session,
        dataset.id,
        revoked_at=utc_now(),
        revoked_by=_provider_id(db_session),
        revoked_reason="Withdrawn",
    )

    result = check_legal_basis(db_session, dataset)

    assert result.ok is False
    assert result.reason == REVOKED


def test_expired_basis_is_rejected(db_session):
    dataset = _dataset(db_session)
    _basis(
        db_session,
        dataset.id,
        valid_until=date.today() - timedelta(days=1),
    )

    result = check_legal_basis(db_session, dataset)

    assert result.ok is False
    assert result.reason == EXPIRED


def test_basis_valid_until_today_is_active(db_session):
    dataset = _dataset(db_session)
    _basis(db_session, dataset.id, valid_until=date.today())

    result = check_legal_basis(db_session, dataset)

    assert result.ok is True


def test_revoked_basis_does_not_block_another_active_basis(db_session):
    dataset = _dataset(db_session)
    _basis(db_session, dataset.id, revoked_at=utc_now())
    _basis(db_session, dataset.id, document_ref="CONSENT-SERVICE-002")

    result = check_legal_basis(db_session, dataset, purpose="analytics")

    assert result.ok is True


def test_expired_basis_does_not_block_another_active_basis(db_session):
    dataset = _dataset(db_session)
    _basis(
        db_session,
        dataset.id,
        valid_until=date.today() - timedelta(days=1),
    )
    _basis(db_session, dataset.id, document_ref="CONSENT-SERVICE-002")

    result = check_legal_basis(db_session, dataset, purpose="analytics")

    assert result.ok is True


def test_contract_and_law_bases_are_checked_the_same_way(db_session):
    dataset = _dataset(db_session)
    _basis(
        db_session,
        dataset.id,
        type=LegalBasisType.CONTRACT,
        purpose=LegalBasisPurpose.PUBLICATION,
    )

    result = check_legal_basis(db_session, dataset, purpose="publication")

    assert result.ok is True


def test_dataset_id_can_be_passed_instead_of_object(db_session):
    dataset = _dataset(db_session)
    _basis(db_session, dataset.id)

    result = check_legal_basis(db_session, dataset.id)

    assert result.ok is True


def test_mixed_revoked_and_expired_returns_expired(db_session):
    dataset = _dataset(db_session)
    _basis(db_session, dataset.id, revoked_at=utc_now())
    _basis(
        db_session,
        dataset.id,
        document_ref="CONSENT-SERVICE-002",
        valid_until=date.today() - timedelta(days=1),
    )

    result = check_legal_basis(db_session, dataset)

    assert result.ok is False
    assert result.reason == EXPIRED


@pytest.mark.parametrize(
    "purpose",
    [
        LegalBasisPurpose.ANALYTICS,
        LegalBasisPurpose.RESEARCH,
        LegalBasisPurpose.REPORTING,
        LegalBasisPurpose.PUBLICATION,
    ],
)
def test_all_supported_purposes_match(db_session, purpose):
    dataset = _dataset(db_session)
    _basis(db_session, dataset.id, purpose=purpose)

    result = check_legal_basis(db_session, dataset, purpose=purpose)

    assert result.ok is True
