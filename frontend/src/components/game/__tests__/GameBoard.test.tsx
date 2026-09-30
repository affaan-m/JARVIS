import "@/test/mocks";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GameBoard } from "../GameBoard";
import type { GameSnapshot, ModeStatus } from "@/lib/gameApi";

const mode = vi.hoisted(() => ({ current: { enabled: false } as ModeStatus }));
const snapshot = vi.hoisted(() => ({ current: null as GameSnapshot | null }));
const calls = vi.hoisted(() => ({ setMode: vi.fn(), join: vi.fn(), confirmTag: vi.fn() }));

vi.mock("@/lib/gameApi", async () => {
  const actual = await vi.importActual<typeof import("@/lib/gameApi")>("@/lib/gameApi");
  return {
    ...actual,
    getMode: vi.fn(async () => mode.current),
    getState: vi.fn(async () => {
      if (!snapshot.current) throw new actual.GameOffError();
      return snapshot.current;
    }),
    tick: vi.fn(async () => ({ released_hints: [], expired_tags: [] })),
    setMode: calls.setMode,
    join: calls.join,
    confirmTag: calls.confirmTag,
    rejectTag: vi.fn(),
  };
});

function makeSnapshot(overrides: Partial<GameSnapshot> = {}): GameSnapshot {
  return {
    game_id: "game_1",
    state: "lobby",
    config: {
      mode: "assassin",
      play_window_start: "10:00",
      play_window_end: "16:00",
      timezone: "Europe/Amsterdam",
      safe_zones: ["toilet"],
      immunity_minutes: 5,
      hint_interval_minutes: 10,
      endgame_minutes: 15,
      endgame_multiplier: 2,
      points_per_tag: 100,
      duration_minutes: 480,
    },
    started_at: null,
    ends_at: null,
    endgame: false,
    in_play_window: true,
    king_id: null,
    winner_id: null,
    players: [],
    me: null,
    my_target: null,
    radar: null,
    bingo_card: [],
    pending_tags: [],
    feed: [],
    scoreboard: [],
    ...overrides,
  };
}

const player = (id: string, name: string) => ({
  player_id: id,
  name,
  nickname: null,
  secret_mission: null,
  weak_spot: null,
  alive: true,
  team: "none" as const,
  points: 0,
  tags_made: 0,
  power_ups: [],
  sharing_location: false,
  hints: [],
  immune_until: null,
  joined_at: null,
});

beforeEach(() => {
  mode.current = { enabled: false, state: "lobby", mode: "assassin", players: 0 };
  snapshot.current = null;
  window.localStorage.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("GameBoard toggle", () => {
  it("shows the off notice and no join form while game mode is off", async () => {
    render(<GameBoard />);

    expect(await screen.findByTestId("game-off-notice")).toBeInTheDocument();
    expect(screen.queryByTestId("join-form")).not.toBeInTheDocument();
  });

  it("renders the switch as off", async () => {
    render(<GameBoard />);

    const toggle = await screen.findByRole("button", { name: /SPELMODUS UIT/ });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
  });

  it("turns game mode on when the switch is used", async () => {
    calls.setMode.mockResolvedValue({ enabled: true });
    render(<GameBoard />);
    const toggle = await screen.findByRole("button", { name: /SPELMODUS UIT/ });

    await userEvent.click(toggle);

    expect(calls.setMode).toHaveBeenCalledWith(true);
  });

  it("asks before switching off while players are in the game", async () => {
    mode.current = { enabled: true, state: "lobby", mode: "assassin", players: 2 };
    snapshot.current = makeSnapshot({
      players: [player("p1", "Jamal"), player("p2", "Sam")],
    });
    render(<GameBoard />);

    await userEvent.click(await screen.findByRole("button", { name: /SPELMODUS AAN/ }));

    expect(screen.getByText(/verwijdert het spel en alle 2 spelers/)).toBeInTheDocument();
    expect(calls.setMode).not.toHaveBeenCalled();

    calls.setMode.mockResolvedValue({ enabled: false });
    await userEvent.click(screen.getByRole("button", { name: "UITZETTEN" }));
    expect(calls.setMode).toHaveBeenCalledWith(false);
  });
});

describe("GameBoard lobby and play", () => {
  beforeEach(() => {
    mode.current = { enabled: true, state: "lobby", mode: "assassin", players: 0 };
  });

  it("offers the join form when you are not in the game yet", async () => {
    snapshot.current = makeSnapshot();
    render(<GameBoard />);

    expect(await screen.findByTestId("join-form")).toBeInTheDocument();
  });

  it("lets a player join themselves", async () => {
    snapshot.current = makeSnapshot();
    calls.join.mockResolvedValue(player("p9", "Jamal"));
    render(<GameBoard />);

    await userEvent.type(await screen.findByLabelText("NAAM *"), "Jamal");
    await userEvent.click(screen.getByRole("button", { name: "MEEDOEN" }));

    await waitFor(() =>
      expect(calls.join).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Jamal" }),
      ),
    );
  });

  it("shows the play window with its timezone", async () => {
    snapshot.current = makeSnapshot();
    render(<GameBoard />);

    expect(await screen.findByText(/10:00–16:00 Europe\/Amsterdam/)).toBeInTheDocument();
  });

  it("offers no start button with a single player", async () => {
    snapshot.current = makeSnapshot({ players: [player("p1", "Jamal")] });
    render(<GameBoard />);

    await screen.findByTestId("join-form");
    expect(screen.queryByRole("button", { name: /START HET SPEL/ })).not.toBeInTheDocument();
  });

  it("offers a start button once two players joined", async () => {
    snapshot.current = makeSnapshot({
      players: [player("p1", "Jamal"), player("p2", "Sam")],
    });
    render(<GameBoard />);

    expect(await screen.findByRole("button", { name: /START HET SPEL/ })).toBeInTheDocument();
  });

  it("asks the tagged player to confirm, and nobody else", async () => {
    window.localStorage.setItem("jarvis.game.playerId", "p2");
    snapshot.current = makeSnapshot({
      state: "running",
      players: [player("p1", "Jamal"), player("p2", "Sam")],
      me: { ...player("p2", "Sam"), target_id: "p1" },
      pending_tags: [
        {
          tag_id: "t1",
          tagger_id: "p1",
          target_id: "p2",
          status: "pending",
          photo_id: null,
          killcam: [],
          points_awarded: 0,
          reason: null,
          created_at: "2026-06-01T12:00:00+00:00",
          resolved_at: null,
        },
      ],
    });
    calls.confirmTag.mockResolvedValue({ status: "confirmed" });
    render(<GameBoard />);

    expect(await screen.findByTestId("pending-tags")).toBeInTheDocument();
    expect(screen.getByText(/Jamal zegt je getagd te hebben/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Tag bevestigen" }));

    expect(calls.confirmTag).toHaveBeenCalledWith("t1", "p2");
  });

  it("shows the scoreboard and the winner", async () => {
    snapshot.current = makeSnapshot({
      state: "ended",
      winner_id: "p1",
      players: [player("p1", "Jamal"), player("p2", "Sam")],
      scoreboard: [
        { rank: 1, player_id: "p1", name: "Jamal", points: 200, tags_made: 2, alive: true },
        { rank: 2, player_id: "p2", name: "Sam", points: 0, tags_made: 0, alive: false },
      ],
    });
    render(<GameBoard />);

    expect(await screen.findByTestId("game-scoreboard")).toBeInTheDocument();
    expect(screen.getByText(/WINNAAR: Jamal/)).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
  });

  it("renders the radar as warm or cold, never a location", async () => {
    window.localStorage.setItem("jarvis.game.playerId", "p1");
    snapshot.current = makeSnapshot({
      state: "running",
      players: [player("p1", "Jamal"), player("p2", "Sam")],
      me: { ...player("p1", "Jamal"), target_id: "p2" },
      my_target: { ...player("p2", "Sam"), hints: [
        { text: "ik zit op 3", released: true, released_at: null },
      ] },
      radar: "warm",
    });
    render(<GameBoard />);

    expect(await screen.findByTestId("target-panel")).toBeInTheDocument();
    expect(screen.getByText(/WARM — dichtbij/)).toBeInTheDocument();
    expect(screen.getByText(/ik zit op 3/)).toBeInTheDocument();
  });

  it("shows the feed with a tag broadcast", async () => {
    snapshot.current = makeSnapshot({
      state: "running",
      players: [player("p1", "Jamal"), player("p2", "Sam")],
      feed: [
        {
          item_id: "f1",
          kind: "tag",
          author_id: "p1",
          text: "Jamal tagde Sam",
          photo_id: null,
          votes: 0,
          meta: { points: 100, endgame: false },
          created_at: "2026-06-01T12:00:00+00:00",
        },
      ],
    });
    render(<GameBoard />);

    expect(await screen.findByTestId("game-feed")).toBeInTheDocument();
    expect(screen.getByText("ELIMINATED")).toBeInTheDocument();
    expect(screen.getByText("Jamal tagde Sam")).toBeInTheDocument();
    expect(screen.getByText(/\+100 punten/)).toBeInTheDocument();
  });
});
