"use client";

import { useState } from "react";

import { join } from "@/lib/gameApi";

interface JoinFormProps {
  onJoined: (playerId: string) => void;
}

const inputStyle = {
  background: "rgba(10,13,8,0.7)",
  borderColor: "rgba(200,214,176,0.2)",
  color: "var(--text-primary)",
  fontFamily: "var(--font-mono)",
} as const;

/** Players enter themselves — there is no way to add someone else. */
export function JoinForm({ onJoined }: JoinFormProps) {
  const [name, setName] = useState("");
  const [nickname, setNickname] = useState("");
  const [hints, setHints] = useState("");
  const [mission, setMission] = useState("");
  const [weakSpot, setWeakSpot] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const player = await join({
        name: name.trim(),
        nickname: nickname.trim() || undefined,
        hints: hints
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean)
          .slice(0, 10),
        secret_mission: mission.trim() || undefined,
        weak_spot: weakSpot.trim() || undefined,
      });
      onJoined(player.player_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Meedoen mislukte");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      data-testid="join-form"
      onSubmit={submit}
      className="mx-auto w-full max-w-md rounded border p-5"
      style={{ borderColor: "rgba(200,214,176,0.15)", background: "rgba(26,32,24,0.85)" }}
    >
      <h2
        className="mb-1 text-lg tracking-[0.2em]"
        style={{ fontFamily: "var(--font-heading)", color: "var(--text-primary)" }}
      >
        MELD JEZELF AAN
      </h2>
      <p className="mb-4 text-xs" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
        Alleen jij kunt jezelf aanmelden. Je kunt er op elk moment weer uit stappen.
      </p>

      <label className="mb-3 block">
        <span className="mb-1 block text-xs tracking-widest" style={{ color: "var(--text-dim)" }}>
          NAAM *
        </span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={80}
          className="w-full rounded border px-3 py-2 text-sm"
          style={inputStyle}
        />
      </label>

      <label className="mb-3 block">
        <span className="mb-1 block text-xs tracking-widest" style={{ color: "var(--text-dim)" }}>
          BIJNAAM
        </span>
        <input
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          maxLength={80}
          className="w-full rounded border px-3 py-2 text-sm"
          style={inputStyle}
        />
      </label>

      <label className="mb-3 block">
        <span className="mb-1 block text-xs tracking-widest" style={{ color: "var(--text-dim)" }}>
          HINTS OVER JEZELF — ÉÉN PER REGEL
        </span>
        <textarea
          value={hints}
          onChange={(e) => setHints(e.target.value)}
          rows={3}
          placeholder={"ik zit meestal op de 3e\nik drink alleen thee"}
          className="w-full rounded border px-3 py-2 text-sm"
          style={inputStyle}
        />
        <span className="mt-1 block text-[11px]" style={{ color: "var(--text-dim)" }}>
          Deze komen pas vrij als je jager je lang niet vindt.
        </span>
      </label>

      <label className="mb-3 block">
        <span className="mb-1 block text-xs tracking-widest" style={{ color: "var(--text-dim)" }}>
          GEHEIME MISSIE
        </span>
        <input
          value={mission}
          onChange={(e) => setMission(e.target.value)}
          maxLength={280}
          className="w-full rounded border px-3 py-2 text-sm"
          style={inputStyle}
        />
      </label>

      <label className="mb-4 block">
        <span className="mb-1 block text-xs tracking-widest" style={{ color: "var(--text-dim)" }}>
          ZWAKKE PLEK
        </span>
        <input
          value={weakSpot}
          onChange={(e) => setWeakSpot(e.target.value)}
          maxLength={280}
          className="w-full rounded border px-3 py-2 text-sm"
          style={inputStyle}
        />
      </label>

      {error && (
        <p role="alert" className="mb-3 text-xs" style={{ color: "var(--accent-red)" }}>
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={busy || !name.trim()}
        className="w-full rounded px-4 py-2.5 text-sm tracking-[0.2em] disabled:opacity-40"
        style={{ background: "var(--intel-green)", color: "#f0f4e8", fontFamily: "var(--font-mono)" }}
      >
        {busy ? "BEZIG..." : "MEEDOEN"}
      </button>
    </form>
  );
}
