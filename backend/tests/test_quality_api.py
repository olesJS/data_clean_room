from pathlib import Path

import pytest

from app.models import Dataset

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture
def test_datasets(db_session):
    # Create payroll dataset
    payroll = Dataset(
        name="Payroll 2024",
        original_filename="payroll.csv",
        file_path=str(DATA_DIR / "payroll.csv"),
        file_size=1024,
        file_type="csv",
        columns={"ipn": "object", "amount_uah": "float64", "payment_date": "object"},
        row_count=500,
        uploaded_by="provider@example.com",
    )
    # Create customers dataset
    customers = Dataset(
        name="Customers Registry",
        original_filename="customers.json",
        file_path=str(DATA_DIR / "customers.json"),
        file_size=2048,
        file_type="json",
        columns={"id": "int64", "age": "int64", "city": "object", "email": "object"},
        row_count=1000,
        uploaded_by="provider@example.com",
    )
    # Foreign dataset owned by another user
    foreign_ds = Dataset(
        name="Foreign Data",
        original_filename="foreign.csv",
        file_path=str(DATA_DIR / "payroll.csv"),
        file_size=1024,
        file_type="csv",
        columns={"a": "int64"},
        row_count=10,
        uploaded_by="other_provider@example.com",
    )
    db_session.add_all([payroll, customers, foreign_ds])
    db_session.commit()
    db_session.refresh(payroll)
    db_session.refresh(customers)
    db_session.refresh(foreign_ds)
    return {"payroll": payroll, "customers": customers, "foreign": foreign_ds}


@pytest.fixture
def auth_tokens(client):
    tokens = {}
    for role, email in [
        ("provider", "provider@example.com"),
        ("consumer", "consumer@example.com"),
        ("steward", "steward@example.com"),
    ]:
        res = client.post(
            "/api/auth/login", json={"email": email, "password": "password123"}
        )
        assert res.status_code == 200
        tokens[role] = res.json()["access_token"]
    return tokens


def test_payroll_quality_rules_and_violations(client, test_datasets, auth_tokens):
    payroll_id = test_datasets["payroll"].id
    headers = {"Authorization": f"Bearer {auth_tokens['provider']}"}

    # 1. Rules
    r_rules = client.get(f"/api/datasets/{payroll_id}/quality-rules", headers=headers)
    assert r_rules.status_code == 200
    rules = r_rules.json()
    assert len(rules) == 3
    rule_cols = {r["column"] for r in rules}
    assert rule_cols == {"ipn", "amount_uah", "payment_date"}

    # 2. Violations
    viol_url = f"/api/datasets/{payroll_id}/quality-violations"
    r_viols = client.get(viol_url, headers=headers)
    assert r_viols.status_code == 200
    report = r_viols.json()

    assert report["dataset_id"] == payroll_id
    assert report["score"] == 91.8
    assert report["total_rows"] == 500
    assert report["duplicated_rows_count"] == 10

    violation_counts = {
        v["column"]: v["violation_count"] for v in report["violations"]
    }
    assert violation_counts["ipn"] == 15
    assert violation_counts["amount_uah"] == 8
    assert violation_counts["payment_date"] == 8
    assert violation_counts["*"] == 10


def test_customers_quality_rules_and_violations(client, test_datasets, auth_tokens):
    customers_id = test_datasets["customers"].id
    # Steward has access
    headers = {"Authorization": f"Bearer {auth_tokens['steward']}"}

    # 1. Rules
    rules_url = f"/api/datasets/{customers_id}/quality-rules"
    r_rules = client.get(rules_url, headers=headers)
    assert r_rules.status_code == 200
    rules = r_rules.json()
    assert len(rules) == 4

    # 2. Violations
    viol_url = f"/api/datasets/{customers_id}/quality-violations"
    r_viols = client.get(viol_url, headers=headers)
    assert r_viols.status_code == 200
    report = r_viols.json()

    assert report["score"] == 87.0
    assert report["total_rows"] == 1000
    assert report["duplicated_rows_count"] == 15

    violation_counts = {
        v["column"]: v["violation_count"] for v in report["violations"]
    }
    assert violation_counts["age"] == 20
    assert violation_counts["email"] == 25
    assert violation_counts["registration_date"] == 30
    assert violation_counts["city"] == 40
    assert violation_counts["*"] == 15


def test_quality_endpoints_rbac(client, test_datasets, auth_tokens):
    payroll_id = test_datasets["payroll"].id
    foreign_id = test_datasets["foreign"].id

    rules_url = f"/api/datasets/{payroll_id}/quality-rules"
    viol_url = f"/api/datasets/{payroll_id}/quality-violations"

    # Unauthenticated -> 401
    assert client.get(rules_url).status_code == 401
    assert client.get(viol_url).status_code == 401

    # DataConsumer -> 403
    consumer_headers = {"Authorization": f"Bearer {auth_tokens['consumer']}"}
    assert client.get(rules_url, headers=consumer_headers).status_code == 403
    assert client.get(viol_url, headers=consumer_headers).status_code == 403

    # DataProvider on foreign dataset -> 404 (PO Decision 8)
    provider_headers = {"Authorization": f"Bearer {auth_tokens['provider']}"}
    foreign_rules = f"/api/datasets/{foreign_id}/quality-rules"
    foreign_viols = f"/api/datasets/{foreign_id}/quality-violations"
    assert client.get(foreign_rules, headers=provider_headers).status_code == 404
    assert client.get(foreign_viols, headers=provider_headers).status_code == 404
