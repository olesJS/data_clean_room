from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Integer, String

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # DataProvider, DataConsumer, DataSteward
    created_at = Column(DateTime, default=utc_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=utc_now, nullable=False)
    actor = Column(String(255), nullable=False)
    action = Column(String(100), nullable=False)
    object = Column(String(255), nullable=False)
    result = Column(String(50), nullable=False)


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String(20), nullable=False)  # csv, json
    columns = Column(JSON, nullable=False)  # {column_name: data_type}
    row_count = Column(Integer, nullable=False)
    uploaded_by = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
