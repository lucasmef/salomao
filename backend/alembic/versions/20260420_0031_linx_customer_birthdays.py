"""add linx customer birth dates and birthday alert tracking

Revision ID: 20260420_0031
Revises: 20260418_0030
Create Date: 2026-04-20 18:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_0031"
down_revision = "20260418_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("linx_customers", sa.Column("birth_date", sa.Date(), nullable=True))
    op.create_index("ix_linx_customers_birth_date", "linx_customers", ["birth_date"], unique=False)
    op.add_column(
        "companies",
        sa.Column("linx_birthday_alert_last_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "linx_birthday_alert_last_sent_at")
    op.drop_index("ix_linx_customers_birth_date", table_name="linx_customers")
    op.drop_column("linx_customers", "birth_date")
