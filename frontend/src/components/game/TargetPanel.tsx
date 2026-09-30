"use client";

import { useState } from "react";
import { Crosshair, Eye, EyeOff, Shield, Radar as RadarIcon } from "lucide-react";

import {
  claimTag,
  getHunters,
  setLocation,
  spendPowerUp,
  type GameSnapshot,
  type PowerUp,
} from "@/lib/gameApi";

interface TargetPanelProps {
  snapshot: GameSnapshot;
  playerId: string;
  onChanged: () => void;
}

const RADAR_LABEL: Record<string, string> = {
  warm: "WARM — dichtbij",
  cold: "KOUD — ver weg",
  unknown: "GEEN SIGNAAL",
};

const POWER_UP_LABEL: Record<PowerUp, string> = {
  shield: "SCHILD — blokkeert automatisch de volgende tag",
  disguise: "VERMOMMING — 10 min geen hints of radar over jou",
  spy: "SPION — laat zien wie op jou jaagt",
};

/** Your own hunt: target, radar, released hints and power-ups. */
export function TargetPanel({ snapshot, playerId, onChanged }: TargetPanelProps) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zone, setZone] = useState("");
  const me = snapshot.me;
  const target = snapshot.my_target;

  if (!me) return null;

  async function run(action: () => Promise<unknown>, note?: string) {
    setError(null);
    setMessage(null);
    try {
      await action();
      if (note) setMessage(note);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Actie mislukte");
    }
  }

  return (
    <section
      data-testid="target-panel"
      className="rounded border p-4"
      style={{ borderColor: "rgba(200,214,176,0.15)", background: "rgba(26,32,24,0.85)" }}
    >
      <div className="mb-3 flex items-center gap-2">
        <Crosshair size={16} color="#e74c3c" />
        <h3
          className="text-sm tracking-[0.2em]"
          style={{ fontFamily: "var(--font-heading)", color: "var(--text-primary)" }}
        >
          JOUW JACHT
        </h3>
      </div>

      {target ? (
        <div className="mb-4 rounded px-3 py-3" style={{ background: "rgba(10,13,8,0.5)" }}>
          <p className="text-xs tracking-widest" style={{ color: "var(--text-dim)" }}>
            DOELWIT
          </p>
          <p className="text-lg" style={{ color: "var(--text-primary)", fontFamily: "var(--font-heading)" }}>
            {target.nickname || target.name}
          </p>

          {target.hints.length > 0 && (
            <ul className="mt-2 flex flex-col gap-1">
              {target.hints.map((hint) => (
                <li key={hint.text} className="text-xs" style={{ color: "var(--alert-amber)" }}>
                  → {hint.text}
                </li>
              ))}
            </ul>
          )}

          <div className="mt-3 flex items-center gap-2">
            <RadarIcon size={14} color="#3498db" />
            <span className="text-xs tracking-widest" style={{ color: "var(--text-ui)" }}>
              {RADAR_LABEL[snapshot.radar ?? "unknown"]}
            </span>
          </div>

          <button
            type="button"
            onClick={() =>
              void run(
                () => claimTag(playerId, target.player_id),
                `Claim verstuurd — ${target.nickname || target.name} moet hem bevestigen.`,
              )
            }
            disabled={!snapshot.in_play_window}
            className="mt-3 w-full rounded px-3 py-2 text-xs tracking-[0.2em] disabled:opacity-40"
            style={{ background: "var(--stamp-red)", color: "#f0e8d8", fontFamily: "var(--font-mono)" }}
          >
            {snapshot.in_play_window ? "IK HEB ZE GETAGD" : "BUITEN DE SPEELTIJD"}
          </button>
        </div>
      ) : (
        <p className="mb-4 text-xs" style={{ color: "var(--text-dim)" }}>
          {me.alive ? "Nog geen doelwit." : "Je bent uitgeschakeld."}
        </p>
      )}

      <div className="mb-4">
        <p className="mb-1 text-xs tracking-widest" style={{ color: "var(--text-dim)" }}>
          JOUW LOCATIE — ALLEEN GROF, NOOIT EXACT
        </p>
        <div className="flex gap-2">
          <input
            value={zone}
            onChange={(e) => setZone(e.target.value)}
            placeholder="bijv. verdieping-3"
            className="min-w-0 flex-1 rounded border px-2 py-1.5 text-xs"
            style={{
              background: "rgba(10,13,8,0.7)",
              borderColor: "rgba(200,214,176,0.2)",
              color: "var(--text-primary)",
            }}
          />
          <button
            type="button"
            onClick={() => void run(() => setLocation(playerId, { zone, sharing: true }), "Zone bijgewerkt.")}
            disabled={!zone.trim()}
            className="flex items-center gap-1 rounded px-2.5 py-1.5 text-xs tracking-widest disabled:opacity-40"
            style={{ border: "1px solid rgba(200,214,176,0.25)", color: "var(--text-ui)" }}
          >
            <Eye size={13} /> DELEN
          </button>
          <button
            type="button"
            onClick={() => void run(() => setLocation(playerId, { sharing: false }), "Locatie delen staat uit.")}
            className="flex items-center gap-1 rounded px-2.5 py-1.5 text-xs tracking-widest"
            style={{ border: "1px solid rgba(200,214,176,0.25)", color: "var(--text-ui)" }}
          >
            <EyeOff size={13} /> PAUZE
          </button>
        </div>
        <p className="mt-1 text-[11px]" style={{ color: "var(--text-dim)" }}>
          Nu: {me.sharing_location ? "je deelt je zone" : "je deelt niets"}
        </p>
      </div>

      <div>
        <p className="mb-1 text-xs tracking-widest" style={{ color: "var(--text-dim)" }}>
          POWER-UPS
        </p>
        {me.power_ups.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            Nog geen. Verdien ze met foto-opdrachten.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {me.power_ups.map((kind, index) => (
              <li key={`${kind}-${index}`} className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-ui)" }}>
                  <Shield size={13} color="#d4a017" /> {POWER_UP_LABEL[kind]}
                </span>
                {kind === "disguise" && (
                  <button
                    type="button"
                    onClick={() => void run(() => spendPowerUp(playerId, "disguise"), "Je bent 10 minuten vermomd.")}
                    className="shrink-0 rounded px-2 py-1 text-[11px] tracking-widest"
                    style={{ background: "var(--pin-gold)", color: "#1a1a1a" }}
                  >
                    GEBRUIK
                  </button>
                )}
                {kind === "spy" && (
                  <button
                    type="button"
                    onClick={() =>
                      void run(async () => {
                        const { hunters } = await getHunters(playerId);
                        const names = hunters
                          .map((id) => {
                            const p = snapshot.players.find((x) => x.player_id === id);
                            return p ? p.nickname || p.name : "onbekend";
                          })
                          .join(", ");
                        setMessage(names ? `Op jou jaagt: ${names}` : "Niemand jaagt op jou.");
                      })
                    }
                    className="shrink-0 rounded px-2 py-1 text-[11px] tracking-widest"
                    style={{ background: "var(--pin-gold)", color: "#1a1a1a" }}
                  >
                    GEBRUIK
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {message && (
        <p className="mt-3 text-xs" style={{ color: "var(--intel-green)" }}>
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-xs" style={{ color: "var(--accent-red)" }}>
          {error}
        </p>
      )}
    </section>
  );
}
