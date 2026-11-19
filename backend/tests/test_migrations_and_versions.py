import os
import tempfile

from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config
from app.models import DatasetVersion, DatasetVersionKind


def test_alembic_upgrade_head_on_clean_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = f.name

    try:
        sqlite_url = f"sqlite:///{temp_db_path}"
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ini_path = os.path.join(backend_dir, "alembic.ini")

        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)
        alembic_cfg.set_main_option(
            "script_location", os.path.join(backend_dir, "alembic")
        )

        # Run migration to head
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(sqlite_url)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "users" in tables
        assert "datasets" in tables
        assert "audit_logs" in tables
        assert "legal_basis" in tables
        assert "dataset_versions" in tables

        lb_columns = {c["name"] for c in inspector.get_columns("legal_basis")}
        required_lb_cols = {
            "id",
            "dataset_id",
            "type",
            "document_ref",
            "date",
            "purpose",
            "valid_until",
            "entered_by",
            "created_at",
            "revoked_at",
            "revoked_by",
            "revoked_reason",
        }
        assert required_lb_cols.issubset(lb_columns)

        columns = {c["name"] for c in inspector.get_columns("dataset_versions")}
        required_cols = {"id", "dataset_id", "kind", "file_path", "sha256", "row_count"}
        assert required_cols.issubset(columns)
        engine.dispose()
    finally:
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except Exception:
                pass


def test_alembic_stamp_on_existing_db():
    """Verify that alembic baseline stamp on existing DB works cleanly."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = f.name

    try:
        sqlite_url = f"sqlite:///{temp_db_path}"
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ini_path = os.path.join(backend_dir, "alembic.ini")

        # Create tables using Base.metadata.create_all (simulating existing deployment)
        from app.database import Base
        engine = create_engine(sqlite_url)
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        tables_before = inspector.get_table_names()
        assert "users" in tables_before
        assert "alembic_version" not in tables_before
        engine.dispose()

        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)
        alembic_cfg.set_main_option(
            "script_location", os.path.join(backend_dir, "alembic")
        )

        # Baseline stamping
        command.stamp(alembic_cfg, "head")

        # Now upgrade head is a safe no-op
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(sqlite_url)
        inspector = inspect(engine)
        tables_after = inspector.get_table_names()
        assert "alembic_version" in tables_after
        engine.dispose()
    finally:
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except Exception:
                pass


def test_upload_creates_raw_dataset_version(client, db_session):
    # Upload a sample csv as provider
    login_res = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    csv_content = b"col1,col2\nval1,val2\nval3,val4\n"
    response = client.post(
        "/api/datasets",
        files={"file": ("version_test.csv", csv_content, "text/csv")},
        data={"name": "Version Test Dataset"},
        headers=headers,
    )
    assert response.status_code == 201
    dataset_id = response.json()["id"]

    version = (
        db_session.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset_id)
        .first()
    )
    assert version is not None
    assert version.kind == DatasetVersionKind.RAW
    assert version.row_count == 2
    assert len(version.sha256) == 64
