"""Persist SMTP configuration without changing the existing environment fallback."""

import sqlalchemy as sa

from alembic import op

revision = "20260930_0035"
down_revision = "20260426_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_email_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("encryption", sa.String(20), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("sender", sa.String(255), nullable=False),
        sa.Column("recipients", sa.Text(), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_system_email_settings_singleton"),
    )


def downgrade() -> None:
    op.drop_table("system_email_settings")
