from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class UserResponse(BaseModel):
    id: int
    email: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    actor: str
    action: str
    object: str
    result: str

    model_config = ConfigDict(from_attributes=True)


class DatasetResponse(BaseModel):
    id: int
    name: str
    original_filename: str
    file_size: int
    file_type: str
    columns: Dict[str, Any]
    row_count: int
    uploaded_by: str
    created_at: datetime
    # Sprint 2 — profiling fields (nullable until first profile run)
    data_class: Optional[str] = None
    quality_score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Sprint 2 — profiling / PII schemas
# ---------------------------------------------------------------------------

class ColumnHistogram(BaseModel):
    bins: List[str]
    counts: List[int]


class ColumnProfile(BaseModel):
    name: str
    type: str  # 'string' | 'numeric' | 'datetime' | 'boolean'
    null_count: int
    null_percentage: float
    unique_count: int
    is_pii: bool
    pii_type: Optional[str] = None
    pii_confidence: Optional[float] = None
    min: Optional[Any] = None
    max: Optional[Any] = None
    mean: Optional[float] = None
    outliers_count: int
    histogram: Optional[ColumnHistogram] = None


class DatasetSummary(BaseModel):
    total_rows: int
    total_columns: int
    duplicate_rows_count: int
    rules_violated_count: int


class DatasetProfileResponse(BaseModel):
    dataset_id: int
    dataset_name: str
    data_class: str
    quality_score: float
    summary: DatasetSummary
    columns: List[ColumnProfile]


class DatasetPIIResponse(BaseModel):
    dataset_id: int
    data_class: str
    pii_columns: List[ColumnProfile]
