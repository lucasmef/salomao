"""add percent config to report layout lines

Revision ID: 20260328_0005
Revises: 20260328_0004
Create Date: 2026-03-28 11:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260328_0005"
down_revision = "20260328_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "report_layout_lines",
        sa.Column("show_percent", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "report_layout_lines",
        sa.Column("percent_mode", sa.String(length=30), nullable=False, server_default="reference_line"),
    )
    op.add_column(
        "report_layout_lines",
        sa.Column("percent_reference_line_id", sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("report_layout_lines", "percent_reference_line_id")
    op.drop_column("report_layout_lines", "percent_mode")
    op.drop_column("report_layout_lines", "show_percent")
