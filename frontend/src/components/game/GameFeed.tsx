"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ThumbsUp } from "lucide-react";

import { photoUrl, voteFeedItem, type FeedItem } from "@/lib/gameApi";

interface GameFeedProps {
  feed: FeedItem[];
  playerId: string | null;
  playerNames: Record<string, string>;
  onVoted: () => void;
}

const KIND_COLOR: Record<FeedItem["kind"], string> = {
  tag: "var(--string-red)",
  hint: "var(--alert-amber)",
  photo: "var(--status-researching)",
  system: "var(--text-dim)",
};

const KIND_LABEL: Record<FeedItem["kind"], string> = {
  tag: "ELIMINATED",
  hint: "HINT",
  photo: "FOTO",
  system: "SYSTEEM",
};

function killcamFrames(item: FeedItem): string[] {
  const frames = item.meta.killcam;
  return Array.isArray(frames) ? frames.filter((id): id is string => typeof id === "string") : [];
}

/** The shared board: tag broadcasts, hint releases and photos the group votes on. */
export function GameFeed({ feed, playerId, playerNames, onVoted }: GameFeedProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const items = [...feed].reverse();

  async function vote(itemId: string) {
    if (!playerId) return;
    setBusy(itemId);
    try {
      await voteFeedItem(itemId, playerId);
      onVoted();
    } finally {
      setBusy(null);
    }
  }

  return (
    <section
      data-testid="game-feed"
      className="rounded border p-4"
      style={{ borderColor: "rgba(200,214,176,0.15)", background: "rgba(26,32,24,0.85)" }}
    >
      <h3
        className="mb-3 text-sm tracking-[0.2em]"
        style={{ fontFamily: "var(--font-heading)", color: "var(--text-primary)" }}
      >
        GROEPSFEED
      </h3>

      {items.length === 0 ? (
        <p className="text-xs" style={{ color: "var(--text-dim)" }}>
          Nog niets gebeurd.
        </p>
      ) : (
        <ul className="flex max-h-[420px] flex-col gap-2 overflow-y-auto">
          <AnimatePresence initial={false}>
            {items.map((item) => (
              <motion.li
                key={item.item_id}
                layout
                initial={{ opacity: 0, y: -12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="rounded px-3 py-2"
                style={{
                  background: "rgba(10,13,8,0.5)",
                  borderLeft: `2px solid ${KIND_COLOR[item.kind]}`,
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p
                      className="text-[10px] tracking-[0.24em]"
                      style={{ color: KIND_COLOR[item.kind] }}
                    >
                      {KIND_LABEL[item.kind]}
                    </p>
                    <p className="text-sm break-words" style={{ color: "var(--text-primary)" }}>
                      {item.text ??
                        (item.author_id ? `${playerNames[item.author_id] ?? "Speler"} plaatste een foto` : "")}
                    </p>
                    {typeof item.meta.points === "number" && (
                      <p className="text-[11px]" style={{ color: "var(--pin-gold)" }}>
                        +{item.meta.points} punten{item.meta.endgame ? " (eindfase, dubbel)" : ""}
                      </p>
                    )}

                    {item.photo_id && (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img
                        src={photoUrl(item.photo_id)}
                        alt="Gedeelde foto, gezichten vervaagd"
                        loading="lazy"
                        className="mt-2 max-h-56 w-full rounded object-cover"
                        style={{ background: "rgba(10,13,8,0.6)" }}
                      />
                    )}

                    {killcamFrames(item).length > 0 && (
                      <div className="mt-2">
                        <p
                          className="mb-1 text-[10px] tracking-[0.24em]"
                          style={{ color: "var(--alert-amber)" }}
                        >
                          KILLCAM
                        </p>
                        <div className="flex gap-1 overflow-x-auto">
                          {killcamFrames(item).map((frameId) => (
                            /* eslint-disable-next-line @next/next/no-img-element */
                            <img
                              key={frameId}
                              src={photoUrl(frameId)}
                              alt="Killcam-beeld, gezichten vervaagd"
                              loading="lazy"
                              className="h-16 w-20 shrink-0 rounded object-cover"
                              style={{ background: "rgba(10,13,8,0.6)" }}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  {item.kind === "photo" && playerId && (
                    <button
                      type="button"
                      onClick={() => void vote(item.item_id)}
                      disabled={busy === item.item_id}
                      aria-label="Stem op deze foto"
                      className="flex shrink-0 items-center gap-1 rounded px-2 py-1 text-[11px] disabled:opacity-40"
                      style={{ border: "1px solid rgba(200,214,176,0.25)", color: "var(--text-ui)" }}
                    >
                      <ThumbsUp size={12} /> {item.votes}
                    </button>
                  )}
                </div>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </section>
  );
}
