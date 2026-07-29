"""Enable success notifications for existing and new devices.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE devices
            SET success_notifications_enabled = true
            WHERE failure_notifications_enabled = true
              AND success_notifications_enabled = false
            """
        )
    )
    with op.batch_alter_table("devices") as batch:
        batch.alter_column(
            "success_notifications_enabled",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=sa.true(),
        )


def downgrade() -> None:
    with op.batch_alter_table("devices") as batch:
        batch.alter_column(
            "success_notifications_enabled",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=None,
        )
