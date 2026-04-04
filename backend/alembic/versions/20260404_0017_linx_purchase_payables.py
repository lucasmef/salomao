"""add linx purchase payables support

Revision ID: 20260404_0017
Revises: 20260404_0016
Create Date: 2026-04-04 20:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260404_0017"
down_revision = "20260404_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("linx_payables_view_name", sa.String(length=160), nullable=True))

    op.create_table(
        "purchase_payable_titles",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("source_batch_id", sa.String(length=36), nullable=True),
        sa.Column("last_seen_batch_id", sa.String(length=36), nullable=True),
        sa.Column("source_reference", sa.String(length=120), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("payable_code", sa.String(length=40), nullable=True),
        sa.Column("company_code", sa.String(length=20), nullable=True),
        sa.Column("installment_label", sa.String(length=20), nullable=True),
        sa.Column("installment_number", sa.Integer(), nullable=True),
        sa.Column("installments_total", sa.Integer(), nullable=True),
        sa.Column("original_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("amount_with_charges", sa.Numeric(14, 2), nullable=True),
        sa.Column("supplier_name", sa.String(length=200), nullable=False),
        sa.Column("supplier_code", sa.String(length=20), nullable=True),
        sa.Column("document_number", sa.String(length=80), nullable=True),
        sa.Column("document_series", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("purchase_invoice_id", sa.String(length=36), nullable=True),
        sa.Column("purchase_installment_id", sa.String(length=36), nullable=True),
        sa.Column("financial_entry_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["financial_entry_id"], ["financial_entries.id"]),
        sa.ForeignKeyConstraint(["last_seen_batch_id"], ["import_batches.id"]),
        sa.ForeignKeyConstraint(["purchase_installment_id"], ["purchase_installments.id"]),
        sa.ForeignKeyConstraint(["purchase_invoice_id"], ["purchase_invoices.id"]),
        sa.ForeignKeyConstraint(["source_batch_id"], ["import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_purchase_payable_titles_company_id",
        "purchase_payable_titles",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_payable_titles_due_date",
        "purchase_payable_titles",
        ["due_date"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_payable_titles_document_number",
        "purchase_payable_titles",
        ["document_number"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_payable_titles_financial_entry_id",
        "purchase_payable_titles",
        ["financial_entry_id"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_payable_titles_issue_date",
        "purchase_payable_titles",
        ["issue_date"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_payable_titles_payable_code",
        "purchase_payable_titles",
        ["payable_code"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_payable_titles_purchase_installment_id",
        "purchase_payable_titles",
        ["purchase_installment_id"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_payable_titles_purchase_invoice_id",
        "purchase_payable_titles",
        ["purchase_invoice_id"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_payable_titles_source_reference",
        "purchase_payable_titles",
        ["source_reference"],
        unique=False,
    )
    op.create_index(
        "idx_purchase_payable_titles_company_source_ref",
        "purchase_payable_titles",
        ["company_id", "source_reference"],
        unique=False,
    )
    op.create_index(
        "idx_purchase_payable_titles_company_due",
        "purchase_payable_titles",
        ["company_id", "due_date", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_purchase_payable_titles_company_due", table_name="purchase_payable_titles")
    op.drop_index("idx_purchase_payable_titles_company_source_ref", table_name="purchase_payable_titles")
    op.drop_index("ix_purchase_payable_titles_source_reference", table_name="purchase_payable_titles")
    op.drop_index("ix_purchase_payable_titles_purchase_invoice_id", table_name="purchase_payable_titles")
    op.drop_index("ix_purchase_payable_titles_purchase_installment_id", table_name="purchase_payable_titles")
    op.drop_index("ix_purchase_payable_titles_payable_code", table_name="purchase_payable_titles")
    op.drop_index("ix_purchase_payable_titles_issue_date", table_name="purchase_payable_titles")
    op.drop_index("ix_purchase_payable_titles_financial_entry_id", table_name="purchase_payable_titles")
    op.drop_index("ix_purchase_payable_titles_document_number", table_name="purchase_payable_titles")
    op.drop_index("ix_purchase_payable_titles_due_date", table_name="purchase_payable_titles")
    op.drop_index("ix_purchase_payable_titles_company_id", table_name="purchase_payable_titles")
    op.drop_table("purchase_payable_titles")
    op.drop_column("companies", "linx_payables_view_name")
