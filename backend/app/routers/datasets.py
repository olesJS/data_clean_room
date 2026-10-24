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
from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import Dataset, User
from app.schemas import DatasetResponse

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
    current_user: User = Depends(require_roles(["DataProvider", "DataSteward"])),
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

            try:
                df = pd.read_csv(
                    io.BytesIO(content),
                    encoding=encoding_used,
                    sep=sep,
                )
            except pd.errors.EmptyDataError:
                raise ValueError("CSV file is empty or has no readable columns.")
            except Exception as e:
                raise ValueError(f"Failed to parse CSV: {str(e)}")

            if len(df) == 0:
                raise ValueError("CSV file contains header only with no data rows.")

            # Preserve identifier columns (IPN, EDRPOU, phone) as string
            id_keywords = ("ipn", "tax_id", "edrpou", "phone")
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
