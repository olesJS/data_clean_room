import hashlib
from pathlib import Path

import pytest

from app.models import (
    AnonymizationMethod,
    Dataset,
    DatasetVersion,
    DatasetVersionKind,
)
from app.services.anonymizer import (
    generalize_val,
    hmac_sha256_val,
    mask_val,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def test_anonymizer_mask_val():
    assert mask_val("ivan.petrenko@domain.com") == "i***@d***.com"
    assert mask_val("+380501234567") == "+380*****67"
    assert mask_val("2938475610") == "******5610"
    assert mask_val(None) is None
    assert mask_val("") == ""


def test_anonymizer_generalize_val():
    assert generalize_val("34", kind="age") == "30-39"
    assert generalize_val("2024-05-12") == "2024"
    assert generalize_val("12.05.2024") == "2024"
    assert generalize_val("м. Київ, вул. Хрещатик, 1") == "м. Київ"
    assert generalize_val(None) is None


def test_anonymizer_hmac_deterministic():
    val = "user@test.com"
    h1 = hmac_sha256_val(val)
    h2 = hmac_sha256_val(val)
    assert h1 == h2
    assert len(h1) == 64
    assert hmac_sha256_val(None) is None


@pytest.fixture
def payroll_dataset(db_session, tmp_path):
    # Copy payroll into tmp to test clean generation
    src = DATA_DIR / "payroll.csv"
    dest = tmp_path / "payroll.csv"
    dest.write_bytes(src.read_bytes())

    raw_sha = hashlib.sha256(dest.read_bytes()).hexdigest()

    ds = Dataset(
        name="Payroll Test",
        original_filename="payroll.csv",
        file_path=str(dest),
        file_size=dest.stat().st_size,
        file_type="csv",
        columns={"ipn": "object", "amount_uah": "float64"},
        row_count=500,
        uploaded_by="provider@example.com",
    )
    db_session.add(ds)
    db_session.commit()
    db_session.refresh(ds)

    raw_v = DatasetVersion(
        dataset_id=ds.id,
        kind=DatasetVersionKind.RAW,
        file_path=str(dest),
        sha256=raw_sha,
        row_count=500,
    )
    db_session.add(raw_v)
    db_session.commit()

    return ds, raw_sha


def test_preview_anonymize(client, payroll_dataset):
    ds, _ = payroll_dataset
    login = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post(
        f"/api/datasets/{ds.id}/anonymize/preview",
        json={"columns": {"ipn": "mask"}},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert "ipn" in data["columns"]
    assert len(data["columns"]["ipn"]["before"]) <= 10
    assert len(data["columns"]["ipn"]["after"]) <= 10


def test_apply_anonymize_creates_clean_version(client, payroll_dataset, db_session):
    ds, initial_raw_sha = payroll_dataset
    login = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post(
        f"/api/datasets/{ds.id}/anonymize",
        json={"columns": {"ipn": "mask"}},
        headers=headers,
    )
    assert res.status_code == 200

    # Raw file must remain completely unaltered!
    with open(ds.file_path, "rb") as f:
        current_raw_bytes = f.read()
    assert hashlib.sha256(current_raw_bytes).hexdigest() == initial_raw_sha

    # Clean DatasetVersion created
    clean_v = (
        db_session.query(DatasetVersion)
        .filter(
            DatasetVersion.dataset_id == ds.id,
            DatasetVersion.kind == DatasetVersionKind.CLEAN,
        )
        .first()
    )
    assert clean_v is not None
    assert clean_v.row_count == 500
    assert len(clean_v.sha256) == 64

    # Check AnonymizationMethod recorded
    meth = (
        db_session.query(AnonymizationMethod)
        .filter(AnonymizationMethod.dataset_id == ds.id)
        .first()
    )
    assert meth is not None
    assert meth.column_name == "ipn"


def test_anonymize_rbac_denials(client, payroll_dataset):
    ds, _ = payroll_dataset

    # Consumer -> 403
    c_login = client.post(
        "/api/auth/login",
        json={"email": "consumer@example.com", "password": "password123"},
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}
    assert (
        client.post(
            f"/api/datasets/{ds.id}/anonymize",
            json={"columns": {"ipn": "mask"}},
            headers=c_headers,
        ).status_code
        == 403
    )

    # Unknown dataset -> 404
    p_login = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    p_headers = {"Authorization": f"Bearer {p_login.json()['access_token']}"}
    assert (
        client.post(
            "/api/datasets/99999/anonymize",
            json={"columns": {"ipn": "mask"}},
            headers=p_headers,
        ).status_code
        == 404
    )
