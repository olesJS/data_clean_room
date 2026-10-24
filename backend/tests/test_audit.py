from app.audit import log_event
from app.models import AuditLog


def test_log_event_direct(db_session):
    entry = log_event(
        actor="system_admin@example.com",
        action="TEST_ACTION",
        object="test_resource",
        result="SUCCESS",
        db=db_session,
    )
    assert entry is not None
    assert entry.id is not None
    assert entry.actor == "system_admin@example.com"
    assert entry.action == "TEST_ACTION"
    assert entry.object == "test_resource"
    assert entry.result == "SUCCESS"

    found = db_session.query(AuditLog).filter_by(id=entry.id).first()
    assert found is not None
    assert found.actor == "system_admin@example.com"


def test_login_creates_audit_record(client, db_session):
    # Failed login attempt
    client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "wrong_pwd"},
    )
    failed_log = (
        db_session.query(AuditLog)
        .filter(AuditLog.actor == "provider@example.com", AuditLog.result == "FAILURE")
        .first()
    )
    assert failed_log is not None
    assert failed_log.action == "LOGIN"

    # Successful login attempt
    client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    success_log = (
        db_session.query(AuditLog)
        .filter(AuditLog.actor == "provider@example.com", AuditLog.result == "SUCCESS")
        .first()
    )
    assert success_log is not None
    assert success_log.action == "LOGIN"


def test_get_audit_as_data_steward(client):
    # Login as DataSteward
    steward_res = client.post(
        "/api/auth/login",
        json={"email": "steward@example.com", "password": "password123"},
    )
    token = steward_res.json()["access_token"]

    response = client.get(
        "/audit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    logs = response.json()
    assert isinstance(logs, list)
    assert len(logs) > 0
    # Every item contains required fields
    first = logs[0]
    assert "actor" in first
    assert "action" in first
    assert "object" in first
    assert "result" in first


def test_get_audit_forbidden_for_other_roles(client, db_session):
    # Login as DataProvider
    provider_res = client.post(
        "/api/auth/login",
        json={"email": "provider@example.com", "password": "password123"},
    )
    token = provider_res.json()["access_token"]

    response = client.get(
        "/audit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "DataSteward" in response.json()["detail"]

    forbidden_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.actor == "provider@example.com",
            AuditLog.result == "FORBIDDEN",
        )
        .first()
    )
    assert forbidden_log is not None
    assert forbidden_log.action == "ACCESS_DENIED"


def test_get_audit_unauthenticated(client, db_session):
    response = client.get("/audit")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}

    unauth_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.actor == "unauthenticated",
            AuditLog.result == "UNAUTHORIZED",
        )
        .first()
    )
    assert unauth_log is not None
