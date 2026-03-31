"""restructure purchase seasons into summer/winter with internal phases

Revision ID: 20260329_0006
Revises: 20260328_0005
Create Date: 2026-03-29 11:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260329_0006"
down_revision = "20260328_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collection_seasons", sa.Column("season_year", sa.Integer(), nullable=True))
    op.add_column("collection_seasons", sa.Column("season_type", sa.String(length=20), nullable=True))
    op.add_column(
        "purchase_plans",
        sa.Column("season_phase", sa.String(length=20), nullable=False, server_default="main"),
    )
    op.add_column(
        "purchase_invoices",
        sa.Column("season_phase", sa.String(length=20), nullable=False, server_default="main"),
    )
    op.add_column(
        "purchase_deliveries",
        sa.Column("season_phase", sa.String(length=20), nullable=False, server_default="main"),
    )
    op.add_column(
        "financial_entries",
        sa.Column("season_phase", sa.String(length=20), nullable=False, server_default="main"),
    )
    op.create_index(
        "idx_collection_seasons_company_year_type",
        "collection_seasons",
        ["company_id", "season_year", "season_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_collection_seasons_company_year_type", table_name="collection_seasons")
    op.drop_column("financial_entries", "season_phase")
    op.drop_column("purchase_deliveries", "season_phase")
    op.drop_column("purchase_invoices", "season_phase")
    op.drop_column("purchase_plans", "season_phase")
    op.drop_column("collection_seasons", "season_type")
    op.drop_column("collection_seasons", "season_year")
