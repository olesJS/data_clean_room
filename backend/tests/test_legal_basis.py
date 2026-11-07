from app.auth import hash_password
from app.models import AuditLog, Dataset, User


def create_sample_dataset(db_session):
    dataset = Dataset(
        name="Test Payroll",
        original_filename="payroll.csv",
        file_path="storage/test.csv",
        file_size=1024,
        file_type="csv",
        columns={"id": "int", "name": "str"},
        row_count=10,
        uploaded_by="provider@example.com",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset.id


def test_create_and_get_legal_basis_success(
    client, provider_token, db_session
):
    dataset_id = create_sample_dataset(db_session)
    payload = {
        "type": "consent",
        "document_ref": "DOC-CONSENT-2026-001",
        "date": "2026-10-24",
    }

    post_res = client.post(
        f"/datasets/{dataset_id}/legal-basis",
        json=payload,
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert post_res.status_code == 201
    data = post_res.json()
    assert data["dataset_id"] == dataset_id
    assert data["type"] == "consent"
    assert data["document_ref"] == "DOC-CONSENT-2026-001"
    assert data["date"] == "2026-10-24"
    assert "id" in data
    assert data["entered_by"] > 0

    get_res = client.get(
        f"/datasets/{dataset_id}/legal-basis",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert get_res.status_code == 200
    entries = get_res.json()
    assert len(entries) == 1
    assert entries[0]["id"] == data["id"]
    assert entries[0]["document_ref"] == "DOC-CONSENT-2026-001"

    audit_record = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "CREATE_LEGAL_BASIS")
        .first()
    )
    assert audit_record is not None
    assert audit_record.result == "SUCCESS"
    assert f"dataset:{dataset_id}" in audit_record.object


def test_create_legal_basis_consumer_forbidden(
    client, consumer_token, db_session
):
    dataset_id = create_sample_dataset(db_session)
    res = client.post(
        f"/datasets/{dataset_id}/legal-basis",
        json={
            "type": "contract",
            "document_ref": "CONTRACT-101",
            "date": "2026-10-24",
        },
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert res.status_code == 403
    assert "Access forbidden" in res.json()["detail"]


def test_steward_can_create_legal_basis(client, steward_token, db_session):
    dataset_id = create_sample_dataset(db_session)
    res = client.post(
        f"/datasets/{dataset_id}/legal-basis",
        json={
            "type": "law",
            "document_ref": "LAW-2026-001",
            "date": "2026-10-24",
        },
        headers={"Authorization": f"Bearer {steward_token}"},
    )
    assert res.status_code == 201


def test_provider_non_owner_is_forbidden(client, db_session):
    dataset_id = create_sample_dataset(db_session)
    other_provider = User(
        email="other-provider@example.com",
        hashed_password=hash_password("password123"),
        role="DataProvider",
    )
    db_session.add(other_provider)
    db_session.commit()

    token_response = client.post(
        "/api/auth/login",
        json={
            "email": "other-provider@example.com",
            "password": "password123",
        },
    )
    assert token_response.status_code == 200

    res = client.get(
        f"/datasets/{dataset_id}/legal-basis",
        headers={
            "Authorization": f"Bearer {token_response.json()['access_token']}"
        },
    )
    assert res.status_code == 403


def test_consumer_cannot_get_legal_basis(client, consumer_token, db_session):
    dataset_id = create_sample_dataset(db_session)
    res = client.get(
        f"/datasets/{dataset_id}/legal-basis",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert res.status_code == 403


def test_create_legal_basis_dataset_not_found(client, provider_token):
    res = client.post(
        "/datasets/999999/legal-basis",
        json={
            "type": "law",
            "document_ref": "LAW-123",
            "date": "2026-10-24",
        },
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert res.status_code == 404
