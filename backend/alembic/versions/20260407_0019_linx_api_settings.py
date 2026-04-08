"""add linx api settings on company

Revision ID: 20260407_0019
Revises: 20260407_0018
Create Date: 2026-04-07 11:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0019"
down_revision = "20260407_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("linx_api_base_url", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("linx_api_cnpj", sa.String(length=20), nullable=True))
    op.add_column("companies", sa.Column("linx_api_key_encrypted", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "linx_api_key_encrypted")
    op.drop_column("companies", "linx_api_cnpj")
    op.drop_column("companies", "linx_api_base_url")
