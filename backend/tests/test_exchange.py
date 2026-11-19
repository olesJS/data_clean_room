from datetime import date
from pathlib import Path

import pytest

from app.models import (
    Dataset,
    DatasetVersion,
    DatasetVersionKind,
    LegalBasis,
    LegalBasisType,
    User,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture
def exchange_setup(db_session, tmp_path):
    # Setup published dataset with clean version and legal basis
    clean_file = tmp_path / "payroll_clean.csv"
    clean_file.write_bytes(b"ipn,amount\n******1234,5000\n")

    steward = db_session.query(User).filter(User.role == "DataSteward").first()

    ds = Dataset(
        name="Published Payroll",
        original_filename="payroll.csv",
        file_path=str(DATA_DIR / "payroll.csv"),
        file_size=1024,
        file_type="csv",
        columns={"ipn": "object", "amount": "int64"},
        row_count=1,
        uploaded_by="provider@example.com",
        status="published",
    )
    db_session.add(ds)
    db_session.commit()
    db_session.refresh(ds)

    clean_v = DatasetVersion(
        dataset_id=ds.id,
        kind=DatasetVersionKind.CLEAN,
        file_path=str(clean_file),
        sha256="dummy_sha256_clean",
        row_count=1,
    )
    db_session.add(clean_v)

    lb = LegalBasis(
        dataset_id=ds.id,
        type=LegalBasisType.CONSENT,
        document_ref="DOC-12345",
        date=date(2024, 1, 1),
        purpose="research",
        entered_by=steward.id,
    )
    db_session.add(lb)
    db_session.commit()

    return ds


def test_full_exchange_workflow(client, exchange_setup, db_session):
    ds = exchange_setup

    # 1. Consumer gets catalog
    c_login = client.post(
        "/api/auth/login",
        json={"email": "consumer@example.com", "password": "password123"},
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}

    cat_res = client.get("/api/catalog", headers=c_headers)
    assert cat_res.status_code == 200
    catalog = cat_res.json()
    assert any(c["id"] == ds.id for c in catalog)

    # 2. Consumer creates request
    req_res = client.post(
        "/api/requests",
        json={
            "dataset_id": ds.id,
            "purpose": "Academic research and statistical analytics",
        },
        headers=c_headers,
    )
    assert req_res.status_code == 201
    request_id = req_res.json()["id"]

    # 3. Consumer tries download before approval -> 403
    down_res = client.get(f"/api/requests/{request_id}/download", headers=c_headers)
    assert down_res.status_code == 403

    # 4. Steward approves request
    s_login = client.post(
        "/api/auth/login",
        json={"email": "steward@example.com", "password": "password123"},
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}

    appr_res = client.post(
        f"/api/requests/{request_id}/approve",
        json={"comment": "Approved under GDPR compliance"},
        headers=s_headers,
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"

    # 5. Consumer downloads clean file
    down_ok = client.get(f"/api/requests/{request_id}/download", headers=c_headers)
    assert down_ok.status_code == 200
    assert b"******1234" in down_ok.content
