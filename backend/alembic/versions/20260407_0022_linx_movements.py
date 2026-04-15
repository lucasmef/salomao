"""add linx movements mirror table

Revision ID: 20260407_0022
Revises: 20260407_0021
Create Date: 2026-04-07 14:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0022"
down_revision = "20260407_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linx_movements",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("source_batch_id", sa.String(length=36), nullable=True),
        sa.Column("last_seen_batch_id", sa.String(length=36), nullable=True),
        sa.Column("portal", sa.Integer(), nullable=True),
        sa.Column("company_code", sa.Integer(), nullable=True),
        sa.Column("linx_transaction", sa.BigInteger(), nullable=False),
        sa.Column("document_number", sa.String(length=40), nullable=True),
        sa.Column("document_series", sa.String(length=20), nullable=True),
        sa.Column("identifier", sa.String(length=80), nullable=True),
        sa.Column("movement_group", sa.String(length=20), nullable=False),
        sa.Column("movement_type", sa.String(length=30), nullable=False),
        sa.Column("operation_code", sa.String(length=2), nullable=True),
        sa.Column("transaction_type_code", sa.String(length=1), nullable=True),
        sa.Column("nature_code", sa.String(length=10), nullable=True),
        sa.Column("nature_description", sa.String(length=120), nullable=True),
        sa.Column("cfop_code", sa.Integer(), nullable=True),
        sa.Column("cfop_description", sa.String(length=160), nullable=True),
        sa.Column("issue_date", sa.DateTime(), nullable=True),
        sa.Column("launch_date", sa.DateTime(), nullable=True),
        sa.Column("linx_updated_at", sa.DateTime(), nullable=True),
        sa.Column("customer_code", sa.Integer(), nullable=True),
        sa.Column("seller_code", sa.Integer(), nullable=True),
        sa.Column("product_code", sa.BigInteger(), nullable=True),
        sa.Column("product_barcode", sa.String(length=30), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 4), nullable=True),
        sa.Column("cost_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("unit_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("net_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("total_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("discount_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("item_discount_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("canceled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("line_order", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("linx_row_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["last_seen_batch_id"], ["import_batches.id"]),
        sa.ForeignKeyConstraint(["source_batch_id"], ["import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_linx_movements_company_id", "linx_movements", ["company_id"], unique=False)
    op.create_index("ix_linx_movements_portal", "linx_movements", ["portal"], unique=False)
    op.create_index("ix_linx_movements_company_code", "linx_movements", ["company_code"], unique=False)
    op.create_index("ix_linx_movements_linx_transaction", "linx_movements", ["linx_transaction"], unique=False)
    op.create_index("ix_linx_movements_document_number", "linx_movements", ["document_number"], unique=False)
    op.create_index("ix_linx_movements_identifier", "linx_movements", ["identifier"], unique=False)
    op.create_index("ix_linx_movements_movement_group", "linx_movements", ["movement_group"], unique=False)
    op.create_index("ix_linx_movements_movement_type", "linx_movements", ["movement_type"], unique=False)
    op.create_index("ix_linx_movements_operation_code", "linx_movements", ["operation_code"], unique=False)
    op.create_index(
        "ix_linx_movements_transaction_type_code",
        "linx_movements",
        ["transaction_type_code"],
        unique=False,
    )
    op.create_index("ix_linx_movements_nature_code", "linx_movements", ["nature_code"], unique=False)
    op.create_index("ix_linx_movements_issue_date", "linx_movements", ["issue_date"], unique=False)
    op.create_index("ix_linx_movements_launch_date", "linx_movements", ["launch_date"], unique=False)
    op.create_index("ix_linx_movements_linx_updated_at", "linx_movements", ["linx_updated_at"], unique=False)
    op.create_index("ix_linx_movements_customer_code", "linx_movements", ["customer_code"], unique=False)
    op.create_index("ix_linx_movements_product_code", "linx_movements", ["product_code"], unique=False)
    op.create_index("ix_linx_movements_linx_row_timestamp", "linx_movements", ["linx_row_timestamp"], unique=False)
    op.create_index(
        "idx_linx_movements_company_transaction",
        "linx_movements",
        ["company_id", "linx_transaction"],
        unique=True,
    )
    op.create_index(
        "idx_linx_movements_company_group_date",
        "linx_movements",
        ["company_id", "movement_group", "launch_date"],
        unique=False,
    )
    op.create_index(
        "idx_linx_movements_company_product",
        "linx_movements",
        ["company_id", "product_code", "nature_code"],
        unique=False,
    )
    op.create_index(
        "idx_linx_movements_company_sync",
        "linx_movements",
        ["company_id", "linx_row_timestamp", "movement_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_linx_movements_company_sync", table_name="linx_movements")
    op.drop_index("idx_linx_movements_company_product", table_name="linx_movements")
    op.drop_index("idx_linx_movements_company_group_date", table_name="linx_movements")
    op.drop_index("idx_linx_movements_company_transaction", table_name="linx_movements")
    op.drop_index("ix_linx_movements_linx_row_timestamp", table_name="linx_movements")
    op.drop_index("ix_linx_movements_product_code", table_name="linx_movements")
    op.drop_index("ix_linx_movements_customer_code", table_name="linx_movements")
    op.drop_index("ix_linx_movements_linx_updated_at", table_name="linx_movements")
    op.drop_index("ix_linx_movements_launch_date", table_name="linx_movements")
    op.drop_index("ix_linx_movements_issue_date", table_name="linx_movements")
    op.drop_index("ix_linx_movements_nature_code", table_name="linx_movements")
    op.drop_index("ix_linx_movements_transaction_type_code", table_name="linx_movements")
    op.drop_index("ix_linx_movements_operation_code", table_name="linx_movements")
    op.drop_index("ix_linx_movements_movement_type", table_name="linx_movements")
    op.drop_index("ix_linx_movements_movement_group", table_name="linx_movements")
    op.drop_index("ix_linx_movements_identifier", table_name="linx_movements")
    op.drop_index("ix_linx_movements_document_number", table_name="linx_movements")
    op.drop_index("ix_linx_movements_linx_transaction", table_name="linx_movements")
    op.drop_index("ix_linx_movements_company_code", table_name="linx_movements")
    op.drop_index("ix_linx_movements_portal", table_name="linx_movements")
    op.drop_index("ix_linx_movements_company_id", table_name="linx_movements")
    op.drop_table("linx_movements")
