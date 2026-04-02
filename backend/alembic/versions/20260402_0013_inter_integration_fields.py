"""add Banco Inter integration fields

Revision ID: 20260402_0013
Revises: 20260331_0012
Create Date: 2026-04-02 11:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260402_0013"
down_revision = "20260331_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("inter_api_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "accounts",
        sa.Column("inter_environment", sa.String(length=20), nullable=False, server_default="production"),
    )
    op.add_column("accounts", sa.Column("inter_api_base_url", sa.String(length=255), nullable=True))
    op.add_column("accounts", sa.Column("inter_api_key", sa.String(length=160), nullable=True))
    op.add_column("accounts", sa.Column("inter_account_number", sa.String(length=30), nullable=True))
    op.add_column("accounts", sa.Column("inter_client_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("inter_certificate_pem_encrypted", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("inter_private_key_pem_encrypted", sa.Text(), nullable=True))
    op.alter_column("accounts", "inter_api_enabled", server_default=None)
    op.alter_column("accounts", "inter_environment", server_default=None)

    op.add_column("boleto_records", sa.Column("inter_codigo_solicitacao", sa.String(length=80), nullable=True))
    op.add_column("boleto_records", sa.Column("inter_seu_numero", sa.String(length=80), nullable=True))
    op.add_column("boleto_records", sa.Column("inter_nosso_numero", sa.String(length=80), nullable=True))
    op.add_column("boleto_records", sa.Column("linha_digitavel", sa.String(length=255), nullable=True))
    op.add_column("boleto_records", sa.Column("pix_copia_e_cola", sa.Text(), nullable=True))
    op.add_column("boleto_records", sa.Column("inter_txid", sa.String(length=120), nullable=True))
    op.create_index(
        op.f("ix_boleto_records_inter_codigo_solicitacao"),
        "boleto_records",
        ["inter_codigo_solicitacao"],
        unique=False,
    )
    op.create_index(
        op.f("ix_boleto_records_inter_seu_numero"),
        "boleto_records",
        ["inter_seu_numero"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_boleto_records_inter_seu_numero"), table_name="boleto_records")
    op.drop_index(op.f("ix_boleto_records_inter_codigo_solicitacao"), table_name="boleto_records")
    op.drop_column("boleto_records", "inter_txid")
    op.drop_column("boleto_records", "pix_copia_e_cola")
    op.drop_column("boleto_records", "linha_digitavel")
    op.drop_column("boleto_records", "inter_nosso_numero")
    op.drop_column("boleto_records", "inter_seu_numero")
    op.drop_column("boleto_records", "inter_codigo_solicitacao")

    op.drop_column("accounts", "inter_private_key_pem_encrypted")
    op.drop_column("accounts", "inter_certificate_pem_encrypted")
    op.drop_column("accounts", "inter_client_secret_encrypted")
    op.drop_column("accounts", "inter_account_number")
    op.drop_column("accounts", "inter_api_key")
    op.drop_column("accounts", "inter_api_base_url")
    op.drop_column("accounts", "inter_environment")
    op.drop_column("accounts", "inter_api_enabled")
