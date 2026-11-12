"""RBAC-матриця «ендпоінт × роль → код відповіді» (SCRUM-33).

Очікування взято з матриці доступу (docs/governance/data-governance-requirements.md,
розділ 3.2) та специфікацій UC. Таблиця з поясненнями: docs/testing/rbac-matrix.md.

Кожен рядок матриці є окремим тест-кейсом. Для кожної відмови (401, 403)
перевіряється запис у журналі аудиту. Новий ендпоінт додається рядком у MATRIX.

Обсяг: ендпоінти, які є в main. Ендпоінти PR #15 і #18 (правова підстава,
профіль, PII, видалення) додаються після їх злиття в задачі SCRUM-51.
"""

import io
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import func

from app.auth import ALGORITHM, SECRET_KEY, create_access_token
from app.models import AuditLog, Dataset

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
