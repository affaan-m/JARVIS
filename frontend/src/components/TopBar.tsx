"use client";

import { useEffect, useState } from "react";
import { Shield } from "lucide-react";

export function TopBar() {
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
          CIRI
        </span>
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
