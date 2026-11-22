"""Publication gate and publication endpoint tests (SCRUM-57, UC-07)."""

import hashlib
import uuid
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from app.auth import create_access_token, hash_password
from app.models import (
    AnonymizationMethod,
    AnonymizationMethodType,
    AuditLog,
    Dataset,
    DatasetVersion,
    DatasetVersionKind,
    LegalBasis,
    LegalBasisPurpose,
    LegalBasisType,
    User,
    utc_now,
)
from app.services.publication_gate import evaluate

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FUTURE_DATE = date.today() + timedelta(days=365)
PAST_DATE = date.today() - timedelta(days=1)

DEFAULT_PII = [
    {
        "column_name": "person_name",
        "pii_type": "person_name",
        "confidence": 0.95,
        "user_confirmed": None,
        "corrected_pii_type": None,
    },
    {
        "column_name": "ipn",
        "pii_type": "ipn",
        "confidence": 0.95,
        "user_confirmed": None,
        "corrected_pii_type": None,
    },
]

MASK_METHODS = {"person_name": "mask", "ipn": "mask"}
HMAC_METHODS = {"person_name": "mask", "ipn": "hmac"}


def _create_dataset(
    db_session,
    tmp_path,
    *,
    pii_findings=None,
    data_class="Personal",
):
    path = tmp_path / f"dataset-{uuid.uuid4().hex}.csv"
    path.write_text(
        "person_name,ipn,amount\nІван Петренко,1234567890,100\n",
        encoding="utf-8",
    )
    dataset = Dataset(
        name=f"Gate {uuid.uuid4().hex[:8]}",
        original_filename=path.name,
        file_path=str(path),
        file_size=path.stat().st_size,
        file_type="csv",
        columns={"person_name": "object", "ipn": "object", "amount": "int64"},
        row_count=1,
        uploaded_by="provider@example.com",
        data_class=data_class,
        pii_json=DEFAULT_PII if pii_findings is None else pii_findings,
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


def _add_clean_version(db_session, dataset, tmp_path):
    path = tmp_path / f"clean-{dataset.id}-{uuid.uuid4().hex}.csv"
    path.write_text(
        "person_name,ipn,amount\n***,******7890,100\n",
        encoding="utf-8",
    )
    version = DatasetVersion(
        dataset_id=dataset.id,
        kind=DatasetVersionKind.CLEAN,
        file_path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        row_count=1,
    )
    db_session.add(version)
    db_session.commit()
    db_session.refresh(version)
    return version


def _add_methods(db_session, dataset, methods):
    for column, method in methods.items():
        db_session.add(
            AnonymizationMethod(
                dataset_id=dataset.id,
                column_name=column,
                method=AnonymizationMethodType(method),
            )
        )
    db_session.commit()


def _add_legal_basis(
    db_session,
    dataset,
    *,
    purpose=LegalBasisPurpose.RESEARCH,
    valid_until=None,
    revoked=False,
):
    user = db_session.query(User).filter(User.email == "steward@example.com").one()
    basis = LegalBasis(
        dataset_id=dataset.id,
        type=LegalBasisType.CONSENT,
        document_ref=f"DOC-{uuid.uuid4().hex[:8]}",
        date=date.today(),
        purpose=purpose,
        valid_until=valid_until,
        entered_by=user.id,
        revoked_at=utc_now() if revoked else None,
    )
    db_session.add(basis)
    db_session.commit()
    db_session.refresh(basis)
    return basis


def _headers(client, email="provider@example.com"):
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _check(client, headers, dataset_id, retention=FUTURE_DATE):
    return client.get(
        f"/api/datasets/{dataset_id}/publish/check",
        params={"retention_until": retention.isoformat()},
        headers=headers,
    )


def _publish(client, headers, dataset_id, retention=FUTURE_DATE):
    return client.post(
        f"/api/datasets/{dataset_id}/publish",
        json={"retention_until": retention.isoformat()},
        headers=headers,
    )


def _codes(response):
    return [reason["code"] for reason in response.json()["reasons"]]


def _audit_rows(db_session, action, result=None, contains=None):
    db_session.expire_all()
    query = db_session.query(AuditLog).filter(AuditLog.action == action)
    if result is not None:
        query = query.filter(AuditLog.result == result)
    rows = query.order_by(AuditLog.id).all()
    if contains is not None:
        rows = [row for row in rows if contains in row.object]
    return rows


# ---------------------------------------------------------------------------
# Gate service
# ---------------------------------------------------------------------------


def test_gate_requires_clean_version_and_processed_pii(db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path)

    result = evaluate(db_session, dataset, retention_until=FUTURE_DATE)

    assert result.allowed is False
    assert result.reason_codes() == ["no_clean_version", "pii_not_processed"]
    assert result.missing_columns == ["ipn", "person_name"]
    assert result.hmac_columns == []
    assert result.new_class == "Confidential"
    assert result.clean_version_id is None


def test_gate_requires_pii_methods_even_with_clean_version(db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path)
    _add_clean_version(db_session, dataset, tmp_path)

    result = evaluate(db_session, dataset, retention_until=FUTURE_DATE)

    assert result.allowed is False
    assert result.reason_codes() == ["pii_not_processed"]
    assert result.missing_columns == ["ipn", "person_name"]


def test_gate_requires_retention_date(db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path, pii_findings=[])
    _add_clean_version(db_session, dataset, tmp_path)

    result = evaluate(db_session, dataset)

    assert result.allowed is False
    assert result.reason_codes() == ["retention_required"]


def test_gate_rejects_past_retention_date(db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path, pii_findings=[])
    _add_clean_version(db_session, dataset, tmp_path)

    result = evaluate(db_session, dataset, retention_until=PAST_DATE)

    assert result.allowed is False
    assert result.reason_codes() == ["retention_required"]


def test_gate_allows_masked_dataset_as_confidential(db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path)
    version = _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, MASK_METHODS)

    result = evaluate(db_session, dataset, retention_until=FUTURE_DATE)

    assert result.allowed is True
    assert result.reasons == []
    assert result.new_class == "Confidential"
    assert result.missing_columns == []
    assert result.hmac_columns == []
    assert result.clean_version_id == version.id


def test_gate_denies_hmac_without_legal_basis(db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path)
    _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, HMAC_METHODS)

    result = evaluate(db_session, dataset, retention_until=FUTURE_DATE)

    assert result.allowed is False
    assert result.reason_codes() == ["hmac_without_legal_basis"]
    assert result.hmac_columns == ["ipn"]
    assert result.new_class == "Personal"
    reason = result.reasons[0]
    assert reason["legal_basis_reason"] == "no_legal_basis"


def test_gate_allows_hmac_with_active_legal_basis(db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path)
    _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, HMAC_METHODS)
    _add_legal_basis(db_session, dataset, valid_until=FUTURE_DATE)

    result = evaluate(db_session, dataset, retention_until=FUTURE_DATE)

    assert result.allowed is True
    assert result.new_class == "Personal"
    assert result.hmac_columns == ["ipn"]


def test_gate_denies_hmac_with_revoked_legal_basis(db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path)
    _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, HMAC_METHODS)
    _add_legal_basis(db_session, dataset, revoked=True)

    result = evaluate(db_session, dataset, retention_until=FUTURE_DATE)

    assert result.allowed is False
    assert result.reason_codes() == ["hmac_without_legal_basis"]
    assert result.reasons[0]["legal_basis_reason"] == "revoked"


def test_gate_allows_dataset_without_pii_as_internal(db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path, pii_findings=[])
    _add_clean_version(db_session, dataset, tmp_path)

    result = evaluate(db_session, dataset, retention_until=FUTURE_DATE)

    assert result.allowed is True
    assert result.new_class == "Internal"


def test_gate_ignores_rejected_pii_findings(db_session, tmp_path):
    findings = [
        {
            "column_name": "person_name",
            "pii_type": "person_name",
            "confidence": 0.95,
            "user_confirmed": False,
            "corrected_pii_type": None,
        }
    ]
    dataset = _create_dataset(db_session, tmp_path, pii_findings=findings)
    _add_clean_version(db_session, dataset, tmp_path)

    result = evaluate(db_session, dataset, retention_until=FUTURE_DATE)

    assert result.allowed is True
    assert result.missing_columns == []
    assert result.new_class == "Internal"


def test_gate_uses_corrected_pii_type(db_session, tmp_path):
    findings = [
        {
            "column_name": "person_name",
            "pii_type": None,
            "confidence": 0.0,
            "user_confirmed": True,
            "corrected_pii_type": "person_name",
        }
    ]
    dataset = _create_dataset(db_session, tmp_path, pii_findings=findings)
    _add_clean_version(db_session, dataset, tmp_path)

    result = evaluate(db_session, dataset, retention_until=FUTURE_DATE)

    assert result.allowed is False
    assert result.reason_codes() == ["pii_not_processed"]
    assert result.missing_columns == ["person_name"]


def test_gate_evaluation_does_not_mutate_dataset(db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path)
    version = _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, MASK_METHODS)
    before = (
        dataset.status,
        dataset.data_class,
        dataset.retention_until,
        dataset.published_at,
        dataset.published_by,
    )
    versions_before = (
        db_session.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id)
        .count()
    )
    methods_before = (
        db_session.query(AnonymizationMethod)
        .filter(AnonymizationMethod.dataset_id == dataset.id)
        .count()
    )

    result = evaluate(db_session, dataset, retention_until=FUTURE_DATE)

    db_session.expire_all()
    db_session.refresh(dataset)
    assert result.allowed is True
    assert result.clean_version_id == version.id
    assert (
        dataset.status,
        dataset.data_class,
        dataset.retention_until,
        dataset.published_at,
        dataset.published_by,
    ) == before
    assert (
        db_session.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id)
        .count()
        == versions_before
    )
    assert (
        db_session.query(AnonymizationMethod)
        .filter(AnonymizationMethod.dataset_id == dataset.id)
        .count()
        == methods_before
    )


# ---------------------------------------------------------------------------
# Publish API
# ---------------------------------------------------------------------------


def test_check_endpoint_returns_gate_and_does_not_mutate(
    client, provider_token, db_session, tmp_path
):
    dataset = _create_dataset(db_session, tmp_path)
    headers = {"Authorization": f"Bearer {provider_token}"}
    versions_before = (
        db_session.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id)
        .count()
    )
    methods_before = (
        db_session.query(AnonymizationMethod)
        .filter(AnonymizationMethod.dataset_id == dataset.id)
        .count()
    )

    response = _check(client, headers, dataset.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["allowed"] is False
    assert [reason["code"] for reason in body["reasons"]] == [
        "no_clean_version",
        "pii_not_processed",
    ]
    assert body["new_class"] == "Confidential"
    assert body["missing_columns"] == ["ipn", "person_name"]
    assert body["clean_version_id"] is None

    db_session.expire_all()
    db_session.refresh(dataset)
    assert dataset.status == "uploaded"
    assert dataset.data_class == "Personal"
    assert dataset.retention_until is None
    assert dataset.published_at is None
    assert dataset.published_by is None
    assert (
        db_session.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id)
        .count()
        == versions_before
    )
    assert (
        db_session.query(AnonymizationMethod)
        .filter(AnonymizationMethod.dataset_id == dataset.id)
        .count()
        == methods_before
    )
    audit = _audit_rows(
        db_session,
        "PUBLISH_CHECK",
        result="SUCCESS",
        contains=f"dataset:{dataset.id}",
    )
    assert len(audit) == 1
    assert audit[0].object.endswith("allowed:False")


def test_check_reports_ready_dataset(client, provider_token, db_session, tmp_path):
    dataset = _create_dataset(db_session, tmp_path)
    version = _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, MASK_METHODS)
    headers = {"Authorization": f"Bearer {provider_token}"}

    response = _check(client, headers, dataset.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["allowed"] is True
    assert body["reasons"] == []
    assert body["new_class"] == "Confidential"
    assert body["clean_version_id"] == version.id
    audit = _audit_rows(
        db_session,
        "PUBLISH_CHECK",
        result="SUCCESS",
        contains=f"dataset:{dataset.id}",
    )
    assert len(audit) == 1
    assert audit[0].object.endswith("allowed:True")


def test_publish_denies_past_retention_and_audits_deny(
    client, provider_token, db_session, tmp_path
):
    dataset = _create_dataset(db_session, tmp_path)
    _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, MASK_METHODS)
    headers = {"Authorization": f"Bearer {provider_token}"}

    response = _publish(client, headers, dataset.id, retention=PAST_DATE)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["allowed"] is False
    assert [reason["code"] for reason in body["reasons"]] == ["retention_required"]

    db_session.expire_all()
    db_session.refresh(dataset)
    assert dataset.status == "uploaded"
    assert dataset.published_at is None
    audit = _audit_rows(
        db_session,
        "DENY",
        result="DENY",
        contains=f"dataset:{dataset.id}:publish:reasons:retention_required",
    )
    assert len(audit) == 1


def test_publish_masked_dataset_as_confidential(
    client, provider_token, db_session, tmp_path
):
    dataset = _create_dataset(db_session, tmp_path)
    version = _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, MASK_METHODS)
    headers = {"Authorization": f"Bearer {provider_token}"}

    response = _publish(client, headers, dataset.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dataset_id"] == dataset.id
    assert body["status"] == "published"
    assert body["data_class"] == "Confidential"
    assert body["published_by"] == "provider@example.com"
    assert body["retention_until"] == FUTURE_DATE.isoformat()
    assert body["gate"]["allowed"] is True
    assert body["gate"]["new_class"] == "Confidential"
    assert body["gate"]["clean_version_id"] == version.id

    db_session.expire_all()
    db_session.refresh(dataset)
    assert dataset.status == "published"
    assert dataset.data_class == "Confidential"
    assert dataset.published_by == "provider@example.com"
    assert dataset.retention_until == FUTURE_DATE
    assert dataset.published_at is not None
    audit = _audit_rows(
        db_session,
        "PUBLISH",
        result="SUCCESS",
        contains=f"dataset:{dataset.id}:class:Confidential",
    )
    assert len(audit) == 1


def test_publish_without_pii_is_internal(
    client, provider_token, db_session, tmp_path
):
    dataset = _create_dataset(db_session, tmp_path, pii_findings=[])
    _add_clean_version(db_session, dataset, tmp_path)
    headers = {"Authorization": f"Bearer {provider_token}"}

    response = _publish(client, headers, dataset.id)

    assert response.status_code == 200, response.text
    assert response.json()["data_class"] == "Internal"


def test_publish_hmac_requires_active_legal_basis(
    client, provider_token, db_session, tmp_path
):
    dataset = _create_dataset(db_session, tmp_path)
    _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, HMAC_METHODS)
    headers = {"Authorization": f"Bearer {provider_token}"}

    denied = _publish(client, headers, dataset.id)
    assert denied.status_code == 422, denied.text
    assert _codes(denied) == ["hmac_without_legal_basis"]
    assert denied.json()["new_class"] == "Personal"
    assert denied.json()["hmac_columns"] == ["ipn"]

    _add_legal_basis(db_session, dataset, valid_until=FUTURE_DATE)

    allowed = _publish(client, headers, dataset.id)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data_class"] == "Personal"
    assert allowed.json()["gate"]["hmac_columns"] == ["ipn"]


def test_publish_twice_returns_conflict(
    client, provider_token, db_session, tmp_path
):
    dataset = _create_dataset(db_session, tmp_path)
    _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, MASK_METHODS)
    headers = {"Authorization": f"Bearer {provider_token}"}

    assert _publish(client, headers, dataset.id).status_code == 200

    second = _publish(client, headers, dataset.id)

    assert second.status_code == 409, second.text
    audit = _audit_rows(
        db_session,
        "PUBLISH",
        result="CONFLICT",
        contains=f"dataset:{dataset.id}",
    )
    assert len(audit) == 1


@pytest.mark.parametrize("role", ["consumer", "steward"])
def test_publish_and_check_reject_non_provider_roles(
    client, provider_token, consumer_token, steward_token, db_session, tmp_path, role
):
    dataset = _create_dataset(db_session, tmp_path)
    _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, MASK_METHODS)
    token = consumer_token if role == "consumer" else steward_token
    headers = {"Authorization": f"Bearer {token}"}

    assert _check(client, headers, dataset.id).status_code == 403
    assert _publish(client, headers, dataset.id).status_code == 403


def test_publish_and_check_hide_foreign_provider_dataset(
    client, provider_token, db_session, tmp_path
):
    dataset = _create_dataset(db_session, tmp_path)
    _add_clean_version(db_session, dataset, tmp_path)
    _add_methods(db_session, dataset, MASK_METHODS)
    other = User(
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("password123"),
        role="DataProvider",
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    token = create_access_token({"sub": other.email})
    headers = {"Authorization": f"Bearer {token}"}

    assert _check(client, headers, dataset.id).status_code == 404
    assert _publish(client, headers, dataset.id).status_code == 404


# ---------------------------------------------------------------------------
# End-to-end flow with the real anonymisation, catalog and exchange endpoints
# ---------------------------------------------------------------------------


def test_full_publication_and_exchange_flow(
    client, provider_token, consumer_token, db_session
):
    provider_headers = {"Authorization": f"Bearer {provider_token}"}
    consumer_headers = {"Authorization": f"Bearer {consumer_token}"}
    raw_bytes = (DATA_DIR / "payroll.csv").read_bytes()

    upload = client.post(
        "/api/datasets",
        files={"file": ("payroll.csv", raw_bytes, "text/csv")},
        data={"name": "SCRUM-57 Payroll"},
        headers=provider_headers,
    )
    assert upload.status_code == 201, upload.text
    dataset_id = upload.json()["id"]

    catalog_before = client.get("/api/catalog", headers=consumer_headers)
    assert catalog_before.status_code == 200
    assert all(item["id"] != dataset_id for item in catalog_before.json())

    check_before = _check(client, provider_headers, dataset_id)
    assert check_before.status_code == 200, check_before.text
    assert "no_clean_version" in _codes(check_before)

    pii = client.get(
        f"/api/datasets/{dataset_id}/pii", headers=provider_headers
    )
    assert pii.status_code == 200, pii.text
    methods = {
        finding["column_name"]: "mask"
        for finding in pii.json()["findings"]
        if finding.get("column_name")
    }
    assert methods

    anonymize = client.post(
        f"/api/datasets/{dataset_id}/anonymize",
        json={"columns": methods},
        headers=provider_headers,
    )
    assert anonymize.status_code == 200, anonymize.text

    check_ready = _check(client, provider_headers, dataset_id)
    assert check_ready.status_code == 200, check_ready.text
    assert check_ready.json()["allowed"] is True
    assert check_ready.json()["new_class"] == "Confidential"

    published = _publish(client, provider_headers, dataset_id)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert published.json()["data_class"] == "Confidential"

    catalog_after = client.get("/api/catalog", headers=consumer_headers)
    assert catalog_after.status_code == 200
    assert any(item["id"] == dataset_id for item in catalog_after.json())

    legal = client.post(
        f"/api/datasets/{dataset_id}/legal-basis",
        json={
            "type": "consent",
            "document_ref": "DOC-SCRUM-57",
            "date": date.today().isoformat(),
            "purpose": "research",
            "valid_until": FUTURE_DATE.isoformat(),
        },
        headers=provider_headers,
    )
    assert legal.status_code == 201, legal.text

    exchange = client.post(
        "/api/requests",
        json={
            "dataset_id": dataset_id,
            "purpose": "Academic research on payroll statistics",
        },
        headers=consumer_headers,
    )
    assert exchange.status_code == 201, exchange.text
    request_id = exchange.json()["id"]

    approve = client.post(
        f"/api/requests/{request_id}/approve",
        json={"comment": "Approved for research"},
        headers=provider_headers,
    )
    assert approve.status_code == 200, approve.text

    download = client.get(
        f"/api/requests/{request_id}/download", headers=consumer_headers
    )
    assert download.status_code == 200, download.text
    content = download.content
    assert b"******" in content

    raw = pd.read_csv(DATA_DIR / "payroll.csv")
    assert str(raw["full_name"].iloc[0]).encode("utf-8") not in content
    assert str(raw["ipn"].iloc[0]).encode("utf-8") not in content
