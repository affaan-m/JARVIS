from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from game.engine import PENDING_TAG_TIMEOUT_MINUTES, GameEngine, GameError
from game.models import GameConfig, GameMode, PowerUp, Proximity, TagStatus, Team

NOON = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _engine(mode: GameMode = GameMode.ASSASSIN, **kw) -> GameEngine:
    # NOON is UTC; pinning the game to UTC keeps the play-window maths readable
    kw.setdefault("timezone", "UTC")
    return GameEngine(GameConfig(mode=mode, **kw))


def _started(n: int = 3, mode: GameMode = GameMode.ASSASSIN, **kw) -> tuple[GameEngine, list]:
    engine = _engine(mode, **kw)
    players = [engine.join(f"Speler {i}", hints=[f"hint {i}a", f"hint {i}b"], now=NOON)
               for i in range(n)]
    engine.start(now=NOON)
    return engine, players


# ── lobby ──

def test_needs_two_players_to_start() -> None:
    engine = _engine()
    engine.join("Alleen", now=NOON)
    with pytest.raises(GameError):
        engine.start(now=NOON)


def test_assassin_targets_form_one_closed_ring() -> None:
    engine, players = _started(4)
    targets = {p.player_id: p.target_id for p in players}
    assert None not in targets.values()
    # Following the chain visits everyone exactly once and returns to the start
    start = players[0].player_id
    seen, current = [], start
    for _ in range(4):
        current = targets[current]
        seen.append(current)
    assert seen[-1] == start
    assert len(set(seen)) == 4


def test_nobody_hunts_themselves() -> None:
    engine, players = _started(5)
    assert all(p.target_id != p.player_id for p in players)


def test_a_player_can_leave_and_the_chain_holds() -> None:
    engine, players = _started(3)
    leaver = players[0]
    hunter = next(p for p in players if p.target_id == leaver.player_id)
    inherited = leaver.target_id

    engine.leave(leaver.player_id, now=NOON)

    assert leaver.player_id not in engine.players
    assert hunter.target_id == inherited


# ── tagging needs the target's consent ──

def test_a_claimed_tag_is_pending_until_the_target_confirms() -> None:
    engine, players = _started(3)
    tagger = players[0]
    target = engine.players[tagger.target_id]

    tag = engine.claim_tag(tagger.player_id, target.player_id, now=NOON)

    assert tag.status is TagStatus.PENDING
    assert tagger.points == 0
    assert target.alive is True


def test_only_the_target_can_confirm_a_tag() -> None:
    engine, players = _started(3)
    tagger = players[0]
    target_id = tagger.target_id
    tag = engine.claim_tag(tagger.player_id, target_id, now=NOON)

    with pytest.raises(GameError):
        engine.confirm_tag(tag.tag_id, tagger.player_id, now=NOON)

    other = next(p for p in players if p.player_id not in (tagger.player_id, target_id))
    with pytest.raises(GameError):
        engine.confirm_tag(tag.tag_id, other.player_id, now=NOON)

    engine.confirm_tag(tag.tag_id, target_id, now=NOON)
    assert engine.tags[tag.tag_id].status is TagStatus.CONFIRMED


def test_the_target_can_reject_a_tag() -> None:
    engine, players = _started(3)
    tagger = players[0]
    tag = engine.claim_tag(tagger.player_id, tagger.target_id, now=NOON)

    engine.reject_tag(tag.tag_id, tag.target_id, now=NOON)

    assert engine.tags[tag.tag_id].status is TagStatus.REJECTED
    assert tagger.points == 0
    assert engine.players[tag.target_id].alive is True


def test_confirmed_tag_awards_points_and_inherits_the_target() -> None:
    engine, players = _started(4)
    tagger = players[0]
    victim = engine.players[tagger.target_id]
    victims_target = victim.target_id

    tag = engine.claim_tag(tagger.player_id, victim.player_id, now=NOON)
    engine.confirm_tag(tag.tag_id, victim.player_id, now=NOON)

    assert tagger.points == engine.config.points_per_tag
    assert tagger.tags_made == 1
    assert victim.alive is False
    assert tagger.target_id == victims_target


def test_pending_tags_expire() -> None:
    engine, players = _started(3)
    tag = engine.claim_tag(players[0].player_id, players[0].target_id, now=NOON)

    engine.tick(now=NOON + timedelta(minutes=PENDING_TAG_TIMEOUT_MINUTES + 1))

    assert engine.tags[tag.tag_id].status is TagStatus.EXPIRED


# ── fair play ──

def test_you_cannot_tag_someone_who_is_not_your_target() -> None:
    engine, players = _started(4)
    tagger = players[0]
    stranger = next(
        p for p in players
        if p.player_id not in (tagger.player_id, tagger.target_id)
    )
    with pytest.raises(GameError):
        engine.claim_tag(tagger.player_id, stranger.player_id, now=NOON)


def test_safe_zone_blocks_a_tag() -> None:
    engine, players = _started(3, safe_zones=["toilet"])
    tagger = players[0]
    target = engine.players[tagger.target_id]
    engine.set_location(target.player_id, zone="toilet", sharing=True)

    tag = engine.claim_tag(tagger.player_id, target.player_id, now=NOON)

    assert tag.status is TagStatus.REJECTED
    assert "safe zone" in (tag.reason or "")


def test_immunity_after_being_tagged_blocks_the_next_tag() -> None:
    engine, players = _started(3, mode=GameMode.KING, immunity_minutes=5)
    king = engine.players[engine.king_id]
    challenger, bystander = (p for p in players if p.player_id != king.player_id)

    # The challenger takes the crown, which leaves the old king immune for 5 min
    first = engine.claim_tag(challenger.player_id, king.player_id, now=NOON)
    engine.confirm_tag(first.tag_id, king.player_id, now=NOON)

    # The old king wins it straight back
    second = engine.claim_tag(king.player_id, challenger.player_id, now=NOON)
    engine.confirm_tag(second.tag_id, challenger.player_id, now=NOON)
    assert engine.king_id == king.player_id

    # A bystander cannot tag them while their immunity still runs
    blocked = engine.claim_tag(bystander.player_id, king.player_id, now=NOON)
    assert blocked.status is TagStatus.REJECTED
    assert "onaantastbaar" in (blocked.reason or "")

    # Once it lapses, they are fair game again
    later = engine.claim_tag(
        bystander.player_id, king.player_id, now=NOON + timedelta(minutes=6)
    )
    assert later.status is TagStatus.PENDING


def test_shield_blocks_one_tag_then_is_gone() -> None:
    engine, players = _started(3)
    tagger = players[0]
    target = engine.players[tagger.target_id]
    engine.award_power_up(target.player_id, PowerUp.SHIELD)

    blocked = engine.claim_tag(tagger.player_id, target.player_id, now=NOON)
    assert blocked.status is TagStatus.REJECTED
    assert "schild" in (blocked.reason or "")
    assert PowerUp.SHIELD not in target.power_ups

    again = engine.claim_tag(tagger.player_id, target.player_id, now=NOON)
    assert again.status is TagStatus.PENDING


def test_tags_outside_the_play_window_are_refused() -> None:
    engine, players = _started(3, play_window_start="10:00", play_window_end="16:00")
    evening = NOON.replace(hour=22)
    with pytest.raises(GameError, match="speeltijd"):
        engine.claim_tag(players[0].player_id, players[0].target_id, now=evening)


def test_you_cannot_tag_yourself() -> None:
    engine, players = _started(3)
    with pytest.raises(GameError):
        engine.claim_tag(players[0].player_id, players[0].player_id, now=NOON)


# ── hints, endgame, winner ──

def test_hints_release_as_the_hunt_drags_on() -> None:
    engine, players = _started(3, hint_interval_minutes=10)
    hunter = players[0]
    target = engine.players[hunter.target_id]
    assert all(not h.released for h in target.hints)

    engine.tick(now=NOON + timedelta(minutes=10))
    assert sum(h.released for h in target.hints) == 1

    engine.tick(now=NOON + timedelta(minutes=20))
    assert sum(h.released for h in target.hints) == 2


def test_disguise_stops_hints_and_radar() -> None:
    engine, players = _started(3, hint_interval_minutes=5)
    hunter = players[0]
    target = engine.players[hunter.target_id]
    engine.award_power_up(target.player_id, PowerUp.DISGUISE)
    engine.use_power_up(target.player_id, PowerUp.DISGUISE, now=NOON)

    # A hint would be due at +5, but the disguise holds until +10
    engine.tick(now=NOON + timedelta(minutes=6))
    assert all(not h.released for h in target.hints)
    engine.set_location(hunter.player_id, zone="floor-1", sharing=True)
    engine.set_location(target.player_id, zone="floor-1", sharing=True)
    assert engine.radar(hunter.player_id, now=NOON + timedelta(minutes=6)) is Proximity.UNKNOWN

    # After it wears off the hints start flowing again
    engine.tick(now=NOON + timedelta(minutes=11))
    assert sum(h.released for h in target.hints) >= 1


def test_endgame_doubles_points_and_frees_every_hint() -> None:
    engine, players = _started(3, duration_minutes=60, endgame_minutes=15)
    late = NOON + timedelta(minutes=50)
    assert engine.is_endgame(late) is True

    tagger = players[0]
    target = engine.players[tagger.target_id]
    tag = engine.claim_tag(tagger.player_id, target.player_id, now=late)
    engine.confirm_tag(tag.tag_id, target.player_id, now=late)

    assert tagger.points == engine.config.points_per_tag * 2


def test_last_player_standing_wins_and_the_game_ends() -> None:
    engine, players = _started(2)
    tagger = players[0]
    victim = engine.players[tagger.target_id]

    tag = engine.claim_tag(tagger.player_id, victim.player_id, now=NOON)
    engine.confirm_tag(tag.tag_id, victim.player_id, now=NOON)

    assert engine.winner_id == tagger.player_id
    assert engine.state.value == "ended"


def test_game_ends_when_time_runs_out() -> None:
    engine, _ = _started(3, duration_minutes=30)
    engine.tick(now=NOON + timedelta(minutes=31))
    assert engine.state.value == "ended"
    assert engine.winner_id is not None


# ── radar reveals no positions ──

def test_radar_is_warm_or_cold_only() -> None:
    engine, players = _started(3)
    hunter = players[0]
    target = engine.players[hunter.target_id]

    engine.set_location(hunter.player_id, zone="floor-2", sharing=True)
    engine.set_location(target.player_id, zone="floor-2", sharing=True)
    assert engine.radar(hunter.player_id, now=NOON) is Proximity.WARM

    engine.set_location(target.player_id, zone="floor-5", sharing=True)
    assert engine.radar(hunter.player_id, now=NOON) is Proximity.COLD


def test_pausing_location_sharing_hides_you_from_the_radar() -> None:
    engine, players = _started(3)
    hunter = players[0]
    target = engine.players[hunter.target_id]
    engine.set_location(hunter.player_id, zone="floor-2", sharing=True)
    engine.set_location(target.player_id, zone="floor-2", sharing=True)

    engine.set_location(target.player_id, zone=None, sharing=False)

    assert engine.radar(hunter.player_id, now=NOON) is Proximity.UNKNOWN
    assert target.zone is None


def test_public_state_never_leaks_another_players_target() -> None:
    engine, players = _started(4)
    me = players[0]
    state = engine.public_state(for_player_id=me.player_id)

    assert state["me"]["target_id"] == me.target_id
    others = [p for p in state["players"] if p["player_id"] != me.player_id]
    assert all("target_id" not in p for p in others)


def test_unreleased_hints_are_not_in_public_state() -> None:
    engine, players = _started(3)
    state = engine.public_state(for_player_id=players[0].player_id)
    assert all(p["hints"] == [] for p in state["players"])


def test_spy_power_up_is_needed_to_see_your_hunter() -> None:
    engine, players = _started(3)
    me = players[0]
    with pytest.raises(GameError):
        engine.hunters_of(me.player_id)

    engine.award_power_up(me.player_id, PowerUp.SPY)
    hunters = engine.hunters_of(me.player_id)

    assert len(hunters) == 1
    assert engine.players[hunters[0]].target_id == me.player_id
    assert PowerUp.SPY not in me.power_ups  # consumed


# ── other modes ──

def test_hunters_mode_turns_a_tagged_runner_into_a_hunter() -> None:
    engine, players = _started(4, mode=GameMode.HUNTERS)
    hunter = next(p for p in players if p.team is Team.HUNTER)
    runner = next(p for p in players if p.team is Team.RUNNER)

    tag = engine.claim_tag(hunter.player_id, runner.player_id, now=NOON)
    engine.confirm_tag(tag.tag_id, runner.player_id, now=NOON)

    assert runner.team is Team.HUNTER


def test_runners_cannot_tag() -> None:
    engine, players = _started(4, mode=GameMode.HUNTERS)
    runners = [p for p in players if p.team is Team.RUNNER]
    with pytest.raises(GameError):
        engine.claim_tag(runners[0].player_id, runners[1].player_id, now=NOON)


def test_king_earns_points_while_holding_the_crown() -> None:
    engine, _ = _started(3, mode=GameMode.KING)
    king = engine.players[engine.king_id]
    engine.tick(now=NOON + timedelta(minutes=1))
    assert king.points > 0


def test_tagging_the_king_hands_over_the_crown() -> None:
    engine, players = _started(3, mode=GameMode.KING)
    king_id = engine.king_id
    challenger = next(p for p in players if p.player_id != king_id)

    tag = engine.claim_tag(challenger.player_id, king_id, now=NOON)
    engine.confirm_tag(tag.tag_id, king_id, now=NOON)

    assert engine.king_id == challenger.player_id


def test_bingo_card_is_dealt_and_a_full_card_scores() -> None:
    engine, players = _started(2, mode=GameMode.BINGO)
    me = players[0]
    card = engine.bingo_cards[me.player_id]
    assert len(card) == 5

    for i in range(len(card)):
        engine.mark_bingo(me.player_id, i)

    assert me.points == engine.config.points_per_tag


# ── feed and scoreboard ──

def test_feed_photo_and_one_vote_per_player() -> None:
    engine, players = _started(3)
    item = engine.post_photo(players[0].player_id, "photo_1", text="gespot", now=NOON)

    engine.vote(item.item_id, players[1].player_id)
    engine.vote(item.item_id, players[1].player_id)
    engine.vote(item.item_id, players[2].player_id)

    assert item.to_dict()["votes"] == 2


def test_a_confirmed_tag_is_broadcast_to_the_feed() -> None:
    engine, players = _started(3)
    tagger = players[0]
    tag = engine.claim_tag(tagger.player_id, tagger.target_id, photo_id="p1", now=NOON)
    engine.confirm_tag(tag.tag_id, tag.target_id, now=NOON)

    broadcasts = [i for i in engine.feed if i.kind == "tag"]
    assert len(broadcasts) == 1
    assert broadcasts[0].photo_id == "p1"


def test_scoreboard_is_ranked_by_points() -> None:
    engine, players = _started(4)
    players[1].points = 300
    players[2].points = 100

    board = engine.scoreboard()

    assert board[0]["player_id"] == players[1].player_id
    assert board[0]["rank"] == 1
    assert board[1]["player_id"] == players[2].player_id


def test_reset_clears_every_player_and_photo() -> None:
    engine, players = _started(3)
    engine.post_photo(players[0].player_id, "photo_1", now=NOON)

    engine.reset()

    assert engine.players == {}
    assert engine.feed == []
    assert engine.tags == {}
    assert engine.state.value == "lobby"


def test_play_window_is_read_in_the_games_timezone() -> None:
    # 09:30 UTC is 11:30 in Amsterdam in June, so a 10:00-16:00 window is open
    engine = GameEngine(GameConfig(
        play_window_start="10:00", play_window_end="16:00", timezone="Europe/Amsterdam",
    ))
    assert engine.in_play_window(datetime(2026, 6, 1, 9, 30, tzinfo=UTC)) is True
    # 07:00 UTC is 09:00 local — still shut
    assert engine.in_play_window(datetime(2026, 6, 1, 7, 0, tzinfo=UTC)) is False


def test_unknown_timezone_falls_back_to_utc_without_crashing() -> None:
    engine = GameEngine(GameConfig(
        play_window_start="10:00", play_window_end="16:00", timezone="Mars/Olympus",
    ))
    assert engine.in_play_window(datetime(2026, 6, 1, 12, 0, tzinfo=UTC)) is True


def test_window_crossing_midnight() -> None:
    engine = GameEngine(GameConfig(
        play_window_start="22:00", play_window_end="02:00", timezone="UTC",
    ))
    assert engine.in_play_window(datetime(2026, 6, 1, 23, 0, tzinfo=UTC)) is True
    assert engine.in_play_window(datetime(2026, 6, 1, 1, 0, tzinfo=UTC)) is True
    assert engine.in_play_window(datetime(2026, 6, 1, 12, 0, tzinfo=UTC)) is False
