import io
import os

import pytest

from app.models import AuditLog, Dataset


@pytest.fixture
def provider_token(client):
    res = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    return res.json()["access_token"]


@pytest.fixture
def consumer_token(client):
    res = client.post(
        "/api/auth/login",
        json={"email": "consumer@example.com", "password": "password123"},
    )
    return res.json()["access_token"]


def test_upload_without_token_returns_401(client):
    csv_content = b"user_id,score\n1,100\n"
    response = client.post(
        "/datasets",
        files={"file": ("users.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_upload_as_consumer_returns_403(client, consumer_token):
    csv_content = b"user_id,score\n1,100\n"
    response = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {consumer_token}"},
        files={"file": ("users.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert response.status_code == 403
    assert "Access forbidden" in response.json()["detail"]


def test_upload_csv_success(client, db_session, provider_token):
    csv_content = b"user_id,score,active\n101,98.5,True\n102,87.0,False\n"
    response = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("users.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "users.csv"
    assert data["file_type"] == "csv"
    assert data["row_count"] == 2
    assert "user_id" in data["columns"]
    assert "score" in data["columns"]
    assert "active" in data["columns"]

    # Verify raw file unchanged on disk
    dataset_in_db = db_session.query(Dataset).filter_by(id=data["id"]).first()
    assert dataset_in_db is not None
    assert os.path.exists(dataset_in_db.file_path)
    with open(dataset_in_db.file_path, "rb") as f:
        assert f.read() == csv_content

    # Verify audit log was created
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "UPLOAD_DATASET", AuditLog.object == "users.csv")
        .first()
    )
    assert audit is not None
    assert audit.result == "SUCCESS"
    assert audit.actor == "provider@example.com"


def test_upload_json_success(client, db_session, provider_token):
    json_content = b'[{"id": 1, "product": "Widget"}, {"id": 2, "product": "Gadget"}]'
    response = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("products.json", io.BytesIO(json_content), "application/json")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["file_type"] == "json"
    assert data["row_count"] == 2
    assert "id" in data["columns"]
    assert "product" in data["columns"]

    # Verify raw file saved unchanged
    dataset_in_db = db_session.query(Dataset).filter_by(id=data["id"]).first()
    with open(dataset_in_db.file_path, "rb") as f:
        assert f.read() == json_content

    # Verify audit log created
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "UPLOAD_DATASET", AuditLog.object == "products.json")
        .first()
    )
    assert audit is not None
    assert audit.result == "SUCCESS"


def test_upload_unsupported_file_extension(client, db_session, provider_token):
    response = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("notes.txt", io.BytesIO(b"some notes"), "text/plain")},
    )
    assert response.status_code == 400
    assert "Only CSV and JSON" in response.json()["detail"]

    # Verify audit record created for failure
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "UPLOAD_DATASET", AuditLog.object == "notes.txt")
        .first()
    )
    assert audit is not None
    assert audit.result == "FAILURE"


def test_upload_empty_file(client, db_session, provider_token):
    response = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "UPLOAD_DATASET", AuditLog.object == "empty.csv")
        .first()
    )
    assert audit is not None
    assert audit.result == "FAILURE"


def test_upload_broken_json(client, db_session, provider_token):
    broken_json = b'{"items": [1, 2, '
    response = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("broken.json", io.BytesIO(broken_json), "application/json")},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Invalid JSON" in detail or "syntax" in detail

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "UPLOAD_DATASET", AuditLog.object == "broken.json")
        .first()
    )
    assert audit is not None
    assert audit.result == "FAILURE"


def test_upload_malformed_csv(client, provider_token):
    empty_csv_no_cols = b"\n\n\n"
    response = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("bad.csv", io.BytesIO(empty_csv_no_cols), "text/csv")},
    )
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "columns" in detail or "empty" in detail


def test_list_datasets(client, provider_token):
    response = client.get(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_datasets_unauthenticated(client):
    response = client.get("/datasets")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_upload_csv_cp1251_semicolon(client, provider_token):
    # Testing UC-02 semicolon delimiter and CP1251 encoding
    content_cp1251 = "ід;зарплата;статус\n101;25000;активний\n".encode("cp1251")
    response = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("payroll_cp1251.csv", io.BytesIO(content_cp1251), "text/csv")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["row_count"] == 1
    assert "ід" in data["columns"]
    assert "зарплата" in data["columns"]


def test_upload_csv_header_only_rejected(client, provider_token):
    header_only = b"user_id,name,role\n"
    response = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("header_only.csv", io.BytesIO(header_only), "text/csv")},
    )
    assert response.status_code == 400
    assert "header only" in response.json()["detail"].lower()


def test_upload_csv_preserves_ipn_as_string(client, provider_token):
    # Ensure IPN with leading zero and empty value is preserved as string
    csv_with_ipn = b"name,ipn_code\nPetro,0123456789\nIvan,\n"
    response = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("tax_report.csv", io.BytesIO(csv_with_ipn), "text/csv")},
    )
    assert response.status_code == 201
    data = response.json()
    assert "ipn_code" in data["columns"]
    assert data["columns"]["ipn_code"] in ("object", "string", "str")
