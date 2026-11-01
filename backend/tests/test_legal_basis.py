import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.database import Base, get_async_db, get_db
from app.main import app
from app.models import AuditLog, Dataset, User

SYNC_URL = "sqlite:///file:test_legal_basis?mode=memory&cache=shared"
ASYNC_URL = "sqlite+aiosqlite:///file:test_legal_basis?mode=memory&cache=shared"
SQLITE_CONNECT_ARGS = {"check_same_thread": False, "uri": True}

sync_engine = create_engine(
    SYNC_URL,
    connect_args=SQLITE_CONNECT_ARGS,
    poolclass=StaticPool,
)
SyncSession = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

async_engine = create_async_engine(
    ASYNC_URL,
    connect_args=SQLITE_CONNECT_ARGS,
    poolclass=StaticPool,
)
AsyncSessionMaker = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(autouse=True)
def setup_teardown_db():
    Base.metadata.drop_all(bind=sync_engine)
    Base.metadata.create_all(bind=sync_engine)

    # Seed users
    db = SyncSession()
    users = [
        ("provider@example.com", "password123", "DataProvider"),
        ("consumer@example.com", "password123", "DataConsumer"),
        ("steward@example.com", "password123", "DataSteward"),
    ]
    for email, password, role in users:
        db.add(User(email=email, hashed_password=hash_password(password), role=role))
    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=sync_engine)


@pytest.fixture(autouse=True)
def override_dependencies(monkeypatch):
    def _get_db():
        db = SyncSession()
        try:
            yield db
        finally:
            db.close()

    async def _get_async_db():
        async with AsyncSessionMaker() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_async_db] = _get_async_db
    monkeypatch.setattr("app.audit.SessionLocal", SyncSession)
    monkeypatch.setattr("app.database.SessionLocal", SyncSession)

    yield

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_async_db, None)


@pytest.fixture
def sample_dataset():
    db = SyncSession()
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
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    dataset_id = dataset.id
    db.close()
    return dataset_id


def test_create_and_get_legal_basis_success(
    client, provider_token, sample_dataset, db_session
):
    dataset_id = sample_dataset
    payload = {
        "type": "consent",
        "document_ref": "DOC-CONSENT-2026-001",
        "date": "2026-10-24",
    }

    # 1. POST
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

    # 2. GET
    get_res = client.get(
        f"/datasets/{dataset_id}/legal-basis",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert get_res.status_code == 200
    entries = get_res.json()
    assert len(entries) == 1
    assert entries[0]["id"] == data["id"]
    assert entries[0]["document_ref"] == "DOC-CONSENT-2026-001"

    # 3. Check audit log
    audit_record = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "CREATE_LEGAL_BASIS")
        .first()
    )
    if audit_record is None:
        db = SyncSession()
        audit_record = (
            db.query(AuditLog)
            .filter(AuditLog.action == "CREATE_LEGAL_BASIS")
            .first()
        )
        db.close()

    assert audit_record is not None
    assert audit_record.result == "SUCCESS"
    assert f"dataset:{dataset_id}" in audit_record.object


def test_create_legal_basis_consumer_forbidden(client, consumer_token, sample_dataset):
    dataset_id = sample_dataset
    payload = {
        "type": "contract",
        "document_ref": "CONTRACT-101",
        "date": "2026-10-24",
    }
    res = client.post(
        f"/datasets/{dataset_id}/legal-basis",
        json=payload,
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert res.status_code == 403
    assert "Access forbidden" in res.json()["detail"]


def test_create_legal_basis_dataset_not_found(client, provider_token):
    payload = {
        "type": "law",
        "document_ref": "LAW-123",
        "date": "2026-10-24",
    }
    res = client.post(
        "/datasets/999999/legal-basis",
        json=payload,
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert res.status_code == 404
