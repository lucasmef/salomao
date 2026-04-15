"""add payment date to boleto records

Revision ID: 20260408_0025
Revises: 20260407_0024
Create Date: 2026-04-08 16:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0025"
down_revision = "20260407_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("boleto_records", sa.Column("payment_date", sa.Date(), nullable=True))
    op.create_index(op.f("ix_boleto_records_payment_date"), "boleto_records", ["payment_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_boleto_records_payment_date"), table_name="boleto_records")
    op.drop_column("boleto_records", "payment_date")
