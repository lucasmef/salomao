"""add C6 bankslip consultation integration fields

Revision ID: 20260409_0026
Revises: 20260408_0025
Create Date: 2026-04-09 18:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260409_0026"
down_revision = "20260408_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("c6_api_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "accounts",
        sa.Column("c6_environment", sa.String(length=20), nullable=False, server_default="production"),
    )
    op.add_column("accounts", sa.Column("c6_api_base_url", sa.String(length=255), nullable=True))
    op.add_column("accounts", sa.Column("c6_client_id", sa.String(length=160), nullable=True))
    op.add_column("accounts", sa.Column("c6_partner_software_name", sa.String(length=160), nullable=True))
    op.add_column("accounts", sa.Column("c6_partner_software_version", sa.String(length=40), nullable=True))
    op.add_column("accounts", sa.Column("c6_client_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("c6_certificate_pem_encrypted", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("c6_private_key_pem_encrypted", sa.Text(), nullable=True))
    op.alter_column("accounts", "c6_api_enabled", server_default=None)
    op.alter_column("accounts", "c6_environment", server_default=None)


def downgrade() -> None:
    op.drop_column("accounts", "c6_private_key_pem_encrypted")
    op.drop_column("accounts", "c6_certificate_pem_encrypted")
    op.drop_column("accounts", "c6_client_secret_encrypted")
    op.drop_column("accounts", "c6_partner_software_version")
    op.drop_column("accounts", "c6_partner_software_name")
    op.drop_column("accounts", "c6_client_id")
    op.drop_column("accounts", "c6_api_base_url")
    op.drop_column("accounts", "c6_environment")
    op.drop_column("accounts", "c6_api_enabled")
