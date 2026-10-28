import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User

TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    users = [
        ("provider@example.com", "password123", "DataProvider"),
        ("consumer@example.com", "password123", "DataConsumer"),
        ("steward@example.com", "password123", "DataSteward"),
    ]
    for email, password, role in users:
        existing = db.query(User).filter(User.email == email).first()
        if not existing:
            db.add(
                User(
                    email=email,
                    hashed_password=hash_password(password),
                    role=role,
                )
            )
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)
    # Cleanup test uploads directory if created
    shutil.rmtree("test_storage", ignore_errors=True)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(monkeypatch):
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def mock_init_db():
        pass

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.main.init_db", mock_init_db)
    monkeypatch.setattr("app.audit.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.database.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.routers.datasets.STORAGE_DIR", "test_storage/datasets")

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
