"use client";

import { useEffect, useState } from "react";
import { Shield, Radio, Eye } from "lucide-react";

interface TopBarProps {
  personCount: number;
}

export function TopBar({ personCount }: TopBarProps) {
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
        <Shield className="w-5 h-5" style={{ color: "var(--intel-green)" }} />
        <span
          className="text-2xl tracking-[6px]"
          style={{ fontFamily: "var(--font-heading)", color: "var(--text-primary)" }}
        >
          SPECTER
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
      <div className="flex items-center gap-6 text-xs" style={{ fontFamily: "var(--font-mono)", color: "var(--text-dim)" }}>
        <div className="flex items-center gap-2">
          <Radio className="w-3 h-3 status-pulse" style={{ color: "var(--intel-green)" }} />
          <span>AGENTS ONLINE</span>
        </div>
        <div className="flex items-center gap-2">
          <Eye className="w-3 h-3" style={{ color: "var(--alert-amber)" }} />
          <span>{personCount} SUBJECTS</span>
        </div>
      </div>

      {/* Clock */}
      <div
        className="text-sm tracking-wider"
        style={{ fontFamily: "var(--font-mono)", color: "var(--text-dim)" }}
      >
        {clock}
      </div>
    </div>
  );
}
