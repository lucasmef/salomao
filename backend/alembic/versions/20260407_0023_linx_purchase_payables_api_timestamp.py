"""add linx row timestamp to purchase payable titles

Revision ID: 20260407_0023
Revises: 20260407_0022
Create Date: 2026-04-07 21:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0023"
down_revision = "20260407_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchase_payable_titles", sa.Column("linx_row_timestamp", sa.BigInteger(), nullable=True))
    op.create_index(
        "ix_purchase_payable_titles_linx_row_timestamp",
        "purchase_payable_titles",
        ["linx_row_timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_payable_titles_linx_row_timestamp", table_name="purchase_payable_titles")
    op.drop_column("purchase_payable_titles", "linx_row_timestamp")
