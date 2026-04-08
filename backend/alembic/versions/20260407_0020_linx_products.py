"""add linx products mirror table

Revision ID: 20260407_0020
Revises: 20260407_0019
Create Date: 2026-04-07 14:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0020"
down_revision = "20260407_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linx_products",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("source_batch_id", sa.String(length=36), nullable=True),
        sa.Column("last_seen_batch_id", sa.String(length=36), nullable=True),
        sa.Column("portal", sa.Integer(), nullable=True),
        sa.Column("linx_code", sa.BigInteger(), nullable=False),
        sa.Column("barcode", sa.String(length=30), nullable=True),
        sa.Column("description", sa.String(length=250), nullable=False),
        sa.Column("reference", sa.String(length=40), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("color_name", sa.String(length=50), nullable=True),
        sa.Column("size_name", sa.String(length=50), nullable=True),
        sa.Column("sector_name", sa.String(length=50), nullable=True),
        sa.Column("line_name", sa.String(length=50), nullable=True),
        sa.Column("brand_name", sa.String(length=50), nullable=True),
        sa.Column("supplier_code", sa.Integer(), nullable=True),
        sa.Column("supplier_name", sa.String(length=200), nullable=True),
        sa.Column("collection_id", sa.Integer(), nullable=True),
        sa.Column("collection_name_raw", sa.String(length=80), nullable=True),
        sa.Column("collection_name", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ncm", sa.String(length=20), nullable=True),
        sa.Column("cest", sa.String(length=10), nullable=True),
        sa.Column("auxiliary_code", sa.String(length=40), nullable=True),
        sa.Column("price_cost", sa.Numeric(14, 4), nullable=True),
        sa.Column("price_sale", sa.Numeric(14, 4), nullable=True),
        sa.Column("stock_quantity", sa.Numeric(14, 4), nullable=True),
        sa.Column("average_cost", sa.Numeric(14, 4), nullable=True),
        sa.Column("detail_company_code", sa.Integer(), nullable=True),
        sa.Column("detail_location", sa.String(length=50), nullable=True),
        sa.Column("linx_created_at", sa.DateTime(), nullable=True),
        sa.Column("linx_updated_at", sa.DateTime(), nullable=True),
        sa.Column("linx_row_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("linx_detail_row_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["last_seen_batch_id"], ["import_batches.id"]),
        sa.ForeignKeyConstraint(["source_batch_id"], ["import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_linx_products_company_id", "linx_products", ["company_id"], unique=False)
    op.create_index("ix_linx_products_portal", "linx_products", ["portal"], unique=False)
    op.create_index("ix_linx_products_linx_code", "linx_products", ["linx_code"], unique=False)
    op.create_index("ix_linx_products_barcode", "linx_products", ["barcode"], unique=False)
    op.create_index("ix_linx_products_reference", "linx_products", ["reference"], unique=False)
    op.create_index("ix_linx_products_supplier_code", "linx_products", ["supplier_code"], unique=False)
    op.create_index("ix_linx_products_collection_id", "linx_products", ["collection_id"], unique=False)
    op.create_index("ix_linx_products_linx_created_at", "linx_products", ["linx_created_at"], unique=False)
    op.create_index("ix_linx_products_linx_updated_at", "linx_products", ["linx_updated_at"], unique=False)
    op.create_index("ix_linx_products_linx_row_timestamp", "linx_products", ["linx_row_timestamp"], unique=False)
    op.create_index(
        "ix_linx_products_linx_detail_row_timestamp",
        "linx_products",
        ["linx_detail_row_timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_linx_products_company_code",
        "linx_products",
        ["company_id", "linx_code"],
        unique=True,
    )
    op.create_index(
        "idx_linx_products_company_search",
        "linx_products",
        ["company_id", "description", "reference"],
        unique=False,
    )
    op.create_index(
        "idx_linx_products_company_supplier",
        "linx_products",
        ["company_id", "supplier_code", "collection_id"],
        unique=False,
    )
    op.create_index(
        "idx_linx_products_company_sync",
        "linx_products",
        ["company_id", "linx_row_timestamp", "linx_detail_row_timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_linx_products_company_sync", table_name="linx_products")
    op.drop_index("idx_linx_products_company_supplier", table_name="linx_products")
    op.drop_index("idx_linx_products_company_search", table_name="linx_products")
    op.drop_index("idx_linx_products_company_code", table_name="linx_products")
    op.drop_index("ix_linx_products_linx_detail_row_timestamp", table_name="linx_products")
    op.drop_index("ix_linx_products_linx_row_timestamp", table_name="linx_products")
    op.drop_index("ix_linx_products_linx_updated_at", table_name="linx_products")
    op.drop_index("ix_linx_products_linx_created_at", table_name="linx_products")
    op.drop_index("ix_linx_products_collection_id", table_name="linx_products")
    op.drop_index("ix_linx_products_supplier_code", table_name="linx_products")
    op.drop_index("ix_linx_products_reference", table_name="linx_products")
    op.drop_index("ix_linx_products_barcode", table_name="linx_products")
    op.drop_index("ix_linx_products_linx_code", table_name="linx_products")
    op.drop_index("ix_linx_products_portal", table_name="linx_products")
    op.drop_index("ix_linx_products_company_id", table_name="linx_products")
    op.drop_table("linx_products")
