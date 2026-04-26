"""purchase brand planning basis

Revision ID: 20260426_0034
Revises: 20260425_0033
Create Date: 2026-04-26 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_0034"
down_revision = "20260425_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchase_brands",
        sa.Column("planning_basis", sa.String(length=20), nullable=False, server_default="supplier"),
    )
    op.create_table(
        "purchase_brand_linx_aliases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("brand_id", sa.String(length=36), nullable=False),
        sa.Column("linx_brand_name", sa.String(length=140), nullable=False),
        sa.Column("normalized_name", sa.String(length=180), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["purchase_brands.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_purchase_brand_linx_aliases_brand_id"), "purchase_brand_linx_aliases", ["brand_id"], unique=False)
    op.create_index(op.f("ix_purchase_brand_linx_aliases_company_id"), "purchase_brand_linx_aliases", ["company_id"], unique=False)
    op.create_index(op.f("ix_purchase_brand_linx_aliases_linx_brand_name"), "purchase_brand_linx_aliases", ["linx_brand_name"], unique=False)
    op.create_index(op.f("ix_purchase_brand_linx_aliases_normalized_name"), "purchase_brand_linx_aliases", ["normalized_name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_purchase_brand_linx_aliases_normalized_name"), table_name="purchase_brand_linx_aliases")
    op.drop_index(op.f("ix_purchase_brand_linx_aliases_linx_brand_name"), table_name="purchase_brand_linx_aliases")
    op.drop_index(op.f("ix_purchase_brand_linx_aliases_company_id"), table_name="purchase_brand_linx_aliases")
    op.drop_index(op.f("ix_purchase_brand_linx_aliases_brand_id"), table_name="purchase_brand_linx_aliases")
    op.drop_table("purchase_brand_linx_aliases")
    op.drop_column("purchase_brands", "planning_basis")
