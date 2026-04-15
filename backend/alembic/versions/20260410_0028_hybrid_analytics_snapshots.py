"""add hybrid analytics snapshots and rebuild queue

Revision ID: 20260410_0028
Revises: 20260409_0027
Create Date: 2026-04-10 20:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0028"
down_revision = "20260409_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_monthly_snapshots",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("analytics_kind", sa.String(length=40), nullable=False),
        sa.Column("snapshot_month", sa.Date(), nullable=False),
        sa.Column("params_key", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("params_json", sa.JSON(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "analytics_kind",
            "snapshot_month",
            "params_key",
            name="uq_analytics_month_snapshot_scope",
        ),
    )
    op.create_index(
        "ix_analytics_monthly_snapshots_company_id",
        "analytics_monthly_snapshots",
        ["company_id"],
    )
    op.create_index(
        "ix_analytics_monthly_snapshots_analytics_kind",
        "analytics_monthly_snapshots",
        ["analytics_kind"],
    )
    op.create_index(
        "ix_analytics_monthly_snapshots_snapshot_month",
        "analytics_monthly_snapshots",
        ["snapshot_month"],
    )
    op.create_index(
        "ix_analytics_monthly_snapshots_params_key",
        "analytics_monthly_snapshots",
        ["params_key"],
    )

    op.create_table(
        "analytics_snapshot_rebuild_tasks",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("analytics_kind", sa.String(length=40), nullable=False),
        sa.Column("snapshot_month", sa.Date(), nullable=False),
        sa.Column("params_key", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("params_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "analytics_kind",
            "snapshot_month",
            "params_key",
            name="uq_analytics_snapshot_rebuild_scope",
        ),
    )
    op.create_index(
        "ix_analytics_snapshot_rebuild_tasks_company_id",
        "analytics_snapshot_rebuild_tasks",
        ["company_id"],
    )
    op.create_index(
        "ix_analytics_snapshot_rebuild_tasks_analytics_kind",
        "analytics_snapshot_rebuild_tasks",
        ["analytics_kind"],
    )
    op.create_index(
        "ix_analytics_snapshot_rebuild_tasks_snapshot_month",
        "analytics_snapshot_rebuild_tasks",
        ["snapshot_month"],
    )
    op.create_index(
        "ix_analytics_snapshot_rebuild_tasks_params_key",
        "analytics_snapshot_rebuild_tasks",
        ["params_key"],
    )
    op.create_index(
        "ix_analytics_snapshot_rebuild_tasks_status",
        "analytics_snapshot_rebuild_tasks",
        ["status"],
    )

    op.alter_column("analytics_monthly_snapshots", "params_key", server_default=None)
    op.alter_column("analytics_snapshot_rebuild_tasks", "params_key", server_default=None)
    op.alter_column("analytics_snapshot_rebuild_tasks", "status", server_default=None)
    op.alter_column("analytics_snapshot_rebuild_tasks", "attempts", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_analytics_snapshot_rebuild_tasks_status", table_name="analytics_snapshot_rebuild_tasks")
    op.drop_index("ix_analytics_snapshot_rebuild_tasks_params_key", table_name="analytics_snapshot_rebuild_tasks")
    op.drop_index("ix_analytics_snapshot_rebuild_tasks_snapshot_month", table_name="analytics_snapshot_rebuild_tasks")
    op.drop_index("ix_analytics_snapshot_rebuild_tasks_analytics_kind", table_name="analytics_snapshot_rebuild_tasks")
    op.drop_index("ix_analytics_snapshot_rebuild_tasks_company_id", table_name="analytics_snapshot_rebuild_tasks")
    op.drop_table("analytics_snapshot_rebuild_tasks")

    op.drop_index("ix_analytics_monthly_snapshots_params_key", table_name="analytics_monthly_snapshots")
    op.drop_index("ix_analytics_monthly_snapshots_snapshot_month", table_name="analytics_monthly_snapshots")
    op.drop_index("ix_analytics_monthly_snapshots_analytics_kind", table_name="analytics_monthly_snapshots")
    op.drop_index("ix_analytics_monthly_snapshots_company_id", table_name="analytics_monthly_snapshots")
    op.drop_table("analytics_monthly_snapshots")
