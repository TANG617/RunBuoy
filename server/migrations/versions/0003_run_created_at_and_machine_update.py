"""Track Run creation time and allow Machines to rename themselves.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    run_columns = {column["name"] for column in sa.inspect(bind).get_columns("runs")}
    if "created_at" not in run_columns:
        with op.batch_alter_table("runs") as batch:
            batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(
            sa.text(
                """
                UPDATE runs
                SET created_at = COALESCE(
                    (
                        SELECT MIN(run_events.occurred_at)
                        FROM run_events
                        WHERE run_events.run_id = runs.id
                          AND run_events.type = 'run.created'
                    ),
                    started_at,
                    updated_at
                )
                """
            )
        )
        with op.batch_alter_table("runs") as batch:
            batch.alter_column(
                "created_at",
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=True,
                nullable=False,
            )
    op.execute(
        sa.text(
            """
            UPDATE machine_credentials
            SET scopes = CASE
                WHEN scopes = '' THEN 'machines:update'
                ELSE scopes || ' machines:update'
            END
            WHERE scopes NOT LIKE '%machines:update%'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE machine_credentials
            SET scopes = TRIM(REPLACE(scopes, 'machines:update', ''))
            WHERE scopes LIKE '%machines:update%'
            """
        )
    )
    run_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("runs")}
    if "created_at" in run_columns:
        with op.batch_alter_table("runs") as batch:
            batch.drop_column("created_at")
