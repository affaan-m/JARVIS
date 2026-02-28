"use client";

import type { PersonRecord } from "@/lib/types";

interface StatusBarProps {
  persons: PersonRecord[];
}

export function StatusBar({ persons }: StatusBarProps) {
  const counts = {
    identified: persons.filter((p) => p.status === "identified").length,
    researching: persons.filter((p) => p.status === "researching").length,
    complete: persons.filter((p) => p.status === "complete").length,
    total: persons.length,
  };

  return (
    <div
      className="h-8 flex items-center justify-between px-4 border-t text-xs z-50 relative"
      style={{
        background: "var(--bg-chrome)",
        borderColor: "var(--board-bg)",
        fontFamily: "var(--font-mono)",
        color: "var(--text-dim)",
      }}
    >
      <div className="flex items-center gap-6">
        <span>
          <span className="inline-block w-2 h-2 rounded-full mr-1" style={{ background: "var(--status-pending)" }} />
          PENDING: {counts.identified}
        </span>
        <span>
          <span className="inline-block w-2 h-2 rounded-full mr-1 status-pulse" style={{ background: "var(--status-researching)" }} />
          RESEARCHING: {counts.researching}
        </span>
        <span>
          <span className="inline-block w-2 h-2 rounded-full mr-1" style={{ background: "var(--status-complete)" }} />
          COMPLETE: {counts.complete}
        </span>
      </div>
      <div>
        TOTAL SUBJECTS: {counts.total} | SPECTER v0.1
      </div>
    </div>
  );
}
