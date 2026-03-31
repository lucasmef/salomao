"""backfill supplier purchase history flag from financial entries

Revision ID: 20260330_0009
Revises: 20260330_0008
Create Date: 2026-03-30 13:05:00
"""

from alembic import op


revision = "20260330_0009"
down_revision = "20260330_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE suppliers SET has_purchase_invoices = FALSE")
    op.execute(
        """
        UPDATE suppliers
        SET has_purchase_invoices = TRUE
        WHERE id IN (
            SELECT DISTINCT supplier_id
            FROM purchase_invoices
            WHERE supplier_id IS NOT NULL
            UNION
            SELECT DISTINCT fe.supplier_id
            FROM financial_entries fe
            JOIN categories c ON c.id = fe.category_id
            WHERE fe.supplier_id IS NOT NULL
              AND fe.is_deleted = FALSE
              AND fe.entry_type = 'expense'
              AND (
                c.name = 'Compras'
                OR c.report_group = 'Compras'
                OR c.report_subgroup = 'Compras'
              )
        )
        """
    )


def downgrade() -> None:
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
