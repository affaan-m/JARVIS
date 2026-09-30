# RESEARCH: Checked open-source assassin/tag game servers (killer-party, assassins-manager,
#   both unmaintained Rails apps) and python-statemachine for the lifecycle.
# DECISION: BUILD — the rules are the product here, and they are ~300 lines of plain
#   dataclasses + pure functions. No dependency earns its keep.
# ALT: python-statemachine if the lifecycle grows beyond lobby/running/ended.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class GameMode(StrEnum):
    ASSASSIN = "assassin"
    HUNTERS = "hunters"
    KING = "king"
    BINGO = "bingo"


class GameState(StrEnum):
    LOBBY = "lobby"
    RUNNING = "running"
    ENDED = "ended"


class Team(StrEnum):
    HUNTER = "hunter"
    RUNNER = "runner"
    NONE = "none"


class TagStatus(StrEnum):
    PENDING = "pending"        # waiting for the target to confirm
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"        # target never answered


class PowerUp(StrEnum):
    SHIELD = "shield"          # blocks one incoming tag
    DISGUISE = "disguise"      # 10 min: no hints or radar about you
    SPY = "spy"                # reveals who is hunting you


class Proximity(StrEnum):
    WARM = "warm"
    COLD = "cold"
    UNKNOWN = "unknown"


@dataclass
class Hint:
    """A clue a player writes about themselves, released as the hunt drags on."""

    text: str
    released: bool = False
    released_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "released": self.released,
            "released_at": self.released_at.isoformat() if self.released_at else None,
        }


@dataclass
class Player:
    """A participant. Only players who joined themselves are ever part of a game."""

    player_id: str
    name: str
    nickname: str | None = None
    # Free-text dossier the player writes about themselves — never filled from the web
    secret_mission: str | None = None
    weak_spot: str | None = None
    hints: list[Hint] = field(default_factory=list)

    alive: bool = True
    team: Team = Team.NONE
    target_id: str | None = None
    immune_until: datetime | None = None

    points: int = 0
    tags_made: int = 0

    power_ups: list[PowerUp] = field(default_factory=list)
    disguised_until: datetime | None = None

    # Coarse location, only while the player shares it. No coordinates are ever
    # handed out — the radar answers warm/cold and nothing else.
    sharing_location: bool = False
    zone: str | None = None

    joined_at: datetime | None = None

    def is_immune(self, now: datetime) -> bool:
        return self.immune_until is not None and now < self.immune_until

    def is_disguised(self, now: datetime) -> bool:
        return self.disguised_until is not None and now < self.disguised_until

    def to_dict(self, *, reveal_target: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "player_id": self.player_id,
            "name": self.name,
            "nickname": self.nickname,
            "secret_mission": self.secret_mission,
            "weak_spot": self.weak_spot,
            "alive": self.alive,
            "team": self.team.value,
            "points": self.points,
            "tags_made": self.tags_made,
            "power_ups": [p.value for p in self.power_ups],
            "sharing_location": self.sharing_location,
            "hints": [h.to_dict() for h in self.hints if h.released],
            "immune_until": self.immune_until.isoformat() if self.immune_until else None,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }
        if reveal_target:
            data["target_id"] = self.target_id
        return data


@dataclass
class Tag:
    """One player's claim to have tagged another. Only the target can confirm it."""

    tag_id: str
    tagger_id: str
    target_id: str
    created_at: datetime
    status: TagStatus = TagStatus.PENDING
    photo_id: str | None = None
    killcam: list[str] = field(default_factory=list)
    points_awarded: int = 0
    reason: str | None = None       # why a tag was rejected
    resolved_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag_id": self.tag_id,
            "tagger_id": self.tagger_id,
            "target_id": self.target_id,
            "status": self.status.value,
            "photo_id": self.photo_id,
            "killcam": list(self.killcam),
            "points_awarded": self.points_awarded,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class FeedItem:
    """An entry on the shared board: a photo, a tag broadcast, a hint release."""

    item_id: str
    kind: str                       # "photo" | "tag" | "hint" | "system"
    created_at: datetime
    author_id: str | None = None
    text: str | None = None
    photo_id: str | None = None
    votes: set[str] = field(default_factory=set)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "kind": self.kind,
            "author_id": self.author_id,
            "text": self.text,
            "photo_id": self.photo_id,
            "votes": len(self.votes),
            "meta": self.meta,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class BingoSquare:
    text: str
    done: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "done": self.done}


@dataclass
class GameConfig:
    """Rules chosen when the game is created."""

    mode: GameMode = GameMode.ASSASSIN
    # Tags only count inside this window, so the game stops at the office door.
    # The times are local to `timezone`, not UTC — "10:00" means 10:00 for players.
    play_window_start: str = "10:00"
    play_window_end: str = "16:00"
    timezone: str = "Europe/Amsterdam"
    safe_zones: list[str] = field(default_factory=list)
    immunity_minutes: int = 5
    hint_interval_minutes: int = 10
    endgame_minutes: int = 15
    endgame_multiplier: int = 2
    points_per_tag: int = 100
    duration_minutes: int = 480

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "play_window_start": self.play_window_start,
            "play_window_end": self.play_window_end,
            "timezone": self.timezone,
            "safe_zones": list(self.safe_zones),
            "immunity_minutes": self.immunity_minutes,
            "hint_interval_minutes": self.hint_interval_minutes,
            "endgame_minutes": self.endgame_minutes,
            "endgame_multiplier": self.endgame_multiplier,
            "points_per_tag": self.points_per_tag,
            "duration_minutes": self.duration_minutes,
        }
