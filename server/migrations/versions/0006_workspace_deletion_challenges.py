"""Add deletion challenges and retention query indexes.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "workspace_deletion_challenges" not in inspector.get_table_names():
        op.create_table(
            "workspace_deletion_challenges",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("device_id", sa.String(length=64), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
            sa.UniqueConstraint(
                "workspace_id",
                "device_id",
                name="uq_workspace_deletion_challenges_workspace_device",
            ),
        )

    indexes = {
        "workspace_deletion_challenges": {
            "ix_workspace_deletion_challenges_device_id": ["device_id"],
            "ix_workspace_deletion_challenges_expires_at": ["expires_at"],
            "ix_workspace_deletion_challenges_workspace_id": ["workspace_id"],
            "ix_workspace_deletion_challenges_workspace_expires": [
                "workspace_id",
                "expires_at",
            ],
        },
        "runs": {
            "ix_runs_retention": ["execution_status", "ended_at"],
            "ix_runs_updated_at": ["updated_at"],
        },
        "run_events": {"ix_run_events_received_at": ["received_at"]},
        "notifications": {"ix_notifications_created_at": ["created_at"]},
        "push_outbox": {
            "ix_push_outbox_status_updated": ["status", "updated_at"]
        },
        "push_attempts": {"ix_push_attempts_attempted_at": ["attempted_at"]},
        "audit_logs": {"ix_audit_logs_created_at": ["created_at"]},
    }
    inspector = sa.inspect(bind)
    for table_name, table_indexes in indexes.items():
        existing = {item["name"] for item in inspector.get_indexes(table_name)}
        for index_name, columns in table_indexes.items():
            if index_name not in existing:
                op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name, index_name in (
        ("audit_logs", "ix_audit_logs_created_at"),
        ("push_attempts", "ix_push_attempts_attempted_at"),
        ("push_outbox", "ix_push_outbox_status_updated"),
        ("notifications", "ix_notifications_created_at"),
        ("run_events", "ix_run_events_received_at"),
        ("runs", "ix_runs_updated_at"),
        ("runs", "ix_runs_retention"),
    ):
        existing = {item["name"] for item in inspector.get_indexes(table_name)}
        if index_name in existing:
            op.drop_index(index_name, table_name=table_name)
    if "workspace_deletion_challenges" in inspector.get_table_names():
        op.drop_table("workspace_deletion_challenges")
