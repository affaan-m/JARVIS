"use client";

import { Crown, Skull } from "lucide-react";

import type { ScoreRow } from "@/lib/gameApi";

interface GameScoreboardProps {
  scoreboard: ScoreRow[];
  kingId: string | null;
  winnerId: string | null;
  myPlayerId: string | null;
}

export function GameScoreboard({
  scoreboard,
  kingId,
  winnerId,
  myPlayerId,
}: GameScoreboardProps) {
  return (
    <section
      data-testid="game-scoreboard"
      className="rounded border p-4"
      style={{ borderColor: "rgba(200,214,176,0.15)", background: "rgba(26,32,24,0.85)" }}
    >
      <h3
        className="mb-3 text-sm tracking-[0.2em]"
        style={{ fontFamily: "var(--font-heading)", color: "var(--text-primary)" }}
      >
        SCOREBORD
      </h3>

      {scoreboard.length === 0 ? (
        <p className="text-xs" style={{ color: "var(--text-dim)" }}>
          Nog geen spelers.
        </p>
      ) : (
        <ol className="flex flex-col gap-1.5">
          {scoreboard.map((row) => (
            <li
              key={row.player_id}
              className="flex items-center justify-between gap-2 rounded px-2.5 py-1.5"
              style={{
                background:
                  row.player_id === myPlayerId ? "rgba(74,124,63,0.16)" : "rgba(10,13,8,0.5)",
              }}
            >
              <span className="flex min-w-0 items-center gap-2">
                <span
                  className="w-5 shrink-0 text-xs"
                  style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}
                >
                  {row.rank}.
                </span>
                <span
                  className="truncate text-sm"
                  style={{
                    color: row.alive ? "var(--text-primary)" : "var(--text-dim)",
                    textDecoration: row.alive ? "none" : "line-through",
                  }}
                >
                  {row.name}
                </span>
                {row.player_id === winnerId && <Crown size={13} color="#d4a017" />}
                {row.player_id === kingId && row.player_id !== winnerId && (
                  <Crown size={13} color="#f39c12" />
                )}
                {!row.alive && <Skull size={13} color="#6b7a58" />}
              </span>
              <span className="flex shrink-0 items-baseline gap-2">
                <span className="text-sm" style={{ color: "var(--pin-gold)", fontFamily: "var(--font-mono)" }}>
                  {row.points}
                </span>
                <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
                  {row.tags_made}×
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
