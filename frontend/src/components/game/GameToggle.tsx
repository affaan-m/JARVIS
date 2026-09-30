"use client";

import { useState } from "react";
import { Power } from "lucide-react";

import { setMode } from "@/lib/gameApi";

interface GameToggleProps {
  enabled: boolean;
  playerCount: number;
  onChanged: () => void;
}

/** The single switch for game mode. Off wipes the game and all player data. */
export function GameToggle({ enabled, playerCount, onChanged }: GameToggleProps) {
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function apply(next: boolean) {
    setBusy(true);
    try {
      await setMode(next);
      onChanged();
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  function handleClick() {
    // Switching off deletes everything, so ask when there is something to lose
    if (enabled && playerCount > 0 && !confirming) {
      setConfirming(true);
      return;
    }
    void apply(!enabled);
  }

  return (
    <div data-testid="game-toggle" className="flex flex-col gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={busy}
        aria-pressed={enabled}
        className="flex items-center gap-3 rounded border px-4 py-2.5 transition-colors disabled:opacity-50"
        style={{
          borderColor: enabled ? "rgba(74,124,63,0.6)" : "rgba(200,214,176,0.2)",
          background: enabled ? "rgba(74,124,63,0.14)" : "rgba(26,32,24,0.8)",
          color: "var(--text-ui)",
          fontFamily: "var(--font-mono)",
        }}
      >
        <Power size={15} color={enabled ? "#4a7c3f" : "#6b7a58"} />
        <span className="text-xs tracking-[0.22em]">
          SPELMODUS {enabled ? "AAN" : "UIT"}
        </span>
      </button>

      {confirming && (
        <div
          className="rounded border px-3 py-2 text-xs"
          style={{
            borderColor: "rgba(192,57,43,0.5)",
            background: "rgba(192,57,43,0.1)",
            color: "var(--text-ui)",
            fontFamily: "var(--font-mono)",
          }}
        >
          <p className="mb-2">
            Uitzetten verwijdert het spel en alle {playerCount} spelers. Doorgaan?
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void apply(false)}
              className="rounded px-2 py-1 tracking-widest"
              style={{ background: "var(--stamp-red)", color: "#f0e8d8" }}
            >
              UITZETTEN
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded px-2 py-1 tracking-widest"
              style={{ border: "1px solid rgba(200,214,176,0.25)" }}
            >
              ANNULEREN
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
