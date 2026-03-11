from __future__ import annotations

from enum import StrEnum


class PeriodType(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class ConstantResource(StrEnum):
    HEROES = "heroes"
    GAME_MODE = "game_mode"
    LOBBY_TYPE = "lobby_type"
