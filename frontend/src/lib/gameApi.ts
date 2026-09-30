// Client for the opt-in hunters game (backend/game). Every route except
// /api/game/mode returns 404 while game mode is switched off.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type GameMode = "assassin" | "hunters" | "king" | "bingo";
export type GameState = "lobby" | "running" | "ended";
export type Proximity = "warm" | "cold" | "unknown";
export type PowerUp = "shield" | "disguise" | "spy";
export type TagStatus = "pending" | "confirmed" | "rejected" | "expired";

export interface Hint {
  text: string;
  released: boolean;
  released_at: string | null;
}

export interface Player {
  player_id: string;
  name: string;
  nickname: string | null;
  secret_mission: string | null;
  weak_spot: string | null;
  alive: boolean;
  team: "hunter" | "runner" | "none";
  points: number;
  tags_made: number;
  power_ups: PowerUp[];
  sharing_location: boolean;
  hints: Hint[];
  immune_until: string | null;
  joined_at: string | null;
  /** Only ever present on your own record. */
  target_id?: string;
}

export interface Tag {
  tag_id: string;
  tagger_id: string;
  target_id: string;
  status: TagStatus;
  photo_id: string | null;
  /** Frames buffered just before the claim, shown as the killcam. */
  killcam: string[];
  points_awarded: number;
  reason: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface UploadedPhoto {
  photo_id: string;
  faces_blurred: number;
  killcam_frames: number;
}

export interface FeedItem {
  item_id: string;
  kind: "photo" | "tag" | "hint" | "system";
  author_id: string | null;
  text: string | null;
  photo_id: string | null;
  votes: number;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface ScoreRow {
  rank: number;
  player_id: string;
  name: string;
  points: number;
  tags_made: number;
  alive: boolean;
}

export interface GameConfig {
  mode: GameMode;
  play_window_start: string;
  play_window_end: string;
  timezone: string;
  safe_zones: string[];
  immunity_minutes: number;
  hint_interval_minutes: number;
  endgame_minutes: number;
  endgame_multiplier: number;
  points_per_tag: number;
  duration_minutes: number;
}

export interface BingoSquare {
  text: string;
  done: boolean;
}

export interface GameSnapshot {
  game_id: string;
  state: GameState;
  config: GameConfig;
  started_at: string | null;
  ends_at: string | null;
  endgame: boolean;
  in_play_window: boolean;
  king_id: string | null;
  winner_id: string | null;
  players: Player[];
  me: Player | null;
  my_target: Player | null;
  radar: Proximity | null;
  bingo_card: BingoSquare[];
  pending_tags: Tag[];
  feed: FeedItem[];
  scoreboard: ScoreRow[];
}

export interface ModeStatus {
  enabled: boolean;
  state: GameState;
  mode: GameMode;
  players: number;
}

export class GameOffError extends Error {
  constructor() {
    super("Spelmodus staat uit");
    this.name = "GameOffError";
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api/game${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (res.status === 404) throw new GameOffError();
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      /* keep the status text */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body?: unknown): Promise<T> =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

// ── the on/off switch ──

export const getMode = (): Promise<ModeStatus> => call<ModeStatus>("/mode");

export const setMode = (enabled: boolean): Promise<{ enabled: boolean }> =>
  post("/mode", { enabled });

// ── lobby ──

export interface NewGameOptions {
  mode?: GameMode;
  play_window_start?: string;
  play_window_end?: string;
  timezone?: string;
  safe_zones?: string[];
  duration_minutes?: number;
  immunity_minutes?: number;
  hint_interval_minutes?: number;
  endgame_minutes?: number;
}

export const newGame = (options: NewGameOptions): Promise<GameSnapshot> =>
  post("/new", options);

export interface JoinOptions {
  name: string;
  nickname?: string;
  hints?: string[];
  secret_mission?: string;
  weak_spot?: string;
}

export const join = (options: JoinOptions): Promise<Player> => post("/join", options);

export const leave = (playerId: string): Promise<{ left: string }> =>
  call(`/players/${playerId}`, { method: "DELETE" });

export const startGame = (): Promise<GameSnapshot> => post("/start");
export const endGame = (): Promise<GameSnapshot> => post("/end");

// ── play ──

export const getState = (playerId?: string): Promise<GameSnapshot> =>
  call<GameSnapshot>(`/state${playerId ? `?player_id=${encodeURIComponent(playerId)}` : ""}`);

export const claimTag = (
  taggerId: string,
  targetId: string,
  photoId?: string,
): Promise<Tag> =>
  post("/tags", { tagger_id: taggerId, target_id: targetId, photo_id: photoId ?? null });

export const confirmTag = (tagId: string, playerId: string): Promise<Tag> =>
  post(`/tags/${tagId}/confirm`, { player_id: playerId });

export const rejectTag = (tagId: string, playerId: string): Promise<Tag> =>
  post(`/tags/${tagId}/reject`, { player_id: playerId });

export const setLocation = (
  playerId: string,
  update: { zone?: string | null; sharing?: boolean },
): Promise<Player> => post(`/players/${playerId}/location`, update);

export const getRadar = (playerId: string): Promise<{ proximity: Proximity }> =>
  call(`/players/${playerId}/radar`);

export const getHunters = (playerId: string): Promise<{ hunters: string[] }> =>
  call(`/players/${playerId}/hunters`);

export const spendPowerUp = (playerId: string, kind: PowerUp): Promise<Player> =>
  post(`/players/${playerId}/power-ups/${kind}`);

export const markBingo = (
  playerId: string,
  index: number,
): Promise<{ card: BingoSquare[] }> => post(`/players/${playerId}/bingo/${index}`);

export const postPhoto = (
  playerId: string,
  photoId: string,
  text?: string,
): Promise<FeedItem> =>
  post("/feed", { player_id: playerId, photo_id: photoId, text: text ?? null });

export const voteFeedItem = (itemId: string, playerId: string): Promise<FeedItem> =>
  post(`/feed/${itemId}/vote`, { player_id: playerId });

/** Upload a photo. Every face is blurred server-side before it is stored. */
export const uploadPhoto = (
  imageBase64: string,
  options: { playerId?: string; killcam?: boolean } = {},
): Promise<UploadedPhoto> =>
  post("/photos", {
    image: imageBase64,
    player_id: options.playerId ?? null,
    killcam: options.killcam ?? false,
  });

export const photoUrl = (photoId: string): string =>
  `${API_BASE}/api/game/photos/${photoId}`;

export const tick = (): Promise<{ released_hints: string[]; expired_tags: string[] }> =>
  post("/tick");
