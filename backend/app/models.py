import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import relationship

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
    # Sprint 2 profiling fields
    data_class = Column(String(50), nullable=True)
    quality_score = Column(Float, nullable=True)
    profile_json = Column(JSON, nullable=True)
    pii_json = Column(JSON, nullable=True)
    status = Column(String(50), default="uploaded", nullable=False)


class LegalBasisType(str, enum.Enum):
    CONSENT = "consent"
    CONTRACT = "contract"
    LAW = "law"


class LegalBasisPurpose(str, enum.Enum):
    ANALYTICS = "analytics"
    RESEARCH = "research"
    REPORTING = "reporting"
    PUBLICATION = "publication"


class LegalBasis(Base):
    """Registry of legal bases (consent, contract, law) for datasets.

    Enforces data governance compliance before dataset publication.
    """

    __tablename__ = "legal_basis"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(
        SQLEnum(LegalBasisType, name="legal_basis_type_enum"),
        nullable=False,
    )
    document_ref = Column(String(255), nullable=False)
    date = Column(Date, nullable=False)
    purpose = Column(
        SQLEnum(LegalBasisPurpose, name="legal_basis_purpose_enum"),
        nullable=False,
    )
    valid_until = Column(Date, nullable=True)
    entered_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(DateTime, default=utc_now, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_reason = Column(String(500), nullable=True)

    dataset = relationship("Dataset", backref="legal_bases")
    user = relationship(
        "User",
        foreign_keys=[entered_by],
        backref="entered_legal_bases",
    )
    revoked_by_user = relationship(
        "User",
        foreign_keys=[revoked_by],
        backref="revoked_legal_bases",
    )

    @property
    def is_active(self) -> bool:
        """Whether the legal basis can be used for new governance checks."""
        if self.revoked_at is not None:
            return False
        if self.valid_until is not None and self.valid_until < date.today():
            return False
        return True


class DatasetVersionKind(str, enum.Enum):
    RAW = "raw"
    CLEAN = "clean"


class DatasetVersion(Base):
    """Stores versions of datasets (raw uploaded vs clean/anonymized)."""

    __tablename__ = "dataset_versions"
    __table_args__ = (
        # At most one raw version per dataset is allowed
        # (clean versions can be replaced or multiple depending on pipeline)
    )

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = Column(
        SQLEnum(DatasetVersionKind, name="dataset_version_kind_enum"),
        nullable=False,
    )
    file_path = Column(String(500), nullable=False)
    sha256 = Column(String(64), nullable=False)
    row_count = Column(Integer, nullable=False)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=utc_now, nullable=False)

    dataset = relationship("Dataset", backref="versions")
    creator = relationship("User", backref="created_dataset_versions")


class AnonymizationMethodType(str, enum.Enum):
    MASK = "mask"
    GENERALIZE = "generalize"
    HMAC = "hmac"


class AnonymizationMethod(Base):
    """Tracks applied anonymization methods per column for dataset versions."""

    __tablename__ = "anonymization_methods"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    column_name = Column(String(255), nullable=False)
    method = Column(
        SQLEnum(AnonymizationMethodType, name="anonymization_method_enum"),
        nullable=False,
    )
    params = Column(JSON, nullable=True)
    applied_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_at = Column(DateTime, default=utc_now, nullable=False)

    dataset = relationship("Dataset", backref="anonymization_methods")
    user = relationship("User", backref="applied_anonymizations")


class ExchangeRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DOWNLOADED = "downloaded"


class ExchangeRequest(Base):
    """Consumer requests to access and download clean anonymized datasets."""

    __tablename__ = "exchange_requests"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consumer_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose = Column(String(500), nullable=False)
    status = Column(
        SQLEnum(ExchangeRequestStatus, name="exchange_request_status_enum"),
        default=ExchangeRequestStatus.PENDING,
        nullable=False,
    )
    reviewed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_comment = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)

    dataset = relationship("Dataset", backref="exchange_requests")
    consumer = relationship(
        "User",
        foreign_keys=[consumer_id],
        backref="exchange_requests",
    )
    reviewer = relationship(
        "User",
        foreign_keys=[reviewed_by],
        backref="reviewed_exchange_requests",
    )


__all__ = [
    "Base",
    "User",
    "AuditLog",
    "Dataset",
    "DatasetVersion",
    "DatasetVersionKind",
    "AnonymizationMethod",
    "AnonymizationMethodType",
    "LegalBasis",
    "LegalBasisPurpose",
    "LegalBasisType",
    "ExchangeRequest",
    "ExchangeRequestStatus",
]
