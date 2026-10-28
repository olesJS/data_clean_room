import io


def test_full_platform_scenario(client):
    # 1. Consumer logs in
    res = client.post(
        "/api/auth/login",
        json={"email": "consumer@example.com", "password": "password123"},
    )
    assert res.status_code == 200
    consumer_token = res.json()["access_token"]
    assert res.json()["role"] == "DataConsumer"

    # 2. Consumer checks /me
    res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert res.status_code == 200
    assert res.json()["email"] == "consumer@example.com"
    assert res.json()["role"] == "DataConsumer"

    # 3. Consumer tries to upload dataset -> 403 Forbidden
    # (Consumer cannot call Provider endpoint)
    res = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {consumer_token}"},
        files={"file": ("hack.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
    )
    assert res.status_code == 403
    assert "Access forbidden" in res.json()["detail"]

    # 4. Consumer tries to access /audit -> 403 Forbidden
    res = client.get(
        "/audit",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert res.status_code == 403

    # 5. Anonymous request without token -> 401 Unauthorized
    res = client.post(
        "/datasets",
        files={"file": ("anon.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
    )
    assert res.status_code == 401
    assert res.json() == {"detail": "Not authenticated"}

    # 6. Provider logs in
    res = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    assert res.status_code == 200
    provider_token = res.json()["access_token"]
    assert res.json()["role"] == "DataProvider"

    # 7. Provider uploads valid CSV
    csv_bytes = b"client_id,amount,is_verified\n501,150.75,True\n502,300.0,False\n"
    res = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("financial.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert res.status_code == 201
    csv_data = res.json()
    assert csv_data["file_type"] == "csv"
    assert csv_data["row_count"] == 2
    assert "client_id" in csv_data["columns"]
    assert "amount" in csv_data["columns"]
    assert "is_verified" in csv_data["columns"]

    # 8. Provider uploads valid JSON
    json_bytes = b'[{"user": "alice", "score": 90}, {"user": "bob", "score": 85}]'
    res = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("scores.json", io.BytesIO(json_bytes), "application/json")},
    )
    assert res.status_code == 201
    json_data = res.json()
    assert json_data["file_type"] == "json"
    assert json_data["row_count"] == 2
    assert "user" in json_data["columns"]
    assert "score" in json_data["columns"]

    # 9. Provider uploads broken JSON -> 400 Bad Request, service does not crash
    broken_json = b'{"unclosed": [1, 2, '
    res = client.post(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
        files={"file": ("corrupt.json", io.BytesIO(broken_json), "application/json")},
    )
    assert res.status_code == 400
    assert "Invalid JSON" in res.json()["detail"] or "syntax" in res.json()["detail"]

    # 10. Steward logs in
    res = client.post(
        "/api/auth/login",
        json={"email": "steward@example.com", "password": "password123"},
    )
    assert res.status_code == 200
    steward_token = res.json()["access_token"]

    # 11. Steward views audit logs -> 200 OK
    res = client.get(
        "/audit",
        headers={"Authorization": f"Bearer {steward_token}"},
    )
    assert res.status_code == 200
    audit_logs = res.json()
    assert len(audit_logs) >= 5

    # Check presence of expected actions
    actions = [log["action"] for log in audit_logs]
    assert "LOGIN" in actions
    assert "UPLOAD_DATASET" in actions
    assert "ACCESS_DENIED" in actions

    # Check that failed upload was recorded
    corrupt_log = next(
        (log for log in audit_logs if log["object"] == "corrupt.json"),
        None,
    )
    assert corrupt_log is not None
    assert corrupt_log["result"] == "FAILURE"

    # Check that success upload was recorded
    success_log = next(
        (log for log in audit_logs if log["object"] == "financial.csv"),
        None,
    )
    assert success_log is not None
    assert success_log["result"] == "SUCCESS"
    assert success_log["actor"] == "provider@example.com"

    # 12. Check GET /datasets permissions
    # Unauthenticated gives 401
    assert client.get("/datasets").status_code == 401

    # Provider sees own datasets
    prov_list = client.get(
        "/datasets",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert prov_list.status_code == 200
    assert len(prov_list.json()) >= 2
    for ds in prov_list.json():
        assert ds["uploaded_by"] == "provider@example.com"
