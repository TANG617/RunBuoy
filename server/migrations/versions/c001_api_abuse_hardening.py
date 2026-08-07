"""Add persistent API abuse accounting and pairing ownership keys.

Revision ID: c001_abuse
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c001_abuse"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    pairing_columns = {column["name"] for column in inspector.get_columns("pairing_sessions")}
    if "creator_key" not in pairing_columns:
        op.add_column(
            "pairing_sessions",
            sa.Column("creator_key", sa.String(length=64), nullable=True),
        )
        op.create_index(
            "ix_pairing_sessions_creator_key",
            "pairing_sessions",
            ["creator_key"],
        )

    if "rate_limit_buckets" not in tables:
        op.create_table(
            "rate_limit_buckets",
            sa.Column("bucket_name", sa.String(length=64), nullable=False),
            sa.Column("subject_key", sa.String(length=64), nullable=False),
            sa.Column("window_start", sa.BigInteger(), nullable=False),
            sa.Column("request_count", sa.Integer(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("bucket_name", "subject_key", "window_start"),
        )
        op.create_index(
            "ix_rate_limit_buckets_expires_at",
            "rate_limit_buckets",
            ["expires_at"],
        )

    if "quota_locks" not in tables:
        op.create_table(
            "quota_locks",
            sa.Column("lock_key", sa.String(length=128), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("lock_key"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "quota_locks" in tables:
        op.drop_table("quota_locks")
    if "rate_limit_buckets" in tables:
        op.drop_index("ix_rate_limit_buckets_expires_at", table_name="rate_limit_buckets")
        op.drop_table("rate_limit_buckets")

    pairing_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("pairing_sessions")
    }
    if "creator_key" in pairing_columns:
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("pairing_sessions")}
        if "ix_pairing_sessions_creator_key" in indexes:
            op.drop_index("ix_pairing_sessions_creator_key", table_name="pairing_sessions")
        op.drop_column("pairing_sessions", "creator_key")
