"""add linx auto sync company settings

Revision ID: 20260404_0016
Revises: 20260404_0015
Create Date: 2026-04-04 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260404_0016"
down_revision = "20260404_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("linx_auto_sync_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("companies", sa.Column("linx_auto_sync_alert_email", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("linx_auto_sync_last_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("companies", sa.Column("linx_auto_sync_last_status", sa.String(length=20), nullable=True))
    op.add_column("companies", sa.Column("linx_auto_sync_last_error", sa.Text(), nullable=True))
    op.alter_column("companies", "linx_auto_sync_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("companies", "linx_auto_sync_last_error")
    op.drop_column("companies", "linx_auto_sync_last_status")
    op.drop_column("companies", "linx_auto_sync_last_run_at")
    op.drop_column("companies", "linx_auto_sync_alert_email")
    op.drop_column("companies", "linx_auto_sync_enabled")
