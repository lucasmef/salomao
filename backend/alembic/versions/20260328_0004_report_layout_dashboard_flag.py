"""add dashboard flag to report layout lines

Revision ID: 20260328_0004
Revises: 20260328_0003
Create Date: 2026-03-28 09:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260328_0004"
down_revision = "20260328_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "report_layout_lines",
        sa.Column("show_on_dashboard", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("report_layout_lines", "show_on_dashboard")
