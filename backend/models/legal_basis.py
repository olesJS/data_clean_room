"""SQLAlchemy 2.0 Model for Legal Basis registry."""

import datetime as dt
import enum
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class LegalBasisType(str, enum.Enum):
    CONSENT = "consent"
    CONTRACT = "contract"
    LAW = "law"


class LegalBasis(Base):
    """Registry of legal bases (consent, contract, law) for datasets.

    Enforces data governance compliance before dataset publication.
    """

    __tablename__ = "legal_basis"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[LegalBasisType] = mapped_column(
        SQLEnum(LegalBasisType, name="legal_basis_type_enum"),
        nullable=False,
    )
    document_ref: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    date: Mapped[dt.date] = mapped_column(
        Date,
        nullable=False,
    )
    entered_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    # Relationships
    dataset = relationship("Dataset", backref="legal_bases")
    user = relationship("User", backref="entered_legal_bases")
