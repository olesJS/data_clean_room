"""create legal_basis table

Revision ID: 001_legal_basis
Revises:
Create Date: 2026-11-01 04:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_legal_basis"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type if in Postgres
    legal_basis_type_enum = sa.Enum(
        "consent", "contract", "law", name="legal_basis_type_enum"
    )
    legal_basis_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "legal_basis",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "dataset_id",
            sa.Integer(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", legal_basis_type_enum, nullable=False),
        sa.Column("document_ref", sa.String(length=255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "entered_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_legal_basis_id"), "legal_basis", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_legal_basis_dataset_id"), "legal_basis", ["dataset_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_legal_basis_dataset_id"), table_name="legal_basis")
    op.drop_index(op.f("ix_legal_basis_id"), table_name="legal_basis")
    op.drop_table("legal_basis")
    legal_basis_type_enum = sa.Enum(
        "consent", "contract", "law", name="legal_basis_type_enum"
    )
    legal_basis_type_enum.drop(op.get_bind(), checkfirst=True)

