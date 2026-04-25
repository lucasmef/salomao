"""fix purchase return refund entries

Revision ID: 20260425_0033
Revises: 20260421_0032
Create Date: 2026-04-25 10:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "20260425_0033"
down_revision = "20260421_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE financial_entries
        SET entry_type = 'income'
        WHERE is_deleted = false
          AND (
            source_system = 'purchase_return_workflow'
            OR description LIKE 'Recebivel gerado automaticamente%'
          )
          AND entry_type <> 'income'
        """
    )
    op.execute(
        """
        UPDATE financial_entries
        SET category_id = (
            SELECT categories.id
            FROM categories
            WHERE categories.company_id = financial_entries.company_id
              AND categories.name = 'Devolucoes de Compra'
              AND categories.entry_kind = 'income'
            LIMIT 1
        )
        WHERE financial_entries.is_deleted = false
          AND (
            financial_entries.source_system = 'purchase_return_workflow'
            OR financial_entries.description LIKE 'Recebivel gerado automaticamente%'
          )
          AND EXISTS (
            SELECT 1
            FROM categories
            WHERE categories.company_id = financial_entries.company_id
              AND categories.name = 'Devolucoes de Compra'
              AND categories.entry_kind = 'income'
          )
          AND (
            financial_entries.category_id IS NULL
            OR financial_entries.category_id <> (
                SELECT categories.id
                FROM categories
                WHERE categories.company_id = financial_entries.company_id
                  AND categories.name = 'Devolucoes de Compra'
                  AND categories.entry_kind = 'income'
                LIMIT 1
            )
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE financial_entries
        SET entry_type = 'historical_purchase_return'
        WHERE is_deleted = false
          AND (
            source_system = 'purchase_return_workflow'
            OR description LIKE 'Recebivel gerado automaticamente%'
          )
          AND entry_type = 'income'
        """
    )
