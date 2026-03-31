"""add default payment term to purchase brands

Revision ID: 20260330_0007
Revises: 20260329_0006
Create Date: 2026-03-30 09:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260330_0007"
down_revision = "20260329_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchase_brands", sa.Column("default_payment_term", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("purchase_brands", "default_payment_term")
