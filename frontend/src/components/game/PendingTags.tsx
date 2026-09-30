"use client";

import { useState } from "react";
import { Check, X } from "lucide-react";

import { confirmTag, rejectTag, type Tag } from "@/lib/gameApi";

interface PendingTagsProps {
  tags: Tag[];
  playerId: string;
  playerNames: Record<string, string>;
  onResolved: () => void;
}

/** A tag only counts once the tagged player answers here. Nobody else can. */
export function PendingTags({ tags, playerId, playerNames, onResolved }: PendingTagsProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (tags.length === 0) return null;

  async function resolve(tagId: string, accept: boolean) {
    setBusy(tagId);
    setError(null);
    try {
      await (accept ? confirmTag(tagId, playerId) : rejectTag(tagId, playerId));
      onResolved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kon dit niet verwerken");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section
      data-testid="pending-tags"
      className="rounded border p-4"
      style={{ borderColor: "rgba(243,156,18,0.5)", background: "rgba(243,156,18,0.08)" }}
    >
      <h3
        className="mb-1 text-sm tracking-[0.2em]"
        style={{ fontFamily: "var(--font-heading)", color: "var(--alert-amber)" }}
      >
        BEN JIJ GETAGD?
      </h3>
      <p className="mb-3 text-xs" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
        Alleen jij kunt dit bevestigen. Klopt het niet, wijs het dan af.
      </p>

      {error && (
        <p role="alert" className="mb-2 text-xs" style={{ color: "var(--accent-red)" }}>
          {error}
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {tags.map((tag) => (
          <li
            key={tag.tag_id}
            className="flex items-center justify-between gap-3 rounded px-3 py-2"
            style={{ background: "rgba(10,13,8,0.5)" }}
          >
            <span className="text-sm" style={{ color: "var(--text-primary)" }}>
              {playerNames[tag.tagger_id] ?? "Een speler"} zegt je getagd te hebben
            </span>
            <span className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => void resolve(tag.tag_id, true)}
                disabled={busy === tag.tag_id}
                aria-label="Tag bevestigen"
                className="flex items-center gap-1 rounded px-2.5 py-1.5 text-xs tracking-widest disabled:opacity-40"
                style={{ background: "var(--intel-green)", color: "#f0f4e8" }}
              >
                <Check size={13} /> KLOPT
              </button>
              <button
                type="button"
                onClick={() => void resolve(tag.tag_id, false)}
                disabled={busy === tag.tag_id}
                aria-label="Tag afwijzen"
                className="flex items-center gap-1 rounded px-2.5 py-1.5 text-xs tracking-widest disabled:opacity-40"
                style={{ background: "var(--stamp-red)", color: "#f0e8d8" }}
              >
                <X size={13} /> NIET
              </button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
