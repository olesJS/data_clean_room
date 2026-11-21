from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.auth import create_access_token, hash_password
from app.models import (
    Dataset,
    DatasetVersion,
    DatasetVersionKind,
    ExchangeRequest,
    ExchangeRequestStatus,
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

    # 4. Dataset owner (DataProvider) approves request
    p_login = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    p_headers = {"Authorization": f"Bearer {p_login.json()['access_token']}"}

    # Verify Steward cannot approve -> 403
    s_login = client.post(
        "/api/auth/login",
        json={"email": "steward@example.com", "password": "password123"},
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}
    s_res = client.post(
        f"/api/requests/{request_id}/approve",
        json={"comment": "Steward attempt"},
        headers=s_headers,
    )
    assert s_res.status_code == 403

    # Provider approves request
    appr_res = client.post(
        f"/api/requests/{request_id}/approve",
        json={"comment": "Approved under GDPR compliance"},
        headers=p_headers,
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"

    # 5. Consumer downloads clean file
    down_ok = client.get(f"/api/requests/{request_id}/download", headers=c_headers)
    assert down_ok.status_code == 200
    assert b"******1234" in down_ok.content

    # Check status changed to downloaded
    req_check = (
        db_session.query(ExchangeRequest)
        .filter(ExchangeRequest.id == request_id)
        .first()
    )
    assert req_check.status == ExchangeRequestStatus.DOWNLOADED


def test_exchange_foreign_provider_cannot_review(
    client, exchange_setup, db_session
):
    """Verify that provider who does not own dataset cannot review (returns 404)."""
    ds = exchange_setup
    c_login = client.post(
        "/api/auth/login",
        json={"email": "consumer@example.com", "password": "password123"},
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}

    req_res = client.post(
        "/api/requests",
        json={
            "dataset_id": ds.id,
            "purpose": "Academic research and statistical analytics",
        },
        headers=c_headers,
    )
    request_id = req_res.json()["id"]

    # Create another provider in db
    p2 = User(
        email="other_provider@example.com",
        hashed_password=hash_password("password123"),
        role="DataProvider",
    )
    db_session.add(p2)
    db_session.commit()
    p2_token = create_access_token({"sub": p2.email, "role": p2.role, "id": p2.id})
    p2_headers = {"Authorization": f"Bearer {p2_token}"}

    # Foreign provider attempt to approve -> 404 (PO Decision 8)
    appr_res = client.post(
        f"/api/requests/{request_id}/approve",
        json={"comment": "Intruder attempt"},
        headers=p2_headers,
    )
    assert appr_res.status_code == 404

    # Foreign provider attempt to reject -> 404
    rej_res = client.post(
        f"/api/requests/{request_id}/reject",
        json={"comment": "Intruder reject"},
        headers=p2_headers,
    )
    assert rej_res.status_code == 404


def test_exchange_foreign_consumer_cannot_download(
    client, exchange_setup, db_session
):
    """Verify that a consumer who did not create the request gets 404 on download."""
    ds = exchange_setup
    c_login = client.post(
        "/api/auth/login",
        json={"email": "consumer@example.com", "password": "password123"},
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}

    req_res = client.post(
        "/api/requests",
        json={
            "dataset_id": ds.id,
            "purpose": "Academic research and statistical analytics",
        },
        headers=c_headers,
    )
    request_id = req_res.json()["id"]

    # Owner approves
    p_login = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    p_headers = {"Authorization": f"Bearer {p_login.json()['access_token']}"}
    client.post(
        f"/api/requests/{request_id}/approve",
        json={"comment": "Approved"},
        headers=p_headers,
    )

    # Another consumer tries to download
    c2 = User(
        email="other_consumer@example.com",
        hashed_password=hash_password("password123"),
        role="DataConsumer",
    )
    db_session.add(c2)
    db_session.commit()
    c2_token = create_access_token({"sub": c2.email, "role": c2.role, "id": c2.id})
    c2_headers = {"Authorization": f"Bearer {c2_token}"}

    down_res = client.get(
        f"/api/requests/{request_id}/download", headers=c2_headers
    )
    assert down_res.status_code == 404



def test_exchange_purpose_mismatch_fails_approval(
    client, exchange_setup, db_session
):
    """Verify that request with purpose mismatch is denied."""
    ds = exchange_setup
    c_login = client.post(
        "/api/auth/login",
        json={"email": "consumer@example.com", "password": "password123"},
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}

    req_res = client.post(
        "/api/requests",
        json={
            "dataset_id": ds.id,
            "purpose": "Public advertising and marketing campaign",
        },
        headers=c_headers,
    )
    assert req_res.status_code == 201
    request_id = req_res.json()["id"]

    p_login = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    p_headers = {"Authorization": f"Bearer {p_login.json()['access_token']}"}

    appr_res = client.post(
        f"/api/requests/{request_id}/approve",
        json={"comment": "Attempting approval"},
        headers=p_headers,
    )
    assert appr_res.status_code == 409
    detail = appr_res.json()["detail"]
    assert "purpose_mismatch" in detail or "legal basis invalid" in detail


def test_exchange_revoked_legal_basis_blocks_download(
    client, exchange_setup, db_session
):
    """Verify that revoking legal basis after approval blocks subsequent download."""
    ds = exchange_setup
    c_login = client.post(
        "/api/auth/login",
        json={"email": "consumer@example.com", "password": "password123"},
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}

    req_res = client.post(
        "/api/requests",
        json={
            "dataset_id": ds.id,
            "purpose": "Medical research purpose only",
        },
        headers=c_headers,
    )
    assert req_res.status_code == 201
    request_id = req_res.json()["id"]

    p_login = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    p_headers = {"Authorization": f"Bearer {p_login.json()['access_token']}"}

    appr_res = client.post(
        f"/api/requests/{request_id}/approve",
        json={"comment": "Approved"},
        headers=p_headers,
    )
    assert appr_res.status_code == 200

    # Revoke legal basis
    lb = db_session.query(LegalBasis).filter(LegalBasis.dataset_id == ds.id).first()
    lb.revoked_at = datetime.now(timezone.utc)
    lb.revoked_reason = "Consent withdrawn by subject"
    db_session.commit()

    # Consumer tries download -> blocked due to revoked legal basis
    down_res = client.get(
        f"/api/requests/{request_id}/download", headers=c_headers
    )
    assert down_res.status_code == 403
    detail = down_res.json()["detail"].lower()
    assert "revoked" in detail or "no longer valid" in detail

