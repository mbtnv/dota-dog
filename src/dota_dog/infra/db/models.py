from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dota_dog.infra.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class TrackedTopicORM(Base):
    __tablename__ = "tracked_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    telegram_thread_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    is_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    topic_players: Mapped[list[TopicPlayerORM]] = relationship(back_populates="topic")
    report_runs: Mapped[list[ReportRunORM]] = relationship(back_populates="topic")
    runtime_state: Mapped[TopicRuntimeStateORM | None] = relationship(back_populates="topic")

    __table_args__ = (
        UniqueConstraint(
            "telegram_chat_id", "telegram_thread_id", name="uq_tracked_topics_chat_thread"
        ),
    )


class PlayerORM(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dota_account_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    topic_players: Mapped[list[TopicPlayerORM]] = relationship(back_populates="player")
    matches: Mapped[list[PlayerMatchORM]] = relationship(back_populates="player")


class TopicPlayerORM(Base):
    __tablename__ = "topic_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("tracked_topics.id", ondelete="CASCADE"), nullable=False
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_seen_match_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    added_by_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    topic: Mapped[TrackedTopicORM] = relationship(back_populates="topic_players")
    player: Mapped[PlayerORM] = relationship(back_populates="topic_players")

    __table_args__ = (
        UniqueConstraint("topic_id", "player_id", name="uq_topic_players_topic_player"),
    )


class PlayerMatchORM(Base):
    __tablename__ = "player_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    match_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    hero_id: Mapped[int] = mapped_column(Integer, nullable=False)
    radiant_win: Mapped[bool] = mapped_column(Boolean, nullable=False)
    player_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    kills: Mapped[int] = mapped_column(Integer, nullable=False)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False)
    assists: Mapped[int] = mapped_column(Integer, nullable=False)
    gpm: Mapped[int] = mapped_column(Integer, nullable=False)
    xpm: Mapped[int] = mapped_column(Integer, nullable=False)
    hero_damage: Mapped[int] = mapped_column(Integer, nullable=False)
    tower_damage: Mapped[int] = mapped_column(Integer, nullable=False)
    hero_healing: Mapped[int] = mapped_column(Integer, nullable=False)
    last_hits: Mapped[int] = mapped_column(Integer, nullable=False)
    game_mode: Mapped[int] = mapped_column(Integer, nullable=False)
    lobby_type: Mapped[int] = mapped_column(Integer, nullable=False)
    party_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    player: Mapped[PlayerORM] = relationship(back_populates="matches")

    __table_args__ = (
        UniqueConstraint("player_id", "match_id", name="uq_player_matches_player_match"),
    )


class ReportRunORM(Base):
    __tablename__ = "report_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("tracked_topics.id", ondelete="CASCADE"), nullable=False
    )
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    topic: Mapped[TrackedTopicORM] = relationship(back_populates="report_runs")


class TopicRuntimeStateORM(Base):
    __tablename__ = "topic_runtime_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("tracked_topics.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    last_poll_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_poll_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_poll_succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_poll_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    topic: Mapped[TrackedTopicORM] = relationship(back_populates="runtime_state")


class ConstantEntryORM(Base):
    __tablename__ = "constant_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        UniqueConstraint("resource", "code", name="uq_constant_entries_resource_code"),
    )
