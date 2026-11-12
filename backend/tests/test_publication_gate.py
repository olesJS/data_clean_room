"""Publication gate and anonymisation tests (SCRUM-55/57, UC-07)."""

from datetime import date, timedelta

import pandas as pd

from app.models import AnonymizationMethod, AuditLog, DatasetVersion

from .sprint3_helpers import (
    FUTURE_DATE,
    add_clean_version,
    anonymize,
    create_dataset,
    create_legal_basis,
    create_other_provider,
    publish,
)

MASK_METHODS = {"person_name": "mask", "ipn": "mask"}
HMAC_METHODS = {"person_name": "mask", "ipn": "hmac"}


def _gate(client, token, dataset_id, retention=None):
    params = {"retention_until": retention or FUTURE_DATE}
    return client.get(
        f"/api/datasets/{dataset_id}/publish/check",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_gate_requires_clean_version_and_processed_pii(
    client, provider_token, db_session, tmp_path
):
    dataset = create_dataset(db_session, tmp_path)

    response = _gate(client, provider_token, dataset.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["allowed"] is False
    codes = [reason["code"] for reason in body["reasons"]]
    assert "no_clean_version" in codes
    assert "pii_not_processed" in codes
    assert body["new_class"] == "Confidential"

    db_session.refresh(dataset)
    assert dataset.status == "uploaded"


def test_gate_reports_missing_pii_methods_even_with_clean_version(
    client, provider_token, db_session, tmp_path
):
    dataset = create_dataset(db_session, tmp_path)
    add_clean_version(db_session, dataset)

    body = _gate(client, provider_token, dataset.id).json()
    codes = [reason["code"] for reason in body["reasons"]]
    assert codes == ["pii_not_processed"]


def test_gate_requires_retention(client, provider_token, db_session, tmp_path):
    dataset = create_dataset(db_session, tmp_path, pii_findings=[])
    assert anonymize(client, provider_token, dataset.id).status_code == 200

    response = client.get(
        f"/api/datasets/{dataset.id}/publish/check",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    body = response.json()
    codes = [reason["code"] for reason in body["reasons"]]
    assert "retention_required" in codes


def test_preview_does_not_write_and_apply_creates_version(
    client, provider_token, db_session, tmp_path
):
    dataset = create_dataset(db_session, tmp_path)

    audit_before = db_session.query(AuditLog).count()
    preview = client.post(
        f"/api/datasets/{dataset.id}/anonymize/preview",
        json={"methods": MASK_METHODS},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert preview.status_code == 200, preview.text
    assert db_session.query(AuditLog).count() == audit_before
    preview_body = preview.json()
    assert preview_body["pii_columns_count"] == 2
    assert preview_body["estimated_class"] == "Confidential"
    methods = {
        item["column_name"]: item["method"]
        for item in preview_body["columns"]
    }
    assert methods == MASK_METHODS
    assert (
        db_session.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id)
        .count()
        == 0
    )
    assert (
        db_session.query(AnonymizationMethod)
        .filter(AnonymizationMethod.dataset_id == dataset.id)
        .count()
        == 0
    )

    applied = anonymize(client, provider_token, dataset.id, MASK_METHODS)
    assert applied.status_code == 200, applied.text
    applied_body = applied.json()
    assert applied_body["kind"] == "clean"
    assert applied_body["version_number"] == 1
    assert len(applied_body["sha256"]) == 64

    version = db_session.get(DatasetVersion, applied_body["version_id"])
    assert version is not None
    assert version.file_path
    import os

    assert os.path.isfile(version.file_path)
    assert (
        db_session.query(AnonymizationMethod)
        .filter(AnonymizationMethod.dataset_id == dataset.id)
        .count()
        == 2
    )

    clean_frame = pd.read_csv(version.file_path)
    assert set(clean_frame["person_name"]) == {"***"}
    assert set(clean_frame["ipn"]) == {"***"}
    assert set(clean_frame["amount"]) == {100, 200}

    versions = client.get(
        f"/api/datasets/{dataset.id}/versions",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert versions.status_code == 200
    assert len(versions.json()) == 1


def test_publish_rejects_missing_retention_and_audits_deny(
    client, provider_token, steward_token, db_session, tmp_path
):
    dataset = create_dataset(db_session, tmp_path)
    assert anonymize(
        client, provider_token, dataset.id, MASK_METHODS
    ).status_code == 200

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    response = publish(client, provider_token, dataset.id, yesterday)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["allowed"] is False
    codes = [reason["code"] for reason in body["reasons"]]
    assert codes == ["retention_required"]

    db_session.refresh(dataset)
    assert dataset.status == "uploaded"

    audit = client.get(
        "/api/audit", headers={"Authorization": f"Bearer {steward_token}"}
    )
    deny_events = [
        item for item in audit.json() if item["action"] == "DENY"
    ]
    assert deny_events


def test_publish_masked_dataset_is_confidential(
    client, provider_token, db_session, tmp_path
):
    dataset = create_dataset(db_session, tmp_path)
    assert anonymize(
        client, provider_token, dataset.id, MASK_METHODS
    ).status_code == 200

    response = publish(client, provider_token, dataset.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "published"
    assert body["data_class"] == "Confidential"
    assert body["retention_until"] == (
        date.today() + timedelta(days=180)
    ).isoformat()

    db_session.refresh(dataset)
    assert dataset.status == "published"
    assert dataset.published_by == "provider@example.com"
    assert dataset.data_class == "Confidential"


def test_hmac_requires_active_legal_basis(
    client, provider_token, db_session, tmp_path
):
    dataset = create_dataset(db_session, tmp_path)
    assert anonymize(
        client, provider_token, dataset.id, HMAC_METHODS
    ).status_code == 200

    denied = publish(client, provider_token, dataset.id)
    assert denied.status_code == 422, denied.text
    codes = [reason["code"] for reason in denied.json()["reasons"]]
    assert "hmac_without_legal_basis" in codes

    create_legal_basis(client, provider_token, dataset.id)
    allowed = publish(client, provider_token, dataset.id)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data_class"] == "Personal"

    version_id = allowed.json()["gate"]["clean_version_id"]
    version = db_session.get(DatasetVersion, version_id)
    clean_frame = pd.read_csv(version.file_path)
    assert all(
        str(value).startswith("hmac_") for value in clean_frame["ipn"]
    )


def test_publishing_without_pii_is_internal(
    client, provider_token, db_session, tmp_path
):
    dataset = create_dataset(db_session, tmp_path, pii_findings=[])
    assert anonymize(client, provider_token, dataset.id).status_code == 200

    response = publish(client, provider_token, dataset.id)
    assert response.status_code == 200, response.text
    assert response.json()["data_class"] == "Internal"


def test_publish_is_owner_only(
    client,
    provider_token,
    consumer_token,
    steward_token,
    db_session,
    tmp_path,
):
    dataset = create_dataset(db_session, tmp_path)
    assert anonymize(
        client, provider_token, dataset.id, MASK_METHODS
    ).status_code == 200

    consumer = publish(client, consumer_token, dataset.id)
    assert consumer.status_code == 403

    steward = publish(client, steward_token, dataset.id)
    assert steward.status_code == 403

    other_token = create_other_provider(client, db_session)
    foreign = publish(client, other_token, dataset.id)
    assert foreign.status_code == 404


def test_publish_twice_returns_conflict(
    client, provider_token, db_session, tmp_path
):
    dataset = create_dataset(db_session, tmp_path)
    assert anonymize(
        client, provider_token, dataset.id, MASK_METHODS
    ).status_code == 200
    assert publish(client, provider_token, dataset.id).status_code == 200

    second = publish(client, provider_token, dataset.id)
    assert second.status_code == 409
