"use client";

import { useEffect, useState } from "react";
import { Radio, Eye } from "lucide-react";

function JarvisLogo({ size = 26 }: { size?: number }) {
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ filter: "drop-shadow(0 0 4px rgba(74,222,128,.25))" }}
      >
        {/* Outer arc reactor ring */}
        <circle cx="16" cy="16" r="14.5" stroke="rgba(74,222,128,.35)" strokeWidth="0.8" />
        {/* Inner rotating ring (animated via CSS) */}
        <circle cx="16" cy="16" r="11" stroke="rgba(74,222,128,.2)" strokeWidth="0.5"
          strokeDasharray="4 8" className="jarvis-spin" />
        {/* Mid ring — solid */}
        <circle cx="16" cy="16" r="8" stroke="rgba(74,222,128,.45)" strokeWidth="1" />
        {/* Crosshair ticks */}
        <line x1="16" y1="1" x2="16" y2="4.5" stroke="rgba(74,222,128,.5)" strokeWidth="1" strokeLinecap="round" />
        <line x1="31" y1="16" x2="27.5" y2="16" stroke="rgba(74,222,128,.5)" strokeWidth="1" strokeLinecap="round" />
        <line x1="16" y1="31" x2="16" y2="27.5" stroke="rgba(74,222,128,.5)" strokeWidth="1" strokeLinecap="round" />
        <line x1="1" y1="16" x2="4.5" y2="16" stroke="rgba(74,222,128,.5)" strokeWidth="1" strokeLinecap="round" />
        {/* Arc reactor center — triple ring */}
        <circle cx="16" cy="16" r="4.5" stroke="rgba(74,222,128,.6)" strokeWidth="1.2" />
        <circle cx="16" cy="16" r="2.5" stroke="rgba(74,222,128,.35)" strokeWidth="0.7" />
        {/* Core glow */}
        <circle cx="16" cy="16" r="1.5" fill="rgba(74,222,128,.7)" />
        <circle cx="16" cy="16" r="3" fill="rgba(74,222,128,.06)" />
        {/* Diagonal accent lines */}
        <line x1="21" y1="5" x2="23.5" y2="2.5" stroke="rgba(74,222,128,.2)" strokeWidth="0.5" strokeLinecap="round" />
        <line x1="11" y1="27" x2="8.5" y2="29.5" stroke="rgba(74,222,128,.2)" strokeWidth="0.5" strokeLinecap="round" />
        <line x1="27" y1="11" x2="29.5" y2="8.5" stroke="rgba(74,222,128,.15)" strokeWidth="0.5" strokeLinecap="round" />
        <line x1="5" y1="21" x2="2.5" y2="23.5" stroke="rgba(74,222,128,.15)" strokeWidth="0.5" strokeLinecap="round" />
      </svg>
      <style>{`
        .jarvis-spin { animation: jarvisSpin 8s linear infinite; transform-origin: 50% 50%; }
        @keyframes jarvisSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
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
      className="h-12 flex items-center justify-between px-4 border-b z-50 relative jarvis-glow"
      style={{
        background: "linear-gradient(180deg, var(--bg-chrome) 0%, rgba(14,20,12,.95) 100%)",
        borderColor: "rgba(74,222,128,.08)",
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3">
        <JarvisLogo size={26} />
        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          <span
            className="text-2xl tracking-[8px]"
            style={{
              fontFamily: "var(--font-heading)",
              color: "var(--text-primary)",
              lineHeight: 1,
              textShadow: "0 0 20px rgba(74,222,128,.15)",
            }}
          >
            JARVIS
          </span>
          <span style={{
            fontSize: 7, letterSpacing: ".25em", fontFamily: "var(--font-mono)",
            color: "rgba(74,222,128,.35)", lineHeight: 1, marginTop: 1,
          }}>
            PERSON INTELLIGENCE SYSTEM
          </span>
        </div>
      </div>

      {/* Center status */}
      {personCount !== undefined && (
        <div className="flex items-center gap-6 text-xs" style={{ fontFamily: "var(--font-mono)", color: "var(--text-dim)" }}>
          <div className="flex items-center gap-2">
            <Radio className="w-3 h-3 status-pulse" style={{ color: isLive ? "rgba(74,222,128,.7)" : "var(--alert-amber)" }} />
            <span style={{ letterSpacing: ".12em" }}>{isLive ? "LIVE" : "STANDBY"}</span>
          </div>
          <div className="flex items-center gap-2">
            <Eye className="w-3 h-3" style={{ color: "rgba(74,222,128,.5)" }} />
            <span style={{ letterSpacing: ".12em" }}>{personCount} SUBJECTS</span>
          </div>
        </div>
      )}

      {/* Actions + Clock */}
      <div className="flex items-center gap-4">
        {children}
        <div style={{
          padding: "3px 10px", borderRadius: 2,
          background: "rgba(74,222,128,.04)", border: "1px solid rgba(74,222,128,.08)",
        }}>
          <div
            className="text-sm tracking-wider"
            style={{ fontFamily: "var(--font-mono)", color: "rgba(74,222,128,.45)", fontSize: 11 }}
          >
            {clock}
          </div>
        </div>
      </div>
    </div>
  );
}
