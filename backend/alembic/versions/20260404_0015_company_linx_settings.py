"""store linx settings on company

Revision ID: 20260404_0015
Revises: 20260402_0014
Create Date: 2026-04-04 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260404_0015"
down_revision = "20260402_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("linx_base_url", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("linx_username", sa.String(length=160), nullable=True))
    op.add_column("companies", sa.Column("linx_password_encrypted", sa.String(length=512), nullable=True))
    op.add_column("companies", sa.Column("linx_sales_view_name", sa.String(length=160), nullable=True))
    op.add_column("companies", sa.Column("linx_receivables_view_name", sa.String(length=160), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "linx_receivables_view_name")
    op.drop_column("companies", "linx_sales_view_name")
    op.drop_column("companies", "linx_password_encrypted")
    op.drop_column("companies", "linx_username")
    op.drop_column("companies", "linx_base_url")
