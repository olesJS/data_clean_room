import os
import tempfile

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
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
