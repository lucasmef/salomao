"""add supplier ignore flag for purchase planning

Revision ID: 20260331_0010
Revises: 20260330_0009
Create Date: 2026-03-31 00:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0010"
down_revision = "20260330_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "suppliers",
        sa.Column("ignore_in_purchase_planning", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("suppliers", "ignore_in_purchase_planning", server_default=None)


def downgrade() -> None:
    op.drop_column("suppliers", "ignore_in_purchase_planning")
