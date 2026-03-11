"""topic runtime state

Revision ID: 20260310_000002
Revises: 20260310_000001
Create Date: 2026-03-10 21:15:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260310_000002"
down_revision = "20260310_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_runtime_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "topic_id",
            sa.Integer(),
            sa.ForeignKey("tracked_topics.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("last_poll_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_poll_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_poll_succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_poll_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("topic_runtime_state")
