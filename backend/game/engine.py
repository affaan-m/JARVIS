# RESEARCH: see models.py — no library models these rules, so they live here as
#   pure state transitions over a single GameEngine instance.
# DECISION: One engine object holds one game; the API layer owns the instance.

from __future__ import annotations

import random
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger

from game.models import (
    BingoSquare,
    FeedItem,
    GameConfig,
    GameMode,
    GameState,
    Hint,
    Player,
    PowerUp,
    Proximity,
    Tag,
    TagStatus,
    Team,
)

BINGO_POOL: list[str] = [
    "Twee spelers op één foto",
    "Een speler bij de koffieautomaat",
    "Een speler op de trap",
    "Een speler met een laptop open",
    "Drie spelers op één foto",
    "Een speler buiten het gebouw",
    "Een speler in een vergaderruimte",
    "Een speler met een jas aan",
    "Een selfie met een speler",
]

PENDING_TAG_TIMEOUT_MINUTES = 30


class GameError(Exception):
    """Raised when an action is not allowed by the rules."""


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_hhmm(value: str) -> time:
    hour, _, minute = value.partition(":")
    return time(int(hour), int(minute or 0))


class GameEngine:
    """Holds one game and applies the rules. Every tag needs the target's consent."""

    def __init__(self, config: GameConfig | None = None) -> None:
        self.config = config or GameConfig()
        self.game_id = f"game_{uuid4().hex[:10]}"
        self.state = GameState.LOBBY
        self.players: dict[str, Player] = {}
        self.tags: dict[str, Tag] = {}
        self.feed: list[FeedItem] = []
        self.bingo_cards: dict[str, list[BingoSquare]] = {}
        self.hunt_started_at: dict[str, datetime] = {}
        self.king_id: str | None = None
        self.started_at: datetime | None = None
        self.ends_at: datetime | None = None
        self.winner_id: str | None = None

    # ── lobby ──────────────────────────────────────────────────────────────

    def join(
        self,
        name: str,
        *,
        nickname: str | None = None,
        hints: list[str] | None = None,
        secret_mission: str | None = None,
        weak_spot: str | None = None,
        now: datetime | None = None,
    ) -> Player:
        """Add a player. Players always add themselves — nobody is entered by others."""
        if self.state is GameState.ENDED:
            raise GameError("Dit spel is afgelopen")
        player = Player(
            player_id=f"pl_{uuid4().hex[:8]}",
            name=name,
            nickname=nickname,
            secret_mission=secret_mission,
            weak_spot=weak_spot,
            hints=[Hint(text=t) for t in (hints or [])],
            joined_at=now or _now(),
        )
        self.players[player.player_id] = player
        logger.info("game={} player joined id={} name={}", self.game_id, player.player_id, name)
        if self.state is GameState.RUNNING:
            self._late_join(player, now or _now())
        return player

    def leave(self, player_id: str, *, now: datetime | None = None) -> None:
        """Remove a player at their own request, at any point in the game."""
        player = self._player(player_id)
        now = now or _now()
        # Hand the leaver's target to whoever was hunting them, so the chain holds
        hunter = self._hunter_of(player_id)
        if hunter is not None and self.config.mode is GameMode.ASSASSIN:
            hunter.target_id = player.target_id
            self.hunt_started_at[hunter.player_id] = now
        player.alive = False
        player.target_id = None
        player.sharing_location = False
        player.zone = None
        del self.players[player_id]
        self.bingo_cards.pop(player_id, None)
        self.hunt_started_at.pop(player_id, None)
        if self.king_id == player_id:
            self.king_id = None
        logger.info("game={} player left id={}", self.game_id, player_id)
        self._check_for_winner(now)

    def start(self, *, now: datetime | None = None) -> None:
        """Lock the lobby and deal targets, teams or bingo cards."""
        if self.state is not GameState.LOBBY:
            raise GameError("Het spel is al gestart")
        if len(self.players) < 2:
            raise GameError("Er zijn minstens 2 spelers nodig")

        now = now or _now()
        self.state = GameState.RUNNING
        self.started_at = now
        self.ends_at = now + timedelta(minutes=self.config.duration_minutes)

        ids = list(self.players)
        random.shuffle(ids)

        if self.config.mode is GameMode.ASSASSIN:
            # One closed ring, so everyone hunts and is hunted exactly once
            for current, nxt in zip(ids, ids[1:] + ids[:1], strict=True):
                self.players[current].target_id = nxt
                self.hunt_started_at[current] = now
        elif self.config.mode is GameMode.HUNTERS:
            split = max(1, len(ids) // 3)
            for i, pid in enumerate(ids):
                self.players[pid].team = Team.HUNTER if i < split else Team.RUNNER
        elif self.config.mode is GameMode.KING:
            self.king_id = ids[0]
        elif self.config.mode is GameMode.BINGO:
            for pid in ids:
                pool = random.sample(BINGO_POOL, k=min(5, len(BINGO_POOL)))
                self.bingo_cards[pid] = [BingoSquare(text=t) for t in pool]

        self._add_feed("system", text=f"Het spel is begonnen: {self.config.mode.value}", now=now)
        logger.info("game={} started mode={} players={}", self.game_id, self.config.mode, len(ids))

    def _late_join(self, player: Player, now: datetime) -> None:
        """Splice a latecomer into the running game."""
        if self.config.mode is GameMode.ASSASSIN:
            others = [p for p in self._alive() if p.player_id != player.player_id]
            if others:
                victim = random.choice(others)
                player.target_id = victim.target_id
                victim.target_id = player.player_id
                self.hunt_started_at[player.player_id] = now
                self.hunt_started_at[victim.player_id] = now
        elif self.config.mode is GameMode.HUNTERS:
            player.team = Team.RUNNER
        elif self.config.mode is GameMode.BINGO:
            pool = random.sample(BINGO_POOL, k=min(5, len(BINGO_POOL)))
            self.bingo_cards[player.player_id] = [BingoSquare(text=t) for t in pool]

    def end(self, *, now: datetime | None = None) -> None:
        """Stop the game and wipe what players shared for it."""
        self.state = GameState.ENDED
        for player in self.players.values():
            player.sharing_location = False
            player.zone = None
            player.target_id = None
        self._add_feed("system", text="Het spel is afgelopen", now=now or _now())
        logger.info("game={} ended winner={}", self.game_id, self.winner_id)

    def reset(self) -> None:
        """Delete every player, photo and tag of the finished game."""
        self.players.clear()
        self.tags.clear()
        self.feed.clear()
        self.bingo_cards.clear()
        self.hunt_started_at.clear()
        self.king_id = None
        self.winner_id = None
        self.started_at = None
        self.ends_at = None
        self.state = GameState.LOBBY
        logger.info("game={} reset — all player data cleared", self.game_id)

    # ── tagging ────────────────────────────────────────────────────────────

    def claim_tag(
        self,
        tagger_id: str,
        target_id: str,
        *,
        photo_id: str | None = None,
        killcam: list[str] | None = None,
        now: datetime | None = None,
    ) -> Tag:
        """Claim a tag. It stays pending until the target confirms it themselves."""
        now = now or _now()
        tagger = self._player(tagger_id)
        target = self._player(target_id)

        if self.state is not GameState.RUNNING:
            raise GameError("Het spel loopt niet")
        if tagger_id == target_id:
            raise GameError("Je kunt jezelf niet taggen")
        if not tagger.alive:
            raise GameError("Je bent uitgeschakeld")
        if not target.alive:
            raise GameError("Deze speler is al uitgeschakeld")
        if not self.in_play_window(now):
            raise GameError("Buiten de speeltijd")
        self._check_mode_rules(tagger, target)

        tag = Tag(
            tag_id=f"tag_{uuid4().hex[:8]}",
            tagger_id=tagger_id,
            target_id=target_id,
            created_at=now,
            photo_id=photo_id,
            killcam=list(killcam or []),
        )
        self.tags[tag.tag_id] = tag

        # Rules that settle the tag without asking the target
        if target.zone and target.zone in self.config.safe_zones:
            return self._reject(tag, f"{target.name} is in een safe zone", now)
        if target.is_immune(now):
            return self._reject(tag, f"{target.name} is nog even onaantastbaar", now)
        if PowerUp.SHIELD in target.power_ups:
            target.power_ups.remove(PowerUp.SHIELD)
            return self._reject(tag, f"{target.name} gebruikte een schild", now)

        logger.info("game={} tag claimed {} -> {}", self.game_id, tagger_id, target_id)
        return tag

    def _check_mode_rules(self, tagger: Player, target: Player) -> None:
        if self.config.mode is GameMode.ASSASSIN and tagger.target_id != target.player_id:
            raise GameError("Dit is niet jouw doelwit")
        if self.config.mode is GameMode.HUNTERS:
            if tagger.team is not Team.HUNTER:
                raise GameError("Alleen hunters mogen taggen")
            if target.team is not Team.RUNNER:
                raise GameError("Je kunt alleen runners taggen")
        if self.config.mode is GameMode.KING and target.player_id != self.king_id:
            raise GameError("Alleen de koning kan getagd worden")

    def confirm_tag(self, tag_id: str, by_player_id: str, *, now: datetime | None = None) -> Tag:
        """Confirm a tag. Only the tagged player can do this."""
        now = now or _now()
        tag = self._tag(tag_id)
        if tag.status is not TagStatus.PENDING:
            raise GameError("Deze tag is al afgehandeld")
        if by_player_id != tag.target_id:
            raise GameError("Alleen de getagde speler kan dit bevestigen")

        tagger = self.players.get(tag.tagger_id)
        target = self.players.get(tag.target_id)
        if tagger is None or target is None:
            return self._reject(tag, "Speler niet meer in het spel", now)

        points = self.config.points_per_tag
        if self.is_endgame(now):
            points *= self.config.endgame_multiplier

        tag.status = TagStatus.CONFIRMED
        tag.points_awarded = points
        tag.resolved_at = now
        tagger.points += points
        tagger.tags_made += 1
        target.immune_until = now + timedelta(minutes=self.config.immunity_minutes)

        self._apply_mode_outcome(tagger, target, now)
        self._add_feed(
            "tag",
            author_id=tagger.player_id,
            text=f"{tagger.name} tagde {target.name}",
            photo_id=tag.photo_id,
            now=now,
            meta={
                "points": points,
                "endgame": self.is_endgame(now),
                "killcam": list(tag.killcam),
            },
        )
        logger.info(
            "game={} tag confirmed {} -> {} points={}",
            self.game_id, tagger.player_id, target.player_id, points,
        )
        self._check_for_winner(now)
        return tag

    def reject_tag(self, tag_id: str, by_player_id: str, *, now: datetime | None = None) -> Tag:
        """Reject a tag. Only the tagged player can do this."""
        tag = self._tag(tag_id)
        if tag.status is not TagStatus.PENDING:
            raise GameError("Deze tag is al afgehandeld")
        if by_player_id != tag.target_id:
            raise GameError("Alleen de getagde speler kan dit afwijzen")
        return self._reject(tag, "Afgewezen door de getagde speler", now or _now())

    def _apply_mode_outcome(self, tagger: Player, target: Player, now: datetime) -> None:
        if self.config.mode is GameMode.ASSASSIN:
            target.alive = False
            tagger.target_id = target.target_id
            target.target_id = None
            self.hunt_started_at[tagger.player_id] = now
            self.hunt_started_at.pop(target.player_id, None)
        elif self.config.mode is GameMode.HUNTERS:
            target.team = Team.HUNTER
        elif self.config.mode is GameMode.KING:
            self.king_id = tagger.player_id
            self._add_feed("system", text=f"{tagger.name} is de nieuwe koning", now=now)

    def _reject(self, tag: Tag, reason: str, now: datetime) -> Tag:
        tag.status = TagStatus.REJECTED
        tag.reason = reason
        tag.resolved_at = now
        logger.info("game={} tag rejected {}: {}", self.game_id, tag.tag_id, reason)
        return tag

    # ── clock-driven rules ─────────────────────────────────────────────────

    def tick(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Apply everything that depends on time passing. Safe to call often."""
        now = now or _now()
        released: list[str] = []
        expired: list[str] = []

        if self.state is not GameState.RUNNING:
            return {"released_hints": released, "expired_tags": expired}

        for tag in self.tags.values():
            if tag.status is TagStatus.PENDING and now - tag.created_at > timedelta(
                minutes=PENDING_TAG_TIMEOUT_MINUTES
            ):
                tag.status = TagStatus.EXPIRED
                tag.resolved_at = now
                expired.append(tag.tag_id)

        # King of the hill earns points just by holding the crown
        if self.config.mode is GameMode.KING and self.king_id in self.players:
            self.players[self.king_id].points += 1

        released.extend(self._release_due_hints(now))

        if self.ends_at and now >= self.ends_at:
            self._decide_winner_on_time()
            self.end(now=now)

        return {"released_hints": released, "expired_tags": expired}

    def _release_due_hints(self, now: datetime) -> list[str]:
        """Release a target's own hints the longer they stay untagged."""
        released: list[str] = []
        endgame = self.is_endgame(now)
        for player in self._alive():
            target = self.players.get(player.target_id or "")
            if target is None or target.is_disguised(now):
                continue
            started = self.hunt_started_at.get(player.player_id)
            if started is None:
                continue
            elapsed = (now - started).total_seconds() / 60
            due = len(target.hints) if endgame else int(
                elapsed // max(1, self.config.hint_interval_minutes)
            )
            for hint in target.hints[:due]:
                if not hint.released:
                    hint.released = True
                    hint.released_at = now
                    released.append(hint.text)
                    self._add_feed(
                        "hint",
                        author_id=target.player_id,
                        text=f"Nieuwe hint over {target.name}: {hint.text}",
                        now=now,
                    )
        return released

    def is_endgame(self, now: datetime | None = None) -> bool:
        now = now or _now()
        if self.ends_at is None or self.state is not GameState.RUNNING:
            return False
        return now >= self.ends_at - timedelta(minutes=self.config.endgame_minutes)

    def in_play_window(self, now: datetime | None = None) -> bool:
        """True inside the play window, read in the game's own timezone."""
        now = now or _now()
        start = _parse_hhmm(self.config.play_window_start)
        end = _parse_hhmm(self.config.play_window_end)
        current = self._local(now).time()
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end  # window crosses midnight

    def _local(self, moment: datetime) -> datetime:
        """The same instant in the game's timezone, so "10:00" means players' 10:00."""
        try:
            zone = ZoneInfo(self.config.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning("Unknown timezone {}, falling back to UTC", self.config.timezone)
            zone = UTC
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(zone)

    def _decide_winner_on_time(self) -> None:
        candidates = [p for p in self.players.values() if p.alive] or list(self.players.values())
        if candidates:
            self.winner_id = max(candidates, key=lambda p: (p.points, p.tags_made)).player_id

    def _check_for_winner(self, now: datetime) -> None:
        if self.config.mode is not GameMode.ASSASSIN or self.state is not GameState.RUNNING:
            return
        alive = self._alive()
        if len(alive) <= 1:
            self.winner_id = alive[0].player_id if alive else None
            self.end(now=now)

    # ── radar, power-ups, feed ─────────────────────────────────────────────

    def radar(self, player_id: str, *, now: datetime | None = None) -> Proximity:
        """Warm or cold on the player's own target. Never a position."""
        now = now or _now()
        player = self._player(player_id)
        target = self.players.get(player.target_id or "")
        if target is None or not target.sharing_location or target.is_disguised(now):
            return Proximity.UNKNOWN
        if not player.sharing_location or player.zone is None:
            return Proximity.UNKNOWN
        return Proximity.WARM if player.zone == target.zone else Proximity.COLD

    def set_location(
        self, player_id: str, *, zone: str | None, sharing: bool | None = None
    ) -> Player:
        """Update a player's own coarse zone, or pause sharing entirely."""
        player = self._player(player_id)
        if sharing is not None:
            player.sharing_location = sharing
            if not sharing:
                player.zone = None
                return player
        player.zone = zone
        if zone is not None and sharing is None:
            player.sharing_location = True
        return player

    def hunters_of(self, player_id: str) -> list[str]:
        """Who is hunting this player — only revealed through the spy power-up."""
        player = self._player(player_id)
        if PowerUp.SPY not in player.power_ups:
            raise GameError("Hiervoor heb je een spy power-up nodig")
        player.power_ups.remove(PowerUp.SPY)
        hunter = self._hunter_of(player_id)
        return [hunter.player_id] if hunter else []

    def use_power_up(self, player_id: str, kind: PowerUp, *, now: datetime | None = None) -> Player:
        """Spend a power-up. Shield and spy are consumed where they take effect."""
        now = now or _now()
        player = self._player(player_id)
        if kind not in player.power_ups:
            raise GameError("Je hebt deze power-up niet")
        if kind is PowerUp.DISGUISE:
            player.power_ups.remove(kind)
            player.disguised_until = now + timedelta(minutes=10)
        elif kind is PowerUp.SHIELD:
            raise GameError("Een schild werkt automatisch bij de volgende tag")
        elif kind is PowerUp.SPY:
            raise GameError("Gebruik de spy power-up via hunters_of")
        return player

    def award_power_up(self, player_id: str, kind: PowerUp) -> Player:
        player = self._player(player_id)
        player.power_ups.append(kind)
        logger.info("game={} power-up {} -> {}", self.game_id, kind.value, player_id)
        return player

    def post_photo(
        self,
        player_id: str,
        photo_id: str,
        *,
        text: str | None = None,
        now: datetime | None = None,
    ) -> FeedItem:
        self._player(player_id)
        return self._add_feed(
            "photo", author_id=player_id, text=text, photo_id=photo_id, now=now or _now()
        )

    def vote(self, item_id: str, player_id: str) -> FeedItem:
        """One vote per player per feed item."""
        self._player(player_id)
        for item in self.feed:
            if item.item_id == item_id:
                item.votes.add(player_id)
                return item
        raise GameError("Deze post bestaat niet")

    def mark_bingo(self, player_id: str, index: int) -> list[BingoSquare]:
        card = self.bingo_cards.get(player_id)
        if card is None:
            raise GameError("Je hebt geen bingokaart")
        if not 0 <= index < len(card):
            raise GameError("Dit vakje bestaat niet")
        card[index].done = True
        if all(square.done for square in card):
            self.players[player_id].points += self.config.points_per_tag
            self._add_feed(
                "system", text=f"{self.players[player_id].name} heeft bingo!", now=_now()
            )
        return card

    def scoreboard(self) -> list[dict[str, Any]]:
        ranked = sorted(
            self.players.values(), key=lambda p: (p.points, p.tags_made), reverse=True
        )
        return [
            {
                "rank": i,
                "player_id": p.player_id,
                "name": p.nickname or p.name,
                "points": p.points,
                "tags_made": p.tags_made,
                "alive": p.alive,
            }
            for i, p in enumerate(ranked, start=1)
        ]

    def public_state(self, *, for_player_id: str | None = None) -> dict[str, Any]:
        """The board as one player may see it: own target, never anyone else's."""
        now = _now()
        me = self.players.get(for_player_id or "")
        return {
            "game_id": self.game_id,
            "state": self.state.value,
            "config": self.config.to_dict(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "endgame": self.is_endgame(now),
            "in_play_window": self.in_play_window(now),
            "king_id": self.king_id,
            "winner_id": self.winner_id,
            "players": [
                p.to_dict(reveal_target=p.player_id == for_player_id)
                for p in self.players.values()
            ],
            "me": me.to_dict(reveal_target=True) if me else None,
            "my_target": (
                self.players[me.target_id].to_dict()
                if me and me.target_id and me.target_id in self.players
                else None
            ),
            "radar": self.radar(for_player_id, now=now).value if me else None,
            "bingo_card": [s.to_dict() for s in self.bingo_cards.get(for_player_id or "", [])],
            "pending_tags": [
                t.to_dict()
                for t in self.tags.values()
                if t.status is TagStatus.PENDING and t.target_id == for_player_id
            ],
            "feed": [i.to_dict() for i in self.feed[-50:]],
            "scoreboard": self.scoreboard(),
        }

    # ── helpers ────────────────────────────────────────────────────────────

    def _alive(self) -> list[Player]:
        return [p for p in self.players.values() if p.alive]

    def _hunter_of(self, player_id: str) -> Player | None:
        for candidate in self.players.values():
            if candidate.target_id == player_id and candidate.alive:
                return candidate
        return None

    def _player(self, player_id: str) -> Player:
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Speler niet gevonden")
        return player

    def _tag(self, tag_id: str) -> Tag:
        tag = self.tags.get(tag_id)
        if tag is None:
            raise GameError("Tag niet gevonden")
        return tag

    def _add_feed(
        self,
        kind: str,
        *,
        author_id: str | None = None,
        text: str | None = None,
        photo_id: str | None = None,
        now: datetime | None = None,
        meta: dict[str, Any] | None = None,
    ) -> FeedItem:
        item = FeedItem(
            item_id=f"feed_{uuid4().hex[:8]}",
            kind=kind,
            created_at=now or _now(),
            author_id=author_id,
            text=text,
            photo_id=photo_id,
            meta=meta or {},
        )
        self.feed.append(item)
        return item
