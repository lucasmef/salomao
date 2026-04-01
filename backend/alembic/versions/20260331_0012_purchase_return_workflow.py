"""add workflow fields to purchase returns

Revision ID: 20260331_0012
Revises: 20260331_0011
Create Date: 2026-03-31 19:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0012"
down_revision = "20260331_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchase_returns", sa.Column("invoice_number", sa.String(length=80), nullable=True))
    op.add_column(
        "purchase_returns",
        sa.Column("status", sa.String(length=40), nullable=False, server_default="request_open"),
    )
    op.add_column("purchase_returns", sa.Column("refund_entry_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_purchase_returns_refund_entry_id_financial_entries",
        "purchase_returns",
        "financial_entries",
        ["refund_entry_id"],
        ["id"],
    )
    op.create_index(op.f("ix_purchase_returns_refund_entry_id"), "purchase_returns", ["refund_entry_id"], unique=False)
    op.alter_column("purchase_returns", "status", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_purchase_returns_refund_entry_id"), table_name="purchase_returns")
    op.drop_constraint("fk_purchase_returns_refund_entry_id_financial_entries", "purchase_returns", type_="foreignkey")
    op.drop_column("purchase_returns", "refund_entry_id")
    op.drop_column("purchase_returns", "status")
    op.drop_column("purchase_returns", "invoice_number")
