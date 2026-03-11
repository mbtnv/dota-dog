from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OpenDotaProfileResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    profile: dict[str, object] | None = None
    rank_tier: int | None = Field(default=None, alias="rank_tier")

    @property
    def account_id(self) -> int | None:
        if self.profile is None:
            return None
        raw_value = self.profile.get("account_id")
        if isinstance(raw_value, int):
            return raw_value
        if isinstance(raw_value, str) and raw_value.isdigit():
            return int(raw_value)
        return None

    @property
    def personaname(self) -> str | None:
        if self.profile is None:
            return None
        raw_value = self.profile.get("personaname")
        return str(raw_value) if raw_value else None

    @property
    def profile_url(self) -> str | None:
        if self.profile is None:
            return None
        raw_value = self.profile.get("profileurl")
        return str(raw_value) if raw_value else None


class OpenDotaRecentMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    match_id: int
    player_slot: int
    radiant_win: bool
    duration: int
    game_mode: int
    lobby_type: int
    hero_id: int
    start_time: int
    kills: int
    deaths: int
    assists: int
    xp_per_min: int = 0
    gold_per_min: int = 0
    hero_damage: int = 0
    tower_damage: int = 0
    hero_healing: int = 0
    last_hits: int = 0
    party_size: int | None = None


class OpenDotaPlayerMatch(OpenDotaRecentMatch):
    pass
