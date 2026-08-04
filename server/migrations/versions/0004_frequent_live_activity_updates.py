"""Track whether a device permits frequent Live Activity pushes.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    device_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("devices")}
    if "frequent_live_activity_updates_enabled" not in device_columns:
        op.add_column(
            "devices",
            sa.Column(
                "frequent_live_activity_updates_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )


def downgrade() -> None:
    device_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("devices")}
    if "frequent_live_activity_updates_enabled" in device_columns:
        op.drop_column("devices", "frequent_live_activity_updates_enabled")
