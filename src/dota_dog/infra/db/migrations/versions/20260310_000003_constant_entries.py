"""constant entries

Revision ID: 20260310_000003
Revises: 20260310_000002
Create Date: 2026-03-10 22:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260310_000003"
down_revision = "20260310_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "constant_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resource", sa.String(length=32), nullable=False),
        sa.Column("code", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resource", "code", name="uq_constant_entries_resource_code"),
    )


def downgrade() -> None:
    op.drop_table("constant_entries")
