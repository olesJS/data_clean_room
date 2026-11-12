"""Data exchange request lifecycle tests (SCRUM-56, UC-08)."""

from datetime import date, timedelta

from app.models import AuditLog, ExchangeRequest, LegalBasis

from .sprint3_helpers import (
    create_consumer,
    create_dataset,
    create_legal_basis,
    create_other_provider,
    prepare_published_dataset,
)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_request(client, token, dataset_id, purpose="analytics"):
    return client.post(
        "/api/exchange-requests",
        json={"dataset_id": dataset_id, "purpose": purpose},
        headers=_headers(token),
    )


def _approve(client, token, request_id, **payload):
    return client.post(
        f"/api/exchange-requests/{request_id}/approve",
        json=payload or None,
        headers=_headers(token),
    )


def _reject(client, token, request_id, comment="Not enough details"):
    return client.post(
        f"/api/exchange-requests/{request_id}/reject",
        json={"review_comment": comment},
        headers=_headers(token),
    )


def _download(client, token, request_id):
    return client.get(
        f"/api/exchange-requests/{request_id}/download",
        headers=_headers(token),
    )


def _audit_count(db_session, **filters) -> int:
    query = db_session.query(AuditLog)
    for field, value in filters.items():
        query = query.filter(getattr(AuditLog, field) == value)
    return query.count()


def test_consumer_creates_request_and_audit_event(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )

    before = _audit_count(db_session, action="REQUEST")
    response = _create_request(client, consumer_token, dataset.id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["dataset_id"] == dataset.id
    assert body["status"] == "Requested"
    assert body["purpose"] == "analytics"
    assert body["access_until"] is None
    assert body["dataset_version_id"] is not None
    assert _audit_count(db_session, action="REQUEST") == before + 1


def test_provider_role_cannot_create_request(
    client, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )

    response = _create_request(client, provider_token, dataset.id)

    assert response.status_code == 403


def test_unpublished_dataset_is_not_discoverable(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = create_dataset(db_session, tmp_path)

    response = _create_request(client, consumer_token, dataset.id)

    assert response.status_code == 404
    assert "Published dataset not found" in response.json()["detail"]


def test_duplicate_active_request_returns_409(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    assert _create_request(client, consumer_token, dataset.id).status_code == 201

    duplicate = _create_request(client, consumer_token, dataset.id)

    assert duplicate.status_code == 409


def test_purpose_mismatch_denies_request(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client,
        provider_token,
        db_session,
        tmp_path,
        purpose="research",
    )

    before = _audit_count(db_session, action="DENY")
    response = _create_request(client, consumer_token, dataset.id, "analytics")

    assert response.status_code == 403
    assert "legal_basis_invalid" in response.json()["detail"]
    assert "purpose_mismatch" in response.json()["detail"]
    assert _audit_count(db_session, action="DENY") == before + 1


def test_revoked_legal_basis_denies_new_request(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    basis = (
        db_session.query(LegalBasis)
        .filter(LegalBasis.dataset_id == dataset.id)
        .one()
    )
    revoked = client.post(
        f"/api/legal-basis/{basis.id}/revoke",
        json={"reason": "Consent withdrawn"},
        headers=_headers(provider_token),
    )
    assert revoked.status_code == 200, revoked.text

    response = _create_request(client, consumer_token, dataset.id)

    assert response.status_code == 403
    assert "revoked" in response.json()["detail"]


def test_visibility_is_scoped_by_role(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    requester = create_consumer(client, db_session)
    created = _create_request(client, requester, dataset.id).json()
    other_consumer = create_consumer(client, db_session)
    other_provider = create_other_provider(client, db_session)

    consumer_list = client.get(
        "/api/exchange-requests", headers=_headers(requester)
    ).json()
    assert [item["id"] for item in consumer_list] == [created["id"]]

    other_consumer_list = client.get(
        "/api/exchange-requests", headers=_headers(other_consumer)
    ).json()
    assert other_consumer_list == []

    provider_list = client.get(
        "/api/exchange-requests", headers=_headers(provider_token)
    ).json()
    assert created["id"] in [item["id"] for item in provider_list]
    assert all(
        item["dataset_id"] > 0 for item in provider_list
    )

    other_provider_list = client.get(
        "/api/exchange-requests", headers=_headers(other_provider)
    ).json()
    assert other_provider_list == []

    hidden = client.get(
        f"/api/exchange-requests/{created['id']}",
        headers=_headers(other_consumer),
    )
    assert hidden.status_code == 404


def test_steward_sees_all_requests_but_cannot_decide(
    client, consumer_token, steward_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()

    listed = client.get(
        "/api/exchange-requests", headers=_headers(steward_token)
    ).json()
    assert created["id"] in [item["id"] for item in listed]

    response = _approve(client, steward_token, created["id"])

    assert response.status_code == 403
    assert "owning DataProvider" in response.json()["detail"]


def test_owner_provider_approves_with_default_access_window(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()

    before = _audit_count(db_session, action="REQUEST_APPROVED")
    response = _approve(
        client, provider_token, created["id"], review_comment="Approved"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "Approved"
    assert body["review_comment"] == "Approved"
    assert body["reviewer_email"] == "provider@example.com"
    assert body["access_until"] == (
        date.today() + timedelta(days=30)
    ).isoformat()
    assert _audit_count(db_session, action="REQUEST_APPROVED") == before + 1


def test_approve_respects_explicit_access_until(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()
    access_until = (date.today() + timedelta(days=7)).isoformat()

    response = _approve(
        client, provider_token, created["id"], access_until=access_until
    )

    assert response.status_code == 200, response.text
    assert response.json()["access_until"] == access_until


def test_approve_rejects_past_access_until(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()

    response = _approve(
        client,
        provider_token,
        created["id"],
        access_until=(date.today() - timedelta(days=1)).isoformat(),
    )

    assert response.status_code == 422


def test_approve_denied_when_basis_revoked_after_request(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()
    basis = (
        db_session.query(LegalBasis)
        .filter(LegalBasis.dataset_id == dataset.id)
        .one()
    )
    client.post(
        f"/api/legal-basis/{basis.id}/revoke",
        json={"reason": "Withdrawn before approval"},
        headers=_headers(provider_token),
    )

    response = _approve(client, provider_token, created["id"])

    assert response.status_code == 403
    assert "revoked" in response.json()["detail"]


def test_double_decision_returns_409(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()
    assert _approve(client, provider_token, created["id"]).status_code == 200

    second_approve = _approve(client, provider_token, created["id"])
    reject = _reject(client, provider_token, created["id"])

    assert second_approve.status_code == 409
    assert reject.status_code == 409


def test_reject_requires_reason_and_records_decision(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()

    missing = client.post(
        f"/api/exchange-requests/{created['id']}/reject",
        json={},
        headers=_headers(provider_token),
    )
    assert missing.status_code == 422

    before = _audit_count(db_session, action="REQUEST_REJECTED")
    response = _reject(client, provider_token, created["id"], "Missing purpose")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "Rejected"
    assert body["review_comment"] == "Missing purpose"
    assert _audit_count(db_session, action="REQUEST_REJECTED") == before + 1

    retry = _create_request(client, consumer_token, dataset.id)
    assert retry.status_code == 201, retry.text


def test_download_requires_approval(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()

    before = _audit_count(db_session, action="DENY")
    response = _download(client, consumer_token, created["id"])

    assert response.status_code == 403
    assert response.json()["detail"] == "request_not_approved"
    assert _audit_count(db_session, action="DENY") == before + 1


def test_download_returns_clean_file_and_marks_downloaded(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()
    assert _approve(client, provider_token, created["id"]).status_code == 200

    before = _audit_count(db_session, action="DOWNLOAD")
    response = _download(client, consumer_token, created["id"])

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "Іван Петренко" not in response.text
    assert "Марія Коваль" not in response.text
    assert "***" in response.text
    assert _audit_count(db_session, action="DOWNLOAD") == before + 1

    stored = db_session.get(ExchangeRequest, created["id"])
    assert stored.status == "Downloaded"
    assert stored.downloaded_at is not None

    repeated = _download(client, consumer_token, created["id"])
    assert repeated.status_code == 200


def test_steward_cannot_download_someone_elses_file(
    client, consumer_token, steward_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()
    assert _approve(client, provider_token, created["id"]).status_code == 200

    response = _download(client, steward_token, created["id"])

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the requester can download this dataset"


def test_expired_access_is_denied_and_marked(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()
    assert _approve(client, provider_token, created["id"]).status_code == 200

    stored = db_session.get(ExchangeRequest, created["id"])
    stored.access_until = date.today() - timedelta(days=1)
    db_session.commit()

    response = _download(client, consumer_token, created["id"])

    assert response.status_code == 403
    assert response.json()["detail"] == "access_expired"
    db_session.refresh(stored)
    assert stored.status == "Expired"

    listed = client.get(
        "/api/exchange-requests", headers=_headers(consumer_token)
    ).json()
    assert listed[0]["status"] == "Expired"


def test_request_requires_clean_version(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = create_dataset(db_session, tmp_path, pii_findings=[])
    dataset.status = "published"
    db_session.commit()
    create_legal_basis(client, provider_token, dataset.id)

    response = _create_request(client, consumer_token, dataset.id)

    assert response.status_code == 409
    assert "clean dataset version" in response.json()["detail"]


def test_catalog_lists_only_published_datasets(
    client, consumer_token, provider_token, steward_token, db_session, tmp_path
):
    published = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    hidden = create_dataset(db_session, tmp_path)

    catalog = client.get("/api/catalog", headers=_headers(consumer_token))
    assert catalog.status_code == 200, catalog.text
    ids = [item["dataset_id"] for item in catalog.json()]
    assert published.id in ids
    assert hidden.id not in ids

    item = next(i for i in catalog.json() if i["dataset_id"] == published.id)
    assert item["clean_version_id"] is not None
    assert item["data_class"] == "Confidential"

    steward_catalog = client.get(
        "/api/catalog", headers=_headers(steward_token)
    )
    assert steward_catalog.status_code == 200

    provider_catalog = client.get(
        "/api/catalog", headers=_headers(provider_token)
    )
    assert provider_catalog.status_code == 403


def test_consumer_dataset_list_hides_unpublished(
    client, consumer_token, provider_token, db_session, tmp_path
):
    published = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    hidden = create_dataset(db_session, tmp_path)

    listed = client.get("/api/datasets", headers=_headers(consumer_token))
    assert listed.status_code == 200, listed.text
    ids = [item["id"] for item in listed.json()]
    assert published.id in ids
    assert hidden.id not in ids

    all_datasets = client.get("/api/datasets", headers=_headers(provider_token))
    provider_ids = [item["id"] for item in all_datasets.json()]
    assert hidden.id in provider_ids


def test_request_response_never_exposes_file_paths(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    body = _create_request(client, consumer_token, dataset.id).json()

    serialized = str(body)
    assert "file_path" not in serialized
    assert "storage" not in serialized
    assert dataset.file_path not in serialized


def test_admin_style_steward_does_not_bypass_ownership(
    client, consumer_token, steward_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()

    approve = _approve(client, steward_token, created["id"])
    reject = _reject(client, steward_token, created["id"])

    assert approve.status_code == 403
    assert reject.status_code == 403
    stored = db_session.get(ExchangeRequest, created["id"])
    db_session.refresh(stored)
    assert stored.status == "Requested"


def test_other_provider_cannot_see_or_approve(
    client, consumer_token, provider_token, db_session, tmp_path
):
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()
    other_provider = create_other_provider(client, db_session)

    visible = client.get(
        f"/api/exchange-requests/{created['id']}",
        headers=_headers(other_provider),
    )
    approve = _approve(client, other_provider, created["id"])
    listed = client.get(
        "/api/exchange-requests", headers=_headers(other_provider)
    )

    assert visible.status_code == 404
    assert approve.status_code == 404
    assert listed.json() == []


def test_owner_email_is_based_on_uploader_record(
    client, consumer_token, provider_token, db_session, tmp_path
):
    """Ownership follows Dataset.uploaded_by, not the reviewer role alone."""
    dataset = prepare_published_dataset(
        client, provider_token, db_session, tmp_path
    )
    created = _create_request(client, consumer_token, dataset.id).json()

    dataset.uploaded_by = "someone-else@example.com"
    db_session.commit()

    response = _approve(client, provider_token, created["id"])

    assert response.status_code == 404
