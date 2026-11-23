"""Негативні сценарії обміну, анонімізації та наскрізний JSON-потік (SCRUM-68).

Кейси з docs/testing/test-cases-uc06-uc10.md, які ще не мали автотестів
(розділ 11 цього документа). Ідентифікатор кейсу вказано в docstring тесту.

БД спільна для всієї тестової сесії, тому кожен тест створює власні набори
й запити з унікальними іменами і рахує записи аудиту відносно стартового id.
"""

import json
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.models import (
    AuditLog,
    Dataset,
    DatasetVersion,
    DatasetVersionKind,
    ExchangeRequest,
    ExchangeRequestStatus,
    LegalBasis,
    LegalBasisPurpose,
    LegalBasisType,
    User,
    utc_now,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FUTURE = date.today() + timedelta(days=365)
PURPOSE = "analytics: regional payment statistics"
MISSING_ID = 999_999


# ---------------------------------------------------------------------------
# Допоміжні функції
# ---------------------------------------------------------------------------


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _last_audit_id(db_session):
    db_session.expire_all()
    last = db_session.query(AuditLog).order_by(AuditLog.id.desc()).first()
    return last.id if last else 0


def _audit_since(db_session, start_id, **filters):
    db_session.expire_all()
    return (
        db_session.query(AuditLog)
        .filter(AuditLog.id > start_id)
        .filter_by(**filters)
        .order_by(AuditLog.id.asc())
        .all()
    )


def _make_dataset(db_session, tmp_path, *, status="published", basis="active"):
    """Набір з чистою версією.

    basis: "active" | "revoked" | "expired" | None — стан правової підстави
    з метою analytics.
    """
    raw = tmp_path / f"neg-raw-{uuid.uuid4().hex}.csv"
    raw.write_text("ipn,amount\n1234567890,5000\n", encoding="utf-8")
    dataset = Dataset(
        name=f"Negative {uuid.uuid4().hex[:8]}",
        original_filename=raw.name,
        file_path=str(raw),
        file_size=raw.stat().st_size,
        file_type="csv",
        columns={"ipn": "object", "amount": "int64"},
        row_count=1,
        uploaded_by="provider@example.com",
        data_class="Confidential",
        status=status,
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)

    clean = tmp_path / f"neg-clean-{dataset.id}.csv"
    clean.write_text("ipn,amount\n******7890,5000\n", encoding="utf-8")
    db_session.add(
        DatasetVersion(
            dataset_id=dataset.id,
            kind=DatasetVersionKind.CLEAN,
            file_path=str(clean),
            sha256=uuid.uuid4().hex,
            row_count=1,
        )
    )

    if basis is not None:
        steward = db_session.query(User).filter_by(role="DataSteward").first()
        entry = LegalBasis(
            dataset_id=dataset.id,
            type=LegalBasisType.CONSENT,
            document_ref=f"NEG-{uuid.uuid4().hex[:6]}",
            date=date.today() - timedelta(days=30),
            purpose=LegalBasisPurpose.ANALYTICS,
            valid_until=FUTURE,
            entered_by=steward.id,
        )
        if basis == "revoked":
            entry.revoked_at = utc_now()
            entry.revoked_by = steward.id
            entry.revoked_reason = "Data subject withdrew consent"
        elif basis == "expired":
            # Через API прострочену підставу створити не можна (валідатор),
            # тому пишемо напряму в БД.
            entry.valid_until = date.today() - timedelta(days=1)
        db_session.add(entry)

    db_session.commit()
    return dataset


def _create_request(client, consumer_token, dataset_id, purpose=PURPOSE):
    return client.post(
        "/api/requests",
        json={"dataset_id": dataset_id, "purpose": purpose},
        headers=_auth(consumer_token),
    )


def _review(client, provider_token, request_id, action, comment="test"):
    return client.post(
        f"/api/requests/{request_id}/{action}",
        json={"comment": comment},
        headers=_auth(provider_token),
    )


def _request_count(db_session, dataset_id):
    db_session.expire_all()
    return db_session.query(ExchangeRequest).filter_by(dataset_id=dataset_id).count()


# ---------------------------------------------------------------------------
# UC-08: подання запиту
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["uploaded", "missing"])
def test_request_for_unpublished_dataset_returns_404(
    client, db_session, tmp_path, consumer_token, state
):
    """TC-N7.1: запит на неопублікований або неіснуючий набір -> 404 + аудит."""
    if state == "missing":
        dataset_id = MISSING_ID
    else:
        dataset_id = _make_dataset(db_session, tmp_path, status="uploaded").id
    start = _last_audit_id(db_session)

    res = _create_request(client, consumer_token, dataset_id)

    assert res.status_code == 404, res.text
    assert _request_count(db_session, dataset_id) == 0
    assert _audit_since(
        db_session,
        start,
        actor="consumer@example.com",
        action="REQUEST_DATASET",
        object=f"dataset:{dataset_id}",
        result="FAILURE",
    )


@pytest.mark.parametrize(
    "token_fixture,email",
    [
        ("provider_token", "provider@example.com"),
        ("steward_token", "steward@example.com"),
    ],
)
def test_only_consumer_can_create_request(
    client, db_session, tmp_path, request, token_fixture, email
):
    """TC-N7.2: Provider і Steward не подають запити -> 403 + ACCESS_DENIED."""
    dataset = _make_dataset(db_session, tmp_path)
    token = request.getfixturevalue(token_fixture)
    start = _last_audit_id(db_session)

    res = _create_request(client, token, dataset.id)

    assert res.status_code == 403, res.text
    assert _request_count(db_session, dataset.id) == 0
    assert _audit_since(
        db_session, start, actor=email, action="ACCESS_DENIED", result="FORBIDDEN"
    )


def test_duplicate_pending_request_returns_409(
    client, db_session, tmp_path, consumer_token
):
    """TC-N7.3: повторний запит, поки перший pending -> 409, запис один."""
    dataset = _make_dataset(db_session, tmp_path)

    first = _create_request(client, consumer_token, dataset.id)
    second = _create_request(client, consumer_token, dataset.id)

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert _request_count(db_session, dataset.id) == 1


@pytest.mark.parametrize("purpose", ["", "short", "123456789"])
def test_short_purpose_is_rejected(
    client, db_session, tmp_path, consumer_token, purpose
):
    """TC-N7.4: мета коротша за 10 символів -> 422, запит не створено."""
    dataset = _make_dataset(db_session, tmp_path)

    res = _create_request(client, consumer_token, dataset.id, purpose=purpose)

    assert res.status_code == 422, res.text
    assert _request_count(db_session, dataset.id) == 0


# ---------------------------------------------------------------------------
# UC-09: рішення власника
# ---------------------------------------------------------------------------


def test_rejected_request_cannot_be_downloaded(
    client, db_session, tmp_path, consumer_token, provider_token
):
    """TC-08.2: відхилення -> rejected, коментар, REQUEST_REJECTED; download -> 403."""
    dataset = _make_dataset(db_session, tmp_path)
    request_id = _create_request(client, consumer_token, dataset.id).json()["id"]
    start = _last_audit_id(db_session)

    rejected = _review(
        client, provider_token, request_id, "reject", comment="Мета не відповідає"
    )

    assert rejected.status_code == 200, rejected.text
    db_session.expire_all()
    req = db_session.get(ExchangeRequest, request_id)
    assert req.status == ExchangeRequestStatus.REJECTED
    assert req.review_comment == "Мета не відповідає"
    assert req.reviewed_at is not None
    assert _audit_since(
        db_session,
        start,
        actor="provider@example.com",
        action="REQUEST_REJECTED",
        result="SUCCESS",
    )

    download = client.get(
        f"/api/requests/{request_id}/download", headers=_auth(consumer_token)
    )

    assert download.status_code == 403, download.text
    assert _audit_since(
        db_session,
        start,
        actor="consumer@example.com",
        action="DENY",
        object=f"request:{request_id}",
    )


@pytest.mark.parametrize(
    "basis,reason",
    [(None, "no_legal_basis"), ("revoked", "revoked"), ("expired", "expired")],
)
def test_approve_without_valid_basis_is_blocked(
    client, db_session, tmp_path, consumer_token, provider_token, basis, reason
):
    """TC-N8.2 (a-c): немає, відкликана, прострочена підстава -> 409 + DENY."""
    dataset = _make_dataset(db_session, tmp_path, basis=basis)
    request_id = _create_request(client, consumer_token, dataset.id).json()["id"]
    start = _last_audit_id(db_session)

    res = _review(client, provider_token, request_id, "approve")

    assert res.status_code == 409, res.text
    assert reason in res.json()["detail"]
    db_session.expire_all()
    req = db_session.get(ExchangeRequest, request_id)
    assert req.status == ExchangeRequestStatus.PENDING
    assert req.reviewed_by is None
    assert _audit_since(
        db_session,
        start,
        actor="provider@example.com",
        action="DENY",
        object=f"request:{request_id}",
        result="FAILURE",
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("approve", "approve"),
        ("approve", "reject"),
        ("reject", "approve"),
        ("reject", "reject"),
    ],
)
def test_repeated_decision_returns_409(
    client, db_session, tmp_path, consumer_token, provider_token, first, second
):
    """TC-N8.3: рішення щодо вже розглянутого запиту -> 409, статус не змінюється."""
    dataset = _make_dataset(db_session, tmp_path)
    request_id = _create_request(client, consumer_token, dataset.id).json()["id"]
    assert _review(client, provider_token, request_id, first).status_code == 200
    db_session.expire_all()
    status_after_first = db_session.get(ExchangeRequest, request_id).status

    res = _review(client, provider_token, request_id, second)

    assert res.status_code == 409, res.text
    db_session.expire_all()
    assert db_session.get(ExchangeRequest, request_id).status == status_after_first


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_review_missing_request_returns_404(client, provider_token, action):
    """TC-N8.4: неіснуючий запит -> 404."""
    res = _review(client, provider_token, MISSING_ID, action)

    assert res.status_code == 404, res.text


# ---------------------------------------------------------------------------
# UC-10: завантаження
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("decision", [None, "reject"])
def test_download_of_not_approved_request_is_denied(
    client, db_session, tmp_path, consumer_token, provider_token, decision
):
    """TC-N9.1: pending або rejected -> 403 + DENY, файл не віддається."""
    dataset = _make_dataset(db_session, tmp_path)
    request_id = _create_request(client, consumer_token, dataset.id).json()["id"]
    if decision:
        assert _review(client, provider_token, request_id, decision).status_code == 200
    start = _last_audit_id(db_session)

    res = client.get(
        f"/api/requests/{request_id}/download", headers=_auth(consumer_token)
    )

    assert res.status_code == 403, res.text
    assert b"******7890" not in res.content
    assert _audit_since(
        db_session,
        start,
        actor="consumer@example.com",
        action="DENY",
        object=f"request:{request_id}",
        result="FORBIDDEN",
    )
    assert not _audit_since(db_session, start, action="DOWNLOAD")


@pytest.mark.xfail(
    strict=True,
    reason="SCRUM-74: повторне завантаження повертає 403 (UC-10, AC2)",
)
def test_repeat_download_is_allowed_while_basis_is_valid(
    client, db_session, tmp_path, consumer_token, provider_token
):
    """TC-N9.4: повторне завантаження при чинній підставі -> 200 і другий DOWNLOAD."""
    dataset = _make_dataset(db_session, tmp_path)
    request_id = _create_request(client, consumer_token, dataset.id).json()["id"]
    assert _review(client, provider_token, request_id, "approve").status_code == 200
    url = f"/api/requests/{request_id}/download"
    start = _last_audit_id(db_session)

    first = client.get(url, headers=_auth(consumer_token))
    second = client.get(url, headers=_auth(consumer_token))

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.content == first.content
    assert len(_audit_since(db_session, start, action="DOWNLOAD")) == 2


# ---------------------------------------------------------------------------
# UC-06: валідація запиту на анонімізацію
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "columns,detail",
    [
        ({"ipn": "encrypt"}, "Unknown anonymization method"),
        ({"no_such_column": "mask"}, "not found"),
        ({"amount": "generalize"}, "Generalization is not supported"),
    ],
    ids=["unknown-method", "missing-column", "generalize-unsupported"],
)
@pytest.mark.parametrize("endpoint", ["anonymize/preview", "anonymize"])
def test_invalid_anonymization_request_returns_422(
    client, db_session, tmp_path, provider_token, endpoint, columns, detail
):
    """TC-N5.3: невідомий метод / відсутня колонка / недопустиме узагальнення -> 422.

    Чиста версія і методи не змінюються, ANONYMIZE не пишеться в аудит.
    """
    dataset = _make_dataset(db_session, tmp_path, status="uploaded", basis=None)
    db_session.expire_all()
    clean_before = (
        db_session.query(DatasetVersion)
        .filter_by(dataset_id=dataset.id, kind=DatasetVersionKind.CLEAN)
        .one()
    )
    sha_before = clean_before.sha256
    start = _last_audit_id(db_session)

    res = client.post(
        f"/api/datasets/{dataset.id}/{endpoint}",
        json={"columns": columns},
        headers=_auth(provider_token),
    )

    assert res.status_code == 422, res.text
    assert detail in res.json()["detail"]
    db_session.expire_all()
    assert db_session.get(DatasetVersion, clean_before.id).sha256 == sha_before
    assert not _audit_since(db_session, start, action="ANONYMIZE")


# ---------------------------------------------------------------------------
# Наскрізний сценарій на JSON-наборі (TC-09.2, TC-E2E.1 крок 8)
# ---------------------------------------------------------------------------

E2E_AUDIT_SEQUENCE = [
    "PII_SCAN",
    "UPLOAD_DATASET",
    "ANONYMIZE",
    "PUBLISH",
    "CREATE_LEGAL_BASIS",
    "REQUEST",
    "REQUEST_APPROVED",
    "DOWNLOAD",
]


def test_json_dataset_end_to_end_without_raw_pii(
    client, db_session, provider_token, consumer_token
):
    """TC-09.2 + TC-E2E.1: customers.json від завантаження до скачування.

    Перевіряє: ім'я і MIME файлу, валідний JSON на 1000 записів, відсутність
    сирих email/телефонів/імен у файлі та в аудиті, порядок подій аудиту.
    """
    provider = _auth(provider_token)
    consumer = _auth(consumer_token)
    raw_bytes = (DATA_DIR / "customers.json").read_bytes()
    raw_records = json.loads(raw_bytes)
    name = f"SCRUM-68 Customers {uuid.uuid4().hex[:6]}"
    start = _last_audit_id(db_session)

    upload = client.post(
        "/api/datasets",
        files={"file": ("customers.json", raw_bytes, "application/json")},
        data={"name": name},
        headers=provider,
    )
    assert upload.status_code == 201, upload.text
    dataset_id = upload.json()["id"]

    pii = client.get(f"/api/datasets/{dataset_id}/pii", headers=provider)
    assert pii.status_code == 200, pii.text
    methods = {
        f["column_name"]: "mask" for f in pii.json()["findings"] if f.get("column_name")
    }
    assert {"full_name", "email", "phone"} <= set(methods), methods

    anonymized = client.post(
        f"/api/datasets/{dataset_id}/anonymize",
        json={"columns": methods},
        headers=provider,
    )
    assert anonymized.status_code == 200, anonymized.text

    published = client.post(
        f"/api/datasets/{dataset_id}/publish",
        json={"retention_until": FUTURE.isoformat()},
        headers=provider,
    )
    assert published.status_code == 200, published.text

    basis = client.post(
        f"/api/datasets/{dataset_id}/legal-basis",
        json={
            "type": "consent",
            "document_ref": "DOC-SCRUM-68",
            "date": date.today().isoformat(),
            "purpose": "analytics",
            "valid_until": FUTURE.isoformat(),
        },
        headers=provider,
    )
    assert basis.status_code == 201, basis.text

    created = _create_request(
        client, consumer_token, dataset_id, purpose="analytics: churn by city"
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    approved = _review(client, provider_token, request_id, "approve")
    assert approved.status_code == 200, approved.text

    download = client.get(f"/api/requests/{request_id}/download", headers=consumer)
    assert download.status_code == 200, download.text

    # Файл: ім'я, тип, вміст
    assert "_clean.json" in download.headers["content-disposition"]
    assert download.headers["content-type"].startswith("application/json")
    records = json.loads(download.content.decode("utf-8"))
    assert len(records) == len(raw_records) == 1000

    pii_columns = ("full_name", "email", "phone")
    raw_values = {
        r[col]
        for r in raw_records
        for col in pii_columns
        if isinstance(r.get(col), str) and len(r[col]) > 3  # без null і порожніх
    }
    clean_values = {
        r.get(col)
        for r in records
        for col in pii_columns
        if isinstance(r.get(col), str)
    }
    assert not raw_values & clean_values, "У завантаженому файлі є сирі PII"

    # Аудит: порядок подій і відсутність сирих PII
    events = _audit_since(db_session, start, result="SUCCESS")
    actions = [e.action for e in events if e.action in E2E_AUDIT_SEQUENCE]
    it = iter(actions)
    assert all(step in it for step in E2E_AUDIT_SEQUENCE), actions

    sample = {
        value
        for r in raw_records[:20]
        for value in (r.get("email"), r.get("phone"))
        if isinstance(value, str) and len(value) > 3
    }
    for event in _audit_since(db_session, start):
        assert not any(value in event.object for value in sample), event.object

    db_session.expire_all()
    req = db_session.get(ExchangeRequest, request_id)
    assert req.status == ExchangeRequestStatus.DOWNLOADED
