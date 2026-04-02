"""link inter boletos to account for pdf download

Revision ID: 20260402_0014
Revises: 20260402_0013
Create Date: 2026-04-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260402_0014"
down_revision = "20260402_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("boleto_records", sa.Column("inter_account_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_boleto_records_inter_account_id"), "boleto_records", ["inter_account_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_boleto_records_inter_account_id"), table_name="boleto_records")
    op.drop_column("boleto_records", "inter_account_id")
