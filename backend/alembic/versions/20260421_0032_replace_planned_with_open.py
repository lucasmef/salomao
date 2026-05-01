"""replace planned statuses with open

Revision ID: 20260421_0032
Revises: 20260420_0031
Create Date: 2026-04-21 11:50:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "20260421_0032"
down_revision = "20260420_0031"
branch_labels = None
depends_on = None


STATUS_TABLES = (
    "financial_entries",
    "transfers",
    "loan_installments",
    "purchase_plans",
    "purchase_installments",
)


def upgrade() -> None:
    for table_name in STATUS_TABLES:
        op.execute(f"UPDATE {table_name} SET status = 'open' WHERE status = 'planned'")


def downgrade() -> None:
    for table_name in STATUS_TABLES:
        op.execute(f"UPDATE {table_name} SET status = 'planned' WHERE status = 'open'")
