"""UC-04 quality rules/violations API tests (SCRUM-49 follow-up)."""

from pathlib import Path

from app.models import Dataset

from .sprint3_helpers import DATA_DIR, create_dataset, create_other_provider


def _payroll_dataset(db_session) -> Dataset:
    dataset = Dataset(
        name="payroll-quality",
        original_filename="payroll.csv",
        file_path=str(DATA_DIR / "payroll.csv"),
        file_size=1,
        file_type="csv",
        columns={"ipn": "object", "amount_uah": "float64"},
        row_count=1,
        uploaded_by="provider@example.com",
        data_class="Personal",
        status="uploaded",
        pii_json=[],
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


def test_quality_rules_and_violations_for_owner(
    client, provider_token, db_session
):
    dataset = _payroll_dataset(db_session)

    rules = client.get(
        f"/api/datasets/{dataset.id}/quality-rules",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert rules.status_code == 200, rules.text
    assert len(rules.json()) >= 3
    assert {"column", "condition", "action", "description"} <= set(
        rules.json()[0]
    )

    report = client.get(
        f"/api/datasets/{dataset.id}/quality-violations",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["dataset_id"] == dataset.id
    assert 0 <= body["score"] <= 100
    assert body["total_rows"] > 0
    assert isinstance(body["violations"], list)
    assert body["rules_configured"] is True
    assert body["summary"]["duplicate_rows_count"] >= 0
    for violation in body["violations"]:
        assert "violation_count" in violation
        assert "violating_indices" not in violation


def test_quality_indices_are_opt_in(client, provider_token, db_session):
    dataset = _payroll_dataset(db_session)

    response = client.get(
        f"/api/datasets/{dataset.id}/quality-violations?include_indices=true",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert response.status_code == 200
    assert any(
        "violating_indices" in violation
        for violation in response.json()["violations"]
    )


def test_quality_is_visible_to_steward_but_not_consumer(
    client, provider_token, consumer_token, steward_token, db_session
):
    dataset = _payroll_dataset(db_session)

    steward = client.get(
        f"/api/datasets/{dataset.id}/quality-rules",
        headers={"Authorization": f"Bearer {steward_token}"},
    )
    assert steward.status_code == 200

    consumer = client.get(
        f"/api/datasets/{dataset.id}/quality-rules",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert consumer.status_code == 403

    consumer_report = client.get(
        f"/api/datasets/{dataset.id}/quality-violations",
        headers={"Authorization": f"Bearer {consumer_token}"},
    )
    assert consumer_report.status_code == 403


def test_quality_foreign_provider_gets_404(
    client, provider_token, db_session
):
    other_token = create_other_provider(client, db_session)
    dataset = _payroll_dataset(db_session)

    response = client.get(
        f"/api/datasets/{dataset.id}/quality-rules",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


def test_quality_without_rules_returns_empty_report(
    client, provider_token, db_session, tmp_path
):
    dataset = create_dataset(
        db_session, tmp_path, pii_findings=[]
    )

    rules = client.get(
        f"/api/datasets/{dataset.id}/quality-rules",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert rules.status_code == 200
    assert rules.json() == []

    report = client.get(
        f"/api/datasets/{dataset.id}/quality-violations",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert report.status_code == 200
    assert report.json()["rules_configured"] is False
    assert report.json()["violations"] == []


def test_quality_audit_events_are_recorded(
    client, provider_token, steward_token, db_session
):
    dataset = _payroll_dataset(db_session)
    client.get(
        f"/api/datasets/{dataset.id}/quality-rules",
        headers={"Authorization": f"Bearer {provider_token}"},
    )

    audit = client.get(
        "/api/audit", headers={"Authorization": f"Bearer {steward_token}"}
    )
    actions = [item["action"] for item in audit.json()]
    assert "GET_QUALITY_RULES" in actions


def test_quality_rules_path_points_to_existing_file(db_session):
    from app.services.quality_service import resolve_rules_path

    dataset = _payroll_dataset(db_session)
    resolved = resolve_rules_path(dataset)
    assert resolved is not None
    assert Path(resolved).name == "payroll_rules.yaml"
