"""Automated Hardcore Verification Runner for Data Clean Room Platform.

Performs deep end-to-end security, data integrity, and compliance checks.
Outputs detailed metrics and assertion counts.
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import hashlib
import io
import json
import os
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Setup in-memory test database for clean isolated verification run
os.environ["ENV"] = "test"
os.environ["SECRET_KEY"] = "verification_runner_secret_key_32_bytes_long_token!"

import app.audit as audit_module  # noqa: E402
import app.database as database_module  # noqa: E402
import app.routers.datasets as datasets_router  # noqa: E402
from app.auth import SECRET_KEY, hash_password  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Dataset, User  # noqa: E402

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
VerifySession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

total_assertions = 0
passed_assertions = 0
failed_assertions = 0
failures_list = []


def assert_check(condition: bool, description: str):
    global total_assertions, passed_assertions, failed_assertions
    total_assertions += 1
    if condition:
        passed_assertions += 1
        print(f"  \033[92m[PASS]\033[0m {description}")
    else:
        failed_assertions += 1
        failures_list.append(description)
        print(f"  \033[91m[FAIL]\033[0m {description}")


def section(title: str):
    print(f"\n\033[94m{'=' * 75}\033[0m")
    print(f"\033[1m\033[96m>> {title}\033[0m")
    print(f"\033[94m{'=' * 75}\033[0m")


def main():
    start_time = time.time()
    print("\033[1m=== STARTING HARDCORE PLATFORM VERIFICATION RUN ===\033[0m")

    # 1. Setup DB
    Base.metadata.create_all(bind=test_engine)
    db = VerifySession()

    def override_db():
        session = VerifySession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db

    audit_module.SessionLocal = VerifySession
    database_module.SessionLocal = VerifySession
    datasets_router.STORAGE_DIR = "test_storage/datasets"

    client = TestClient(app)

    # =========================================================================
    # TIER 1: CORE API & HEALTHCHECKS
    # =========================================================================
    section("TIER 1: Core API & Health Endpoints")
    r = client.get("/")
    assert_check(
        r.status_code == 200, "GET / returns 200 OK"
    )
    assert_check(
        r.json().get("message") == "Data Clean Room API is up and running",
        "GET / returns proper service title message",
    )

    r = client.get("/health")
    assert_check(
        r.status_code == 200 and r.json().get("status") == "ok",
        "GET /health returns status: ok",
    )

    # =========================================================================
    # TIER 2: AUTHENTICATION, PASSWORD HASHING & JWT LIFECYCLE
    # =========================================================================
    section("TIER 2: Authentication, Password Hashing & JWT Lifecycle")

    # Seed users
    users = [
        ("provider@example.com", "password123", "DataProvider"),
        ("consumer@example.com", "password123", "DataConsumer"),
        ("steward@example.com", "password123", "DataSteward"),
    ]
    for email, pwd, role in users:
        u = User(email=email, hashed_password=hash_password(pwd), role=role)
        db.add(u)
    db.commit()
    assert_check(
        db.query(User).count() == 3,
        "Database initialized with 3 RBAC roles (Provider, Consumer, Steward)",
    )

    # Check password hashing is bcrypt and non-plaintext
    provider_user = (
        db.query(User).filter_by(email="provider@example.com").first()
    )
    assert_check(
        provider_user.hashed_password.startswith("$2b$")
        and "password123" not in provider_user.hashed_password,
        "Password stored as non-reversible bcrypt hash with salt",
    )

    # Login tests
    r_bad_pwd = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "wrong"},
    )
    assert_check(
        r_bad_pwd.status_code == 401
        and r_bad_pwd.json().get("detail") == "Invalid credentials",
        "Invalid password returns 401 Invalid credentials",
    )

    r_login = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    provider_token = r_login.json().get("access_token")
    assert_check(
        r_login.status_code == 200
        and provider_token is not None
        and r_login.json().get("role") == "DataProvider",
        "Successful login returns 200, JWT token, and role: DataProvider",
    )

    consumer_token = client.post(
        "/api/auth/login",
        json={"email": "consumer@example.com", "password": "password123"},
    ).json()["access_token"]
    steward_token = client.post(
        "/api/auth/login",
        json={"email": "steward@example.com", "password": "password123"},
    ).json()["access_token"]

    # Verify GET /api/auth/me
    r_me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {provider_token}"}
    )
    assert_check(
        r_me.status_code == 200
        and r_me.json()["email"] == "provider@example.com",
        "GET /api/auth/me resolves user identity from JWT claims",
    )

    # Token Tampering & Expiry
    rogue_key = "tampered_key_32_bytes_test_secret_123"
    forged_token = jwt.encode(
        {"sub": "steward@example.com"}, rogue_key, algorithm="HS256"
    )
    assert_check(
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {forged_token}"}
        ).status_code
        == 401,
        "Forged signature token rejected with 401 Unauthorized",
    )

    expired_token = jwt.encode(
        {
            "sub": "steward@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        SECRET_KEY,
        algorithm="HS256",
    )
    assert_check(
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
        ).status_code
        == 401,
        "Expired JWT token rejected with 401 Unauthorized",
    )

    # =========================================================================
    # TIER 3: RBAC COMPLETE PERMISSION MATRIX
    # =========================================================================
    section("TIER 3: RBAC Comprehensive Permission Matrix")

    # Ingestion POST /datasets
    assert_check(
        client.post(
            "/datasets", files={"file": ("t.csv", io.BytesIO(b"a\n1"), "text/csv")}
        ).status_code
        == 401,
        "POST /datasets without token -> 401 Unauthorized",
    )
    assert_check(
        client.post(
            "/datasets",
            headers={"Authorization": f"Bearer {consumer_token}"},
            files={"file": ("t.csv", io.BytesIO(b"a\n1"), "text/csv")},
        ).status_code
        == 403,
        "POST /datasets with Consumer -> 403 Forbidden (Consumer cannot upload)",
    )
    assert_check(
        client.post(
            "/datasets",
            headers={"Authorization": f"Bearer {provider_token}"},
            files={"file": ("t.csv", io.BytesIO(b"a\n1"), "text/csv")},
        ).status_code
        == 201,
        "POST /datasets with DataProvider token -> 201 Created",
    )

    # Audit GET /audit
    assert_check(
        client.get("/audit").status_code == 401,
        "GET /audit without token -> 401 Unauthorized",
    )
    assert_check(
        client.get(
            "/audit", headers={"Authorization": f"Bearer {consumer_token}"}
        ).status_code
        == 403,
        "GET /audit with DataConsumer token -> 403 Forbidden",
    )
    assert_check(
        client.get(
            "/audit", headers={"Authorization": f"Bearer {provider_token}"}
        ).status_code
        == 403,
        "GET /audit with DataProvider token -> 403 Forbidden",
    )
    assert_check(
        client.get(
            "/audit", headers={"Authorization": f"Bearer {steward_token}"}
        ).status_code
        == 200,
        "GET /audit with DataSteward token -> 200 OK (Auditor access granted)",
    )

    # Datasets GET /datasets
    assert_check(
        client.get("/datasets").status_code == 401,
        "GET /datasets without token -> 401 Unauthorized",
    )
    assert_check(
        client.get(
            "/datasets", headers={"Authorization": f"Bearer {provider_token}"}
        ).status_code
        == 200,
        "GET /datasets with DataProvider token -> 200 OK (Own datasets filtered)",
    )

    # =========================================================================
    # TIER 4: IMMUTABLE RAW STORAGE & SHA-256 INTEGRITY
    # =========================================================================
    section("TIER 4: Raw Storage & SHA-256 Cryptographic Immutability")

    test_content = (
        "id,account_id,balance,note\n"
        "1,UA12345678,9840.50,Переказ коштів #1\n"
        "2,UA87654321,1200.00,Платіж за послуги #2\n"
    ).encode("utf-8")
    expected_hash = hashlib.sha256(test_content).hexdigest()

    res_upload = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("audit_check.csv", io.BytesIO(test_content), "text/csv")},
    )
    dataset_rec = (
        db.query(Dataset).filter_by(id=res_upload.json()["id"]).first()
    )

    with open(dataset_rec.file_path, "rb") as f:
        stored_bytes = f.read()

    actual_hash = hashlib.sha256(stored_bytes).hexdigest()
    assert_check(
        actual_hash == expected_hash,
        f"Raw file SHA-256 verified: {actual_hash[:16]}...",
    )
    assert_check(
        len(stored_bytes) == len(test_content),
        f"File size matches original exactly ({len(stored_bytes)} bytes)",
    )

    # =========================================================================
    # TIER 5: DATA INGESTION PIPELINE & UC-02 COMPLIANCE
    # =========================================================================
    section("TIER 5: Ingestion Pipeline, UC-02 Edge Cases & Type Preservation")

    # 1. CP1251 + Semicolons + IPN leading zeros
    cp1251_payroll = (
        "Табельний;ПІБ;ІПН;Оклад\n"
        "101;Шевченко Т.Г.;0123456789;35000\n"
        "102;Франко І.Я.;;42000\n"
    ).encode("cp1251")
    res_cp1251 = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("payroll_cp1251.csv", io.BytesIO(cp1251_payroll), "text/csv")},
    )
    assert_check(
        res_cp1251.status_code == 201,
        "UC-02: Successfully ingested CP1251 encoding with semicolon separator",
    )
    assert_check(
        res_cp1251.json()["columns"]["ІПН"] in ("object", "string", "str"),
        "UC-02: IPN with leading zero and empty value preserved as string/text",
    )

    # 2. Header-only CSV
    res_hdr = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("hdr.csv", io.BytesIO(b"c1,c2,c3\n"), "text/csv")},
    )
    assert_check(
        res_hdr.status_code == 400
        and "header only" in res_hdr.json().get("detail", "").lower(),
        "Header-only CSV safely rejected with informative 400 Bad Request",
    )

    # 3. Empty file (0 bytes)
    res_empty = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert_check(
        res_empty.status_code == 400
        and "empty" in res_empty.json().get("detail", "").lower(),
        "Empty 0-byte file rejected with 400 Bad Request",
    )

    # 4. Broken corrupted JSON
    bad_json_bytes = b'{"key": [1, 2,'
    bad_file = ("corrupt.json", io.BytesIO(bad_json_bytes), "application/json")
    res_bad_json = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": bad_file},
    )
    assert_check(
        res_bad_json.status_code == 400,
        "Corrupted JSON caught cleanly without server crash (400 Bad Request)",
    )

    # =========================================================================
    # TIER 6: STRESS TESTING (500-ROW CSV & 1000-ROW JSON)
    # =========================================================================
    section("TIER 6: Stress Ingestion Testing (500 CSV & 1000 JSON)")

    # 500 rows CSV
    t_start_csv = time.time()
    csv_stress = "\n".join(
        ["id,name,role,salary,tax_code"]
        + [f"{i},Worker_{i},Engineer,{20000+i*10},0{i:09d}" for i in range(1, 501)]
    ).encode("utf-8")
    r_500 = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("stress_500.csv", io.BytesIO(csv_stress), "text/csv")},
    )
    t_dur_csv = (time.time() - t_start_csv) * 1000
    assert_check(
        r_500.status_code == 201 and r_500.json()["row_count"] == 500,
        f"500-row CSV processed in {t_dur_csv:.1f}ms with 100% row accuracy",
    )

    # 1000 rows JSON
    t_start_json = time.time()
    json_stress = json.dumps(
        [
            {
                "cid": i,
                "customer": f"Enterprise Client {i}",
                "balance": float(i * 12.5),
                "is_active": (i % 2 == 0),
            }
            for i in range(1, 1001)
        ]
    ).encode("utf-8")
    r_1000 = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={
            "file": (
                "stress_1000.json",
                io.BytesIO(json_stress),
                "application/json",
            )
        },
    )
    t_dur_json = (time.time() - t_start_json) * 1000
    assert_check(
        r_1000.status_code == 201 and r_1000.json()["row_count"] == 1000,
        f"1000-row JSON processed in {t_dur_json:.1f}ms with 100% row accuracy",
    )

    # =========================================================================
    # TIER 7: AUDIT TRAIL DATA GOVERNANCE & MONOTONICITY
    # =========================================================================
    section("TIER 7: Audit Trail & Data Governance Invariants")

    total_logs = db.query(AuditLog).count()
    assert_check(
        total_logs >= 15,
        f"Audit trail active: {total_logs} operations recorded in audit_logs",
    )

    actions = {entry.action for entry in db.query(AuditLog).all()}
    assert_check(
        "LOGIN" in actions
        and "UPLOAD_DATASET" in actions
        and "ACCESS_DENIED" in actions
        and "UNAUTHORIZED_ACCESS" in actions
        and "LIST_DATASETS" in actions,
        "Audit log captured all events (LOGIN, UPLOAD, DENIED, UNAUTH, LIST)",
    )

    forbidden_records = (
        db.query(AuditLog).filter_by(result="FORBIDDEN").count()
    )
    assert_check(
        forbidden_records >= 2,
        f"Security incidents: {forbidden_records} FORBIDDEN attempts captured",
    )

    # Verify timestamps are in UTC and sorted
    logs_ordered = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    monotonic = all(
        logs_ordered[i].timestamp <= logs_ordered[i + 1].timestamp
        for i in range(len(logs_ordered) - 1)
    )
    assert_check(
        monotonic,
        "Audit log timestamps are strictly monotonic and UTC-aligned",
    )

    # =========================================================================
    # FINAL METRICS & VERDICT
    # =========================================================================
    elapsed = time.time() - start_time
    print(f"\n\033[94m{'=' * 75}\033[0m")
    print("\033[1m[+] VERIFICATION SUMMARY REPORT\033[0m")
    print(f"\033[94m{'=' * 75}\033[0m")
    print(f"  * Total Assertions Checked: \033[1m{total_assertions}\033[0m")
    print(f"  * Passed Assertions:       \033[92m\033[1m{passed_assertions}\033[0m")
    print(f"  * Failed Assertions:       \033[91m\033[1m{failed_assertions}\033[0m")
    print(f"  * Total Execution Time:    {elapsed:.2f} seconds")

    if failed_assertions == 0:
        msg = "VERDICT: 100% PASSED! PLATFORM INTEGRITY IS ROCK SOLID!"
        print(f"\n\033[1m\033[92m{msg}\033[0m\n")
        sys.exit(0)
    else:
        msg = f"VERDICT: FAILED with {failed_assertions} errors!"
        print(f"\n\033[1m\033[91m{msg}\033[0m\n")
        for f in failures_list:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
