"""Tests for SCRUM-57 consent fields and legal basis revocation."""

from datetime import date, timedelta

from app.auth import hash_password
from app.models import AuditLog, Dataset, LegalBasis, User

FUTURE_DATE = (date.today() + timedelta(days=365)).isoformat()


def create_sample_dataset(db_session, uploaded_by="provider@example.com"):
    dataset = Dataset(
        name="Consent Test Dataset",
        original_filename="consent.csv",
        file_path="storage/consent.csv",
        file_size=1024,
        file_type="csv",
        columns={"id": "int", "email": "str"},
        row_count=5,
        uploaded_by=uploaded_by,
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset.id


def create_other_provider_token(client, db_session):
    email = "other-consent-provider@example.com"
    existing = db_session.query(User).filter(User.email == email).first()
    if not existing:
        db_session.add(
            User(
                email=email,
                hashed_password=hash_password("password123"),
                role="DataProvider",
            )
        )
        db_session.commit()

    token_response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert token_response.status_code == 200
    return token_response.json()["access_token"]


def create_legal_basis(client, token, dataset_id, **overrides):
    payload = {
        "type": "consent",
        "document_ref": "CONSENT-2026-REVOKE-001",
        "date": "2026-10-24",
        "purpose": "analytics",
        "valid_until": FUTURE_DATE,
    }
    payload.update(overrides)

    response = client.post(
        f"/datasets/{dataset_id}/legal-basis",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_legal_basis_requires_purpose(client, provider_token, db_session):
    dataset_id = create_sample_dataset(db_session)
    response = client.post(
        f"/datasets/{dataset_id}/legal-basis",
        json={
            "type": "consent",
            "document_ref": "CONSENT-NO-PURPOSE",
            "date": "2026-10-24",
        },
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert response.status_code == 422


def test_create_legal_basis_rejects_invalid_purpose(
    client, provider_token, db_session
):
    dataset_id = create_sample_dataset(db_session)
    response = client.post(
        f"/datasets/{dataset_id}/legal-basis",
        json={
            "type": "consent",
            "document_ref": "CONSENT-BAD-PURPOSE",
            "date": "2026-10-24",
            "purpose": "marketing",
        },
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert response.status_code == 422


def test_create_legal_basis_rejects_past_valid_until(
    client, provider_token, db_session
):
    dataset_id = create_sample_dataset(db_session)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    response = client.post(
        f"/datasets/{dataset_id}/legal-basis",
        json={
            "type": "consent",
            "document_ref": "CONSENT-EXPIRED",
            "date": "2026-10-24",
            "purpose": "analytics",
            "valid_until": yesterday,
        },
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert response.status_code == 422


def test_owner_can_revoke_and_audit_has_no_document_ref(
    client, provider_token, db_session
):
    dataset_id = create_sample_dataset(db_session)
    legal_basis = create_legal_basis(client, provider_token, dataset_id)

    response = client.post(
        f"/legal-basis/{legal_basis['id']}/revoke",
        json={"reason": "Data subject withdrew consent"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert response.status_code == 200, response.text
    revoked = response.json()
    assert revoked["revoked_at"] is not None
    assert revoked["revoked_by"] is not None
    assert revoked["revoked_reason"] == "Data subject withdrew consent"
    assert revoked["is_active"] is False
    assert revoked["document_ref"] == "CONSENT-2026-REVOKE-001"

    provider = (
        db_session.query(User)
        .filter(User.email == "provider@example.com")
        .one()
    )
    assert revoked["revoked_by"] == provider.id

    audit_record = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "CONSENT_REVOKED")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit_record is not None
    assert audit_record.result == "SUCCESS"
    assert f"dataset:{dataset_id}" in audit_record.object
    assert f"legal_basis:{legal_basis['id']}" in audit_record.object
    assert "CONSENT-2026-REVOKE-001" not in audit_record.object
    assert "Data subject withdrew consent" not in audit_record.object


def test_steward_can_revoke_via_api_alias(
    client, provider_token, steward_token, db_session
):
    dataset_id = create_sample_dataset(db_session)
    legal_basis = create_legal_basis(client, provider_token, dataset_id)

    response = client.post(
        f"/api/legal-basis/{legal_basis['id']}/revoke",
        json={"reason": "Steward review"},
        headers={"Authorization": f"Bearer {steward_token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False


def test_consumer_cannot_revoke(client, provider_token, consumer_token, db_session):
    dataset_id = create_sample_dataset(db_session)
    legal_basis = create_legal_basis(client, provider_token, dataset_id)

    response = client.post(
        f"/legal-basis/{legal_basis['id']}/revoke",
        json={"reason": "Should not be allowed"},
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert response.status_code == 403

    stored = (
        db_session.query(LegalBasis)
        .filter(LegalBasis.id == legal_basis["id"])
        .one()
    )
    assert stored.revoked_at is None


def test_other_provider_gets_404_on_revoke(
    client, provider_token, db_session
):
    dataset_id = create_sample_dataset(db_session)
    legal_basis = create_legal_basis(client, provider_token, dataset_id)
    other_token = create_other_provider_token(client, db_session)

    response = client.post(
        f"/legal-basis/{legal_basis['id']}/revoke",
        json={"reason": "Foreign provider"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404

    stored = (
        db_session.query(LegalBasis)
        .filter(LegalBasis.id == legal_basis["id"])
        .one()
    )
    assert stored.revoked_at is None


def test_revoke_unknown_legal_basis_returns_404(client, provider_token):
    response = client.post(
        "/legal-basis/00000000-0000-0000-0000-000000000000/revoke",
        json={"reason": "Unknown"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert response.status_code == 404


def test_repeated_revoke_returns_409(client, provider_token, db_session):
    dataset_id = create_sample_dataset(db_session)
    legal_basis = create_legal_basis(client, provider_token, dataset_id)
    headers = {"Authorization": f"Bearer {provider_token}"}
    payload = {"reason": "First revocation"}

    first = client.post(
        f"/legal-basis/{legal_basis['id']}/revoke",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 200

    second = client.post(
        f"/legal-basis/{legal_basis['id']}/revoke",
        json={"reason": "Second revocation"},
        headers=headers,
    )
    assert second.status_code == 409

    stored = (
        db_session.query(LegalBasis)
        .filter(LegalBasis.id == legal_basis["id"])
        .one()
    )
    assert stored.revoked_reason == "First revocation"


def test_expired_legal_basis_is_inactive(
    client, provider_token, db_session
):
    dataset_id = create_sample_dataset(db_session)
    legal_basis = create_legal_basis(client, provider_token, dataset_id)

    stored = (
        db_session.query(LegalBasis)
        .filter(LegalBasis.id == legal_basis["id"])
        .one()
    )
    stored.valid_until = date.today() - timedelta(days=1)
    db_session.commit()

    response = client.get(
        f"/datasets/{dataset_id}/legal-basis",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert response.status_code == 200
    entry = response.json()[0]
    assert entry["is_active"] is False
    assert entry["revoked_at"] is None


def test_legal_basis_without_expiry_is_active(
    client, provider_token, db_session
):
    dataset_id = create_sample_dataset(db_session)
    legal_basis = create_legal_basis(
        client, provider_token, dataset_id, valid_until=None
    )

    assert legal_basis["valid_until"] is None
    assert legal_basis["is_active"] is True


def test_contract_basis_can_be_revoked_via_api(
    client, provider_token, db_session
):
    """The API allows revoking any basis type; the UI limits it to consent."""
    dataset_id = create_sample_dataset(db_session)
    legal_basis = create_legal_basis(
        client, provider_token, dataset_id, type="contract"
    )

    response = client.post(
        f"/legal-basis/{legal_basis['id']}/revoke",
        json={"reason": "Contract terminated"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["type"] == "contract"
    assert response.json()["is_active"] is False
