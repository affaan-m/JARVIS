import "@/test/mocks";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { GameFeed } from "../GameFeed";
import type { FeedItem } from "@/lib/gameApi";

const voteFeedItem = vi.hoisted(() => vi.fn());

vi.mock("@/lib/gameApi", async () => {
  const actual = await vi.importActual<typeof import("@/lib/gameApi")>("@/lib/gameApi");
  return { ...actual, voteFeedItem };
});

function item(overrides: Partial<FeedItem> = {}): FeedItem {
  return {
    item_id: "f1",
    kind: "photo",
    author_id: "p1",
    text: "bij de koffie",
    photo_id: null,
    votes: 0,
    meta: {},
    created_at: "2026-06-01T12:00:00+00:00",
    ...overrides,
  };
}

const names = { p1: "Jamal", p2: "Sam" };

describe("GameFeed photos", () => {
  it("renders a shared photo with a blur note in the alt text", () => {
    render(
      <GameFeed feed={[item({ photo_id: "ph_1" })]} playerId="p2" playerNames={names} onVoted={vi.fn()} />,
    );

    const img = screen.getByAltText(/gezichten vervaagd/i);
    expect(img).toHaveAttribute("src", expect.stringContaining("/api/game/photos/ph_1"));
  });

  it("renders the killcam strip on a tag broadcast", () => {
    render(
      <GameFeed
        feed={[
          item({
            item_id: "f2",
            kind: "tag",
            text: "Jamal tagde Sam",
            meta: { points: 100, endgame: false, killcam: ["ph_a", "ph_b", "ph_c"] },
          }),
        ]}
        playerId="p2"
        playerNames={names}
        onVoted={vi.fn()}
      />,
    );

    expect(screen.getByText("KILLCAM")).toBeInTheDocument();
    expect(screen.getAllByAltText(/Killcam-beeld/)).toHaveLength(3);
  });

  it("shows no killcam strip when there are no frames", () => {
    render(
      <GameFeed
        feed={[item({ kind: "tag", meta: { points: 100, killcam: [] } })]}
        playerId="p2"
        playerNames={names}
        onVoted={vi.fn()}
      />,
    );

    expect(screen.queryByText("KILLCAM")).not.toBeInTheDocument();
  });

  it("ignores a malformed killcam value instead of crashing", () => {
    render(
      <GameFeed
        feed={[item({ kind: "tag", meta: { killcam: "not-an-array" } })]}
        playerId="p2"
        playerNames={names}
        onVoted={vi.fn()}
      />,
    );

    expect(screen.queryByText("KILLCAM")).not.toBeInTheDocument();
  });

  it("lets a player vote on a photo", async () => {
    voteFeedItem.mockResolvedValue(item({ votes: 1 }));
    const onVoted = vi.fn();
    render(
      <GameFeed feed={[item({ photo_id: "ph_1" })]} playerId="p2" playerNames={names} onVoted={onVoted} />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Stem op deze foto/ }));

    expect(voteFeedItem).toHaveBeenCalledWith("f1", "p2");
  });

  it("offers no vote button to someone who has not joined", () => {
    render(
      <GameFeed feed={[item({ photo_id: "ph_1" })]} playerId={null} playerNames={names} onVoted={vi.fn()} />,
    );

    expect(screen.queryByRole("button", { name: /Stem op deze foto/ })).not.toBeInTheDocument();
  });
});
