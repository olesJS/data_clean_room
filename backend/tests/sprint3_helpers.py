"""Shared fixtures for Sprint 3 publication/exchange tests."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from app.auth import hash_password
from app.models import Dataset, DatasetVersion, User, utc_now

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FUTURE_DATE = (date.today() + timedelta(days=365)).isoformat()


def create_dataset(
    db_session,
    tmp_path: Path,
    *,
    name: str | None = None,
    uploaded_by: str = "provider@example.com",
    pii_findings: list[dict] | None = None,
    dataframe: pd.DataFrame | None = None,
) -> Dataset:
    name = name or f"sprint3-{uuid.uuid4().hex[:8]}"
    if dataframe is None:
        dataframe = pd.DataFrame(
            {
                "person_name": ["Іван Петренко", "Марія Коваль"],
                "ipn": ["1234567890", "9876543210"],
                "amount": [100, 200],
            }
        )
    file_path = tmp_path / f"{name}.csv"
    dataframe.to_csv(file_path, index=False, encoding="utf-8-sig")

    dataset = Dataset(
        name=name,
        original_filename=f"{name}.csv",
        file_path=str(file_path),
        file_size=file_path.stat().st_size,
        file_type="csv",
        columns={str(c): str(t) for c, t in dataframe.dtypes.items()},
        row_count=int(len(dataframe)),
        uploaded_by=uploaded_by,
        data_class="Personal" if pii_findings else "Internal",
        status="uploaded",
        pii_json=pii_findings
        if pii_findings is not None
        else [
            {
                "column_name": "person_name",
                "pii_type": "person_name",
                "confidence": 0.9,
                "sample_masked": "І***",
                "detection_method": "test",
                "user_confirmed": None,
                "corrected_pii_type": None,
            },
            {
                "column_name": "ipn",
                "pii_type": "ipn",
                "confidence": 0.9,
                "sample_masked": "12******90",
                "detection_method": "test",
                "user_confirmed": None,
                "corrected_pii_type": None,
            },
        ],
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


def add_clean_version(
    db_session,
    dataset: Dataset,
    *,
    file_path: str | None = None,
) -> DatasetVersion:
    version = DatasetVersion(
        dataset_id=dataset.id,
        kind="clean",
        version_number=1,
        file_path=file_path or dataset.file_path,
        file_name="clean.csv",
        file_type="csv",
        file_size=dataset.file_size,
        row_count=dataset.row_count,
        sha256="0" * 64,
        columns=dataset.columns,
        data_class="Confidential",
        created_by="provider@example.com",
        created_at=utc_now(),
    )
    db_session.add(version)
    db_session.commit()
    db_session.refresh(version)
    return version


def create_legal_basis(
    client,
    token: str,
    dataset_id: int,
    *,
    purpose: str = "analytics",
    valid_until: str = FUTURE_DATE,
):
    response = client.post(
        f"/datasets/{dataset_id}/legal-basis",
        json={
            "type": "consent",
            "document_ref": f"CONSENT-{uuid.uuid4().hex[:8]}",
            "date": date.today().isoformat(),
            "purpose": purpose,
            "valid_until": valid_until,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def anonymize(
    client,
    token: str,
    dataset_id: int,
    methods: dict[str, str] | None = None,
):
    response = client.post(
        f"/datasets/{dataset_id}/anonymize",
        json={"methods": methods or {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    return response


def publish(
    client,
    token: str,
    dataset_id: int,
    retention_until: str | None = None,
):
    return client.post(
        f"/datasets/{dataset_id}/publish",
        json={
            "retention_until": retention_until
            or (date.today() + timedelta(days=180)).isoformat()
        },
        headers={"Authorization": f"Bearer {token}"},
    )


def create_other_provider(client, db_session) -> str:
    email = f"other-provider-{uuid.uuid4().hex[:6]}@example.com"
    db_session.add(
        User(
            email=email,
            hashed_password=hash_password("password123"),
            role="DataProvider",
        )
    )
    db_session.commit()
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def create_consumer(client, db_session, email: str | None = None) -> str:
    email = email or f"consumer-{uuid.uuid4().hex[:6]}@example.com"
    db_session.add(
        User(
            email=email,
            hashed_password=hash_password("password123"),
            role="DataConsumer",
        )
    )
    db_session.commit()
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def prepare_published_dataset(
    client,
    provider_token: str,
    db_session,
    tmp_path: Path,
    *,
    methods: dict[str, str] | None = None,
    with_legal_basis: bool = True,
    purpose: str = "analytics",
) -> Dataset:
    dataset = create_dataset(db_session, tmp_path)
    if with_legal_basis:
        create_legal_basis(
            client, provider_token, dataset.id, purpose=purpose
        )
    response = anonymize(
        client, provider_token, dataset.id, methods or {"ipn": "mask"}
    )
    assert response.status_code == 200, response.text
    response = publish(client, provider_token, dataset.id)
    assert response.status_code == 200, response.text
    db_session.refresh(dataset)
    return dataset
