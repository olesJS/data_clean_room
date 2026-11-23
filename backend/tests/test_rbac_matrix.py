"""RBAC-матриця «ендпоінт × роль → код відповіді» (SCRUM-33).

Очікування взято з матриці доступу (docs/governance/data-governance-requirements.md,
розділ 3.2) та специфікацій UC. Таблиця з поясненнями: docs/testing/rbac-matrix.md.

Кожен рядок матриці є окремим тест-кейсом. Для кожної відмови (401, 403)
перевіряється запис у журналі аудиту. Новий ендпоінт додається рядком у MATRIX.

Частина 1 (MATRIX): ендпоінти без конкретного ресурсу в шляху.
Частина 2 (RESOURCE_MATRIX, SCRUM-51): ендпоінти з ідентифікатором набору,
правової підстави чи запиту. Для них є п'ята роль «чужий Provider», який
за рішенням PO №8 отримує 404, а не 403. Кожен кейс отримує свіжий набір
ресурсів (фікстура world), тож змінювальні виклики не впливають один на одного.
"""

import io
import uuid
from datetime import date, datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import func

from app.auth import ALGORITHM, SECRET_KEY, create_access_token, hash_password
from app.models import (
    AnonymizationMethod,
    AnonymizationMethodType,
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
)

ANON = "anon"
USERS = {
    "provider": "provider@example.com",
    "consumer": "consumer@example.com",
    "steward": "steward@example.com",
}

# (метод, шлях) -> {роль: очікуваний код}
MATRIX = {
    # Публічні ендпоінти
    ("GET", "/"): {ANON: 200, "provider": 200, "consumer": 200, "steward": 200},
    ("GET", "/health"): {ANON: 200, "provider": 200, "consumer": 200, "steward": 200},
    ("GET", "/health/db"): {
        ANON: 200,
        "provider": 200,
        "consumer": 200,
        "steward": 200,
    },
    # UC-01: власний профіль доступний будь-якому автентифікованому користувачу
    ("GET", "/api/auth/me"): {
        ANON: 401,
        "provider": 200,
        "consumer": 200,
        "steward": 200,
    },
    # UC-02: завантажує лише Data Provider (SCRUM-41)
    ("POST", "/datasets"): {
        ANON: 401,
        "provider": 201,
        "consumer": 403,
        "steward": 403,
    },
    ("POST", "/api/datasets"): {
        ANON: 401,
        "provider": 201,
        "consumer": 403,
        "steward": 403,
    },
    # Список наборів: будь-яка роль (вміст списку перевіряється окремо)
    ("GET", "/datasets"): {
        ANON: 401,
        "provider": 200,
        "consumer": 200,
        "steward": 200,
    },
    ("GET", "/api/datasets"): {
        ANON: 401,
        "provider": 200,
        "consumer": 200,
        "steward": 200,
    },
    # Журнал аудиту: лише Data Steward
    ("GET", "/audit"): {ANON: 401, "provider": 403, "consumer": 403, "steward": 200},
    ("GET", "/api/audit"): {
        ANON: 401,
        "provider": 403,
        "consumer": 403,
        "steward": 200,
    },
}

CASES = [
    (method, path, role, code)
    for (method, path), expected in MATRIX.items()
    for role, code in expected.items()
]
DENIED_CASES = [case for case in CASES if case[3] in (401, 403)]
PROTECTED_ENDPOINTS = [
    endpoint for endpoint, expected in MATRIX.items() if expected[ANON] == 401
]


def _case_id(case):
    method, path, role, code = case
    return f"{role}-{method}-{path}-{code}"


def _headers(role):
    if role == ANON:
        return {}
    token = create_access_token({"sub": USERS[role]})
    return {"Authorization": f"Bearer {token}"}


def _call(client, method, path, headers, filename="rbac.csv"):
    if method == "POST":
        files = {"file": (filename, io.BytesIO(b"id,val\n1,10\n"), "text/csv")}
        return client.post(path, headers=headers, files=files)
    return client.get(path, headers=headers)


def _audit_count(db, **filters):
    db.expire_all()
    return db.query(func.count(AuditLog.id)).filter_by(**filters).scalar()


# 1. Матриця: кожна роль на кожному ендпоінті отримує очікуваний код


@pytest.mark.parametrize(
    "method,path,role,expected", CASES, ids=[_case_id(c) for c in CASES]
)
def test_rbac_matrix(client, method, path, role, expected):
    res = _call(client, method, path, _headers(role))
    assert res.status_code == expected, (
        f"{role} {method} {path}: очікувано {expected}, "
        f"отримано {res.status_code} ({res.text})"
    )


# 2. Кожна відмова (401, 403) записується в журнал аудиту


@pytest.mark.parametrize(
    "method,path,role,expected",
    DENIED_CASES,
    ids=[_case_id(c) for c in DENIED_CASES],
)
def test_denied_request_is_audited(client, db_session, method, path, role, expected):
    if expected == 401:
        filters = {
            "actor": "unauthenticated",
            "action": "UNAUTHORIZED_ACCESS",
            "result": "UNAUTHORIZED",
            "object": path,
        }
    else:
        filters = {
            "actor": USERS[role],
            "action": "ACCESS_DENIED",
            "result": "FORBIDDEN",
            "object": path,
        }
    before = _audit_count(db_session, **filters)

    res = _call(client, method, path, _headers(role))

    assert res.status_code == expected
    assert _audit_count(db_session, **filters) == before + 1


# 3. Відхилене завантаження не створює набір


@pytest.mark.parametrize("path", ["/datasets", "/api/datasets"])
@pytest.mark.parametrize("role", [ANON, "consumer", "steward"])
def test_denied_upload_creates_no_dataset(client, db_session, role, path):
    filename = f"rbac-{uuid.uuid4().hex}.csv"

    res = _call(client, "POST", path, _headers(role), filename)

    assert res.status_code in (401, 403)
    db_session.expire_all()
    assert db_session.query(Dataset).filter_by(original_filename=filename).count() == 0


# 4. Невалідні токени відхиляються з 401 і записом в аудит


def _bad_token(kind):
    steward = USERS["steward"]
    if kind == "forged":
        return jwt.encode({"sub": steward}, "x" * 40, algorithm=ALGORITHM)
    if kind == "expired":
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        payload = {"sub": steward, "exp": past}
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    if kind == "no_subject":
        return create_access_token({"role": "DataSteward"})
    if kind == "unknown_user":
        return create_access_token({"sub": "ghost@example.com"})
    raise ValueError(kind)


BAD_TOKEN_ACTORS = {
    "forged": "invalid_token",
    "expired": "invalid_token",
    "no_subject": "invalid_token",
    "unknown_user": "ghost@example.com",
}


@pytest.mark.parametrize("kind", list(BAD_TOKEN_ACTORS))
@pytest.mark.parametrize(
    "method,path",
    PROTECTED_ENDPOINTS,
    ids=[f"{m}-{p}" for m, p in PROTECTED_ENDPOINTS],
)
def test_invalid_token_is_rejected_and_audited(client, db_session, method, path, kind):
    filters = {
        "actor": BAD_TOKEN_ACTORS[kind],
        "action": "UNAUTHORIZED_ACCESS",
        "result": "UNAUTHORIZED",
        "object": path,
    }
    before = _audit_count(db_session, **filters)
    headers = {"Authorization": f"Bearer {_bad_token(kind)}"}

    res = _call(client, method, path, headers)

    assert res.status_code == 401
    assert res.json() == {"detail": "Not authenticated"}
    assert _audit_count(db_session, **filters) == before + 1


# 5. Роль береться з БД, а не з токена (без підвищення привілеїв)


def test_role_claim_in_token_does_not_grant_access(client):
    token = create_access_token({"sub": USERS["consumer"], "role": "DataSteward"})

    res = client.get("/audit", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 403


# 6. Вміст списку наборів за матрицею 3.2


def test_provider_sees_only_own_datasets(client):
    filename = f"rbac-{uuid.uuid4().hex}.csv"
    up = _call(client, "POST", "/datasets", _headers("provider"), filename)
    assert up.status_code == 201

    listed = client.get("/datasets", headers=_headers("provider")).json()

    assert any(d["original_filename"] == filename for d in listed)
    assert all(d["uploaded_by"] == USERS["provider"] for d in listed)


def test_consumer_does_not_see_unpublished_datasets(client):
    filename = f"rbac-{uuid.uuid4().hex}.csv"
    up = _call(client, "POST", "/datasets", _headers("provider"), filename)
    assert up.status_code == 201

    listed = client.get("/datasets", headers=_headers("consumer")).json()

    assert all(d["original_filename"] != filename for d in listed)


# ---------------------------------------------------------------------------
# Частина 2. Ендпоінти з ресурсом у шляху (SCRUM-51)
# ---------------------------------------------------------------------------
#
# Ролі: ANON, "provider" (власник набору), OTHER (інший Data Provider),
# "consumer", "steward". Шлях і тіло містять плейсхолдери, які
# підставляються з фікстури world:
#   {draft}     набір у статусі uploaded з чистою версією і методами
#               анонімізації (готовий до публікації)
#   {published} опублікований набір з активною підставою analytics
#   {spare}     опублікований набір без запитів (для створення запиту)
#   {basis}     активна правова підстава набору {published}
#   {pending}   запит Consumer у статусі pending на {published}
#   {approved}  запит Consumer у статусі approved на {published}

OTHER = "other_provider"
RESOURCE_ROLES = (ANON, "provider", OTHER, "consumer", "steward")
FUTURE = (date.today() + timedelta(days=365)).isoformat()


def _codes(anon, owner, other, consumer, steward):
    return dict(zip(RESOURCE_ROLES, (anon, owner, other, consumer, steward)))


# (метод, шаблон шляху, тіло або None) -> коди для п'яти ролей
RESOURCE_MATRIX = {
    # UC-04/UC-05: профіль і PII читають власник і Steward
    ("GET", "/api/datasets/{draft}/profile", None): _codes(401, 200, 404, 403, 200),
    ("GET", "/api/datasets/{draft}/pii", None): _codes(401, 200, 404, 403, 200),
    # UC-05: класифікацію PII змінює лише власник (рішення PO №1)
    (
        "PATCH",
        "/api/datasets/{draft}/pii/email",
        (("user_confirmed", True),),
    ): _codes(401, 200, 404, 403, 403),
    # Якість даних: Consumer не бачить деталей
    ("GET", "/api/datasets/{draft}/quality-rules", None): _codes(
        401, 200, 404, 403, 200
    ),
    ("GET", "/api/datasets/{draft}/quality-violations", None): _codes(
        401, 200, 404, 403, 200
    ),
    # UC-13: правова підстава — власник або Steward
    (
        "POST",
        "/api/datasets/{draft}/legal-basis",
        (
            ("type", "consent"),
            ("document_ref", "RBAC-DOC-1"),
            ("date", date.today().isoformat()),
            ("purpose", "analytics"),
            ("valid_until", FUTURE),
        ),
    ): _codes(401, 201, 404, 403, 201),
    ("GET", "/api/datasets/{draft}/legal-basis", None): _codes(401, 200, 404, 403, 200),
    # UC-14: відкликання — власник або Steward
    (
        "POST",
        "/api/legal-basis/{basis}/revoke",
        (("reason", "RBAC matrix check"),),
    ): _codes(401, 200, 404, 403, 200),
    # UC-06: анонімізація — лише власник
    (
        "POST",
        "/api/datasets/{draft}/anonymize/preview",
        (("columns", (("email", "mask"),)),),
    ): _codes(401, 200, 404, 403, 403),
    (
        "POST",
        "/api/datasets/{draft}/anonymize",
        (("columns", (("email", "mask"),)),),
    ): _codes(401, 200, 404, 403, 403),
    # UC-07: перевірка і публікація — лише власник
    ("GET", "/api/datasets/{draft}/publish/check", None): _codes(
        401, 200, 404, 403, 403
    ),
    (
        "POST",
        "/api/datasets/{draft}/publish",
        (("retention_until", FUTURE),),
    ): _codes(401, 200, 404, 403, 403),
    # UC-08: каталог — будь-яка автентифікована роль
    ("GET", "/api/catalog", None): _codes(401, 200, 200, 200, 200),
    # UC-08: запит створює лише Consumer
    (
        "POST",
        "/api/requests",
        (("dataset_id", "{spare}"), ("purpose", "analytics of regional payments")),
    ): _codes(401, 403, 403, 201, 403),
    # Список запитів: кожна роль бачить свою частину
    ("GET", "/api/requests", None): _codes(401, 200, 200, 200, 200),
    # UC-09: рішення ухвалює власник набору (не Steward)
    (
        "POST",
        "/api/requests/{pending}/approve",
        (("comment", "ok"),),
    ): _codes(401, 200, 404, 403, 403),
    (
        "POST",
        "/api/requests/{pending}/reject",
        (("comment", "no"),),
    ): _codes(401, 200, 404, 403, 403),
    # UC-10: завантажує лише автор запиту; для інших запит «не існує»
    ("GET", "/api/requests/{approved}/download", None): _codes(401, 404, 404, 200, 404),
}

RESOURCE_CASES = [
    (method, path, body, role, code)
    for (method, path, body), expected in RESOURCE_MATRIX.items()
    for role, code in expected.items()
]
RESOURCE_DENIED_CASES = [c for c in RESOURCE_CASES if c[4] in (401, 403)]


def _resource_case_id(case):
    method, path, _body, role, code = case
    return f"{role}-{method}-{path}-{code}"


def _to_dict(pairs):
    """Кортежі пар (хешовані для ключів словника) -> звичайний dict."""
    if not isinstance(pairs, tuple):
        return pairs
    return {key: _to_dict(value) for key, value in pairs}


def _fill(value, world):
    if isinstance(value, str):
        filled = value.format(**world["ids"])
        if value.startswith("{") and value.endswith("}"):
            return int(filled)
        return filled
    if isinstance(value, dict):
        return {key: _fill(item, world) for key, item in value.items()}
    return value


def _resource_headers(role, world):
    if role == ANON:
        return {}
    email = world["other_email"] if role == OTHER else USERS[role]
    return {"Authorization": f"Bearer {create_access_token({'sub': email})}"}


def _resource_actor(role, world):
    if role == ANON:
        return "unauthenticated"
    return world["other_email"] if role == OTHER else USERS[role]


def _resource_call(client, method, path, body, headers):
    if method == "GET":
        return client.get(path, headers=headers)
    return client.request(method, path, headers=headers, json=body)


def _rbac_dataset(db_session, tmp_path, *, status):
    raw = tmp_path / f"rbac-raw-{uuid.uuid4().hex}.csv"
    raw.write_text(
        "person_name,email,amount\n"
        "Іван Петренко,ivan.petrenko@example.com,100\n"
        "Олена Коваль,olena.koval@example.com,200\n",
        encoding="utf-8",
    )
    dataset = Dataset(
        name=f"RBAC {uuid.uuid4().hex[:8]}",
        original_filename=raw.name,
        file_path=str(raw),
        file_size=raw.stat().st_size,
        file_type="csv",
        columns={"person_name": "object", "email": "object", "amount": "int64"},
        row_count=2,
        uploaded_by=USERS["provider"],
        data_class="Personal",
        status=status,
        pii_json=[
            {
                "column_name": column,
                "pii_type": column,
                "confidence": 0.95,
                "detection_method": "regex",
                "user_confirmed": None,
                "corrected_pii_type": None,
            }
            for column in ("person_name", "email")
        ],
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)

    clean = tmp_path / f"rbac-clean-{dataset.id}.csv"
    clean.write_text(
        "person_name,email,amount\nІ***о,i***@e***.com,100\nО***ь,o***@e***.com,200\n",
        encoding="utf-8",
    )
    db_session.add(
        DatasetVersion(
            dataset_id=dataset.id,
            kind=DatasetVersionKind.CLEAN,
            file_path=str(clean),
            sha256=uuid.uuid4().hex,
            row_count=2,
        )
    )
    for column in ("person_name", "email"):
        db_session.add(
            AnonymizationMethod(
                dataset_id=dataset.id,
                column_name=column,
                method=AnonymizationMethodType.MASK,
            )
        )
    db_session.commit()
    return dataset


@pytest.fixture
def world(db_session, tmp_path):
    other = User(
        email=f"rbac-other-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("password123"),
        role="DataProvider",
    )
    db_session.add(other)
    db_session.commit()

    consumer = db_session.query(User).filter_by(email=USERS["consumer"]).one()
    steward = db_session.query(User).filter_by(email=USERS["steward"]).one()

    draft = _rbac_dataset(db_session, tmp_path, status="uploaded")
    published = _rbac_dataset(db_session, tmp_path, status="published")
    spare = _rbac_dataset(db_session, tmp_path, status="published")

    basis = LegalBasis(
        dataset_id=published.id,
        type=LegalBasisType.CONSENT,
        document_ref="RBAC-DOC-0",
        date=date.today(),
        purpose=LegalBasisPurpose.ANALYTICS,
        valid_until=date.today() + timedelta(days=365),
        entered_by=steward.id,
    )
    pending = ExchangeRequest(
        dataset_id=published.id,
        consumer_id=consumer.id,
        purpose="analytics of regional payments",
        status=ExchangeRequestStatus.PENDING,
    )
    approved = ExchangeRequest(
        dataset_id=published.id,
        consumer_id=consumer.id,
        purpose="analytics of regional payments",
        status=ExchangeRequestStatus.APPROVED,
    )
    db_session.add_all([basis, pending, approved])
    db_session.commit()

    return {
        "other_email": other.email,
        "ids": {
            "draft": draft.id,
            "published": published.id,
            "spare": spare.id,
            "basis": basis.id,
            "pending": pending.id,
            "approved": approved.id,
        },
    }


# 7. Матриця для ендпоінтів з ресурсом: п'ять ролей, включно з чужим Provider


@pytest.mark.parametrize(
    "method,path,body,role,expected",
    RESOURCE_CASES,
    ids=[_resource_case_id(c) for c in RESOURCE_CASES],
)
def test_resource_rbac_matrix(client, world, method, path, body, role, expected):
    url = _fill(path, world)
    payload = _fill(_to_dict(body), world)

    res = _resource_call(client, method, url, payload, _resource_headers(role, world))

    assert res.status_code == expected, (
        f"{role} {method} {url}: очікувано {expected}, "
        f"отримано {res.status_code} ({res.text})"
    )


# 8. Кожна відмова 401/403 на ресурсних ендпоінтах пишеться в аудит.
# Назва дії різниться між роутерами (ACCESS_DENIED, VIEW_PII, CREATE_LEGAL_BASIS
# тощо), тому інваріант такий: +1 запис з цим actor і result UNAUTHORIZED/FORBIDDEN.


@pytest.mark.parametrize(
    "method,path,body,role,expected",
    RESOURCE_DENIED_CASES,
    ids=[_resource_case_id(c) for c in RESOURCE_DENIED_CASES],
)
def test_resource_denial_is_audited(
    client, db_session, world, method, path, body, role, expected
):
    url = _fill(path, world)
    payload = _fill(_to_dict(body), world)
    result = "UNAUTHORIZED" if expected == 401 else "FORBIDDEN"
    filters = {"actor": _resource_actor(role, world), "result": result}
    before = _audit_count(db_session, **filters)

    res = _resource_call(client, method, url, payload, _resource_headers(role, world))

    assert res.status_code == expected
    assert _audit_count(db_session, **filters) == before + 1


# 9. Відмова не змінює стан ресурсу


@pytest.mark.parametrize("role", ["consumer", "steward", OTHER])
def test_denied_publish_does_not_publish(client, db_session, world, role):
    dataset_id = world["ids"]["draft"]

    res = client.post(
        f"/api/datasets/{dataset_id}/publish",
        json={"retention_until": FUTURE},
        headers=_resource_headers(role, world),
    )

    assert res.status_code in (403, 404)
    db_session.expire_all()
    assert db_session.get(Dataset, dataset_id).status == "uploaded"


@pytest.mark.parametrize("role", ["consumer", "steward", OTHER])
@pytest.mark.parametrize("action", ["approve", "reject"])
def test_denied_review_keeps_request_pending(client, db_session, world, role, action):
    request_id = world["ids"]["pending"]

    res = client.post(
        f"/api/requests/{request_id}/{action}",
        json={"comment": "intruder"},
        headers=_resource_headers(role, world),
    )

    assert res.status_code in (403, 404)
    db_session.expire_all()
    req = db_session.get(ExchangeRequest, request_id)
    assert req.status == ExchangeRequestStatus.PENDING
    assert req.reviewed_by is None


@pytest.mark.parametrize("role", ["consumer", OTHER])
def test_denied_revoke_keeps_basis_active(client, db_session, world, role):
    basis_id = world["ids"]["basis"]

    res = client.post(
        f"/api/legal-basis/{basis_id}/revoke",
        json={"reason": "intruder"},
        headers=_resource_headers(role, world),
    )

    assert res.status_code in (403, 404)
    db_session.expire_all()
    assert db_session.get(LegalBasis, basis_id).revoked_at is None
