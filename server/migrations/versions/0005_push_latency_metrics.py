"""Record push queue and APNs provider latency.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("push_attempts")}
    if "queue_latency_ms" not in columns:
        op.add_column("push_attempts", sa.Column("queue_latency_ms", sa.Integer()))
    if "provider_latency_ms" not in columns:
        op.add_column("push_attempts", sa.Column("provider_latency_ms", sa.Integer()))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("push_attempts")}
    if "provider_latency_ms" in columns:
        op.drop_column("push_attempts", "provider_latency_ms")
    if "queue_latency_ms" in columns:
        op.drop_column("push_attempts", "queue_latency_ms")
