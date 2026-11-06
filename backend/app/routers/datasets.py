import io
import json
import os
import uuid
from typing import List, Optional

import pandas as pd
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import Dataset, User
from app.profiler import profile_dataframe
from app.schemas import (
    DatasetProfileResponse,
    DatasetResponse,
    PiiFinding,
    PiiScanResponse,
    PiiUpdatePayload,
)

router = APIRouter(tags=["datasets"])

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage/datasets")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 50 * 1024 * 1024))  # 50MB default


@router.post(
    "/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/api/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    current_user: User = Depends(require_role("DataProvider")),
    db: Session = Depends(get_db),
):
    actor = current_user.email
    filename = file.filename or "unnamed_file"

    # 1. Check file extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".csv", ".json"]:
        log_event(
            actor=actor,
            action="UPLOAD_DATASET",
            object=filename,
            result="FAILURE",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Only CSV and JSON files are allowed.",
        )

    # 2. Read content in chunks to enforce size limits before allocating full memory
    chunks = []
    total_size = 0
    chunk_size = 1024 * 1024  # 1MB
    limit_mb = MAX_FILE_SIZE // (1024 * 1024)

    try:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                log_event(
                    actor=actor,
                    action="UPLOAD_DATASET",
                    object=filename,
                    result="FAILURE",
                    db=db,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File size exceeds the allowed limit ({limit_mb}MB).",
                )
            chunks.append(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        log_event(
            actor=actor,
            action="UPLOAD_DATASET",
            object=filename,
            result="FAILURE",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(exc)}",
        )

    content = b"".join(chunks)

    # 3. Check for empty file
    if len(content) == 0:
        log_event(
            actor=actor,
            action="UPLOAD_DATASET",
            object=filename,
            result="FAILURE",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 4. Parse content with pandas, detect encoding/separator, determine schema
    file_type = ext.lstrip(".")
    try:
        if file_type == "csv":
            # Attempt encoding detection (UTF-8, UTF-8-SIG, CP1251, Latin1)
            text_sample = None
            encoding_used = "utf-8"
            for enc in ("utf-8-sig", "utf-8", "cp1251", "latin1"):
                try:
                    text_sample = content.decode(enc)
                    encoding_used = enc
                    break
                except UnicodeDecodeError:
                    continue

            if text_sample is None:
                raise ValueError("Unsupported encoding. Expected UTF-8 or CP1251.")

            lines = text_sample.splitlines()
            if not lines:
                raise ValueError("CSV file is empty or has no readable columns.")

            first_line = lines[0]
            sep = ";" if first_line.count(";") > first_line.count(",") else ","

            id_keywords = (
                "ipn",
                "tax_id",
                "edrpou",
                "phone",
                "іпн",
                "едрпоу",
                "єдрпоу",
                "рнокпп",
                "табель",
            )
            header_cols = [
                c.strip().strip('"').strip("'") for c in first_line.split(sep)
            ]
            dtype_overrides = {
                col: str
                for col in header_cols
                if any(k in col.lower() for k in id_keywords)
            }

            try:
                df = pd.read_csv(
                    io.BytesIO(content),
                    encoding=encoding_used,
                    sep=sep,
                    dtype=dtype_overrides if dtype_overrides else None,
                )
            except pd.errors.EmptyDataError:
                raise ValueError("CSV file is empty or has no readable columns.")
            except Exception as e:
                raise ValueError(f"Failed to parse CSV: {str(e)}")

            if len(df) == 0:
                raise ValueError("CSV file contains header only with no data rows.")

            for col in df.columns:
                if any(k in str(col).lower() for k in id_keywords):
                    df[col] = df[col].astype(str)

        elif file_type == "json":
            try:
                decoded_text = content.decode("utf-8")
                json_data = json.loads(decoded_text)
            except UnicodeDecodeError as ue:
                raise ValueError(f"Invalid text encoding in JSON file: {str(ue)}")
            except json.JSONDecodeError as je:
                raise ValueError(f"Invalid JSON syntax: {str(je)}")

            if isinstance(json_data, list):
                if len(json_data) == 0:
                    raise ValueError("JSON array is empty.")
                df = pd.DataFrame(json_data)
            elif isinstance(json_data, dict):
                if len(json_data) == 0:
                    raise ValueError("JSON object is empty.")
                try:
                    df = pd.DataFrame(json_data)
                except Exception:
                    df = pd.read_json(io.BytesIO(content))
            else:
                msg = "JSON must be an array of objects or an object of columns."
                raise ValueError(msg)

        if df is None or len(df.columns) == 0:
            raise ValueError("File contains no tabular columns.")

        columns_schema = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
        row_count = int(len(df))

    except Exception as exc:
        log_event(
            actor=actor,
            action="UPLOAD_DATASET",
            object=filename,
            result="FAILURE",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File validation or parsing failed: {str(exc)}",
        )

    # 5. Save raw file unaltered to storage
    os.makedirs(STORAGE_DIR, exist_ok=True)
    safe_filename = f"{uuid.uuid4().hex}_{os.path.basename(filename)}"
    saved_file_path = os.path.join(STORAGE_DIR, safe_filename)

    try:
        with open(saved_file_path, "wb") as f:
            f.write(content)
    except Exception as exc:
        log_event(
            actor=actor,
            action="UPLOAD_DATASET",
            object=filename,
            result="FAILURE",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file to storage: {str(exc)}",
        )

    # 6. Save metadata to database
    dataset_name = name.strip() if name and name.strip() else filename
    dataset = Dataset(
        name=dataset_name,
        original_filename=filename,
        file_path=saved_file_path,
        file_size=len(content),
        file_type=file_type,
        columns=columns_schema,
        row_count=row_count,
        uploaded_by=actor,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    # 6b. Run profiling immediately after saving
    try:
        profile = profile_dataframe(df, dataset.id, dataset.name)
        pii_cols = [c for c in profile["columns"] if c["is_pii"]]
        dataset.profile_json = profile
        dataset.data_class = profile["data_class"]
        dataset.quality_score = profile["quality_score"]
        dataset.pii_json = profile.get("pii_findings", pii_cols)
        db.commit()
        db.refresh(dataset)
    except Exception as exc:
        # Profiling failure must not block the upload response
        print(f"[PROFILER WARNING] Could not profile dataset {dataset.id}: {exc}")

    # 7. Log successful upload in audit service
    log_event(
        actor=actor,
        action="UPLOAD_DATASET",
        object=dataset.name,
        result="SUCCESS",
        db=db,
    )

    return dataset


@router.get("/datasets", response_model=List[DatasetResponse])
@router.get("/api/datasets", response_model=List[DatasetResponse])
def list_datasets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == "DataProvider":
        datasets = (
            db.query(Dataset)
            .filter(Dataset.uploaded_by == current_user.email)
            .order_by(Dataset.created_at.desc())
            .all()
        )
    else:
        datasets = db.query(Dataset).order_by(Dataset.created_at.desc()).all()

    log_event(
        actor=current_user.email,
        action="LIST_DATASETS",
        object="/datasets",
        result="SUCCESS",
        db=db,
    )

    return datasets


# ---------------------------------------------------------------------------
# Sprint 2 â€” Profile & PII endpoints
# ---------------------------------------------------------------------------


def _load_df_for_dataset(dataset: Dataset) -> "pd.DataFrame":
    """Re-read the stored file and return a DataFrame for re-profiling."""
    import io
    import json as _json

    file_path = dataset.file_path
    file_type = dataset.file_type.lower()

    with open(file_path, "rb") as fh:
        content = fh.read()

    if file_type == "csv":
        for enc in ("utf-8-sig", "utf-8", "cp1251", "latin1"):
            try:
                return pd.read_csv(io.BytesIO(content), encoding=enc)
            except Exception:
                continue
        raise ValueError("Cannot decode CSV file.")
    elif file_type == "json":
        data = _json.loads(content.decode("utf-8"))
        if isinstance(data, list):
            return pd.DataFrame(data)
        return pd.DataFrame(data)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


@router.get("/datasets/{dataset_id}/profile", response_model=DatasetProfileResponse)
@router.get("/api/datasets/{dataset_id}/profile", response_model=DatasetProfileResponse)
def get_dataset_profile(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the cached profile for a dataset (re-computes if missing)."""
    # Fetch dataset with role-based visibility
    if current_user.role == "DataProvider":
        dataset = (
            db.query(Dataset)
            .filter(Dataset.id == dataset_id, Dataset.uploaded_by == current_user.email)
            .first()
        )
    else:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found."
        )

    # Re-profile if no cached result
    if dataset.profile_json is None:
        try:
            df = _load_df_for_dataset(dataset)
            profile = profile_dataframe(df, dataset.id, dataset.name)
            pii_cols = [c for c in profile["columns"] if c["is_pii"]]
            dataset.profile_json = profile
            dataset.data_class = profile["data_class"]
            dataset.quality_score = profile["quality_score"]
            dataset.pii_json = profile.get("pii_findings", pii_cols)
            db.commit()
            db.refresh(dataset)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Profiling failed: {exc}",
            )

    log_event(
        actor=current_user.email,
        action="VIEW_PROFILE",
        object=f"dataset:{dataset_id}",
        result="SUCCESS",
        db=db,
    )

    return dataset.profile_json


@router.get("/datasets/{dataset_id}/pii", response_model=PiiScanResponse)
@router.get("/api/datasets/{dataset_id}/pii", response_model=PiiScanResponse)
def get_dataset_pii(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return PII scan findings for a dataset in the format expected by UI."""
    if current_user.role == "DataProvider":
        dataset = (
            db.query(Dataset)
            .filter(Dataset.id == dataset_id, Dataset.uploaded_by == current_user.email)
            .first()
        )
    else:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found."
        )

    # Ensure profile exists
    if dataset.profile_json is None:
        try:
            df = _load_df_for_dataset(dataset)
            profile = profile_dataframe(df, dataset.id, dataset.name)
            pii_cols = [c for c in profile["columns"] if c["is_pii"]]
            dataset.profile_json = profile
            dataset.data_class = profile["data_class"]
            dataset.quality_score = profile["quality_score"]
            dataset.pii_json = profile.get("pii_findings", pii_cols)
            db.commit()
            db.refresh(dataset)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Profiling failed: {exc}",
            )

    log_event(
        actor=current_user.email,
        action="VIEW_PII",
        object=f"dataset:{dataset_id}",
        result="SUCCESS",
        db=db,
    )

    findings = dataset.pii_json or []
    total_cols = (
        len(dataset.columns)
        if isinstance(dataset.columns, (dict, list))
        else len(findings)
    )
    pii_count = len(
        [
            f
            for f in findings
            if f.get("pii_type") and f.get("user_confirmed") is not False
        ]
    )

    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "data_class": dataset.data_class or "Internal",
        "pii_columns_count": pii_count,
        "total_columns": total_cols,
        "findings": findings,
    }


@router.patch("/datasets/{dataset_id}/pii/{column_name}", response_model=PiiFinding)
@router.patch("/api/datasets/{dataset_id}/pii/{column_name}", response_model=PiiFinding)
def update_pii_column(
    dataset_id: int,
    column_name: str,
    payload: PiiUpdatePayload,
    current_user: User = Depends(require_roles(["DataProvider", "DataSteward"])),
    db: Session = Depends(get_db),
):
    """Confirm or correct a PII finding classification for a column."""
    if current_user.role == "DataProvider":
        dataset = (
            db.query(Dataset)
            .filter(Dataset.id == dataset_id, Dataset.uploaded_by == current_user.email)
            .first()
        )
    else:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found."
        )

    findings = list(dataset.pii_json or [])
    found_idx = next(
        (i for i, f in enumerate(findings) if f.get("column_name") == column_name), None
    )

    if found_idx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PII finding for column '{column_name}' not found.",
        )

    finding = dict(findings[found_idx])
    finding["user_confirmed"] = payload.user_confirmed
    if payload.corrected_pii_type is not None:
        finding["corrected_pii_type"] = payload.corrected_pii_type

    findings[found_idx] = finding
    dataset.pii_json = findings

    active_types = {
        f.get("corrected_pii_type") or f.get("pii_type")
        for f in findings
        if f.get("user_confirmed") is not False
        and (f.get("corrected_pii_type") or f.get("pii_type"))
    }
    personal_markers = {
        "ipn",
        "passport",
        "card",
        "UA_IPN",
        "UA_PASSPORT",
        "CREDIT_CARD",
    }
    confidential_markers = {
        "iban",
        "email",
        "phone",
        "person_name",
        "address",
        "UA_IBAN",
        "UA_PHONE",
        "UA_FULL_NAME",
    }

    if active_types & personal_markers:
        dataset.data_class = "Personal"
    elif active_types & confidential_markers:
        dataset.data_class = "Confidential"
    else:
        dataset.data_class = "Internal"

    db.commit()
    db.refresh(dataset)

    log_event(
        actor=current_user.email,
        action="UPDATE_PII_CLASSIFICATION",
        object=f"dataset:{dataset_id}:column:{column_name}",
        result="SUCCESS",
        db=db,
    )

    return finding


# ---------------------------------------------------------------------------
# DELETE /api/datasets/{id} — видалити набір даних (тільки власник-DataProvider)
# ---------------------------------------------------------------------------


@router.delete("/datasets/{dataset_id}", status_code=204)
@router.delete("/api/datasets/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: int,
    current_user: User = Depends(require_roles(["DataProvider", "DataSteward"])),
    db: Session = Depends(get_db),
):
    """Delete a dataset owned by the current DataProvider.
    Removes the file from disk and the row from the database.
    """
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.uploaded_by == current_user.email)
        .first()
    )

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found or you do not have permission to delete it.",
        )

    # Remove stored file (best-effort — don't block deletion if missing)
    file_path = dataset.file_path
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as exc:
            print(f"[WARN] Could not remove file {file_path}: {exc}")

    dataset_name = dataset.name

    db.delete(dataset)
    db.commit()

    log_event(
        actor=current_user.email,
        action="DELETE_DATASET",
        object=f"dataset:{dataset_id}:{dataset_name}",
        result="SUCCESS",
        db=db,
    )
