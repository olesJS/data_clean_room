"""Наповнення демо-середовища Data Clean Room (Sprint 3).

Сценарій проходить повний шлях UC-07/UC-08 через публічний API:
завантаження -> PII review -> правова підстава -> анонімізація ->
публікація -> запит Data Consumer -> схвалення Data Provider.

Запуск (стек уже піднятий, БД свіжа):

    python scripts/demo_seed.py
    python scripts/demo_seed.py --base-url http://localhost:8000

Скрипт не використовує службові паролі з коду застосунку і працює лише
з демонстраційними акаунтами, які створює init_db у development/test.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_PASSWORD = "password123"
DATASETS = (
    ("payroll.csv", "payroll.csv", "Демо: зарплатний реєстр"),
    ("customers.json", "customers.json", "Демо: клієнти"),
)


def login(client: httpx.Client, email: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": DEFAULT_PASSWORD},
    )
    if response.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {response.text}")
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def must(response: httpx.Response, expected: int, action: str) -> dict:
    if response.status_code != expected:
        raise RuntimeError(f"{action} failed ({response.status_code}): {response.text}")
    return response.json()


def review_pii(client: httpx.Client, token: str, dataset_id: int) -> int:
    scan = must(
        client.get(f"/api/datasets/{dataset_id}/pii", headers=auth(token)),
        200,
        "PII scan",
    )
    reviewed = 0
    for finding in scan.get("findings", []):
        if finding.get("user_confirmed") is not None:
            continue
        must(
            client.patch(
                f"/api/datasets/{dataset_id}/pii/{finding['column_name']}",
                json={"user_confirmed": True},
                headers=auth(token),
            ),
            200,
            f"PII review ({finding['column_name']})",
        )
        reviewed += 1
    return reviewed


def create_and_publish(
    client: httpx.Client,
    token: str,
    filename: str,
    display_name: str,
) -> dict:
    path = DATA_DIR / filename
    media_type = "application/json" if path.suffix == ".json" else "text/csv"
    with path.open("rb") as handle:
        uploaded = must(
            client.post(
                "/api/datasets",
                data={"name": display_name},
                files={"file": (filename, handle, media_type)},
                headers=auth(token),
            ),
            201,
            f"Upload {filename}",
        )

    dataset_id = int(uploaded["id"])
    reviewed = review_pii(client, token, dataset_id)
    must(
        client.post(
            f"/api/datasets/{dataset_id}/legal-basis",
            json={
                "type": "consent",
                "document_ref": f"DEMO-CONSENT-{dataset_id}",
                "date": date.today().isoformat(),
                "purpose": "analytics",
                "valid_until": (date.today() + timedelta(days=365)).isoformat(),
            },
            headers=auth(token),
        ),
        201,
        "Legal basis",
    )
    anonymized = must(
        client.post(
            f"/api/datasets/{dataset_id}/anonymize",
            json={"methods": {}},
            headers=auth(token),
        ),
        200,
        "Anonymisation",
    )
    retention = (date.today() + timedelta(days=180)).isoformat()
    gate = must(
        client.get(
            f"/api/datasets/{dataset_id}/publish/check",
            params={"retention_until": retention},
            headers=auth(token),
        ),
        200,
        "Publication check",
    )
    if not gate["allowed"]:
        raise RuntimeError(
            f"Publication gate blocked {filename}: {gate['reasons']}"
        )
    published = must(
        client.post(
            f"/api/datasets/{dataset_id}/publish",
            json={"retention_until": retention},
            headers=auth(token),
        ),
        200,
        "Publish",
    )
    return {
        "dataset_id": dataset_id,
        "name": display_name,
        "pii_reviewed": reviewed,
        "clean_version": anonymized["version_number"],
        "data_class": published["data_class"],
        "retention_until": published["retention_until"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Sprint 3 demo data")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60.0) as client:
        provider = login(client, "provider@example.com")
        consumer = login(client, "consumer@example.com")

        summaries = []
        for filename, display_name in [(f, n) for f, _, n in DATASETS]:
            summaries.append(
                create_and_publish(client, provider, filename, display_name)
            )

        first = summaries[0]
        request = must(
            client.post(
                "/api/exchange-requests",
                json={"dataset_id": first["dataset_id"], "purpose": "analytics"},
                headers=auth(consumer),
            ),
            201,
            "Exchange request",
        )
        approved = must(
            client.post(
                f"/api/exchange-requests/{request['id']}/approve",
                json={
                    "access_until": (date.today() + timedelta(days=30)).isoformat(),
                    "review_comment": "Демо: доступ схвалено",
                },
                headers=auth(provider),
            ),
            200,
            "Exchange approval",
        )

    print("Демо-дані готові:")
    for item in summaries:
        print(
            f"  dataset #{item['dataset_id']} «{item['name']}»: "
            f"clean v{item['clean_version']}, class {item['data_class']}, "
            f"retention {item['retention_until']}, PII review {item['pii_reviewed']}"
        )
    print(
        f"  exchange request #{approved['id']}: {approved['status']}, "
        f"access_until {approved['access_until']}"
    )
    print("Далі: consumer@example.com -> «Мої запити» -> Завантажити.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, httpx.HTTPError) as exc:
        print(f"ПОМИЛКА: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
