"""Anonymisation of PII columns and clean DatasetVersion creation (SCRUM-55/57).

Supported methods:
    mask        replace every non-null value with ``***``
    redact      remove the column from the clean copy
    generalize  keep a coarse bucket (year for dates, decade for numbers,
                first character for text)
    hmac        deterministic pseudonymisation with HMAC-SHA256

HMAC is pseudonymisation, not full anonymisation: the publication gate keeps
the dataset class at ``Personal`` and requires an active legal basis.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AnonymizationMethod, Dataset, DatasetVersion, utc_now
from app.services.dataset_io import load_dataframe_for_dataset
from app.services.pii_utils import active_pii_findings

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage/datasets")

SUPPORTED_METHODS = ("mask", "generalize", "hmac", "redact")

DEFAULT_METHOD_BY_PII: dict[str, str] = {
    "person_name": "mask",
    "address": "mask",
    "email": "mask",
    "phone": "mask",
    "birth_date": "generalize",
    "ipn": "hmac",
    "passport": "hmac",
    "iban": "hmac",
    "card": "hmac",
}


class AnonymizerError(ValueError):
    """Raised for invalid anonymisation requests."""


@dataclass(frozen=True)
class ColumnMethod:
    column_name: str
    pii_type: str
    method: str


def _hmac_key() -> bytes:
    key = os.getenv("HMAC_KEY")
    if key:
        return key.encode("utf-8")
    env = os.getenv("ENV", "development").lower()
    if env in ("development", "test", "dev"):
        # Deterministic development-only fallback. Production must set HMAC_KEY.
        return b"dev_hmac_key_data_clean_room_change_me"
    raise RuntimeError("HMAC_KEY environment variable must be set in production")


def _default_method(pii_type: str) -> str:
    return DEFAULT_METHOD_BY_PII.get(pii_type.lower(), "mask")


def resolve_column_methods(
    dataset: Dataset,
    overrides: dict[str, str] | None = None,
) -> list[ColumnMethod]:
    """Build the method list for every active PII column.

    ``overrides`` maps a column name to one of ``SUPPORTED_METHODS``. Unknown
    columns and unsupported methods are rejected with ``AnonymizerError`` so a
    typo cannot silently leave PII unprocessed.
    """
    findings = active_pii_findings(dataset)
    known_columns = {finding["column_name"] for finding in findings}
    overrides = overrides or {}

    unknown = sorted(set(overrides) - known_columns)
    if unknown:
        raise AnonymizerError(
            "Unknown PII column(s) in methods: " + ", ".join(unknown)
        )

    methods: list[ColumnMethod] = []
    for finding in findings:
        column = finding["column_name"]
        method = overrides.get(column) or _default_method(finding["pii_type"])
        method = method.strip().lower()
        if method not in SUPPORTED_METHODS:
            raise AnonymizerError(
                f"Unsupported anonymisation method '{method}' for column "
                f"'{column}'. Allowed: {', '.join(SUPPORTED_METHODS)}."
            )
        methods.append(
            ColumnMethod(
                column_name=column,
                pii_type=finding["pii_type"],
                method=method,
            )
        )
    return methods


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _mask_series(series: pd.Series) -> pd.Series:
    return series.map(lambda value: value if _is_missing(value) else "***")


def _generalize_series(series: pd.Series, pii_type: str) -> pd.Series:
    if pii_type.lower() == "birth_date" or pd.api.types.is_datetime64_any_dtype(
        series
    ):
        parsed = pd.to_datetime(series, errors="coerce")
        return parsed.dt.year.map(
            lambda value: None if pd.isna(value) else str(int(value))
        )

    if pd.api.types.is_numeric_dtype(series):
        def bucket(value: Any) -> Any:
            if _is_missing(value):
                return value
            try:
                lower = (int(float(value)) // 10) * 10
            except (TypeError, ValueError):
                return "***"
            return f"{lower}-{lower + 9}"

        return series.map(bucket)

    def text_bucket(value: Any) -> Any:
        if _is_missing(value):
            return value
        text = str(value)
        return f"{text[:1]}***" if text else "***"

    return series.map(text_bucket)


def _hmac_series(series: pd.Series, key: bytes) -> pd.Series:
    def digest(value: Any) -> Any:
        if _is_missing(value):
            return value
        raw = str(value).encode("utf-8")
        return "hmac_" + hmac.new(key, raw, hashlib.sha256).hexdigest()[:32]

    return series.map(digest)


def _apply_to_dataframe(
    dataframe: pd.DataFrame,
    methods: list[ColumnMethod],
) -> pd.DataFrame:
    clean = dataframe.copy()
    key = _hmac_key()
    for column_method in methods:
        column = column_method.column_name
        if column not in clean.columns:
            continue
        if column_method.method == "redact":
            clean = clean.drop(columns=[column])
        elif column_method.method == "mask":
            clean[column] = _mask_series(clean[column])
        elif column_method.method == "generalize":
            clean[column] = _generalize_series(
                clean[column], column_method.pii_type
            )
        elif column_method.method == "hmac":
            clean[column] = _hmac_series(clean[column], key)
    return clean


def _estimated_class(methods: list[ColumnMethod]) -> str:
    if not methods:
        return "Internal"
    if any(item.method == "hmac" for item in methods):
        return "Personal"
    return "Confidential"


def _method_counts(methods: list[ColumnMethod]) -> dict[str, int]:
    counts = {name: 0 for name in SUPPORTED_METHODS}
    for item in methods:
        counts[item.method] = counts.get(item.method, 0) + 1
    return counts


def _serialize_preview(
    dataset: Dataset,
    methods: list[ColumnMethod],
) -> dict[str, Any]:
    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "columns": [
            {
                "column_name": item.column_name,
                "pii_type": item.pii_type,
                "method": item.method,
            }
            for item in methods
        ],
        "method_counts": _method_counts(methods),
        "estimated_class": _estimated_class(methods),
        "hmac_requires_legal_basis": any(
            item.method == "hmac" for item in methods
        ),
        "pii_columns_count": len(methods),
    }


def preview_anonymization(
    dataset: Dataset,
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Describe what an anonymisation run would do, without writing anything."""
    methods = resolve_column_methods(dataset, overrides)
    return _serialize_preview(dataset, methods)


def _write_clean_file(
    dataframe: pd.DataFrame,
    dataset: Dataset,
) -> tuple[str, str, int, str]:
    os.makedirs(STORAGE_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(dataset.original_filename))[0]
    extension = f".{dataset.file_type.lower()}"
    file_name = f"{stem}_clean{extension}"
    file_path = os.path.join(
        STORAGE_DIR, f"{uuid.uuid4().hex}_{file_name}"
    )

    if dataset.file_type.lower() == "json":
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write(
                dataframe.to_json(
                    orient="records", force_ascii=False, indent=2
                )
            )
    else:
        dataframe.to_csv(file_path, index=False, encoding="utf-8-sig")

    with open(file_path, "rb") as handle:
        content = handle.read()
    checksum = hashlib.sha256(content).hexdigest()
    return file_path, file_name, len(content), checksum


def apply_anonymization(
    db: Session,
    dataset: Dataset,
    overrides: dict[str, str] | None = None,
    actor: str = "system",
) -> DatasetVersion:
    """Create a clean dataset version and persist the applied methods."""
    methods = resolve_column_methods(dataset, overrides)
    dtype_columns = {
        item.column_name: str for item in methods if item.method == "hmac"
    }
    dataframe = load_dataframe_for_dataset(
        dataset, dtype_columns=dtype_columns or None
    )
    clean_dataframe = _apply_to_dataframe(dataframe, methods)

    file_path, file_name, file_size, checksum = _write_clean_file(
        clean_dataframe, dataset
    )

    max_version = (
        db.query(func.max(DatasetVersion.version_number))
        .filter(
            DatasetVersion.dataset_id == dataset.id,
            DatasetVersion.kind == "clean",
        )
        .scalar()
        or 0
    )
    version = DatasetVersion(
        dataset_id=dataset.id,
        kind="clean",
        version_number=int(max_version) + 1,
        file_path=file_path,
        file_name=file_name,
        file_type=dataset.file_type.lower(),
        file_size=file_size,
        row_count=int(len(clean_dataframe)),
        sha256=checksum,
        columns={
            str(column): str(dtype)
            for column, dtype in clean_dataframe.dtypes.items()
        },
        data_class=_estimated_class(methods),
        created_by=actor,
        created_at=utc_now(),
    )
    db.add(version)
    db.flush()

    db.query(AnonymizationMethod).filter(
        AnonymizationMethod.dataset_id == dataset.id
    ).delete(synchronize_session=False)
    for item in methods:
        db.add(
            AnonymizationMethod(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                column_name=item.column_name,
                method=item.method,
                params={"pii_type": item.pii_type},
                created_by=actor,
            )
        )

    # A new clean version invalidates an earlier publication decision.
    if dataset.status == "published":
        dataset.status = "uploaded"
        dataset.published_at = None
        dataset.published_by = None

    db.commit()
    db.refresh(version)
    return version


def latest_clean_version(
    db: Session, dataset_id: int
) -> DatasetVersion | None:
    return (
        db.query(DatasetVersion)
        .filter(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.kind == "clean",
        )
        .order_by(DatasetVersion.version_number.desc())
        .first()
    )


def method_map(db: Session, dataset_id: int) -> dict[str, str]:
    rows = (
        db.query(AnonymizationMethod)
        .filter(AnonymizationMethod.dataset_id == dataset_id)
        .all()
    )
    return {row.column_name: row.method for row in rows}


__all__ = [
    "AnonymizerError",
    "ColumnMethod",
    "DEFAULT_METHOD_BY_PII",
    "SUPPORTED_METHODS",
    "apply_anonymization",
    "latest_clean_version",
    "method_map",
    "preview_anonymization",
    "resolve_column_methods",
]
