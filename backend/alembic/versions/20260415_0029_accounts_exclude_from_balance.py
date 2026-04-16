"""add account exclude_from_balance flag

Revision ID: 20260415_0029
Revises: 20260410_0028
Create Date: 2026-04-15 21:35:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260415_0029"
down_revision = "20260410_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("exclude_from_balance", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("accounts", "exclude_from_balance", server_default=None)


def downgrade() -> None:
    op.drop_column("accounts", "exclude_from_balance")
