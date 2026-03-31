"""add trusted MFA devices

Revision ID: 20260326_0002
Revises: 20260325_0001
Create Date: 2026-03-26 09:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260326_0002"
down_revision = "20260325_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mfa_trusted_devices",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=120), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_mfa_trusted_devices_user_active",
        "mfa_trusted_devices",
        ["user_id", "is_active", "expires_at"],
        unique=False,
    )
    op.create_index(
        "idx_mfa_trusted_devices_token_hash",
        "mfa_trusted_devices",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_mfa_trusted_devices_token_hash", table_name="mfa_trusted_devices")
    op.drop_index("idx_mfa_trusted_devices_user_active", table_name="mfa_trusted_devices")
    op.drop_table("mfa_trusted_devices")
