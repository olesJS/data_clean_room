import hashlib
import io
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth import SECRET_KEY, hash_password
from app.models import AuditLog, Dataset, User


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


@pytest.fixture
def steward_token(client):
    res = client.post(
        "/api/auth/login",
        json={"email": "steward@example.com", "password": "password123"},
    )
    return res.json()["access_token"]


# =====================================================================
# 1. HARDCORE FULL RBAC PERMISSIONS MATRIX
# =====================================================================
def test_hardcore_rbac_matrix_complete(
    client, provider_token, consumer_token, steward_token
):
    """Exhaustively verify RBAC matrix for all roles across all endpoints."""
    csv_file = ("matrix.csv", io.BytesIO(b"id,val\n1,10\n"), "text/csv")

    matrix_cases = [
        # (Endpoint, Method, Headers, Expected Status, Test ID)
        # /datasets POST (Ingestion)
        ("/datasets", "POST", {}, 401, "Anon -> POST /datasets (401)"),
        (
            "/datasets",
            "POST",
            {"Authorization": f"Bearer {consumer_token}"},
            403,
            "Consumer -> POST /datasets (403)",
        ),
        (
            "/datasets",
            "POST",
            {"Authorization": f"Bearer {provider_token}"},
            201,
            "Provider -> POST /datasets (201)",
        ),
        (
            "/datasets",
            "POST",
            {"Authorization": f"Bearer {steward_token}"},
            201,
            "Steward -> POST /datasets (201)",
        ),
        # /audit GET (Audit logs)
        ("/audit", "GET", {}, 401, "Anon -> GET /audit (401)"),
        (
            "/audit",
            "GET",
            {"Authorization": f"Bearer {consumer_token}"},
            403,
            "Consumer -> GET /audit (403)",
        ),
        (
            "/audit",
            "GET",
            {"Authorization": f"Bearer {provider_token}"},
            403,
            "Provider -> GET /audit (403)",
        ),
        (
            "/audit",
            "GET",
            {"Authorization": f"Bearer {steward_token}"},
            200,
            "Steward -> GET /audit (200)",
        ),
        # /datasets GET (Dataset listing)
        ("/datasets", "GET", {}, 401, "Anon -> GET /datasets (401)"),
        (
            "/datasets",
            "GET",
            {"Authorization": f"Bearer {consumer_token}"},
            200,
            "Consumer -> GET /datasets (200)",
        ),
        (
            "/datasets",
            "GET",
            {"Authorization": f"Bearer {provider_token}"},
            200,
            "Provider -> GET /datasets (200)",
        ),
        (
            "/datasets",
            "GET",
            {"Authorization": f"Bearer {steward_token}"},
            200,
            "Steward -> GET /datasets (200)",
        ),
        # /api/auth/me GET
        ("/api/auth/me", "GET", {}, 401, "Anon -> GET /me (401)"),
        (
            "/api/auth/me",
            "GET",
            {"Authorization": f"Bearer {consumer_token}"},
            200,
            "Consumer -> GET /me (200)",
        ),
        (
            "/api/auth/me",
            "GET",
            {"Authorization": f"Bearer {provider_token}"},
            200,
            "Provider -> GET /me (200)",
        ),
        (
            "/api/auth/me",
            "GET",
            {"Authorization": f"Bearer {steward_token}"},
            200,
            "Steward -> GET /me (200)",
        ),
        # Public health endpoints
        ("/health", "GET", {}, 200, "Anon -> /health (200)"),
        ("/", "GET", {}, 200, "Anon -> / (200)"),
    ]

    for endpoint, method, headers, expected_status, case_id in matrix_cases:
        if method == "POST":
            # Rewind BytesIO buffer for each POST
            csv_file[1].seek(0)
            res = client.post(endpoint, headers=headers, files={"file": csv_file})
        else:
            res = client.get(endpoint, headers=headers)

        err_msg = (
            f"Failed {case_id}: expected {expected_status}, "
            f"got {res.status_code} ({res.text})"
        )
        assert res.status_code == expected_status, err_msg


# =====================================================================
# 2. HARDCORE CRYPTOGRAPHIC TOKEN TAMPERING & EXPIRY TESTS
# =====================================================================
def test_hardcore_tampered_and_expired_tokens(client, db_session):
    """Verify system strictly rejects tampered, forged, or expired tokens."""
    # 1. Tampered signature (signed with rogue secret)
    forged_token = jwt.encode(
        {"sub": "steward@example.com", "role": "DataSteward"},
        "wrong_rogue_secret_key_123456789012345",
        algorithm="HS256",
    )
    res = client.get("/audit", headers={"Authorization": f"Bearer {forged_token}"})
    assert res.status_code == 401
    assert res.json() == {"detail": "Not authenticated"}

    # 2. Expired token (expired 2 hours ago)
    past_exp = datetime.now(timezone.utc) - timedelta(hours=2)
    expired_token = jwt.encode(
        {"sub": "steward@example.com", "role": "DataSteward", "exp": past_exp},
        SECRET_KEY,
        algorithm="HS256",
    )
    res = client.get("/audit", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert res.json() == {"detail": "Not authenticated"}

    # 3. Completely bogus string
    res = client.get(
        "/audit", headers={"Authorization": "Bearer not_a_real_jwt_token"}
    )
    assert res.status_code == 401

    # 4. Header without Bearer prefix
    res = client.get("/audit", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert res.status_code == 401

    # 5. Empty Bearer header
    res = client.get("/audit", headers={"Authorization": "Bearer "})
    assert res.status_code == 401

    # Verify audit logs captured unauthorized attempts
    unauth_logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.result == "UNAUTHORIZED")
        .all()
    )
    assert len(unauth_logs) >= 5


# =====================================================================
# 3. HARDCORE CRYPTOGRAPHIC RAW FILE IMMUTABILITY (SHA-256 HASH)
# =====================================================================
def test_hardcore_sha256_cryptographic_file_immutability(
    client, provider_token, db_session
):
    """Verify stored raw files match original bytes byte-for-byte via SHA-256."""
    raw_payload = (
        "id,user_uuid,payload,flag\n"
        "1,a1b2c3d4-e5f6-7890-abcd-ef1234567890,Привіт Світ! 🚀,TRUE\n"
        "2,b2c3d4e5-f6a7-8901-bcde-f12345678901,Тестові Дані CleanRoom,FALSE\n"
    ).encode("utf-8")

    input_sha256 = hashlib.sha256(raw_payload).hexdigest()

    res = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("immutable_test.csv", io.BytesIO(raw_payload), "text/csv")},
    )
    assert res.status_code == 201
    dataset_id = res.json()["id"]

    # Retrieve dataset record from DB
    dataset = db_session.query(Dataset).filter_by(id=dataset_id).first()
    assert dataset is not None

    # Read the exact bytes from disk
    with open(dataset.file_path, "rb") as f:
        stored_bytes = f.read()

    disk_sha256 = hashlib.sha256(stored_bytes).hexdigest()

    # Exact byte-for-byte SHA256 comparison
    assert (
        disk_sha256 == input_sha256
    ), f"Data corruption! SHA256 mismatch: {disk_sha256} != {input_sha256}"
    assert stored_bytes == raw_payload
    assert dataset.file_size == len(raw_payload)


# =====================================================================
# 4. HARDCORE LARGE DATASETS STRESS (500 ROWS CSV & 1000 ROWS JSON)
# =====================================================================
def test_hardcore_large_datasets_stress_500_csv_and_1000_json(
    client, provider_token, db_session
):
    """Stress test with 500-row CSV and 1000-row JSON as mentioned in code review."""
    # 1. Generate 500-row realistic payroll CSV with IPN leading zeros
    csv_lines = [
        "employee_id,full_name,department,salary,tax_id,hire_date"
    ]
    for i in range(1, 501):
        # alternate leading zero IPN and empty values
        tax_id = f"0{100000000 + i}" if i % 4 != 0 else ""
        salary = f"{30000 + (i * 50):.2f}"
        csv_lines.append(
            f"{1000 + i},Employee {i},Engineering,{salary},{tax_id},2023-01-15"
        )
    payroll_csv_bytes = "\n".join(csv_lines).encode("utf-8")

    res = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("payroll_500.csv", io.BytesIO(payroll_csv_bytes), "text/csv")},
    )
    assert res.status_code == 201
    payroll_data = res.json()
    assert payroll_data["row_count"] == 500
    assert len(payroll_data["columns"]) == 6
    assert "tax_id" in payroll_data["columns"]
    # Check IPN/tax_id was preserved as string despite leading zeros & empty values
    assert payroll_data["columns"]["tax_id"] in ("object", "string", "str")

    # 2. Generate 1000-row realistic customers JSON
    import json

    customers_list = [
        {
            "customer_id": i,
            "name": f"Customer Name {i}",
            "email": f"cust_{i}@enterprise.ua",
            "balance": round(150.25 * i, 2),
            "is_active": (i % 2 == 0),
        }
        for i in range(1, 1001)
    ]
    customers_json_bytes = json.dumps(customers_list, ensure_ascii=False).encode(
        "utf-8"
    )

    res = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={
            "file": (
                "customers_1000.json",
                io.BytesIO(customers_json_bytes),
                "application/json",
            )
        },
    )
    assert res.status_code == 201
    cust_data = res.json()
    assert cust_data["row_count"] == 1000
    assert len(cust_data["columns"]) == 5
    assert "customer_id" in cust_data["columns"]
    assert "balance" in cust_data["columns"]
    assert "is_active" in cust_data["columns"]


# =====================================================================
# 5. HARDCORE UKRAINIAN CP1251 SEMICOLON & IPN TEST (UC-02)
# =====================================================================
def test_hardcore_cp1251_ukrainian_payroll_semicolon(client, provider_token):
    """Verify UC-02: CP1251 encoding + semicolon delimiter + Cyrillic."""
    ukr_payroll = (
        "Табельний_номер;ПІБ;ІПН;Посада;Оклад;Стаж_років\n"
        "101;Шевченко Тарас Григорович;0234567891;Головний аналітик;45000.50;8\n"
        "102;Франко Іван Якович;;Провідний інженер;38000.00;5\n"
        "103;Леся Українка;0345678912;Керівник проектів;52000.00;10\n"
    ).encode("cp1251")

    res = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("payroll_cp1251.csv", io.BytesIO(ukr_payroll), "text/csv")},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["row_count"] == 3
    assert "Табельний_номер" in data["columns"]
    assert "ПІБ" in data["columns"]
    assert "ІПН" in data["columns"]
    assert "Посада" in data["columns"]
    assert "Оклад" in data["columns"]
    # Verify string preservation for ІПН
    assert data["columns"]["ІПН"] in ("object", "string", "str")


# =====================================================================
# 6. HARDCORE MULTI-PROVIDER DATA ISOLATION
# =====================================================================
def test_hardcore_multi_provider_data_isolation(
    client, db_session, steward_token
):
    """Verify DataProvider A cannot view or list DataProvider B's datasets."""
    # Seed Provider Alpha and Provider Beta
    for email, role in [
        ("provider_alpha@example.com", "DataProvider"),
        ("provider_beta@example.com", "DataProvider"),
    ]:
        if not db_session.query(User).filter_by(email=email).first():
            db_session.add(
                User(
                    email=email,
                    hashed_password=hash_password("password123"),
                    role=role,
                )
            )
    db_session.commit()

    token_alpha = client.post(
        "/api/auth/login",
        json={"email": "provider_alpha@example.com", "password": "password123"},
    ).json()["access_token"]

    token_beta = client.post(
        "/api/auth/login",
        json={"email": "provider_beta@example.com", "password": "password123"},
    ).json()["access_token"]

    # Provider Alpha uploads alpha dataset
    res_a = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {token_alpha}"},
        files={"file": ("alpha_dataset.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    assert res_a.status_code == 201

    # Provider Beta uploads beta dataset
    res_b = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {token_beta}"},
        files={"file": ("beta_dataset.csv", io.BytesIO(b"x,y\n8,9\n"), "text/csv")},
    )
    assert res_b.status_code == 201

    # Provider Alpha lists datasets -> sees ONLY alpha
    list_a = client.get(
        "/datasets", headers={"Authorization": f"Bearer {token_alpha}"}
    ).json()
    filenames_a = [d["original_filename"] for d in list_a]
    assert "alpha_dataset.csv" in filenames_a
    assert "beta_dataset.csv" not in filenames_a

    # Provider Beta lists datasets -> sees ONLY beta
    list_b = client.get(
        "/datasets", headers={"Authorization": f"Bearer {token_beta}"}
    ).json()
    filenames_b = [d["original_filename"] for d in list_b]
    assert "beta_dataset.csv" in filenames_b
    assert "alpha_dataset.csv" not in filenames_b

    # Steward lists datasets -> sees BOTH alpha and beta
    list_steward = client.get(
        "/datasets", headers={"Authorization": f"Bearer {steward_token}"}
    ).json()
    filenames_steward = [d["original_filename"] for d in list_steward]
    assert "alpha_dataset.csv" in filenames_steward
    assert "beta_dataset.csv" in filenames_steward


# =====================================================================
# 7. HARDCORE AUDIT TRAIL DATA GOVERNANCE COMPLETENESS
# =====================================================================
def test_hardcore_audit_trail_invariants(steward_token, client, db_session):
    """Verify that every single operation records verifiable, monotonic audit logs."""
    res = client.get("/audit", headers={"Authorization": f"Bearer {steward_token}"})
    assert res.status_code == 200
    logs = res.json()
    assert len(logs) > 0

    actions = {log["action"] for log in logs}
    assert "LOGIN" in actions
    assert "UPLOAD_DATASET" in actions
    assert "LIST_DATASETS" in actions
    assert "GET_AUDIT" in actions

    # Verify all logs contain non-empty essential governance fields
    for entry in logs:
        assert entry["id"] > 0
        assert entry["actor"] is not None and len(entry["actor"]) > 0
        assert entry["action"] is not None and len(entry["action"]) > 0
        assert entry["object"] is not None and len(entry["object"]) > 0
        assert entry["result"] in (
            "SUCCESS",
            "FAILURE",
            "FORBIDDEN",
            "UNAUTHORIZED",
        )
        assert entry["timestamp"] is not None
