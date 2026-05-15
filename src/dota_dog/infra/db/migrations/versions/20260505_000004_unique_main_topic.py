"""unique main chat topic

Revision ID: 20260505_000004
Revises: 20260310_000003
Create Date: 2026-05-05 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260505_000004"
down_revision = "20260310_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_tracked_topics_chat_null_thread",
        "tracked_topics",
        ["telegram_chat_id"],
        unique=True,
        postgresql_where=sa.text("telegram_thread_id IS NULL"),
        sqlite_where=sa.text("telegram_thread_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_tracked_topics_chat_null_thread",
        table_name="tracked_topics",
    )
