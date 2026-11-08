import io
from pathlib import Path

import pandas as pd
from fastapi import status

from app.profiler import detect_pii, mask_sample, profile_dataframe
from app.services.quality_engine import validate_dataframe

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def test_detect_pii_types_accuracy():
    """Verify high-precision PII detection across Ukrainian PII formats."""
    # 1. IPN with valid checksum (real valid Ukrainian IPNs)
    s_ipn = pd.Series(["2663272534", "2253088783", "3328316385"])
    res = detect_pii(s_ipn, "tax_id")
    assert res["is_pii"] is True
    assert res["pii_type"] == "ipn"
    assert res["detection_method"] == "regex+checksum"

    # 2. IBAN with valid mod97
    s_iban = pd.Series(
        ["UA883644124840841495022491758", "UA713080671603080108791538475"]
    )
    res = detect_pii(s_iban, "account_no")
    assert res["is_pii"] is True
    assert res["pii_type"] == "iban"

    # 3. Email
    s_email = pd.Series(
        ["john.doe@example.com", "ivan.petrenko@corp.ua", "test@domain.org"]
    )
    res = detect_pii(s_email, "contact")
    assert res["is_pii"] is True
    assert res["pii_type"] == "email"

    # 4. Phone
    s_phone = pd.Series(["+380501234567", "+380679876543", "0931112233"])
    res = detect_pii(s_phone, "tel")
    assert res["is_pii"] is True
    assert res["pii_type"] == "phone"

    # 5. Full name
    s_name = pd.Series(
        ["Шевченко Тарас Григорович", "Франко Іван Якович", "Леся Українка"]
    )
    res = detect_pii(s_name, "employee_name")
    assert res["is_pii"] is True
    assert res["pii_type"] == "person_name"


def test_no_false_positives_on_traps():
    """Verify traps (invalid checksums, brands, non-Luhn cards) not flagged."""
    # 10-digit number without IPN checksum (like order number)
    s_order = pd.Series(["4017765327", "4303361178", "4212760172"])
    assert detect_pii(s_order, "order_number")["is_pii"] is False

    # 16-digit number failing Luhn algorithm (like transaction id)
    s_tx = pd.Series(["5644249027221250", "5990591655121041"])
    assert detect_pii(s_tx, "tx_ref")["is_pii"] is False

    # Contract ref failing mod97
    s_contract = pd.Series(
        ["UA263780340855214368584725559", "UA675700301137413451120000085"]
    )
    assert detect_pii(s_contract, "contract_code")["is_pii"] is False

    # Whole-word city check must not treat 'ethnicity' as city column
    s_ethnicity = pd.Series(
        ["Шевченко Тарас", "Франко Іван", "Леся Українка"]
    )
    res_eth = detect_pii(s_ethnicity, "ethnicity")
    assert res_eth["is_pii"] is True


def test_profile_dataframe_data_class_personal():
    """A dataset containing PII MUST receive data_class='Personal'."""
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "full_name": ["Іван Франко", "Тарас Шевченко", "Леся Українка"],
            "salary": [30000, 40000, 50000],
        }
    )
    profile = profile_dataframe(df, dataset_id=1, dataset_name="staff")
    assert profile["data_class"] == "Personal"
    assert len(profile["pii_findings"]) == 1
    assert profile["pii_findings"][0]["pii_type"] == "person_name"


def test_profile_dataframe_data_class_internal():
    """A dataset without PII receives data_class='Internal'."""
    df = pd.DataFrame(
        {
            "product_id": [101, 102, 103],
            "quantity": [10, 20, 30],
            "price": [150.0, 250.0, 350.0],
        }
    )
    profile = profile_dataframe(df, dataset_id=2, dataset_name="inventory")
    assert profile["data_class"] == "Internal"
    assert len(profile["pii_findings"]) == 0


def test_consumer_and_non_owner_provider_rbac(client):
    """Consumer and non-owner Provider must get 403 when accessing profiles."""
    p_login = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    provider_token = p_login.json()["access_token"]

    c_login = client.post(
        "/api/auth/login",
        json={"email": "consumer@example.com", "password": "password123"},
    )
    consumer_token = c_login.json()["access_token"]

    steward_login = client.post(
        "/api/auth/login",
        json={"email": "steward@example.com", "password": "password123"},
    )
    steward_token = steward_login.json()["access_token"]

    # 1. Upload a dataset as Provider
    csv_bytes = b"id,name\n1,Alpha\n2,Beta\n"
    res_upload = client.post(
        "/api/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("test_rbac.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert res_upload.status_code == 201
    dataset_id = res_upload.json()["id"]

    # 2. Consumer attempts -> 403 Forbidden
    res_prof = client.get(
        f"/api/datasets/{dataset_id}/profile",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert res_prof.status_code == status.HTTP_403_FORBIDDEN

    res_pii = client.get(
        f"/api/datasets/{dataset_id}/pii",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert res_pii.status_code == status.HTTP_403_FORBIDDEN

    # 3. Steward has full access -> 200 OK
    res_steward = client.get(
        f"/api/datasets/{dataset_id}/profile",
        headers={"Authorization": f"Bearer {steward_token}"},
    )
    assert res_steward.status_code == status.HTTP_200_OK


def test_update_pii_column_maintains_personal_class(client):
    """Confirm/correct PII keeps Personal class if any PII remains."""
    p_login = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    provider_token = p_login.json()["access_token"]

    csv_bytes = (
        "id,full_name,ipn\n"
        "1,Франко Іван Якович,2663272534\n"
        "2,Шевченко Тарас Григорович,2253088783\n"
    ).encode("utf-8")
    res_upload = client.post(
        "/api/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("test_pii.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert res_upload.status_code == 201
    dataset_id = res_upload.json()["id"]

    # Profile shows Personal
    res_pii = client.get(
        f"/api/datasets/{dataset_id}/pii",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert res_pii.status_code == 200
    assert res_pii.json()["data_class"] == "Personal"

    # User un-confirms IPN: full_name still remains PII -> data_class must stay Personal
    res_patch = client.patch(
        f"/api/datasets/{dataset_id}/pii/ipn",
        headers={"Authorization": f"Bearer {provider_token}"},
        json={"user_confirmed": False},
    )
    assert res_patch.status_code == 200

    res_pii_after = client.get(
        f"/api/datasets/{dataset_id}/pii",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert res_pii_after.json()["data_class"] == "Personal"

    # Un-confirm full_name too -> no active PII -> data_class becomes Internal
    res_patch2 = client.patch(
        f"/api/datasets/{dataset_id}/pii/full_name",
        headers={"Authorization": f"Bearer {provider_token}"},
        json={"user_confirmed": False},
    )
    assert res_patch2.status_code == 200

    res_pii_final = client.get(
        f"/api/datasets/{dataset_id}/pii",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert res_pii_final.json()["data_class"] == "Internal"


def test_real_data_defects_payroll():
    """Verify defects in data/payroll.csv match data/defects.md expectations."""
    payroll_csv = DATA_DIR / "payroll.csv"
    if not payroll_csv.exists():
        return
    df = pd.read_csv(payroll_csv)
    profile = profile_dataframe(df, 1, "payroll.csv")

    cols = {c["name"]: c for c in profile["columns"]}

    # 1. 15 null IPN values
    assert cols["ipn"]["null_count"] == 15

    # 2. 10 duplicate rows
    assert profile["summary"]["duplicate_rows_count"] == 10

    # 3. 13 IQR outliers on salary
    assert cols["amount_uah"]["outliers_count"] == 13

    # 4. PII columns and Personal class
    pii_cols = [c["name"] for c in profile["columns"] if c["is_pii"]]
    assert set(pii_cols) == {"full_name", "ipn", "iban"}
    assert profile["data_class"] == "Personal"

    # 5. Quality Engine validation on payroll_rules.yaml
    rules_path = DATA_DIR / "payroll_rules.yaml"
    if rules_path.exists():
        q_res = validate_dataframe(df, rules_path)
        v_by_col = {v["column"]: v["violation_count"] for v in q_res["violations"]}
        assert v_by_col["ipn"] == 15
        assert v_by_col["amount_uah"] == 8
        assert v_by_col["payment_date"] == 8
        assert v_by_col["*"] == 10


def test_real_data_defects_customers():
    """Verify defects in data/customers.json match data/defects.md expectations."""
    customers_json = DATA_DIR / "customers.json"
    if not customers_json.exists():
        return
    df = pd.read_json(customers_json)
    profile = profile_dataframe(df, 2, "customers.json")

    cols = {c["name"]: c for c in profile["columns"]}

    # 1. 40 empty city values (25 null + 15 empty strings)
    assert cols["city"]["null_count"] == 40

    # 2. 15 duplicate rows
    assert profile["summary"]["duplicate_rows_count"] == 15

    # 3. 13 IQR outliers on age
    assert cols["age"]["outliers_count"] == 13

    # 4. PII columns and Personal class
    pii_cols = [c["name"] for c in profile["columns"] if c["is_pii"]]
    assert set(pii_cols) == {"full_name", "email", "phone"}
    assert profile["data_class"] == "Personal"

    # 5. Quality Engine validation on customers_rules.yaml
    rules_path = DATA_DIR / "customers_rules.yaml"
    if rules_path.exists():
        q_res = validate_dataframe(df, rules_path)
        v_by_col = {v["column"]: v["violation_count"] for v in q_res["violations"]}
        assert v_by_col["age"] == 20
        assert v_by_col["email"] == 25
        assert v_by_col["registration_date"] == 30
        assert v_by_col["city"] == 40
        assert v_by_col["*"] == 15


def test_mask_sample_function():
    """Verify masking logic for UI previews."""
    assert mask_sample("john.doe@gmail.com", "email") == "j***@gmail.com"
    assert "380" in mask_sample("+380501234567", "phone")
    assert mask_sample("2253089128", "ipn") == "22****28"
    assert mask_sample(None, "email") == "—"
