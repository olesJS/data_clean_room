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
    UniqueConstraint,
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
    # Sprint 3 publication fields (SCRUM-57)
    status = Column(String(20), nullable=False, default="uploaded")
    published_at = Column(DateTime, nullable=True)
    published_by = Column(String(255), nullable=True)
    retention_until = Column(Date, nullable=True)


class DatasetVersion(Base):
    """Immutable snapshot of a dataset file (raw or anonymised clean copy)."""

    __tablename__ = "dataset_versions"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = Column(String(10), nullable=False)  # raw | clean
    version_number = Column(Integer, nullable=False, default=1)
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    row_count = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False)
    columns = Column(JSON, nullable=True)
    data_class = Column(String(50), nullable=True)
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    dataset = relationship("Dataset", backref="versions")

    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "kind",
            "version_number",
            name="uq_dataset_version_kind_number",
        ),
    )


class AnonymizationMethod(Base):
    """Anonymisation method applied to one PII column (SCRUM-55/57)."""

    __tablename__ = "anonymization_methods"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    column_name = Column(String(255), nullable=False)
    method = Column(String(20), nullable=False)  # mask | generalize | hmac | redact
    params = Column(JSON, nullable=True)
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    dataset = relationship("Dataset", backref="anonymization_methods")
    dataset_version = relationship("DatasetVersion", backref="anonymization_methods")

    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "column_name",
            name="uq_anonymization_dataset_column",
        ),
    )


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


class ExchangeRequestStatus(str, enum.Enum):
    REQUESTED = "Requested"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    DOWNLOADED = "Downloaded"
    EXPIRED = "Expired"


class ExchangeRequest(Base):
    """Consumer request to access the clean version of a published dataset."""

    __tablename__ = "exchange_requests"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    requester_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reviewer_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(
        String(20),
        nullable=False,
        default=ExchangeRequestStatus.REQUESTED.value,
        index=True,
    )
    purpose = Column(String(30), nullable=False)
    requested_at = Column(DateTime, default=utc_now, nullable=False)
    decided_at = Column(DateTime, nullable=True)
    review_comment = Column(String(500), nullable=True)
    access_until = Column(Date, nullable=True)
    downloaded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    dataset = relationship("Dataset", backref="exchange_requests")
    dataset_version = relationship("DatasetVersion", backref="exchange_requests")
    requester = relationship(
        "User",
        foreign_keys=[requester_id],
        backref="exchange_requests",
    )
    reviewer = relationship(
        "User",
        foreign_keys=[reviewer_id],
        backref="reviewed_exchange_requests",
    )


__all__ = [
    "AnonymizationMethod",
    "Base",
    "Dataset",
    "DatasetVersion",
    "ExchangeRequest",
    "ExchangeRequestStatus",
    "LegalBasis",
    "LegalBasisPurpose",
    "LegalBasisType",
    "User",
    "AuditLog",
]
