"""add linx open receivables mirror table

Revision ID: 20260407_0021
Revises: 20260407_0020
Create Date: 2026-04-07 15:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0021"
down_revision = "20260407_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linx_open_receivables",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("source_batch_id", sa.String(length=36), nullable=True),
        sa.Column("last_seen_batch_id", sa.String(length=36), nullable=True),
        sa.Column("portal", sa.Integer(), nullable=True),
        sa.Column("company_code", sa.Integer(), nullable=True),
        sa.Column("linx_code", sa.BigInteger(), nullable=False),
        sa.Column("customer_code", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.String(length=200), nullable=False),
        sa.Column("issue_date", sa.DateTime(), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("paid_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("discount_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("interest_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("document_number", sa.String(length=40), nullable=True),
        sa.Column("document_series", sa.String(length=20), nullable=True),
        sa.Column("installment_number", sa.Integer(), nullable=True),
        sa.Column("installment_count", sa.Integer(), nullable=True),
        sa.Column("identifier", sa.String(length=80), nullable=True),
        sa.Column("payment_method_name", sa.String(length=80), nullable=True),
        sa.Column("payment_plan_code", sa.Integer(), nullable=True),
        sa.Column("seller_code", sa.Integer(), nullable=True),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("linx_row_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["last_seen_batch_id"], ["import_batches.id"]),
        sa.ForeignKeyConstraint(["source_batch_id"], ["import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_linx_open_receivables_company_id", "linx_open_receivables", ["company_id"], unique=False)
    op.create_index("ix_linx_open_receivables_portal", "linx_open_receivables", ["portal"], unique=False)
    op.create_index("ix_linx_open_receivables_company_code", "linx_open_receivables", ["company_code"], unique=False)
    op.create_index("ix_linx_open_receivables_linx_code", "linx_open_receivables", ["linx_code"], unique=False)
    op.create_index("ix_linx_open_receivables_customer_code", "linx_open_receivables", ["customer_code"], unique=False)
    op.create_index("ix_linx_open_receivables_issue_date", "linx_open_receivables", ["issue_date"], unique=False)
    op.create_index("ix_linx_open_receivables_due_date", "linx_open_receivables", ["due_date"], unique=False)
    op.create_index(
        "ix_linx_open_receivables_document_number",
        "linx_open_receivables",
        ["document_number"],
        unique=False,
    )
    op.create_index("ix_linx_open_receivables_identifier", "linx_open_receivables", ["identifier"], unique=False)
    op.create_index(
        "ix_linx_open_receivables_linx_row_timestamp",
        "linx_open_receivables",
        ["linx_row_timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_linx_open_receivables_company_code_unique",
        "linx_open_receivables",
        ["company_id", "linx_code"],
        unique=True,
    )
    op.create_index(
        "idx_linx_open_receivables_company_search",
        "linx_open_receivables",
        ["company_id", "customer_name", "document_number"],
        unique=False,
    )
    op.create_index(
        "idx_linx_open_receivables_company_due",
        "linx_open_receivables",
        ["company_id", "due_date", "linx_row_timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_linx_open_receivables_company_due", table_name="linx_open_receivables")
    op.drop_index("idx_linx_open_receivables_company_search", table_name="linx_open_receivables")
    op.drop_index("idx_linx_open_receivables_company_code_unique", table_name="linx_open_receivables")
    op.drop_index("ix_linx_open_receivables_linx_row_timestamp", table_name="linx_open_receivables")
    op.drop_index("ix_linx_open_receivables_identifier", table_name="linx_open_receivables")
    op.drop_index("ix_linx_open_receivables_document_number", table_name="linx_open_receivables")
    op.drop_index("ix_linx_open_receivables_due_date", table_name="linx_open_receivables")
    op.drop_index("ix_linx_open_receivables_issue_date", table_name="linx_open_receivables")
    op.drop_index("ix_linx_open_receivables_customer_code", table_name="linx_open_receivables")
    op.drop_index("ix_linx_open_receivables_linx_code", table_name="linx_open_receivables")
    op.drop_index("ix_linx_open_receivables_company_code", table_name="linx_open_receivables")
    op.drop_index("ix_linx_open_receivables_portal", table_name="linx_open_receivables")
    op.drop_index("ix_linx_open_receivables_company_id", table_name="linx_open_receivables")
    op.drop_table("linx_open_receivables")
