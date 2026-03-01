"use client";

import { useEffect, useState } from "react";
import { Radio, Eye } from "lucide-react";

function CiriLogo({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Outer ring — thin surveillance reticle */}
      <circle cx="16" cy="16" r="14.5" stroke="var(--intel-green)" strokeWidth="1" opacity="0.5" />
      {/* Inner ring */}
      <circle cx="16" cy="16" r="9" stroke="var(--intel-green)" strokeWidth="0.75" opacity="0.35" />
      {/* Crosshair ticks — top, right, bottom, left */}
      <line x1="16" y1="1" x2="16" y2="5" stroke="var(--intel-green)" strokeWidth="1.2" strokeLinecap="round" />
      <line x1="31" y1="16" x2="27" y2="16" stroke="var(--intel-green)" strokeWidth="1.2" strokeLinecap="round" />
      <line x1="16" y1="31" x2="16" y2="27" stroke="var(--intel-green)" strokeWidth="1.2" strokeLinecap="round" />
      <line x1="1" y1="16" x2="5" y2="16" stroke="var(--intel-green)" strokeWidth="1.2" strokeLinecap="round" />
      {/* Center eye — the "iris" */}
      <circle cx="16" cy="16" r="3.5" stroke="var(--intel-green)" strokeWidth="1.5" />
      {/* Pupil dot */}
      <circle cx="16" cy="16" r="1.2" fill="var(--intel-green)" />
      {/* Diagonal scan lines — NE and SW quadrant accents */}
      <line x1="21.5" y1="5.5" x2="24" y2="3" stroke="var(--intel-green)" strokeWidth="0.6" opacity="0.3" strokeLinecap="round" />
      <line x1="10.5" y1="26.5" x2="8" y2="29" stroke="var(--intel-green)" strokeWidth="0.6" opacity="0.3" strokeLinecap="round" />
    </svg>
  );
}

interface TopBarProps {
  personCount?: number;
  isLive?: boolean;
  children?: React.ReactNode;
}

export function TopBar({ personCount, isLive = false, children }: TopBarProps) {
  const [clock, setClock] = useState("");

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setClock(
        now.toLocaleTimeString("en-US", { hour12: false }) +
          " " +
          now.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" }).toUpperCase()
      );
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div
      className="h-12 flex items-center justify-between px-4 border-b z-50 relative"
      style={{
        background: "var(--bg-chrome)",
        borderColor: "var(--board-bg)",
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3">
        <CiriLogo size={22} />
        <span
          className="text-2xl tracking-[6px]"
          style={{ fontFamily: "var(--font-heading)", color: "var(--text-primary)" }}
        >
          CIRI
        </span>
        <span
          className="text-xs px-2 py-0.5 rounded"
          style={{
            background: "var(--stamp-red)",
            color: "#fff",
            fontFamily: "var(--font-mono)",
          }}
        >
          CLASSIFIED
        </span>
      </div>

      {/* Center status */}
      {personCount !== undefined && (
        <div className="flex items-center gap-6 text-xs" style={{ fontFamily: "var(--font-mono)", color: "var(--text-dim)" }}>
          <div className="flex items-center gap-2">
            <Radio className="w-3 h-3 status-pulse" style={{ color: isLive ? "var(--intel-green)" : "var(--alert-amber)" }} />
            <span>{isLive ? "LIVE" : "DEMO"}</span>
          </div>
          <div className="flex items-center gap-2">
            <Eye className="w-3 h-3" style={{ color: "var(--alert-amber)" }} />
            <span>{personCount} SUBJECTS</span>
          </div>
        </div>
      )}

      {/* Actions + Clock */}
      <div className="flex items-center gap-4">
        {children}
        <div
          className="text-sm tracking-wider"
          style={{ fontFamily: "var(--font-mono)", color: "var(--text-dim)" }}
        >
          {clock}
        </div>
      </div>
    </div>
  );
}
