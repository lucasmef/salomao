"""add report layout configuration tables

Revision ID: 20260328_0003
Revises: 20260326_0002
Create Date: 2026-03-28 09:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260328_0003"
down_revision = "20260326_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_layouts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "kind", name="uq_report_layout_company_kind"),
    )
    op.create_index("ix_report_layouts_company_id", "report_layouts", ["company_id"])
    op.create_index("ix_report_layouts_kind", "report_layouts", ["kind"])

    op.create_table(
        "report_layout_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("layout_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("line_type", sa.String(length=20), nullable=False, server_default="source"),
        sa.Column("operation", sa.String(length=10), nullable=False, server_default="add"),
        sa.Column("special_source", sa.String(length=60), nullable=True),
        sa.Column("summary_binding", sa.String(length=60), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["layout_id"], ["report_layouts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_layout_lines_layout_id", "report_layout_lines", ["layout_id"])
    op.create_index("idx_report_layout_lines_layout_position", "report_layout_lines", ["layout_id", "position"])

    op.create_table(
        "report_layout_line_groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("line_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("group_name", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(["line_id"], ["report_layout_lines.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_layout_line_groups_line_id", "report_layout_line_groups", ["line_id"])
    op.create_index("idx_report_layout_line_groups_line_position", "report_layout_line_groups", ["line_id", "position"])

    op.create_table(
        "report_layout_formula_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("line_id", sa.String(length=36), nullable=False),
        sa.Column("referenced_line_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("operation", sa.String(length=10), nullable=False, server_default="add"),
        sa.ForeignKeyConstraint(["line_id"], ["report_layout_lines.id"]),
        sa.ForeignKeyConstraint(["referenced_line_id"], ["report_layout_lines.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_layout_formula_items_line_id", "report_layout_formula_items", ["line_id"])
    op.create_index("ix_report_layout_formula_items_referenced_line_id", "report_layout_formula_items", ["referenced_line_id"])
    op.create_index("idx_report_layout_formula_items_line_position", "report_layout_formula_items", ["line_id", "position"])


def downgrade() -> None:
    op.drop_index("idx_report_layout_formula_items_line_position", table_name="report_layout_formula_items")
    op.drop_index("ix_report_layout_formula_items_referenced_line_id", table_name="report_layout_formula_items")
    op.drop_index("ix_report_layout_formula_items_line_id", table_name="report_layout_formula_items")
    op.drop_table("report_layout_formula_items")

    op.drop_index("idx_report_layout_line_groups_line_position", table_name="report_layout_line_groups")
    op.drop_index("ix_report_layout_line_groups_line_id", table_name="report_layout_line_groups")
    op.drop_table("report_layout_line_groups")

    op.drop_index("idx_report_layout_lines_layout_position", table_name="report_layout_lines")
    op.drop_index("ix_report_layout_lines_layout_id", table_name="report_layout_lines")
    op.drop_table("report_layout_lines")

    op.drop_index("ix_report_layouts_kind", table_name="report_layouts")
    op.drop_index("ix_report_layouts_company_id", table_name="report_layouts")
    op.drop_table("report_layouts")
