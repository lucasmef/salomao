"""add linx customers mirror table

Revision ID: 20260407_0018
Revises: 20260404_0017
Create Date: 2026-04-07 10:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0018"
down_revision = "20260404_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linx_customers",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("source_batch_id", sa.String(length=36), nullable=True),
        sa.Column("last_seen_batch_id", sa.String(length=36), nullable=True),
        sa.Column("portal", sa.Integer(), nullable=True),
        sa.Column("linx_code", sa.Integer(), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("document_number", sa.String(length=20), nullable=True),
        sa.Column("person_type", sa.String(length=1), nullable=True),
        sa.Column("registration_type", sa.String(length=1), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("address_street", sa.String(length=250), nullable=True),
        sa.Column("address_number", sa.String(length=40), nullable=True),
        sa.Column("address_complement", sa.String(length=160), nullable=True),
        sa.Column("neighborhood", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=True),
        sa.Column("zip_code", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=80), nullable=True),
        sa.Column("phone_primary", sa.String(length=40), nullable=True),
        sa.Column("mobile", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("state_registration", sa.String(length=40), nullable=True),
        sa.Column("municipal_registration", sa.String(length=40), nullable=True),
        sa.Column("loyalty_card_number", sa.String(length=40), nullable=True),
        sa.Column("convenio_registration", sa.String(length=40), nullable=True),
        sa.Column("anonymous_customer", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("credit_limit_inhouse", sa.Numeric(14, 2), nullable=True),
        sa.Column("credit_limit_cash_card", sa.Numeric(14, 2), nullable=True),
        sa.Column("class_name", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_code_ws", sa.String(length=100), nullable=True),
        sa.Column("linx_created_at", sa.DateTime(), nullable=True),
        sa.Column("linx_updated_at", sa.DateTime(), nullable=True),
        sa.Column("linx_row_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["last_seen_batch_id"], ["import_batches.id"]),
        sa.ForeignKeyConstraint(["source_batch_id"], ["import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_linx_customers_company_id", "linx_customers", ["company_id"], unique=False)
    op.create_index("ix_linx_customers_document_number", "linx_customers", ["document_number"], unique=False)
    op.create_index("ix_linx_customers_linx_code", "linx_customers", ["linx_code"], unique=False)
    op.create_index("ix_linx_customers_linx_created_at", "linx_customers", ["linx_created_at"], unique=False)
    op.create_index("ix_linx_customers_linx_row_timestamp", "linx_customers", ["linx_row_timestamp"], unique=False)
    op.create_index("ix_linx_customers_linx_updated_at", "linx_customers", ["linx_updated_at"], unique=False)
    op.create_index("ix_linx_customers_portal", "linx_customers", ["portal"], unique=False)
    op.create_index(
        "ix_linx_customers_registration_type",
        "linx_customers",
        ["registration_type"],
        unique=False,
    )
    op.create_index(
        "idx_linx_customers_company_code",
        "linx_customers",
        ["company_id", "linx_code"],
        unique=True,
    )
    op.create_index(
        "idx_linx_customers_company_document",
        "linx_customers",
        ["company_id", "document_number"],
        unique=False,
    )
    op.create_index(
        "idx_linx_customers_company_registration_type",
        "linx_customers",
        ["company_id", "registration_type", "is_active"],
        unique=False,
    )
    op.create_index(
        "idx_linx_customers_company_sync",
        "linx_customers",
        ["company_id", "linx_updated_at", "linx_row_timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_linx_customers_company_sync", table_name="linx_customers")
    op.drop_index("idx_linx_customers_company_registration_type", table_name="linx_customers")
    op.drop_index("idx_linx_customers_company_document", table_name="linx_customers")
    op.drop_index("idx_linx_customers_company_code", table_name="linx_customers")
    op.drop_index("ix_linx_customers_registration_type", table_name="linx_customers")
    op.drop_index("ix_linx_customers_portal", table_name="linx_customers")
    op.drop_index("ix_linx_customers_linx_updated_at", table_name="linx_customers")
    op.drop_index("ix_linx_customers_linx_row_timestamp", table_name="linx_customers")
    op.drop_index("ix_linx_customers_linx_created_at", table_name="linx_customers")
    op.drop_index("ix_linx_customers_linx_code", table_name="linx_customers")
    op.drop_index("ix_linx_customers_document_number", table_name="linx_customers")
    op.drop_index("ix_linx_customers_company_id", table_name="linx_customers")
    op.drop_table("linx_customers")
