"""Add the persistent workspace sync revision.

Revision ID: d001_sync
Revises: e001_ops
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d001_sync"
down_revision = "e001_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("workspaces")}
    if "revision" not in columns:
        op.add_column(
            "workspaces",
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("workspaces")}
    if "revision" in columns:
        op.drop_column("workspaces", "revision")
