"""initial schema

Revision ID: 20260310_000001
Revises:
Create Date: 2026-03-10 18:50:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260310_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracked_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_thread_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "telegram_chat_id", "telegram_thread_id", name="uq_tracked_topics_chat_thread"
        ),
    )
    op.create_index("ix_tracked_topics_telegram_chat_id", "tracked_topics", ["telegram_chat_id"])
    op.create_index(
        "ix_tracked_topics_telegram_thread_id", "tracked_topics", ["telegram_thread_id"]
    )

    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dota_account_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dota_account_id"),
    )
    op.create_index("ix_players_dota_account_id", "players", ["dota_account_id"])

    op.create_table(
        "topic_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "topic_id",
            sa.Integer(),
            sa.ForeignKey("tracked_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_id",
            sa.Integer(),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(length=255), nullable=True),
        sa.Column("last_seen_match_id", sa.BigInteger(), nullable=True),
        sa.Column("added_by_telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("topic_id", "player_id", name="uq_topic_players_topic_player"),
    )

    op.create_table(
        "player_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "player_id",
            sa.Integer(),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("match_id", sa.BigInteger(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hero_id", sa.Integer(), nullable=False),
        sa.Column("radiant_win", sa.Boolean(), nullable=False),
        sa.Column("player_slot", sa.Integer(), nullable=False),
        sa.Column("kills", sa.Integer(), nullable=False),
        sa.Column("deaths", sa.Integer(), nullable=False),
        sa.Column("assists", sa.Integer(), nullable=False),
        sa.Column("gpm", sa.Integer(), nullable=False),
        sa.Column("xpm", sa.Integer(), nullable=False),
        sa.Column("hero_damage", sa.Integer(), nullable=False),
        sa.Column("tower_damage", sa.Integer(), nullable=False),
        sa.Column("hero_healing", sa.Integer(), nullable=False),
        sa.Column("last_hits", sa.Integer(), nullable=False),
        sa.Column("game_mode", sa.Integer(), nullable=False),
        sa.Column("lobby_type", sa.Integer(), nullable=False),
        sa.Column("party_size", sa.Integer(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("player_id", "match_id", name="uq_player_matches_player_match"),
    )
    op.create_index("ix_player_matches_start_time", "player_matches", ["start_time"])
    op.create_index("ix_player_matches_end_time", "player_matches", ["end_time"])

    op.create_table(
        "report_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "topic_id",
            sa.Integer(),
            sa.ForeignKey("tracked_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger_source", sa.String(length=32), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("report_runs")
    op.drop_index("ix_player_matches_end_time", table_name="player_matches")
    op.drop_index("ix_player_matches_start_time", table_name="player_matches")
    op.drop_table("player_matches")
    op.drop_table("topic_players")
    op.drop_index("ix_players_dota_account_id", table_name="players")
    op.drop_table("players")
    op.drop_index("ix_tracked_topics_telegram_thread_id", table_name="tracked_topics")
    op.drop_index("ix_tracked_topics_telegram_chat_id", table_name="tracked_topics")
    op.drop_table("tracked_topics")
