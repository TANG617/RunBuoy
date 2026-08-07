"""Add persistent multi-instance service heartbeats.

Revision ID: e001_ops
Revises: c001_abuse
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e001_ops"
down_revision = "c001_abuse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 materializes current metadata for brand-new databases, while an
    # existing deployment reaches this revision without the new table.
    if "service_heartbeats" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "service_heartbeats",
            sa.Column("service_name", sa.String(length=64), nullable=False),
            sa.Column("instance_id", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("error_code", sa.String(length=128), nullable=True),
            sa.Column("counters_json", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("service_name", "instance_id"),
        )
        op.create_index(
            "ix_service_heartbeats_service_last_seen",
            "service_heartbeats",
            ["service_name", "last_seen_at"],
            unique=False,
        )


def downgrade() -> None:
    if "service_heartbeats" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index(
            "ix_service_heartbeats_service_last_seen",
            table_name="service_heartbeats",
        )
        op.drop_table("service_heartbeats")
