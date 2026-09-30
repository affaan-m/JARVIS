"""Game mode endpoints for JARVIS.

Everything here is gated behind a single on/off switch: with game mode off every
route returns 404, so the normal capture pipeline is untouched. With it on, only
players who joined themselves take part, and a tag counts only once the tagged
player confirms it.
"""
from __future__ import annotations

import base64
import binascii
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from loguru import logger
from pydantic import BaseModel, Field

from game.engine import GameEngine, GameError
from game.models import GameConfig, GameMode, PowerUp
from game.photos import PhotoStore, blur_faces

router = APIRouter(prefix="/api/game", tags=["game"])

MAX_PHOTO_BYTES = 8 * 1024 * 1024

_engine = GameEngine()
_photos = PhotoStore()
_enabled = False
_detector: Any = None


def configure(*, enabled: bool, detector: Any = None) -> None:
    """Set the default on/off state at startup (JARVIS_GAME_MODE)."""
    global _enabled, _detector  # noqa: PLW0603
    _enabled = enabled
    _detector = detector
    logger.info("Game mode {}", "enabled" if enabled else "disabled")


def get_photo_store() -> PhotoStore:
    return _photos


def get_engine() -> GameEngine:
    return _engine


def is_enabled() -> bool:
    return _enabled


def _require_enabled() -> GameEngine:
    if not _enabled:
        raise HTTPException(
            status_code=404,
            detail="Spelmodus staat uit — zet hem aan via POST /api/game/mode",
        )
    return _engine


def _guard(action: Any) -> Any:
    try:
        return action()
    except GameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── the switch ─────────────────────────────────────────────────────────────


class ModeToggle(BaseModel):
    enabled: bool


@router.get("/mode")
async def get_mode() -> dict[str, Any]:
    """Report whether game mode is on. Always reachable, on or off."""
    return {
        "enabled": _enabled,
        "state": _engine.state.value,
        "mode": _engine.config.mode.value,
        "players": len(_engine.players),
    }


@router.post("/mode")
async def set_mode(body: ModeToggle) -> dict[str, Any]:
    """Turn game mode on or off. Turning it off wipes the game and its player data."""
    global _enabled  # noqa: PLW0603
    _enabled = body.enabled
    if not body.enabled:
        _engine.reset()
        _photos.clear()
    logger.info("Game mode switched {}", "on" if body.enabled else "off")
    return {"enabled": _enabled}


# ── lobby ──────────────────────────────────────────────────────────────────


class GameSetup(BaseModel):
    mode: GameMode = GameMode.ASSASSIN
    play_window_start: str = "10:00"
    play_window_end: str = "16:00"
    timezone: str = "Europe/Amsterdam"
    safe_zones: list[str] = Field(default_factory=list)
    duration_minutes: int = Field(default=480, ge=5, le=1440)
    immunity_minutes: int = Field(default=5, ge=0, le=120)
    hint_interval_minutes: int = Field(default=10, ge=1, le=240)
    endgame_minutes: int = Field(default=15, ge=0, le=240)


class JoinRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    nickname: str | None = Field(default=None, max_length=80)
    hints: list[str] = Field(default_factory=list, max_length=10)
    secret_mission: str | None = Field(default=None, max_length=280)
    weak_spot: str | None = Field(default=None, max_length=280)


@router.post("/new")
async def new_game(body: GameSetup) -> dict[str, Any]:
    """Start a fresh lobby with these rules, clearing any previous game."""
    engine = _require_enabled()
    engine.reset()
    _photos.clear()
    engine.config = GameConfig(
        mode=body.mode,
        play_window_start=body.play_window_start,
        play_window_end=body.play_window_end,
        timezone=body.timezone,
        safe_zones=body.safe_zones,
        duration_minutes=body.duration_minutes,
        immunity_minutes=body.immunity_minutes,
        hint_interval_minutes=body.hint_interval_minutes,
        endgame_minutes=body.endgame_minutes,
    )
    return engine.public_state()


@router.post("/join")
async def join(body: JoinRequest) -> dict[str, Any]:
    """Join the game yourself. Nobody can be entered by someone else."""
    engine = _require_enabled()
    player = _guard(lambda: engine.join(
        body.name,
        nickname=body.nickname,
        hints=body.hints,
        secret_mission=body.secret_mission,
        weak_spot=body.weak_spot,
    ))
    return player.to_dict(reveal_target=True)


@router.delete("/players/{player_id}")
async def leave(player_id: str) -> dict[str, Any]:
    """Leave the game and have your data removed."""
    engine = _require_enabled()
    _guard(lambda: engine.leave(player_id))
    return {"left": player_id}


@router.post("/start")
async def start() -> dict[str, Any]:
    engine = _require_enabled()
    _guard(engine.start)
    return engine.public_state()


@router.post("/end")
async def end() -> dict[str, Any]:
    engine = _require_enabled()
    engine.end()
    return engine.public_state()


# ── play ───────────────────────────────────────────────────────────────────


class TagClaim(BaseModel):
    tagger_id: str
    target_id: str
    photo_id: str | None = None
    # Attach the frames buffered just before the claim as a killcam
    with_killcam: bool = True


class TagDecision(BaseModel):
    player_id: str


class LocationUpdate(BaseModel):
    zone: str | None = None
    sharing: bool | None = None


class PhotoPost(BaseModel):
    player_id: str
    photo_id: str
    text: str | None = Field(default=None, max_length=280)


@router.post("/tags")
async def claim_tag(body: TagClaim) -> dict[str, Any]:
    """Claim a tag. It waits for the target to confirm before it counts."""
    engine = _require_enabled()
    killcam = _photos.take_killcam(body.tagger_id) if body.with_killcam else []
    tag = _guard(lambda: engine.claim_tag(
        body.tagger_id, body.target_id, photo_id=body.photo_id, killcam=killcam,
    ))
    return tag.to_dict()


@router.post("/tags/{tag_id}/confirm")
async def confirm_tag(tag_id: str, body: TagDecision) -> dict[str, Any]:
    engine = _require_enabled()
    tag = _guard(lambda: engine.confirm_tag(tag_id, body.player_id))
    return tag.to_dict()


@router.post("/tags/{tag_id}/reject")
async def reject_tag(tag_id: str, body: TagDecision) -> dict[str, Any]:
    engine = _require_enabled()
    tag = _guard(lambda: engine.reject_tag(tag_id, body.player_id))
    return tag.to_dict()


@router.post("/players/{player_id}/location")
async def set_location(player_id: str, body: LocationUpdate) -> dict[str, Any]:
    """Share your own coarse zone, or pause sharing. Exact positions are never stored."""
    engine = _require_enabled()
    player = _guard(lambda: engine.set_location(
        player_id, zone=body.zone, sharing=body.sharing,
    ))
    return player.to_dict(reveal_target=True)


@router.get("/players/{player_id}/radar")
async def radar(player_id: str) -> dict[str, Any]:
    engine = _require_enabled()
    return {"proximity": _guard(lambda: engine.radar(player_id)).value}


@router.get("/players/{player_id}/hunters")
async def hunters(player_id: str) -> dict[str, Any]:
    """Spend a spy power-up to see who is hunting you."""
    engine = _require_enabled()
    return {"hunters": _guard(lambda: engine.hunters_of(player_id))}


@router.post("/players/{player_id}/power-ups/{kind}")
async def use_power_up(player_id: str, kind: PowerUp) -> dict[str, Any]:
    engine = _require_enabled()
    player = _guard(lambda: engine.use_power_up(player_id, kind))
    return player.to_dict(reveal_target=True)


@router.post("/players/{player_id}/power-ups/{kind}/award")
async def award_power_up(player_id: str, kind: PowerUp) -> dict[str, Any]:
    engine = _require_enabled()
    player = _guard(lambda: engine.award_power_up(player_id, kind))
    return player.to_dict(reveal_target=True)


@router.post("/players/{player_id}/bingo/{index}")
async def mark_bingo(player_id: str, index: int) -> dict[str, Any]:
    engine = _require_enabled()
    card = _guard(lambda: engine.mark_bingo(player_id, index))
    return {"card": [s.to_dict() for s in card]}


@router.post("/feed")
async def post_photo(body: PhotoPost) -> dict[str, Any]:
    engine = _require_enabled()
    item = _guard(lambda: engine.post_photo(body.player_id, body.photo_id, text=body.text))
    return item.to_dict()


@router.post("/feed/{item_id}/vote")
async def vote(item_id: str, body: TagDecision) -> dict[str, Any]:
    engine = _require_enabled()
    item = _guard(lambda: engine.vote(item_id, body.player_id))
    return item.to_dict()


@router.post("/tick")
async def tick() -> dict[str, Any]:
    """Apply the time-based rules: hint releases, expiries, endgame, game over."""
    engine = _require_enabled()
    return engine.tick()


@router.get("/state")
async def state(player_id: str | None = None) -> dict[str, Any]:
    engine = _require_enabled()
    return engine.public_state(for_player_id=player_id)


@router.get("/scoreboard")
async def scoreboard() -> dict[str, Any]:
    engine = _require_enabled()
    return {"scoreboard": engine.scoreboard()}


# ── photos ─────────────────────────────────────────────────────────────────


class PhotoUpload(BaseModel):
    """A base64 JPEG/PNG, with or without a data: prefix."""

    image: str
    player_id: str | None = None
    killcam: bool = False


def _decode_image(raw: str) -> bytes:
    payload = raw.split(",", 1)[1] if raw.startswith("data:") else raw
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Ongeldige afbeelding") from exc
    if not data:
        raise HTTPException(status_code=400, detail="Lege afbeelding")
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Afbeelding is te groot")
    return data


@router.post("/photos")
async def upload_photo(body: PhotoUpload) -> dict[str, Any]:
    """Store a photo with every face blurred, and return its id.

    Set killcam=true to add it to the player's rolling buffer instead of
    sharing it; those frames are attached to their next tag claim.
    """
    _require_enabled()
    data = _decode_image(body.image)
    try:
        blurred, faces = await blur_faces(data, _detector)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    photo_id = _photos.add(blurred)
    buffered = 0
    if body.killcam and body.player_id:
        buffered = len(_photos.push_killcam(body.player_id, photo_id))
    return {
        "photo_id": photo_id,
        "faces_blurred": faces,
        "killcam_frames": buffered,
    }


@router.get("/photos/{photo_id}")
async def get_photo(photo_id: str) -> Response:
    """Serve a stored photo. Faces were blurred before it was stored."""
    _require_enabled()
    data = _photos.get(photo_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Foto niet gevonden")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )
