def test_login_success(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "DataProvider"


def test_login_invalid_password(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "wrong_password"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


def test_login_nonexistent_user(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "unknown@example.com", "password": "password123"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


def test_get_me_success(client):
    login_res = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    token = login_res.json()["access_token"]

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "provider@example.com"
    assert data["role"] == "DataProvider"
    assert "id" in data


def test_get_me_unauthenticated(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_get_me_invalid_token(client):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer bad_token_123"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
