"""publication_gate_fields

Revision ID: 9c2f7a1b4d80
Revises: 436c85ba9928
Create Date: 2026-11-22 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9c2f7a1b4d80'
down_revision: Union[str, Sequence[str], None] = '436c85ba9928'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'datasets',
        sa.Column('retention_until', sa.Date(), nullable=True),
    )
    op.add_column(
        'datasets',
        sa.Column('published_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'datasets',
        sa.Column('published_by', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('datasets', 'published_by')
    op.drop_column('datasets', 'published_at')
    op.drop_column('datasets', 'retention_until')
