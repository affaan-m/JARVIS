"use client";

import type { IntelPerson } from "@/lib/types";

const SIDE_W = 270;

interface SidebarProps {
  people: IntelPerson[];
  activePerson: IntelPerson | null;
  onSelect: (person: IntelPerson) => void;
  search: string;
  setSearch: (s: string) => void;
}

const statusColor: Record<string, string> = {
  complete: "#22c55e",
  scanning: "#f59e0b",
  inactive: "#4b5563",
};

export function Sidebar({ people, activePerson, onSelect, search, setSearch }: SidebarProps) {
  const filtered = people.filter(p => p.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div style={{ width: SIDE_W, height: "100%", flexShrink: 0, position: "relative", zIndex: 20, display: "flex", flexDirection: "column" }}>
      {/* Frosted glass panel */}
      <div style={{
        position: "absolute", inset: 0,
        background: "linear-gradient(180deg,rgba(12,18,30,.85),rgba(8,14,25,.9))",
        backdropFilter: "blur(20px)",
        borderRight: "1px solid rgba(255,255,255,.06)",
        boxShadow: "4px 0 30px rgba(0,0,0,.3)",
      }} />

      {/* Content */}
      <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", height: "100%", padding: "20px 16px" }}>

        {/* Header */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ color: "#94a3b8", fontSize: 9, fontWeight: 700, letterSpacing: ".14em", marginBottom: 14 }}>
            TARGETS
          </div>
          {/* Search bar */}
          <div style={{ position: "relative" }}>
            <svg style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }}
              width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4a5568" strokeWidth="2" strokeLinecap="round">
              <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
            </svg>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search targets..."
              style={{
                width: "100%", padding: "9px 12px 9px 32px",
                background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.08)",
                borderRadius: 8, color: "#e2e8f0", fontSize: 12,
                outline: "none", fontFamily: "inherit", transition: "border-color .2s",
              }}
              onFocus={e => (e.target.style.borderColor = "rgba(255,255,255,.15)")}
              onBlur={e => (e.target.style.borderColor = "rgba(255,255,255,.08)")}
            />
          </div>
        </div>

        {/* Person list */}
        <div style={{ flex: 1, overflowY: "auto", margin: "0 -4px", padding: "0 4px" }}>
          {filtered.length === 0 && people.length === 0 && (
            /* Empty state — no people scanned yet */
            <div style={{ padding: "40px 12px", textAlign: "center" }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#2a3445" strokeWidth="1.5"
                style={{ margin: "0 auto 12px", display: "block" }} strokeLinecap="round">
                <circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
                <line x1="12" y1="1" x2="12" y2="3" /><line x1="18.36" y1="4.64" x2="16.95" y2="6.05" />
              </svg>
              <div style={{ color: "#3a4a5a", fontSize: 12, lineHeight: 1.5 }}>Start scanning people</div>
              <div style={{ color: "#2a3445", fontSize: 10, marginTop: 4 }}>Targets will appear here</div>
            </div>
          )}
          {filtered.length === 0 && people.length > 0 && (
            <div style={{ padding: "30px 12px", textAlign: "center", color: "#3a4a5a", fontSize: 12 }}>
              No matching targets
            </div>
          )}
          {/*
           * PERSON LIST ITEMS
           * When Browser Use scans a new person:
           * 1. Add to people array with status "scanning"
           * 2. New person appears at top, pushes others down
           * 3. The transition animation handles the push-down effect
           */}
          {filtered.map((p, i) => {
            const isActive = activePerson?.id === p.id;
            const dotColor = statusColor[p.status] ?? "#4b5563";
            return (
              <div
                key={p.id}
                onClick={() => onSelect(p)}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "10px 12px", marginBottom: 2, borderRadius: 8,
                  cursor: "pointer",
                  background: isActive ? "rgba(255,255,255,.07)" : "transparent",
                  transition: "all .3s ease",
                  animation: `listSlideIn .4s ease-out ${i * .05}s both`,
                }}
                onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,.04)"; }}
                onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
              >
                {/* Status dot */}
                <div style={{
                  width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
                  background: dotColor,
                  boxShadow: p.status === "scanning" ? `0 0 6px ${dotColor}40` : "none",
                  animation: p.status === "scanning" ? "scanPulse 2s ease-in-out infinite" : "none",
                }} />
                {/* Name */}
                <div style={{
                  color: isActive ? "#e2e8f0" : "#8a9bb8", fontSize: 12.5, fontWeight: isActive ? 600 : 500,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1,
                  transition: "color .2s",
                }}>
                  {p.name}
                </div>
                {/* Source count */}
                <div style={{ color: "#3a4a5a", fontSize: 10, fontWeight: 500, flexShrink: 0 }}>
                  {p.sources.length}
                </div>
              </div>
            );
          })}
        </div>

      </div>
    </div>
  );
}
