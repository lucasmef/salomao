"""add standalone boletos table

Revision ID: 20260407_0024
Revises: 20260407_0023
Create Date: 2026-04-07 23:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0024"
down_revision = "20260407_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standalone_boleto_records",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("source_batch_id", sa.String(length=36), nullable=True),
        sa.Column("bank", sa.String(length=20), nullable=False),
        sa.Column("client_key", sa.String(length=200), nullable=False),
        sa.Column("client_name", sa.String(length=200), nullable=False),
        sa.Column("tax_id", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("document_id", sa.String(length=80), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("local_status", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("barcode", sa.String(length=160), nullable=True),
        sa.Column("inter_account_id", sa.String(length=36), nullable=True),
        sa.Column("inter_codigo_solicitacao", sa.String(length=80), nullable=True),
        sa.Column("inter_seu_numero", sa.String(length=80), nullable=True),
        sa.Column("inter_nosso_numero", sa.String(length=80), nullable=True),
        sa.Column("linha_digitavel", sa.String(length=255), nullable=True),
        sa.Column("pix_copia_e_cola", sa.Text(), nullable=True),
        sa.Column("inter_txid", sa.String(length=120), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["source_batch_id"], ["import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_standalone_boleto_records_company_id", "standalone_boleto_records", ["company_id"], unique=False)
    op.create_index("ix_standalone_boleto_records_bank", "standalone_boleto_records", ["bank"], unique=False)
    op.create_index("ix_standalone_boleto_records_client_key", "standalone_boleto_records", ["client_key"], unique=False)
    op.create_index("ix_standalone_boleto_records_document_id", "standalone_boleto_records", ["document_id"], unique=False)
    op.create_index("ix_standalone_boleto_records_issue_date", "standalone_boleto_records", ["issue_date"], unique=False)
    op.create_index("ix_standalone_boleto_records_due_date", "standalone_boleto_records", ["due_date"], unique=False)
    op.create_index("ix_standalone_boleto_records_local_status", "standalone_boleto_records", ["local_status"], unique=False)
    op.create_index("ix_standalone_boleto_records_inter_account_id", "standalone_boleto_records", ["inter_account_id"], unique=False)
    op.create_index("ix_standalone_boleto_records_inter_codigo_solicitacao", "standalone_boleto_records", ["inter_codigo_solicitacao"], unique=False)
    op.create_index("ix_standalone_boleto_records_inter_seu_numero", "standalone_boleto_records", ["inter_seu_numero"], unique=False)
    op.create_index(
        "idx_standalone_boleto_records_company_status_due",
        "standalone_boleto_records",
        ["company_id", "local_status", "due_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_standalone_boleto_records_company_status_due", table_name="standalone_boleto_records")
    op.drop_index("ix_standalone_boleto_records_inter_seu_numero", table_name="standalone_boleto_records")
    op.drop_index("ix_standalone_boleto_records_inter_codigo_solicitacao", table_name="standalone_boleto_records")
    op.drop_index("ix_standalone_boleto_records_inter_account_id", table_name="standalone_boleto_records")
    op.drop_index("ix_standalone_boleto_records_local_status", table_name="standalone_boleto_records")
    op.drop_index("ix_standalone_boleto_records_due_date", table_name="standalone_boleto_records")
    op.drop_index("ix_standalone_boleto_records_issue_date", table_name="standalone_boleto_records")
    op.drop_index("ix_standalone_boleto_records_document_id", table_name="standalone_boleto_records")
    op.drop_index("ix_standalone_boleto_records_client_key", table_name="standalone_boleto_records")
    op.drop_index("ix_standalone_boleto_records_bank", table_name="standalone_boleto_records")
    op.drop_index("ix_standalone_boleto_records_company_id", table_name="standalone_boleto_records")
    op.drop_table("standalone_boleto_records")
