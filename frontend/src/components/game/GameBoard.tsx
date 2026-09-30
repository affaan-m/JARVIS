"use client";

import { useMemo, useState } from "react";
import { LogOut, Play } from "lucide-react";

import {
  endGame,
  leave,
  markBingo,
  newGame,
  startGame,
  type GameMode,
} from "@/lib/gameApi";
import { useGame } from "@/lib/useGame";

import { GameFeed } from "./GameFeed";
import { GameScoreboard } from "./GameScoreboard";
import { GameToggle } from "./GameToggle";
import { JoinForm } from "./JoinForm";
import { PendingTags } from "./PendingTags";
import { PhotoCapture } from "./PhotoCapture";
import { TargetPanel } from "./TargetPanel";

const MODES: { value: GameMode; label: string }[] = [
  { value: "assassin", label: "ASSASSIN" },
  { value: "hunters", label: "HUNTERS VS RUNNERS" },
  { value: "king", label: "KONING VAN DE HEUVEL" },
  { value: "bingo", label: "FOTO-BINGO" },
];

/** The whole game screen: the switch, the lobby and the live board. */
export function GameBoard() {
  const { enabled, snapshot, playerId, error, loading, setPlayerId, refresh } = useGame();
  const [mode, setMode] = useState<GameMode>("assassin");
  const [safeZones, setSafeZones] = useState("toilet, vergaderruimte");
  const [windowStart, setWindowStart] = useState("10:00");
  const [windowEnd, setWindowEnd] = useState("16:00");
  const [actionError, setActionError] = useState<string | null>(null);

  const playerNames = useMemo(() => {
    const names: Record<string, string> = {};
    for (const player of snapshot?.players ?? []) {
      names[player.player_id] = player.nickname || player.name;
    }
    return names;
  }, [snapshot?.players]);

  async function run(action: () => Promise<unknown>) {
    setActionError(null);
    try {
      await action();
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Actie mislukte");
    }
  }

  if (loading) {
    return (
      <p className="p-6 text-sm" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
        LADEN...
      </p>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1
            className="text-2xl tracking-[0.18em]"
            style={{ fontFamily: "var(--font-heading)", color: "var(--text-primary)" }}
          >
            HUNTERS GAME
          </h1>
          <p className="text-xs" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
            Alleen voor collega&apos;s die zich zelf aanmelden.
          </p>
        </div>
        <GameToggle
          enabled={enabled === true}
          playerCount={snapshot?.players.length ?? 0}
          onChanged={() => void refresh()}
        />
      </header>

      {error && (
        <p role="alert" className="text-xs" style={{ color: "var(--accent-red)" }}>
          Backend onbereikbaar: {error}
        </p>
      )}
      {actionError && (
        <p role="alert" className="text-xs" style={{ color: "var(--accent-red)" }}>
          {actionError}
        </p>
      )}

      {enabled !== true && (
        <p
          data-testid="game-off-notice"
          className="rounded border p-4 text-sm"
          style={{
            borderColor: "rgba(200,214,176,0.15)",
            background: "rgba(26,32,24,0.85)",
            color: "var(--text-dim)",
            fontFamily: "var(--font-mono)",
          }}
        >
          Spelmodus staat uit. JARVIS werkt normaal verder. Zet de schakelaar aan om te spelen.
        </p>
      )}

      {enabled === true && snapshot && (
        <>
          <section
            className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded border px-4 py-3 text-xs"
            style={{
              borderColor: "rgba(200,214,176,0.15)",
              background: "rgba(26,32,24,0.85)",
              fontFamily: "var(--font-mono)",
              color: "var(--text-ui)",
            }}
          >
            <span>SPEL: {snapshot.config.mode.toUpperCase()}</span>
            <span>STATUS: {snapshot.state.toUpperCase()}</span>
            <span>SPELERS: {snapshot.players.length}</span>
            <span style={{ color: snapshot.in_play_window ? "var(--intel-green)" : "var(--alert-amber)" }}>
              {snapshot.in_play_window ? "BINNEN SPEELTIJD" : "BUITEN SPEELTIJD"}
              {" "}({snapshot.config.play_window_start}–{snapshot.config.play_window_end}{" "}
              {snapshot.config.timezone})
            </span>
            {snapshot.endgame && <span style={{ color: "var(--string-red)" }}>EINDFASE — DUBBELE PUNTEN</span>}
          </section>

          {snapshot.state === "lobby" && (
            <section
              className="rounded border p-4"
              style={{ borderColor: "rgba(200,214,176,0.15)", background: "rgba(26,32,24,0.85)" }}
            >
              <h3
                className="mb-3 text-sm tracking-[0.2em]"
                style={{ fontFamily: "var(--font-heading)", color: "var(--text-primary)" }}
              >
                SPELREGELS
              </h3>
              <div className="flex flex-wrap items-end gap-3 text-xs" style={{ color: "var(--text-dim)" }}>
                <label className="flex flex-col gap-1">
                  SPELVORM
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value as GameMode)}
                    className="rounded border px-2 py-1.5"
                    style={{
                      background: "rgba(10,13,8,0.7)",
                      borderColor: "rgba(200,214,176,0.2)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {MODES.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  SPEELTIJD VAN
                  <input
                    type="time"
                    value={windowStart}
                    onChange={(e) => setWindowStart(e.target.value)}
                    className="rounded border px-2 py-1.5"
                    style={{
                      background: "rgba(10,13,8,0.7)",
                      borderColor: "rgba(200,214,176,0.2)",
                      color: "var(--text-primary)",
                    }}
                  />
                </label>
                <label className="flex flex-col gap-1">
                  TOT
                  <input
                    type="time"
                    value={windowEnd}
                    onChange={(e) => setWindowEnd(e.target.value)}
                    className="rounded border px-2 py-1.5"
                    style={{
                      background: "rgba(10,13,8,0.7)",
                      borderColor: "rgba(200,214,176,0.2)",
                      color: "var(--text-primary)",
                    }}
                  />
                </label>
                <label className="flex min-w-[200px] flex-1 flex-col gap-1">
                  SAFE ZONES — KOMMAGESCHEIDEN
                  <input
                    value={safeZones}
                    onChange={(e) => setSafeZones(e.target.value)}
                    className="rounded border px-2 py-1.5"
                    style={{
                      background: "rgba(10,13,8,0.7)",
                      borderColor: "rgba(200,214,176,0.2)",
                      color: "var(--text-primary)",
                    }}
                  />
                </label>
                <button
                  type="button"
                  onClick={() =>
                    void run(() =>
                      newGame({
                        mode,
                        play_window_start: windowStart,
                        play_window_end: windowEnd,
                        safe_zones: safeZones
                          .split(",")
                          .map((z) => z.trim())
                          .filter(Boolean),
                      }),
                    )
                  }
                  className="rounded px-3 py-2 tracking-widest"
                  style={{ border: "1px solid rgba(200,214,176,0.25)", color: "var(--text-ui)" }}
                >
                  REGELS TOEPASSEN
                </button>
              </div>
              <p className="mt-2 text-[11px]" style={{ color: "var(--text-dim)" }}>
                Let op: regels toepassen start een nieuwe lobby en verwijdert de huidige spelers.
              </p>
            </section>
          )}

          {!snapshot.me && snapshot.state !== "ended" && (
            <JoinForm onJoined={(id) => { setPlayerId(id); void refresh(); }} />
          )}

          {snapshot.state === "lobby" && snapshot.players.length >= 2 && (
            <button
              type="button"
              onClick={() => void run(startGame)}
              className="flex items-center justify-center gap-2 rounded px-4 py-2.5 text-sm tracking-[0.2em]"
              style={{ background: "var(--intel-green)", color: "#f0f4e8", fontFamily: "var(--font-mono)" }}
            >
              <Play size={15} /> START HET SPEL
            </button>
          )}

          {snapshot.winner_id && (
            <p
              className="rounded border px-4 py-3 text-center text-sm tracking-[0.2em]"
              style={{
                borderColor: "rgba(212,160,23,0.5)",
                background: "rgba(212,160,23,0.12)",
                color: "var(--pin-gold)",
                fontFamily: "var(--font-heading)",
              }}
            >
              WINNAAR: {playerNames[snapshot.winner_id] ?? "onbekend"}
            </p>
          )}

          {playerId && snapshot.pending_tags.length > 0 && (
            <PendingTags
              tags={snapshot.pending_tags}
              playerId={playerId}
              playerNames={playerNames}
              onResolved={() => void refresh()}
            />
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="flex flex-col gap-4">
              {playerId && snapshot.me && snapshot.state === "running" && (
                <TargetPanel
                  snapshot={snapshot}
                  playerId={playerId}
                  onChanged={() => void refresh()}
                />
              )}

              {snapshot.bingo_card.length > 0 && playerId && (
                <section
                  data-testid="bingo-card"
                  className="rounded border p-4"
                  style={{ borderColor: "rgba(200,214,176,0.15)", background: "rgba(26,32,24,0.85)" }}
                >
                  <h3
                    className="mb-2 text-sm tracking-[0.2em]"
                    style={{ fontFamily: "var(--font-heading)", color: "var(--text-primary)" }}
                  >
                    JOUW BINGOKAART
                  </h3>
                  <ul className="flex flex-col gap-1.5">
                    {snapshot.bingo_card.map((square, index) => (
                      <li key={square.text}>
                        <button
                          type="button"
                          disabled={square.done}
                          onClick={() => void run(() => markBingo(playerId, index))}
                          className="w-full rounded px-2.5 py-1.5 text-left text-xs disabled:opacity-50"
                          style={{
                            background: square.done ? "rgba(74,124,63,0.18)" : "rgba(10,13,8,0.5)",
                            color: "var(--text-ui)",
                            textDecoration: square.done ? "line-through" : "none",
                          }}
                        >
                          {square.done ? "✓ " : "□ "}
                          {square.text}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {playerId && snapshot.me && snapshot.state === "running" && (
                <PhotoCapture
                  playerId={playerId}
                  hunting={Boolean(snapshot.my_target)}
                  onPosted={() => void refresh()}
                />
              )}

              <GameScoreboard
                scoreboard={snapshot.scoreboard}
                kingId={snapshot.king_id}
                winnerId={snapshot.winner_id}
                myPlayerId={playerId}
              />
            </div>

            <GameFeed
              feed={snapshot.feed}
              playerId={playerId}
              playerNames={playerNames}
              onVoted={() => void refresh()}
            />
          </div>

          <footer className="flex flex-wrap gap-3">
            {playerId && snapshot.me && (
              <button
                type="button"
                onClick={() =>
                  void run(async () => {
                    await leave(playerId);
                    setPlayerId(null);
                  })
                }
                className="flex items-center gap-2 rounded px-3 py-2 text-xs tracking-widest"
                style={{ border: "1px solid rgba(192,57,43,0.5)", color: "var(--accent-red)" }}
              >
                <LogOut size={13} /> UIT HET SPEL STAPPEN
              </button>
            )}
            {snapshot.state === "running" && (
              <button
                type="button"
                onClick={() => void run(endGame)}
                className="rounded px-3 py-2 text-xs tracking-widest"
                style={{ border: "1px solid rgba(200,214,176,0.25)", color: "var(--text-ui)" }}
              >
                SPEL BEËINDIGEN
              </button>
            )}
          </footer>
        </>
      )}
    </div>
  );
}
