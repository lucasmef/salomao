"""add purchase returns table

Revision ID: 20260331_0011
Revises: 20260331_0010
Create Date: 2026-03-31 12:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0011"
down_revision = "20260331_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_returns",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("supplier_id", sa.String(length=36), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_purchase_returns_company_id"), "purchase_returns", ["company_id"], unique=False)
    op.create_index(op.f("ix_purchase_returns_supplier_id"), "purchase_returns", ["supplier_id"], unique=False)
    op.create_index(op.f("ix_purchase_returns_return_date"), "purchase_returns", ["return_date"], unique=False)
    op.alter_column("purchase_returns", "amount", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_purchase_returns_return_date"), table_name="purchase_returns")
    op.drop_index(op.f("ix_purchase_returns_supplier_id"), table_name="purchase_returns")
    op.drop_index(op.f("ix_purchase_returns_company_id"), table_name="purchase_returns")
    op.drop_table("purchase_returns")
