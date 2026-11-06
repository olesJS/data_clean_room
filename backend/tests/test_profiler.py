import io

import pandas as pd
from fastapi import status

from app.profiler import detect_pii, mask_sample, profile_dataframe


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


def test_consumer_cannot_access_profile_or_pii(client):
    """Consumer must get 403 when trying to access raw dataset profiles."""
    # Obtain tokens
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

    # 1. Upload a dataset as Provider
    csv_bytes = b"id,name\n1,Alpha\n2,Beta\n"
    res_upload = client.post(
        "/api/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("test_rbac.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert res_upload.status_code == 201
    dataset_id = res_upload.json()["id"]

    # 2. Consumer attempts to GET /api/datasets/{id}/profile -> 403 Forbidden
    res_prof = client.get(
        f"/api/datasets/{dataset_id}/profile",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert res_prof.status_code == status.HTTP_403_FORBIDDEN

    # 3. Consumer attempts to GET /api/datasets/{id}/pii -> 403 Forbidden
    res_pii = client.get(
        f"/api/datasets/{dataset_id}/pii",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert res_pii.status_code == status.HTTP_403_FORBIDDEN


def test_mask_sample_function():
    """Verify masking logic for UI previews."""
    assert mask_sample("john.doe@gmail.com", "email") == "j***@gmail.com"
    assert "380" in mask_sample("+380501234567", "phone")
    assert mask_sample("2253089128", "ipn") == "22****28"
    assert mask_sample(None, "email") == "—"
