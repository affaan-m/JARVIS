"use client";

import { motion, AnimatePresence } from "framer-motion";

import type { ActivityRecord } from "@/lib/types";

interface LiveFeedProps {
  activity: ActivityRecord[];
  onEventClick: (personId: string | undefined) => void;
}

const feedItemVariants = {
  initial: { opacity: 0, y: -20, scale: 0.95 },
  animate: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring" as const, stiffness: 400, damping: 25 },
  },
  exit: {
    opacity: 0,
    y: 20,
    scale: 0.95,
    transition: { duration: 0.2 },
  },
};

export function LiveFeed({ activity, onEventClick }: LiveFeedProps) {
  return (
    <aside
      data-testid="live-feed"
      className="w-[320px] shrink-0 border-l px-4 py-4"
      style={{
        background: "rgba(20,26,18,0.92)",
        borderColor: "rgba(200,214,176,0.12)",
      }}
    >
      <div className="mb-4">
        <p
          className="text-xs tracking-[0.32em]"
          style={{ fontFamily: "var(--font-mono)", color: "var(--text-dim)" }}
        >
          LIVE FEED
        </p>
        <h2
          className="text-2xl"
          style={{ fontFamily: "var(--font-heading)", letterSpacing: "0.16em" }}
        >
          ACTIVE SIGNALS
        </h2>
      </div>

      <div className="space-y-3 overflow-y-auto pr-1">
        <AnimatePresence initial={false}>
          {activity.map((item) => (
            <motion.button
              key={item._id}
              className="w-full rounded-sm border p-3 text-left transition hover:bg-white/5"
              style={{ borderColor: "rgba(200,214,176,0.08)" }}
              onClick={() => onEventClick(item.personId)}
              type="button"
              variants={feedItemVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              layout
            >
              <p
                className="text-[10px] tracking-[0.28em]"
                style={{ fontFamily: "var(--font-mono)", color: "var(--text-dim)" }}
              >
                {new Date(item.timestamp).toLocaleTimeString("en-US", {
                  hour12: false,
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </p>
              <p className="mt-2 text-sm leading-5">{item.message}</p>
              {item.agentName ? (
                <p className="mt-2 text-[11px]" style={{ color: "var(--text-dim)" }}>
                  SOURCE // {item.agentName.toUpperCase()}
                </p>
              ) : null}
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </aside>
  );
}
