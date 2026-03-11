from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from dota_dog.domain.enums import ConstantResource, PeriodType


@dataclass(slots=True)
class TrackedTopicRef:
    id: int
    telegram_chat_id: int
    telegram_thread_id: int | None
    title: str | None
    timezone: str
    is_paused: bool


@dataclass(slots=True)
class TrackedPlayerRef:
    player_id: int
    dota_account_id: int
    display_name: str
    profile_url: str | None
    alias: str | None
    last_seen_match_id: int | None


@dataclass(slots=True)
class MatchSnapshot:
    player_id: int
    match_id: int
    start_time: datetime
    end_time: datetime
    hero_id: int
    radiant_win: bool
    player_slot: int
    kills: int
    deaths: int
    assists: int
    gpm: int
    xpm: int
    hero_damage: int
    tower_damage: int
    hero_healing: int
    last_hits: int
    game_mode: int
    lobby_type: int
    party_size: int | None
    raw_payload: dict[str, object] = field(default_factory=dict)

    @property
    def is_win(self) -> bool:
        return (self.radiant_win and self.player_slot < 128) or (
            not self.radiant_win and self.player_slot >= 128
        )

    @property
    def duration(self) -> timedelta:
        return self.end_time - self.start_time


@dataclass(slots=True)
class ReportSummary:
    player_id: int
    label: str
    period_type: PeriodType
    period_start: datetime
    period_end: datetime
    matches_count: int
    wins: int
    losses: int
    winrate: float
    avg_kills: float
    avg_deaths: float
    avg_assists: float
    avg_gpm: float
    avg_xpm: float
    avg_duration_minutes: float
    avg_hero_damage: float
    best_streak: int
    worst_streak: int
    top_heroes: list[tuple[int, int]]


@dataclass(slots=True)
class TopicRuntimeStatus:
    topic_id: int
    last_poll_started_at: datetime | None
    last_poll_finished_at: datetime | None
    last_poll_succeeded_at: datetime | None
    last_poll_error: str | None


@dataclass(slots=True)
class ConstantEntry:
    resource: ConstantResource
    code: int
    name: str
    raw_payload: dict[str, object]


@dataclass(slots=True)
class ConstantSnapshot:
    heroes: dict[int, str] = field(default_factory=dict)
    game_modes: dict[int, str] = field(default_factory=dict)
    lobby_types: dict[int, str] = field(default_factory=dict)
