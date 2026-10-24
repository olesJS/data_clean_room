from datetime import datetime
from typing import Any, Dict

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

    model_config = ConfigDict(from_attributes=True)
