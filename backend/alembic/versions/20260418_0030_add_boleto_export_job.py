"""add boleto export jobs table

Revision ID: 20260418_0030
Revises: 20260415_0029
Create Date: 2026-04-18 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260418_0030"
down_revision = "20260415_0029"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "boleto_export_jobs",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(length=255), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_boleto_export_jobs_company_id", "boleto_export_jobs", ["company_id"], unique=False)
    op.create_index("ix_boleto_export_jobs_status", "boleto_export_jobs", ["status"], unique=False)

def downgrade() -> None:
    op.drop_index("ix_boleto_export_jobs_status", table_name="boleto_export_jobs")
    op.drop_index("ix_boleto_export_jobs_company_id", table_name="boleto_export_jobs")
    op.drop_table("boleto_export_jobs")
