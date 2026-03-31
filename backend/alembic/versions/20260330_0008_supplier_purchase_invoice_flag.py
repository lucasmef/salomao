"""add supplier purchase invoice flag

Revision ID: 20260330_0008
Revises: 20260330_0007
Create Date: 2026-03-30 12:35:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260330_0008"
down_revision = "20260330_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "suppliers",
        sa.Column("has_purchase_invoices", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE suppliers
        SET has_purchase_invoices = TRUE
        WHERE id IN (
            SELECT DISTINCT supplier_id
            FROM purchase_invoices
            WHERE supplier_id IS NOT NULL
        )
        """
    )
    op.alter_column("suppliers", "has_purchase_invoices", server_default=None)


def downgrade() -> None:
    op.drop_column("suppliers", "has_purchase_invoices")
