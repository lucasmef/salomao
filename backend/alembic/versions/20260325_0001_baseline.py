"""baseline schema for sqlite/postgresql dual mode

Revision ID: 20260325_0001
Revises:
Create Date: 2026-03-25 10:30:00
"""

from __future__ import annotations

from alembic import op

from app.db.base import Base
from app.db.models import all_models  # noqa: F401

# revision identifiers, used by Alembic.
revision = "20260325_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
